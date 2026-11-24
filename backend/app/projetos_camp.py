"""Projetos da CAMP (CAMP-PROJ, 24/11/2026). Os projetos institucionais da CAMP: Lei Rouanet, editais, patrocínios e projetos internos.

Rafael: "vamos ter uma área de projetos no sistema, interligados aos outros módulos dele, que vai ter os objetivos e prazos, e precisa sempre
me avisar tudo." Modelo: a proposta do SALIC (identificação, objetivos, etapas e cronograma, orçamento por item, documentos, prazos).

- NÃO é o projeto do acervo (F0xx-P000x, imutável): na tela e no código é sempre "Projetos da CAMP" / projeto_camp.
- Ligações: a conta do projeto (financeiro_conta; no Rouanet a do Banco do Brasil, PRONAC 2613864) dá o orçamento do SALIC (rouanet.py, sem
  copiar a planilha), as despesas da conta e as notas da CAMP para o projeto; despesas de outras contas e patrocínios podem ser ligados ao
  projeto; entradas do projeto (captação, aporte, prêmio) são lançadas aqui. Projeto sem conta própria tem orçamento próprio (previsto ×
  realizado pelas despesas ligadas a cada item).
- Avisos: o que está atrasado, o que vence em 7 dias, prazos institucionais (30 dias; vazio no Rouanet = "a preencher (veja no SALIC)"),
  orçamento acima do previsto ou perto do limite, despesa sem comprovante, e o que mudou desde a última vez que a pessoa abriu o projeto.
  Aparecem na Home do painel e num resumo diário por e-mail (desligado até alguém escolher quem recebe: projetos_camp.email_diario).
- Nada é inventado: campo sem informação fica vazio e aparece como "a preencher". Só admin e master.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import auth
from .config import settings
from .db import connect
from .log_tecnico import registrar

router = APIRouter(prefix="/api/projetos-camp", tags=["projetos_camp"])

TIPOS = {"rouanet": "Lei Rouanet", "edital": "Edital", "patrocinio": "Patrocínio", "interno": "Projeto interno"}
SITUACOES = {"planejamento": "Planejamento", "captacao": "Captação", "execucao": "Execução", "prestacao": "Prestação de contas",
             "concluido": "Concluído", "arquivado": "Arquivado"}
SIT_TAREFA = {"a_fazer": "A fazer", "fazendo": "Fazendo", "feita": "Feita", "nao_se_aplica": "Não se aplica"}
FECHADAS = ("feita", "nao_se_aplica")
TIPOS_ARQUIVO = {"proposta": "Proposta", "aprovacao": "Aprovação ou portaria", "contrato": "Contrato ou termo", "orcamento": "Orçamento",
                 "relatorio": "Relatório", "prestacao": "Prestação de contas", "outro": "Outro documento"}
PRAZOS = (("prazo_captacao", "Prazo de captação"), ("prazo_execucao", "Fim da execução"), ("prazo_prestacao", "Prestação de contas"))
DIAS_PERTO = 7          # tarefa ou etapa: "vence em N dias"
DIAS_INSTITUCIONAL = 30  # prazos do SALIC/edital: avisa com mais antecedência
EXT_MIME = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MAX_ARQUIVO = 15 * 1024 * 1024
ENTIDADE = "projeto_camp"
RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ROUANET_CONTA = 2   # conta do PRONAC 2613864 já cadastrada (migrações 249/254)


# ---------------------------------------------------------------- utilidades
def _fin():
    from . import financeiro
    return financeiro


def _rou():
    from . import rouanet
    return rouanet


def hoje() -> date:
    return _fin().hoje()


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _txt(v, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def _txt_longo(v, n: int) -> str:
    return str(v or "").replace("\r\n", "\n").strip()[:n]


def _r2(v) -> float:
    return round(float(v or 0) + 0.0, 2)


def _ator(u: dict | None) -> str:
    return (u or {}).get("email") or "painel"


def _data(v, campo: str = "data") -> str | None:
    s = str(v or "").strip()[:10]
    if not s:
        return None
    if not RE_DATA.match(s):
        raise HTTPException(400, f"Data inválida em {campo}: use o calendário (dia/mês/ano).")
    try:
        date.fromisoformat(s)
    except ValueError as e:
        raise HTTPException(400, f"Data inválida em {campo}.") from e
    return s


def _br(d: str | None) -> str:
    return "/".join(reversed(d[:10].split("-"))) if d else ""


def _ev(con, pid: int, tipo: str, ator: str, det: dict | None = None) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)",
                (ENTIDADE, str(pid), tipo, ator, json.dumps(det or {}, ensure_ascii=False)))


def _tem(con, tabela: str) -> bool:
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)).fetchone())


def _colunas(con, tabela: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}


def _projeto_row(con, pid: int):
    r = con.execute("SELECT * FROM projeto_camp WHERE id=?", (int(pid),)).fetchone()
    if not r:
        raise HTTPException(404, "Projeto da CAMP não encontrado")
    return r


def _dias(d: str | None, ref: date) -> int | None:
    if not d:
        return None
    try:
        return (date.fromisoformat(d[:10]) - ref).days
    except ValueError:
        return None


def _quando(n: int) -> str:
    if n < 0:
        return f"atrasado há {-n} dia{'s' if n != -1 else ''}"
    if n == 0:
        return "vence hoje"
    return f"vence em {n} dia{'s' if n != 1 else ''}"


def _conta_incentivada(con, cid) -> bool:
    if not cid:
        return False
    r = con.execute("SELECT tipo FROM financeiro_conta WHERE id=?", (cid,)).fetchone()
    return bool(r and r[0] == "projeto_incentivado")


# ---------------------------------------------------------------- leitura
def _objetivos(con, pid: int) -> list[dict]:
    out = []
    for r in con.execute("SELECT * FROM projeto_camp_objetivo WHERE projeto_id=? AND apagado_em IS NULL ORDER BY ordem, id", (pid,)):
        pct = None
        if r["meta"] and r["meta"] > 0:
            pct = round(min(1.0, max(0.0, float(r["atual"] or 0) / float(r["meta"]))), 4)
        out.append({"id": r["id"], "texto": r["texto"], "indicador": r["indicador"] or "", "meta": r["meta"], "atual": r["atual"], "pct": pct, "ordem": r["ordem"]})
    return out


def _tarefas(con, pid: int) -> list[dict]:
    return [{"id": r["id"], "etapa_id": r["etapa_id"], "o_que": r["o_que"], "responsavel": r["responsavel"] or "", "prazo": r["prazo"] or "",
             "situacao": r["situacao"], "situacao_nome": SIT_TAREFA.get(r["situacao"], r["situacao"]), "nota": r["nota"] or "", "feita_em": r["feita_em"] or ""}
            for r in con.execute("SELECT * FROM projeto_camp_tarefa WHERE projeto_id=? AND apagado_em IS NULL "
                                 "ORDER BY situacao IN ('feita','nao_se_aplica'), prazo IS NULL OR prazo='', prazo, id", (pid,))]


def _etapas(con, pid: int) -> list[dict]:
    return [{"id": r["id"], "nome": r["nome"], "inicio": r["inicio"] or "", "prazo": r["prazo"] or "", "situacao": r["situacao"],
             "situacao_nome": SIT_TAREFA.get(r["situacao"], r["situacao"]), "marco": bool(r["marco"]), "ordem": r["ordem"], "feita_em": r["feita_em"] or ""}
            for r in con.execute("SELECT * FROM projeto_camp_etapa WHERE projeto_id=? AND apagado_em IS NULL "
                                 "ORDER BY ordem, prazo IS NULL OR prazo='', prazo, id", (pid,))]


def progresso(etapas: list[dict], tarefas: list[dict], objetivos: list[dict]) -> dict:
    conta = [x for x in etapas + tarefas if x["situacao"] != "nao_se_aplica"]
    feitas = sum(1 for x in conta if x["situacao"] == "feita")
    metas = [o["pct"] for o in objetivos if o["pct"] is not None]
    pt = round(feitas / len(conta), 4) if conta else None
    pm = round(sum(metas) / len(metas), 4) if metas else None
    return {"feitas": feitas, "total": len(conta), "pct_trabalho": pt, "pct_metas": pm, "pct": pt if pt is not None else pm}


def _despesas(con, p) -> list[dict]:
    if not _tem(con, "despesa"):
        return []
    cols = _colunas(con, "despesa")
    if "projeto_camp_id" not in cols:
        return []
    anexo = "(SELECT COUNT(*) FROM despesa_anexo a WHERE a.despesa_id=d.id" + (" AND a.apagado_em IS NULL" if "apagado_em" in _colunas(con, "despesa_anexo") else "") + ")"
    rows = con.execute(f"SELECT d.*, {anexo} AS n_anexos FROM despesa d WHERE d.apagado_em IS NULL AND d.tipo='despesa' AND (d.projeto_camp_id=? OR (? IS NOT NULL AND d.conta_id=?)) "
                       "ORDER BY d.data DESC, d.id DESC", (p["id"], p["conta_id"], p["conta_id"])).fetchall()
    out = []
    for r in rows:
        out.append({"id": r["id"], "data": r["data"], "valor": _r2(r["valor"]), "contraparte": r["contraparte"] or "", "descricao": r["descricao"] or "",
                    "justificativa": r["justificativa"] or "", "categoria": r["categoria"] or "", "conta_id": r["conta_id"],
                    "da_conta": p["conta_id"] is not None and r["conta_id"] == p["conta_id"], "ligada": r["projeto_camp_id"] == p["id"],
                    "item": r["projeto_camp_item"], "orcamento_item": r["orcamento_item"] if "orcamento_item" in cols else None,
                    "comprovantes": r["n_anexos"] or 0, "criado_em": r["criado_em"]})
    return out


def _patrocinios(con, pid: int) -> list[dict]:
    if not _tem(con, "patrocinio") or "projeto_camp_id" not in _colunas(con, "patrocinio"):
        return []
    return [{"site_id": r["site_id"], "empresa": r["empresa"] or r["razao_social"] or "", "cota": r["cota"] or "", "etapa": r["etapa"] or "",
             "valor_anual": _r2(r["valor_anual"]), "valor_pago": _r2(r["valor_pago"])}
            for r in con.execute("SELECT * FROM patrocinio WHERE projeto_camp_id=? ORDER BY site_id DESC", (pid,))]


def _receitas(con, pid: int) -> list[dict]:
    return [{"id": r["id"], "data": r["data"], "valor": _r2(r["valor"]), "origem": r["origem"] or "", "descricao": r["descricao"] or ""}
            for r in con.execute("SELECT * FROM projeto_camp_receita WHERE projeto_id=? AND apagado_em IS NULL ORDER BY data DESC, id DESC", (pid,))]


def _notas(con, p) -> list[dict]:
    if not _conta_incentivada(con, p["conta_id"]):
        return []
    try:
        return [{"id": n["id"], "competencia": n["competencia"], "valor": _r2(n["valor"]), "situacao": n["situacao"], "nf_numero": n.get("nf_numero") or "",
                 "descricao": n["descricao"]} for n in _rou()._notas_rows(con, p["conta_id"])]
    except Exception:  # noqa: BLE001  (banco sem a migração 254)
        return []


def orcamento(con, p, despesas: list[dict] | None = None) -> dict:
    """Projeto com conta de projeto incentivado: a planilha do SALIC do Financeiro (orçado × gasto × saldo). Senão: o orçamento próprio,
    com o realizado pelas despesas ligadas a cada item."""
    if _conta_incentivada(con, p["conta_id"]):
        try:
            o = _rou().orcamento(con, p["conta_id"])
        except HTTPException:
            o = None
        if o and o["itens"]:
            itens = [{"id": None, "item": it["item"], "descricao": it["descricao"], "grupo": f"{it['produto']} · {it['etapa']}", "previsto": it["orcado"],
                      "realizado": it["gasto"], "saldo": it["saldo"], "pct": it["pct"], "nivel": it["nivel"]} for it in o["itens"]]
            t = o["total"]
            return {"fonte": "salic", "conta_id": p["conta_id"], "banner": o.get("banner") or "", "itens": itens,
                    "total": {"previsto": t["orcado"], "realizado": t["gasto"], "saldo": t["saldo"], "pct": t["pct"], "nivel": t["nivel"]}}
    despesas = _despesas(con, p) if despesas is None else despesas
    real: dict[int, float] = {}
    for d in despesas:
        if d["item"]:
            real[d["item"]] = real.get(d["item"], 0.0) + d["valor"]
    itens = []
    for r in con.execute("SELECT * FROM projeto_camp_item WHERE projeto_id=? AND apagado_em IS NULL ORDER BY ordem, id", (p["id"],)):
        prev, rea = _r2(r["previsto"]), _r2(real.get(r["id"], 0.0))
        itens.append({"id": r["id"], "item": None, "descricao": r["descricao"], "grupo": "", "previsto": prev, "realizado": rea, "saldo": _r2(prev - rea),
                      "pct": round(rea / prev, 4) if prev else (1.0 if rea else 0.0), "nivel": _nivel(rea, prev)})
    prev, rea = _r2(sum(i["previsto"] for i in itens)), _r2(sum(i["realizado"] for i in itens))
    sem_item = _r2(sum(d["valor"] for d in despesas if not d["item"]))
    return {"fonte": "proprio", "conta_id": p["conta_id"], "banner": "", "itens": itens, "sem_item": sem_item,
            "total": {"previsto": prev, "realizado": rea, "saldo": _r2(prev - rea), "pct": round(rea / prev, 4) if prev else (1.0 if rea else 0.0), "nivel": _nivel(rea, prev)}}


def _nivel(gasto: float, previsto: float) -> str:
    if gasto > previsto + 0.005:
        return "vermelho"
    if previsto > 0 and gasto > 0 and gasto >= 0.9 * previsto - 0.005:
        return "ambar"
    return "ok"


def _arquivos(con, pid: int) -> list[dict]:
    return [{"id": r["id"], "tipo": r["tipo"], "tipo_nome": TIPOS_ARQUIVO.get(r["tipo"], r["tipo"]), "nome": r["nome"], "mime": r["mime"] or "",
             "tamanho": r["tamanho"] or 0, "criado_em": r["criado_em"], "criado_por": r["criado_por"] or ""}
            for r in con.execute("SELECT * FROM projeto_camp_arquivo WHERE projeto_id=? AND apagado_em IS NULL ORDER BY id DESC", (pid,))]


def _texto_evento(tipo: str, d: dict) -> str:
    t = {
        "criado": "Projeto criado", "dados_alterados": "Dados do projeto alterados", "semeado_rouanet": "Projeto criado a partir do Financeiro (PRONAC)",
        "objetivo_criado": "Objetivo adicionado", "objetivo_alterado": "Objetivo alterado", "objetivo_apagado": "Objetivo apagado",
        "etapa_criada": "Etapa adicionada", "etapa_alterada": "Etapa alterada", "etapa_apagada": "Etapa apagada",
        "tarefa_criada": "Tarefa adicionada", "tarefa_alterada": "Tarefa alterada", "tarefa_apagada": "Tarefa apagada",
        "item_criado": "Item do orçamento adicionado", "item_alterado": "Item do orçamento alterado", "item_apagado": "Item do orçamento apagado",
        "receita_criada": "Entrada lançada", "receita_apagada": "Entrada apagada", "despesa_ligada": "Despesa ligada ao projeto",
        "despesa_desligada": "Despesa tirada do projeto", "patrocinio_ligado": "Patrocínio ligado ao projeto", "patrocinio_desligado": "Patrocínio tirado do projeto",
        "arquivo_adicionado": "Documento adicionado", "arquivo_tirado": "Documento tirado",
    }.get(tipo, tipo.replace("_", " ").capitalize())
    extra = d.get("nome") or d.get("o_que") or d.get("texto") or d.get("descricao") or ""
    if d.get("situacao"):
        extra = (extra + " · " if extra else "") + SIT_TAREFA.get(d["situacao"], SITUACOES.get(d["situacao"], d["situacao"]))
    if d.get("campos"):
        extra = (extra + " · " if extra else "") + ", ".join(d["campos"])
    return t + (f": {extra}" if extra else "")


def historico(con, pid: int, limite: int = 200) -> list[dict]:
    out = []
    for r in con.execute("SELECT * FROM evento WHERE entidade=? AND codigo=? ORDER BY quando DESC, id DESC LIMIT ?", (ENTIDADE, str(pid), limite)):
        try:
            d = json.loads(r["detalhe"] or "{}")
        except ValueError:
            d = {}
        out.append({"quando": r["quando"], "ator": r["ator"], "tipo": r["tipo"], "texto": _texto_evento(r["tipo"], d)})
    return out


def _prazos(p, etapas: list[dict], tarefas: list[dict], ref: date) -> list[dict]:
    """Todos os prazos abertos, do mais próximo ao mais distante (atrasados primeiro)."""
    out = []
    for k, nome in PRAZOS:
        if p[k]:
            out.append({"tipo": "institucional", "nome": nome, "data": p[k], "dias": _dias(p[k], ref)})
    for e in etapas:
        if e["prazo"] and e["situacao"] not in FECHADAS:
            out.append({"tipo": "marco" if e["marco"] else "etapa", "nome": e["nome"], "data": e["prazo"], "dias": _dias(e["prazo"], ref), "id": e["id"]})
    for t in tarefas:
        if t["prazo"] and t["situacao"] not in FECHADAS:
            out.append({"tipo": "tarefa", "nome": t["o_que"], "data": t["prazo"], "dias": _dias(t["prazo"], ref), "id": t["id"], "responsavel": t["responsavel"]})
    return sorted(out, key=lambda x: (x["dias"] if x["dias"] is not None else 99999, x["nome"]))


def a_preencher(p) -> list[str]:
    falta = []
    if not p["objetivo_geral"]:
        falta.append("Objetivo geral")
    if not p["responsavel"]:
        falta.append("Responsável")
    if not p["inicio"] or not p["fim"]:
        falta.append("Início e fim")
    if p["tipo"] in ("rouanet", "edital"):
        falta += [nome for k, nome in PRAZOS if not p[k]]
    return falta


def alertas_projeto(con, p, etapas: list[dict], tarefas: list[dict], orc: dict, despesas: list[dict], ref: date) -> list[dict]:
    """Avisos do projeto, do mais grave ao mais leve. nivel: r (vermelho) · a (âmbar) · b (informação)."""
    nome, out = p["nome"], []
    if p["situacao"] in ("concluido", "arquivado"):
        return out
    for x in _prazos(p, etapas, tarefas, ref):
        d = x["dias"]
        if d is None:
            continue
        lim = DIAS_INSTITUCIONAL if x["tipo"] == "institucional" else DIAS_PERTO
        if d < 0 or d <= lim:
            rot = {"institucional": x["nome"], "marco": "Marco", "etapa": "Etapa", "tarefa": "Tarefa"}[x["tipo"]]
            titulo = f"{rot}: {_quando(d)} ({_br(x['data'])})" if x["tipo"] == "institucional" else f"{rot} {x['nome']}: {_quando(d)} ({_br(x['data'])})"
            out.append({"nivel": "r" if d < 0 else "a", "tipo": "atrasado" if d < 0 else "prazo", "projeto_id": p["id"], "projeto": nome,
                        "titulo": titulo, "motivo": (f"responsável: {x['responsavel']}" if x.get("responsavel") else ""), "aba": "cronograma", "dias": d})
    br = _fin().brl
    for it in orc["itens"]:
        rot = f"item {it['item']} · {it['descricao']}" if it["item"] else it["descricao"]
        if it["nivel"] == "vermelho":
            out.append({"nivel": "r", "tipo": "orcamento", "projeto_id": p["id"], "projeto": nome, "aba": "orcamento", "dias": None,
                        "titulo": f"Acima do previsto: {rot}", "motivo": f"{br(it['realizado'])} de {br(it['previsto'])}"})
        elif it["nivel"] == "ambar":
            out.append({"nivel": "a", "tipo": "orcamento", "projeto_id": p["id"], "projeto": nome, "aba": "orcamento", "dias": None,
                        "titulo": f"Perto do limite: {rot} ({round(it['pct'] * 100)}% usado)", "motivo": f"saldo {br(it['saldo'])}"})
    sem = [d for d in despesas if not d["comprovantes"]]
    if sem:
        out.append({"nivel": "a", "tipo": "comprovante", "projeto_id": p["id"], "projeto": nome, "aba": "financeiro", "dias": None,
                    "titulo": f"{len(sem)} despesa{'s' if len(sem) > 1 else ''} sem comprovante", "motivo": f"{br(sum(d['valor'] for d in sem))} sem nota fiscal ou recibo"})
    falta = a_preencher(p)
    if falta:
        out.append({"nivel": "b", "tipo": "a_preencher", "projeto_id": p["id"], "projeto": nome, "aba": "geral", "dias": None,
                    "titulo": "A preencher: " + ", ".join(falta),
                    "motivo": "veja na proposta do SALIC" if p["tipo"] == "rouanet" else "complete os dados do projeto"})
    ordem = {"r": 0, "a": 1, "b": 2}
    return sorted(out, key=lambda a: (ordem[a["nivel"]], a["dias"] if a["dias"] is not None else 9999))


def _visto(con, usuario: str, pid: int) -> str | None:
    r = con.execute("SELECT visto_em FROM projeto_camp_visto WHERE usuario=? AND projeto_id=?", (usuario, pid)).fetchone()
    return r[0] if r else None


def mudancas(con, pid: int, usuario: str, desde: str | None = None) -> list[dict]:
    """O que outras pessoas (ou o sistema) mudaram no projeto desde a última visita; despesas novas da conta do projeto também."""
    desde = desde if desde is not None else _visto(con, usuario, pid)
    if not desde:
        return []
    out = [{"quando": r["quando"], "ator": r["ator"], "texto": _texto_evento(r["tipo"], json.loads(r["detalhe"] or "{}"))}
           for r in con.execute("SELECT * FROM evento WHERE entidade=? AND codigo=? AND quando>? AND ator<>? ORDER BY quando DESC LIMIT 50",
                                (ENTIDADE, str(pid), desde, usuario))]
    p = _projeto_row(con, pid)
    if p["conta_id"] and _tem(con, "despesa"):
        for r in con.execute("SELECT data, valor, contraparte, criado_em FROM despesa WHERE conta_id=? AND apagado_em IS NULL AND criado_em>? ORDER BY criado_em DESC LIMIT 20",
                             (p["conta_id"], desde)):
            out.append({"quando": r["criado_em"], "ator": "financeiro", "texto": f"Despesa nova na conta do projeto: {_fin().brl(r['valor'])} · {r['contraparte'] or ''}".rstrip(" ·")})
    return sorted(out, key=lambda x: x["quando"], reverse=True)


def resumo(con, p, ref: date | None = None) -> dict:
    ref = ref or hoje()
    et, ta, ob = _etapas(con, p["id"]), _tarefas(con, p["id"]), _objetivos(con, p["id"])
    desp = _despesas(con, p)
    orc = orcamento(con, p, desp)
    al = alertas_projeto(con, p, et, ta, orc, desp, ref)
    pz = [x for x in _prazos(p, et, ta, ref) if x["dias"] is not None]
    prox = next((x for x in pz if x["dias"] >= 0), None)
    return {"id": p["id"], "nome": p["nome"], "tipo": p["tipo"], "tipo_nome": TIPOS.get(p["tipo"], p["tipo"]), "codigo_externo": p["codigo_externo"] or "",
            "situacao": p["situacao"], "situacao_nome": SITUACOES.get(p["situacao"], p["situacao"]), "responsavel": p["responsavel"] or "",
            "inicio": p["inicio"] or "", "fim": p["fim"] or "", "progresso": progresso(et, ta, ob), "proximo_prazo": prox,
            "atrasados": sum(1 for x in pz if x["dias"] < 0), "vencem_7d": sum(1 for x in pz if 0 <= x["dias"] <= DIAS_PERTO),
            "alertas": al, "orcamento_total": orc["total"], "conta_id": p["conta_id"]}


def listar(con, incluir_arquivados: bool = False) -> list[dict]:
    rows = con.execute("SELECT * FROM projeto_camp " + ("" if incluir_arquivados else "WHERE situacao<>'arquivado' ") +
                       "ORDER BY situacao IN ('concluido','arquivado'), nome").fetchall()
    ref = hoje()
    return [resumo(con, p, ref) for p in rows]


def _conta_nome(con, cid) -> str:
    if not cid:
        return ""
    r = con.execute("SELECT nome FROM financeiro_conta WHERE id=?", (cid,)).fetchone()
    return r[0] if r else ""


def detalhe(con, pid: int, usuario: str) -> dict:
    p = _projeto_row(con, pid)
    ref = hoje()
    et, ta, ob = _etapas(con, pid), _tarefas(con, pid), _objetivos(con, pid)
    desp = _despesas(con, p)
    orc = orcamento(con, p, desp)
    rec, pat, notas = _receitas(con, pid), _patrocinios(con, pid), _notas(con, p)
    br = _fin().brl
    total_rec = _r2(sum(r["valor"] for r in rec) + sum(x["valor_pago"] for x in pat))
    total_desp = _r2(sum(d["valor"] for d in desp))
    dados = {k: (p[k] if p[k] is not None else "") for k in p.keys()}
    dados.update({"tipo_nome": TIPOS.get(p["tipo"], p["tipo"]), "situacao_nome": SITUACOES.get(p["situacao"], p["situacao"]), "conta_nome": _conta_nome(con, p["conta_id"])})
    return {"projeto": dados, "objetivos": ob, "etapas": et, "tarefas": ta, "progresso": progresso(et, ta, ob),
            "prazos": _prazos(p, et, ta, ref), "a_preencher": a_preencher(p), "alertas": alertas_projeto(con, p, et, ta, orc, desp, ref),
            "orcamento": orc, "financeiro": {"despesas": desp, "receitas": rec, "patrocinios": pat, "notas": notas,
                                             "total_receitas": total_rec, "total_despesas": total_desp, "saldo": _r2(total_rec - total_desp),
                                             "texto": f"Entradas {br(total_rec)} · saídas {br(total_desp)}"},
            "arquivos": _arquivos(con, pid), "historico": historico(con, pid), "mudancas": mudancas(con, pid, usuario),
            "visto_em": _visto(con, usuario, pid), "hoje": ref.isoformat(),
            "opcoes": {"tipos": TIPOS, "situacoes": SITUACOES, "sit_tarefa": SIT_TAREFA, "tipos_arquivo": TIPOS_ARQUIVO, "contas": _contas(con)}}


def _contas(con) -> list[dict]:
    if not _tem(con, "financeiro_conta"):
        return []
    return [{"id": r["id"], "nome": r["nome"], "tipo": r["tipo"]} for r in con.execute("SELECT id, nome, tipo FROM financeiro_conta ORDER BY id")]


def home(con, usuario: str) -> dict:
    """Bloco da Home: o que está atrasado, o que vence em 7 dias, avisos de orçamento e comprovante, e o que mudou desde a última visita."""
    ps = listar(con)
    itens, mud = [], 0
    for x in ps:
        itens += [a for a in x["alertas"] if a["nivel"] in ("r", "a")]
        mud += len(mudancas(con, x["id"], usuario))
    ordem = {"r": 0, "a": 1}
    itens.sort(key=lambda a: (ordem[a["nivel"]], a["dias"] if a["dias"] is not None else 9999))
    return {"projetos": len(ps), "atrasados": sum(x["atrasados"] for x in ps), "vencem_7d": sum(x["vencem_7d"] for x in ps),
            "mudancas": mud, "itens": itens[:8], "mais": max(0, len(itens) - 8),
            "lista": [{"id": x["id"], "nome": x["nome"], "situacao_nome": x["situacao_nome"], "proximo_prazo": x["proximo_prazo"], "progresso": x["progresso"]["pct"]} for x in ps[:5]]}


# ---------------------------------------------------------------- resumo diário por e-mail
def email_estado(con) -> dict:
    para = [e.strip() for e in re.split(r"[,;\s]+", _cfg(con, "projetos_camp.email_diario")) if e.strip()]
    try:
        hora = max(0, min(23, int(_cfg(con, "projetos_camp.email_hora", "8") or 8)))
    except ValueError:
        hora = 8
    ult = con.execute("SELECT dia, para, ok, erro, enviado_em FROM projeto_camp_email_envio ORDER BY dia DESC LIMIT 1").fetchone()
    return {"para": para, "hora": hora, "ligado": bool(para), "ultimo": dict(ult) if ult else None}


def texto_email(con, ref: date, url: str) -> tuple[str, str, dict]:
    ps = listar(con)
    atras = [(x, a) for x in ps for a in x["alertas"] if a["tipo"] == "atrasado"]
    perto = [(x, a) for x in ps for a in x["alertas"] if a["tipo"] == "prazo"]
    outros = [(x, a) for x in ps for a in x["alertas"] if a["tipo"] in ("orcamento", "comprovante")]
    ontem = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    mud = []
    for x in ps:
        for m in mudancas(con, x["id"], "", desde=ontem):
            mud.append((x, m))
    n = {"projetos": len(ps), "atrasados": len(atras), "prazos": len(perto), "outros": len(outros), "mudancas": len(mud)}
    titulo = f"Projetos da CAMP · {_br(ref.isoformat())}: {len(atras)} atrasado{'s' if len(atras) != 1 else ''}, {len(perto)} prazo{'s' if len(perto) != 1 else ''} próximo{'s' if len(perto) != 1 else ''}"
    linhas = [f"Resumo dos Projetos da CAMP em {_br(ref.isoformat())}.", ""]
    def bloco(nome, xs, fmt):
        linhas.append(f"{nome} ({len(xs)})")
        linhas.extend(fmt(x, a) for x, a in xs[:30]) if xs else linhas.append("  nada")
        linhas.append("")
    bloco("Atrasado", atras, lambda x, a: f"  - {x['nome']}: {a['titulo']}")
    bloco(f"Vence nos próximos dias (tarefas em {DIAS_PERTO}, prazos do SALIC/edital em {DIAS_INSTITUCIONAL})", perto, lambda x, a: f"  - {x['nome']}: {a['titulo']}")
    bloco("Orçamento e comprovantes", outros, lambda x, a: f"  - {x['nome']}: {a['titulo']} ({a['motivo']})")
    bloco("Mudou nas últimas 24 horas", mud, lambda x, m: f"  - {x['nome']}: {m['texto']} ({m['ator']})")
    linhas.append(f"Abrir no painel: {url}/#projetos_camp")
    return titulo, "\n".join(linhas), n


def resumo_email(con, agora: datetime | None = None, enviar=None, forcar: bool = False) -> dict:
    """Um e-mail por dia, a partir de projetos_camp.email_hora, para quem está em projetos_camp.email_diario (vazio = desligado).
    forcar=True (botão "Enviar um teste agora") ignora o horário e o "já enviado hoje" e não conta como o resumo do dia."""
    from . import email_envio
    agora = agora or datetime.now()
    est = email_estado(con)
    if not est["ligado"]:
        return {"enviado": False, "motivo": "desligado"}
    if agora.hour < est["hora"] and not forcar:
        return {"enviado": False, "motivo": f"antes das {est['hora']}h"}
    dia = agora.strftime("%Y-%m-%d")
    if not forcar and con.execute("SELECT 1 FROM projeto_camp_email_envio WHERE dia=?", (dia,)).fetchone():
        return {"enviado": False, "motivo": "já enviado hoje"}
    if not forcar and not con.execute("SELECT 1 FROM projeto_camp WHERE situacao NOT IN ('concluido','arquivado') LIMIT 1").fetchone():
        return {"enviado": False, "motivo": "nenhum projeto em andamento"}
    titulo, corpo, n = texto_email(con, agora.date() if not _fin()._HOJE else hoje(), _cfg(con, "painel.url", "https://painel.camp.arq.br").rstrip("/"))
    smtp = email_envio.configuracao(con)
    erros, ok = [], 0
    if not email_envio.configurado(smtp):
        erros.append("SMTP não configurado (Configurações → E-mail e avisos)")
    else:
        for para in est["para"]:
            try:
                (enviar or email_envio.enviar)(smtp, para, titulo, corpo)
                ok += 1
            except Exception as ex:  # noqa: BLE001
                erros.append(f"{para}: {str(ex)[:160]}")
    res = {"enviado": ok > 0, "para": est["para"], "enviados": ok, "erro": "; ".join(erros) or None, "titulo": titulo, "corpo": corpo, "numeros": n}
    if forcar:
        return res
    con.execute("""INSERT INTO projeto_camp_email_envio (dia, para, ok, erro, conteudo) VALUES (?,?,?,?,?)
                   ON CONFLICT(dia) DO UPDATE SET para=excluded.para, ok=excluded.ok, erro=excluded.erro, conteudo=excluded.conteudo, enviado_em=datetime('now')""",
                (dia, ", ".join(est["para"]), int(ok > 0), res["erro"], json.dumps(n, ensure_ascii=False)))
    con.commit()
    return res


# ---------------------------------------------------------------- criar o projeto do PRONAC a partir do Financeiro
def semear_rouanet(con, aplicar: bool, ator: str) -> dict:
    """Simula (padrão) ou cria o projeto do PRONAC 2613864 com os dados que JÁ estão no Financeiro (conta do Banco do Brasil e planilha do
    SALIC). Não inventa: datas, objetivo, responsável e prazos ficam vazios ("a preencher")."""
    if not _tem(con, "projeto_incentivado"):
        return {"acao": "nada", "motivo": "O Financeiro ainda não tem o projeto incentivado."}
    r = con.execute("SELECT c.id, c.nome, p.pronac, p.titulo, p.inicio, p.fim FROM financeiro_conta c LEFT JOIN projeto_incentivado p ON p.conta_id=c.id "
                    "WHERE c.id=? AND c.tipo='projeto_incentivado'", (ROUANET_CONTA,)).fetchone()
    if not r:
        return {"acao": "nada", "motivo": "A conta do projeto incentivado não está cadastrada no Financeiro."}
    codigo = f"PRONAC {r['pronac']}" if r["pronac"] else None
    ja = con.execute("SELECT id FROM projeto_camp WHERE conta_id=? OR (codigo_externo IS NOT NULL AND codigo_externo=?)", (r["id"], codigo or "")).fetchone()
    if ja:
        return {"acao": "ja_existe", "projeto_id": ja[0], "motivo": "O projeto deste PRONAC já existe."}
    n_itens = con.execute("SELECT COUNT(*) FROM orcamento_item WHERE conta_id=?", (r["id"],)).fetchone()[0] if _tem(con, "orcamento_item") else 0
    total = _r2(con.execute("SELECT SUM(valor_aprovado) FROM orcamento_item WHERE conta_id=?", (r["id"],)).fetchone()[0]) if n_itens else 0.0
    ini = f"{r['inicio']}-01" if r["inicio"] and re.match(r"^\d{4}-\d{2}$", r["inicio"]) else None
    fim = None
    if r["fim"] and re.match(r"^\d{4}-\d{2}$", r["fim"]):
        a, m = map(int, r["fim"].split("-"))
        fim = (date(a + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).isoformat()
    plano = {"nome": r["titulo"] or r["nome"], "tipo": "rouanet", "codigo_externo": codigo, "conta_id": r["id"], "conta_nome": r["nome"],
             "itens_orcamento": n_itens, "orcamento_total": total, "inicio": ini, "fim": fim,
             "a_preencher": ["Objetivo geral", "Responsável"] + ([] if ini and fim else ["Início e fim"]) + [nome for _, nome in PRAZOS]}
    if not aplicar:
        return {"acao": "simulado", "plano": plano}
    cur = con.execute("INSERT INTO projeto_camp (nome, tipo, codigo_externo, conta_id, inicio, fim, criado_por) VALUES (?,?,?,?,?,?,?)",
                      (plano["nome"], "rouanet", codigo, r["id"], ini, fim, ator))
    pid = cur.lastrowid
    _ev(con, pid, "semeado_rouanet", ator, {"nome": plano["nome"], "conta_id": r["id"], "itens_orcamento": n_itens})
    con.commit()
    return {"acao": "criado", "projeto_id": pid, "plano": plano}


# ---------------------------------------------------------------- rotas
class NovoProjeto(BaseModel):
    nome: str
    tipo: str = "interno"
    codigo_externo: str | None = None
    responsavel: str | None = None
    objetivo_geral: str | None = None
    conta_id: int | None = None


class MudarProjeto(BaseModel):
    nome: str | None = None
    tipo: str | None = None
    codigo_externo: str | None = None
    situacao: str | None = None
    responsavel: str | None = None
    objetivo_geral: str | None = None
    resumo: str | None = None
    inicio: str | None = None
    fim: str | None = None
    prazo_captacao: str | None = None
    prazo_execucao: str | None = None
    prazo_prestacao: str | None = None
    conta_id: int | None = None
    sem_conta: bool = False


@router.get("")
def ver_lista(arquivados: bool = False, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        semear = semear_rouanet(con, False, _ator(u))
        return {"projetos": listar(con, arquivados), "semear": semear if semear["acao"] == "simulado" else None, "email": email_estado(con),
                "opcoes": {"tipos": TIPOS, "situacoes": SITUACOES, "contas": _contas(con)}, "hoje": hoje().isoformat()}
    finally:
        con.close()


@router.get("/home")
def ver_home(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return home(con, _ator(u))
    finally:
        con.close()


class Aplicar(BaseModel):
    aplicar: bool = False


@router.post("/semear-rouanet")
def rota_semear(b: Aplicar, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = semear_rouanet(con, b.aplicar, _ator(u))
        if r["acao"] == "criado":
            registrar(logging.INFO, "projeto_camp_semeado", "Projeto da CAMP criado a partir do PRONAC", projeto_id=r["projeto_id"])
        return r
    finally:
        con.close()


class Email(BaseModel):
    para: str = ""
    hora: int = 8


@router.put("/email")
def mudar_email(b: Email, u: dict = Depends(auth.exige("admin"))) -> dict:
    from . import email_envio
    ends = [e.strip() for e in re.split(r"[,;\s]+", b.para or "") if e.strip()]
    ruins = [e for e in ends if not email_envio.ENDERECO.match(e)]
    if ruins:
        raise HTTPException(400, f"Endereço de e-mail inválido: {', '.join(ruins[:3])}")
    if len(ends) > 10:
        raise HTTPException(400, "No máximo 10 endereços.")
    con = connect()
    try:
        for k, v in (("projetos_camp.email_diario", ", ".join(ends)), ("projetos_camp.email_hora", str(max(0, min(23, int(b.hora)))))):
            con.execute("INSERT INTO configuracao (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (k, v))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('configuracao','projetos_camp.email','editado',?,?)",
                    (_ator(u), json.dumps({"destinatarios": len(ends), "hora": b.hora})))
        con.commit()
        return email_estado(con)
    finally:
        con.close()


@router.post("/email/teste")
def email_teste(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = resumo_email(con, forcar=True)
        if r.get("motivo") == "desligado":
            raise HTTPException(400, "Escolha quem recebe o resumo antes de enviar o teste.")
        return {k: r.get(k) for k in ("enviado", "para", "enviados", "erro", "titulo")}
    finally:
        con.close()


def _validar_tipo(t: str | None) -> str:
    t = (t or "interno").strip()
    if t not in TIPOS:
        raise HTTPException(400, "Tipo de projeto inválido")
    return t


def _validar_conta(con, cid) -> int | None:
    if cid in (None, 0, ""):
        return None
    if not con.execute("SELECT 1 FROM financeiro_conta WHERE id=?", (int(cid),)).fetchone():
        raise HTTPException(400, "Conta do Financeiro não encontrada")
    return int(cid)


@router.post("")
def criar(b: NovoProjeto, u: dict = Depends(auth.exige("admin"))) -> dict:
    nome = _txt(b.nome, 200)
    if not nome:
        raise HTTPException(400, "Dê um nome ao projeto.")
    con = connect()
    try:
        cod = _txt(b.codigo_externo, 60) or None
        if cod and con.execute("SELECT 1 FROM projeto_camp WHERE codigo_externo=?", (cod,)).fetchone():
            raise HTTPException(409, f"Já existe um projeto com o código {cod}.")
        cur = con.execute("INSERT INTO projeto_camp (nome, tipo, codigo_externo, responsavel, objetivo_geral, conta_id, criado_por) VALUES (?,?,?,?,?,?,?)",
                          (nome, _validar_tipo(b.tipo), cod, _txt(b.responsavel, 120) or None, _txt_longo(b.objetivo_geral, 4000) or None,
                           _validar_conta(con, b.conta_id), _ator(u)))
        pid = cur.lastrowid
        _ev(con, pid, "criado", _ator(u), {"nome": nome})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


@router.get("/{pid}")
def ver(pid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


@router.post("/{pid}/visto")
def marcar_visto(pid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        _projeto_row(con, pid)
        con.execute("INSERT INTO projeto_camp_visto (usuario, projeto_id, visto_em) VALUES (?,?,datetime('now')) "
                    "ON CONFLICT(usuario, projeto_id) DO UPDATE SET visto_em=excluded.visto_em", (_ator(u), pid))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


@router.put("/{pid}")
def mudar(pid: int, b: MudarProjeto, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        p = _projeto_row(con, pid)
        v: dict = {}
        if b.nome is not None:
            if not _txt(b.nome, 200):
                raise HTTPException(400, "O projeto precisa de um nome.")
            v["nome"] = _txt(b.nome, 200)
        if b.tipo is not None:
            v["tipo"] = _validar_tipo(b.tipo)
        if b.situacao is not None:
            if b.situacao not in SITUACOES:
                raise HTTPException(400, "Situação inválida")
            v["situacao"] = b.situacao
            v["arquivado_em"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if b.situacao == "arquivado" else None
        if b.codigo_externo is not None:
            cod = _txt(b.codigo_externo, 60) or None
            if cod and con.execute("SELECT 1 FROM projeto_camp WHERE codigo_externo=? AND id<>?", (cod, pid)).fetchone():
                raise HTTPException(409, f"Já existe um projeto com o código {cod}.")
            v["codigo_externo"] = cod
        for k, n in (("responsavel", 120),):
            if getattr(b, k) is not None:
                v[k] = _txt(getattr(b, k), n) or None
        for k, n in (("objetivo_geral", 4000), ("resumo", 4000)):
            if getattr(b, k) is not None:
                v[k] = _txt_longo(getattr(b, k), n) or None
        for k, nome in (("inicio", "Início"), ("fim", "Fim"), ("prazo_captacao", "Prazo de captação"), ("prazo_execucao", "Fim da execução"),
                        ("prazo_prestacao", "Prestação de contas")):
            if getattr(b, k) is not None:
                v[k] = _data(getattr(b, k), nome)
        if (v.get("inicio", p["inicio"]) and v.get("fim", p["fim"])) and v.get("fim", p["fim"]) < v.get("inicio", p["inicio"]):
            raise HTTPException(400, "O fim não pode ser antes do início.")
        if b.sem_conta:
            v["conta_id"] = None
        elif b.conta_id is not None:
            v["conta_id"] = _validar_conta(con, b.conta_id)
        mudou = [k for k in v if k != "arquivado_em" and (p[k] or None) != (v[k] or None)]
        if mudou:
            con.execute(f"UPDATE projeto_camp SET {', '.join(k + '=?' for k in v)}, alterado_por=?, alterado_em=datetime('now') WHERE id=?",
                        (*v.values(), _ator(u), pid))
            nomes = {"nome": "nome", "tipo": "tipo", "situacao": "situação", "codigo_externo": "código", "responsavel": "responsável",
                     "objetivo_geral": "objetivo geral", "resumo": "resumo", "inicio": "início", "fim": "fim", "prazo_captacao": "prazo de captação",
                     "prazo_execucao": "fim da execução", "prazo_prestacao": "prestação de contas", "conta_id": "conta"}
            _ev(con, pid, "dados_alterados", _ator(u), {"campos": [nomes.get(k, k) for k in mudou], **({"situacao": v["situacao"]} if "situacao" in mudou else {})})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


# objetivos ------------------------------------------------------------------------------------------------
class Objetivo(BaseModel):
    texto: str | None = None
    indicador: str | None = None
    meta: float | None = None
    atual: float | None = None
    limpar_meta: bool = False


@router.post("/{pid}/objetivos")
def objetivo_criar(pid: int, b: Objetivo, u: dict = Depends(auth.exige("admin"))) -> dict:
    t = _txt_longo(b.texto, 1000)
    if not t:
        raise HTTPException(400, "Escreva o objetivo.")
    con = connect()
    try:
        _projeto_row(con, pid)
        n = con.execute("SELECT COALESCE(MAX(ordem),0)+1 FROM projeto_camp_objetivo WHERE projeto_id=?", (pid,)).fetchone()[0]
        con.execute("INSERT INTO projeto_camp_objetivo (projeto_id, texto, indicador, meta, atual, ordem) VALUES (?,?,?,?,?,?)",
                    (pid, t, _txt(b.indicador, 120) or None, b.meta, b.atual, n))
        _ev(con, pid, "objetivo_criado", _ator(u), {"texto": t[:120]})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


@router.put("/{pid}/objetivos/{oid}")
def objetivo_mudar(pid: int, oid: int, b: Objetivo, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT * FROM projeto_camp_objetivo WHERE id=? AND projeto_id=? AND apagado_em IS NULL", (oid, pid)).fetchone()
        if not r:
            raise HTTPException(404, "Objetivo não encontrado")
        v = {}
        if b.texto is not None:
            if not _txt_longo(b.texto, 1000):
                raise HTTPException(400, "Escreva o objetivo.")
            v["texto"] = _txt_longo(b.texto, 1000)
        if b.indicador is not None:
            v["indicador"] = _txt(b.indicador, 120) or None
        if b.limpar_meta:
            v["meta"], v["atual"] = None, None
        else:
            if b.meta is not None:
                v["meta"] = b.meta
            if b.atual is not None:
                v["atual"] = b.atual
        if v:
            con.execute(f"UPDATE projeto_camp_objetivo SET {', '.join(k + '=?' for k in v)} WHERE id=?", (*v.values(), oid))
            _ev(con, pid, "objetivo_alterado", _ator(u), {"texto": (v.get("texto") or r["texto"])[:120]})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


@router.delete("/{pid}/objetivos/{oid}")
def objetivo_apagar(pid: int, oid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT texto FROM projeto_camp_objetivo WHERE id=? AND projeto_id=? AND apagado_em IS NULL", (oid, pid)).fetchone()
        if not r:
            raise HTTPException(404, "Objetivo não encontrado")
        con.execute("UPDATE projeto_camp_objetivo SET apagado_em=datetime('now') WHERE id=?", (oid,))
        _ev(con, pid, "objetivo_apagado", _ator(u), {"texto": r[0][:120]})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


# etapas e tarefas -----------------------------------------------------------------------------------------
class Etapa(BaseModel):
    nome: str | None = None
    inicio: str | None = None
    prazo: str | None = None
    situacao: str | None = None
    marco: bool | None = None


class Tarefa(BaseModel):
    o_que: str | None = None
    responsavel: str | None = None
    prazo: str | None = None
    situacao: str | None = None
    nota: str | None = None
    etapa_id: int | None = None
    sem_etapa: bool = False


def _sit(s: str | None) -> str | None:
    if s is None:
        return None
    if s not in SIT_TAREFA:
        raise HTTPException(400, "Situação inválida")
    return s


@router.post("/{pid}/etapas")
def etapa_criar(pid: int, b: Etapa, u: dict = Depends(auth.exige("admin"))) -> dict:
    nome = _txt(b.nome, 200)
    if not nome:
        raise HTTPException(400, "Dê um nome à etapa.")
    con = connect()
    try:
        _projeto_row(con, pid)
        ini, pz = _data(b.inicio, "Início"), _data(b.prazo, "Prazo")
        if ini and pz and pz < ini:
            raise HTTPException(400, "O prazo não pode ser antes do início.")
        n = con.execute("SELECT COALESCE(MAX(ordem),0)+1 FROM projeto_camp_etapa WHERE projeto_id=?", (pid,)).fetchone()[0]
        s = _sit(b.situacao) or "a_fazer"
        con.execute("INSERT INTO projeto_camp_etapa (projeto_id, nome, inicio, prazo, situacao, marco, ordem, feita_em) VALUES (?,?,?,?,?,?,?,?)",
                    (pid, nome, ini, pz, s, int(bool(b.marco)), n, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if s == "feita" else None))
        _ev(con, pid, "etapa_criada", _ator(u), {"nome": nome})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


@router.put("/{pid}/etapas/{eid}")
def etapa_mudar(pid: int, eid: int, b: Etapa, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT * FROM projeto_camp_etapa WHERE id=? AND projeto_id=? AND apagado_em IS NULL", (eid, pid)).fetchone()
        if not r:
            raise HTTPException(404, "Etapa não encontrada")
        v = {}
        if b.nome is not None:
            if not _txt(b.nome, 200):
                raise HTTPException(400, "Dê um nome à etapa.")
            v["nome"] = _txt(b.nome, 200)
        if b.inicio is not None:
            v["inicio"] = _data(b.inicio, "Início")
        if b.prazo is not None:
            v["prazo"] = _data(b.prazo, "Prazo")
        if b.marco is not None:
            v["marco"] = int(b.marco)
        if b.situacao is not None:
            v["situacao"] = _sit(b.situacao)
            v["feita_em"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if b.situacao == "feita" else None
        ini, pz = v.get("inicio", r["inicio"]), v.get("prazo", r["prazo"])
        if ini and pz and pz < ini:
            raise HTTPException(400, "O prazo não pode ser antes do início.")
        if v:
            con.execute(f"UPDATE projeto_camp_etapa SET {', '.join(k + '=?' for k in v)} WHERE id=?", (*v.values(), eid))
            _ev(con, pid, "etapa_alterada", _ator(u), {"nome": v.get("nome") or r["nome"], **({"situacao": b.situacao} if b.situacao else {})})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


@router.delete("/{pid}/etapas/{eid}")
def etapa_apagar(pid: int, eid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT nome FROM projeto_camp_etapa WHERE id=? AND projeto_id=? AND apagado_em IS NULL", (eid, pid)).fetchone()
        if not r:
            raise HTTPException(404, "Etapa não encontrada")
        con.execute("UPDATE projeto_camp_etapa SET apagado_em=datetime('now') WHERE id=?", (eid,))
        con.execute("UPDATE projeto_camp_tarefa SET etapa_id=NULL WHERE etapa_id=?", (eid,))   # as tarefas ficam, sem etapa
        _ev(con, pid, "etapa_apagada", _ator(u), {"nome": r[0]})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


def _etapa_ok(con, pid: int, eid) -> int | None:
    if not eid:
        return None
    if not con.execute("SELECT 1 FROM projeto_camp_etapa WHERE id=? AND projeto_id=? AND apagado_em IS NULL", (eid, pid)).fetchone():
        raise HTTPException(400, "Etapa não encontrada neste projeto")
    return int(eid)


@router.post("/{pid}/tarefas")
def tarefa_criar(pid: int, b: Tarefa, u: dict = Depends(auth.exige("admin"))) -> dict:
    t = _txt(b.o_que, 300)
    if not t:
        raise HTTPException(400, "Escreva o que fazer.")
    con = connect()
    try:
        _projeto_row(con, pid)
        s = _sit(b.situacao) or "a_fazer"
        con.execute("INSERT INTO projeto_camp_tarefa (projeto_id, etapa_id, o_que, responsavel, prazo, situacao, nota, feita_em, criado_por) VALUES (?,?,?,?,?,?,?,?,?)",
                    (pid, _etapa_ok(con, pid, b.etapa_id), t, _txt(b.responsavel, 120) or None, _data(b.prazo, "Prazo"), s, _txt_longo(b.nota, 2000) or None,
                     datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if s == "feita" else None, _ator(u)))
        _ev(con, pid, "tarefa_criada", _ator(u), {"o_que": t})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


@router.put("/{pid}/tarefas/{tid}")
def tarefa_mudar(pid: int, tid: int, b: Tarefa, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT * FROM projeto_camp_tarefa WHERE id=? AND projeto_id=? AND apagado_em IS NULL", (tid, pid)).fetchone()
        if not r:
            raise HTTPException(404, "Tarefa não encontrada")
        v = {}
        if b.o_que is not None:
            if not _txt(b.o_que, 300):
                raise HTTPException(400, "Escreva o que fazer.")
            v["o_que"] = _txt(b.o_que, 300)
        if b.responsavel is not None:
            v["responsavel"] = _txt(b.responsavel, 120) or None
        if b.prazo is not None:
            v["prazo"] = _data(b.prazo, "Prazo")
        if b.nota is not None:
            v["nota"] = _txt_longo(b.nota, 2000) or None
        if b.sem_etapa:
            v["etapa_id"] = None
        elif b.etapa_id is not None:
            v["etapa_id"] = _etapa_ok(con, pid, b.etapa_id)
        if b.situacao is not None:
            v["situacao"] = _sit(b.situacao)
            v["feita_em"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if b.situacao == "feita" else None
        if v:
            con.execute(f"UPDATE projeto_camp_tarefa SET {', '.join(k + '=?' for k in v)} WHERE id=?", (*v.values(), tid))
            _ev(con, pid, "tarefa_alterada", _ator(u), {"o_que": v.get("o_que") or r["o_que"], **({"situacao": b.situacao} if b.situacao else {})})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


@router.delete("/{pid}/tarefas/{tid}")
def tarefa_apagar(pid: int, tid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT o_que FROM projeto_camp_tarefa WHERE id=? AND projeto_id=? AND apagado_em IS NULL", (tid, pid)).fetchone()
        if not r:
            raise HTTPException(404, "Tarefa não encontrada")
        con.execute("UPDATE projeto_camp_tarefa SET apagado_em=datetime('now') WHERE id=?", (tid,))
        _ev(con, pid, "tarefa_apagada", _ator(u), {"o_que": r[0]})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


# orçamento próprio e entradas -----------------------------------------------------------------------------
class Item(BaseModel):
    descricao: str | None = None
    previsto: float | None = None


@router.post("/{pid}/itens")
def item_criar(pid: int, b: Item, u: dict = Depends(auth.exige("admin"))) -> dict:
    d = _txt(b.descricao, 200)
    if not d:
        raise HTTPException(400, "Descreva o item do orçamento.")
    if b.previsto is None or b.previsto < 0:
        raise HTTPException(400, "Informe o valor previsto.")
    con = connect()
    try:
        p = _projeto_row(con, pid)
        if _conta_incentivada(con, p["conta_id"]):
            raise HTTPException(400, "O orçamento deste projeto é a planilha do SALIC (Financeiro → Projeto incentivado).")
        n = con.execute("SELECT COALESCE(MAX(ordem),0)+1 FROM projeto_camp_item WHERE projeto_id=?", (pid,)).fetchone()[0]
        con.execute("INSERT INTO projeto_camp_item (projeto_id, descricao, previsto, ordem) VALUES (?,?,?,?)", (pid, d, _r2(b.previsto), n))
        _ev(con, pid, "item_criado", _ator(u), {"descricao": d})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


@router.put("/{pid}/itens/{iid}")
def item_mudar(pid: int, iid: int, b: Item, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT * FROM projeto_camp_item WHERE id=? AND projeto_id=? AND apagado_em IS NULL", (iid, pid)).fetchone()
        if not r:
            raise HTTPException(404, "Item não encontrado")
        v = {}
        if b.descricao is not None and _txt(b.descricao, 200):
            v["descricao"] = _txt(b.descricao, 200)
        if b.previsto is not None:
            if b.previsto < 0:
                raise HTTPException(400, "O previsto não pode ser negativo.")
            v["previsto"] = _r2(b.previsto)
        if v:
            con.execute(f"UPDATE projeto_camp_item SET {', '.join(k + '=?' for k in v)} WHERE id=?", (*v.values(), iid))
            _ev(con, pid, "item_alterado", _ator(u), {"descricao": v.get("descricao") or r["descricao"]})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


@router.delete("/{pid}/itens/{iid}")
def item_apagar(pid: int, iid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT descricao FROM projeto_camp_item WHERE id=? AND projeto_id=? AND apagado_em IS NULL", (iid, pid)).fetchone()
        if not r:
            raise HTTPException(404, "Item não encontrado")
        con.execute("UPDATE projeto_camp_item SET apagado_em=datetime('now') WHERE id=?", (iid,))
        con.execute("UPDATE despesa SET projeto_camp_item=NULL WHERE projeto_camp_item=?", (iid,))
        _ev(con, pid, "item_apagado", _ator(u), {"descricao": r[0]})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


class Receita(BaseModel):
    data: str
    valor: float
    origem: str | None = None
    descricao: str | None = None


@router.post("/{pid}/receitas")
def receita_criar(pid: int, b: Receita, u: dict = Depends(auth.exige("admin"))) -> dict:
    if b.valor is None or b.valor <= 0:
        raise HTTPException(400, "Informe o valor da entrada.")
    dt = _data(b.data, "Data")
    if not dt:
        raise HTTPException(400, "Informe a data da entrada.")
    con = connect()
    try:
        _projeto_row(con, pid)
        con.execute("INSERT INTO projeto_camp_receita (projeto_id, data, valor, origem, descricao, criado_por) VALUES (?,?,?,?,?,?)",
                    (pid, dt, _r2(b.valor), _txt(b.origem, 200) or None, _txt(b.descricao, 300) or None, _ator(u)))
        _ev(con, pid, "receita_criada", _ator(u), {"descricao": f"{_fin().brl(b.valor)} · {_txt(b.origem, 80)}".rstrip(" ·")})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


@router.delete("/{pid}/receitas/{rid}")
def receita_apagar(pid: int, rid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT valor, origem FROM projeto_camp_receita WHERE id=? AND projeto_id=? AND apagado_em IS NULL", (rid, pid)).fetchone()
        if not r:
            raise HTTPException(404, "Entrada não encontrada")
        con.execute("UPDATE projeto_camp_receita SET apagado_em=datetime('now') WHERE id=?", (rid,))
        _ev(con, pid, "receita_apagada", _ator(u), {"descricao": f"{_fin().brl(r[0])} · {r[1] or ''}".rstrip(" ·")})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


# ligar despesas e patrocínios -----------------------------------------------------------------------------
@router.get("/{pid}/candidatas")
def candidatas(pid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Despesas que ainda não são de nenhum projeto (fora da conta do projeto) e patrocínios sem projeto, para ligar."""
    con = connect()
    try:
        p = _projeto_row(con, pid)
        desp = [{"id": r["id"], "data": r["data"], "valor": _r2(r["valor"]), "contraparte": r["contraparte"] or "", "justificativa": r["justificativa"] or r["descricao"] or ""}
                for r in con.execute("SELECT * FROM despesa WHERE apagado_em IS NULL AND tipo='despesa' AND projeto_camp_id IS NULL AND (? IS NULL OR conta_id<>?) "
                                     "ORDER BY data DESC, id DESC LIMIT 200", (p["conta_id"], p["conta_id"]))]
        pat = []
        if _tem(con, "patrocinio"):
            pat = [{"site_id": r["site_id"], "empresa": r["empresa"] or r["razao_social"] or "", "cota": r["cota"] or "", "valor_pago": _r2(r["valor_pago"])}
                   for r in con.execute("SELECT * FROM patrocinio WHERE projeto_camp_id IS NULL AND anonimizado=0 ORDER BY site_id DESC LIMIT 100")]
        return {"despesas": desp, "patrocinios": pat}
    finally:
        con.close()


class Ligar(BaseModel):
    ligar: bool = True
    item: int | None = None


@router.put("/{pid}/despesas/{did}")
def ligar_despesa(pid: int, did: int, b: Ligar, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        _projeto_row(con, pid)
        r = con.execute("SELECT * FROM despesa WHERE id=? AND apagado_em IS NULL", (did,)).fetchone()
        if not r:
            raise HTTPException(404, "Despesa não encontrada")
        if b.ligar and r["projeto_camp_id"] and r["projeto_camp_id"] != pid:
            raise HTTPException(409, "Esta despesa já está em outro projeto da CAMP.")
        item = None
        if b.ligar and b.item:
            if not con.execute("SELECT 1 FROM projeto_camp_item WHERE id=? AND projeto_id=? AND apagado_em IS NULL", (b.item, pid)).fetchone():
                raise HTTPException(400, "Item do orçamento não encontrado neste projeto")
            item = b.item
        con.execute("UPDATE despesa SET projeto_camp_id=?, projeto_camp_item=? WHERE id=?", (pid if b.ligar else None, item, did))
        _ev(con, pid, "despesa_ligada" if b.ligar else "despesa_desligada", _ator(u),
            {"descricao": f"{_fin().brl(r['valor'])} · {r['contraparte'] or ''}".rstrip(" ·"), "despesa": did})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


@router.put("/{pid}/patrocinios/{sid}")
def ligar_patrocinio(pid: int, sid: int, b: Ligar, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        _projeto_row(con, pid)
        r = con.execute("SELECT * FROM patrocinio WHERE site_id=?", (sid,)).fetchone()
        if not r:
            raise HTTPException(404, "Patrocínio não encontrado")
        if b.ligar and r["projeto_camp_id"] and r["projeto_camp_id"] != pid:
            raise HTTPException(409, "Este patrocínio já está em outro projeto da CAMP.")
        con.execute("UPDATE patrocinio SET projeto_camp_id=? WHERE site_id=?", (pid if b.ligar else None, sid))
        _ev(con, pid, "patrocinio_ligado" if b.ligar else "patrocinio_desligado", _ator(u), {"nome": r["empresa"] or r["razao_social"] or str(sid)})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


# documentos -----------------------------------------------------------------------------------------------
def pasta_arquivos() -> Path:
    p = Path(os.environ.get("CAMP_PROJETOS_CAMP_DIR") or Path(settings.CAMP_DB_PATH).resolve().parent / "projetos_camp_arquivos")
    p.mkdir(parents=True, exist_ok=True)
    return p


class Arquivo(BaseModel):
    nome: str
    base64: str
    tipo: str = "outro"


@router.post("/{pid}/arquivos")
def arquivo_enviar(pid: int, b: Arquivo, u: dict = Depends(auth.exige("admin"))) -> dict:
    from .doacoes_central import _ext, nome_limpo, tipo_pelos_bytes
    con = connect()
    try:
        _projeto_row(con, pid)
        try:
            dados = base64.b64decode(re.sub(r"^data:[^,]*,", "", b.base64 or "").strip(), validate=True)
        except (binascii.Error, ValueError) as e:
            raise HTTPException(400, "O arquivo chegou incompleto: escolha de novo.") from e
        ext = _ext(b.nome)
        if ext not in EXT_MIME:
            raise HTTPException(400, "Tipo de arquivo não aceito: PDF, JPG, PNG, WEBP, XLSX ou DOCX.")
        if not dados:
            raise HTTPException(400, "O arquivo chegou vazio: escolha de novo.")
        if len(dados) > MAX_ARQUIVO:
            raise HTTPException(400, "O arquivo passa de 15 MB: diminua ou divida.")
        if not tipo_pelos_bytes(dados, ext):
            raise HTTPException(400, f"O conteúdo do arquivo não é {ext.upper()} de verdade (a extensão não bate com o arquivo).")
        sha = hashlib.sha256(dados).hexdigest()
        if con.execute("SELECT 1 FROM projeto_camp_arquivo WHERE projeto_id=? AND sha256=? AND apagado_em IS NULL", (pid, sha)).fetchone():
            raise HTTPException(409, "Este arquivo já está nos documentos do projeto.")
        tipo = b.tipo if b.tipo in TIPOS_ARQUIVO else "outro"
        ext = "jpg" if ext == "jpeg" else ext
        nm = nome_limpo(b.nome, ext)
        cur = con.execute("INSERT INTO projeto_camp_arquivo (projeto_id, tipo, nome, arquivo, mime, tamanho, sha256, criado_por) VALUES (?,?,?,?,?,?,?,?)",
                          (pid, tipo, nm, "", EXT_MIME[ext], len(dados), sha, _ator(u)))
        aid = cur.lastrowid
        rel = f"{int(pid)}/{aid}-{sha[:12]}.{ext}"
        (pasta_arquivos() / str(int(pid))).mkdir(parents=True, exist_ok=True)
        (pasta_arquivos() / rel).write_bytes(dados)
        con.execute("UPDATE projeto_camp_arquivo SET arquivo=? WHERE id=?", (rel, aid))
        _ev(con, pid, "arquivo_adicionado", _ator(u), {"nome": nm})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()


@router.get("/{pid}/arquivos/{aid}")
def arquivo_baixar(pid: int, aid: int, u: dict = Depends(auth.exige("admin"))):
    con = connect()
    try:
        r = con.execute("SELECT * FROM projeto_camp_arquivo WHERE id=? AND projeto_id=? AND apagado_em IS NULL", (aid, pid)).fetchone()
    finally:
        con.close()
    if not r:
        raise HTTPException(404, "Documento não encontrado")
    f = (pasta_arquivos() / r["arquivo"]).resolve()
    if not r["arquivo"] or pasta_arquivos().resolve() not in f.parents or not f.is_file():
        raise HTTPException(404, "O arquivo não está mais na pasta do painel")
    return FileResponse(str(f), media_type=r["mime"] or "application/octet-stream", filename=r["nome"],
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@router.delete("/{pid}/arquivos/{aid}")
def arquivo_tirar(pid: int, aid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Tira o documento do projeto (some da lista); a linha e o arquivo ficam guardados e a retirada vai para o histórico."""
    con = connect()
    try:
        r = con.execute("SELECT nome FROM projeto_camp_arquivo WHERE id=? AND projeto_id=? AND apagado_em IS NULL", (aid, pid)).fetchone()
        if not r:
            raise HTTPException(404, "Documento não encontrado")
        con.execute("UPDATE projeto_camp_arquivo SET apagado_em=datetime('now'), apagado_por=? WHERE id=?", (_ator(u), aid))
        _ev(con, pid, "arquivo_tirado", _ator(u), {"nome": r[0]})
        con.commit()
        return detalhe(con, pid, _ator(u))
    finally:
        con.close()
