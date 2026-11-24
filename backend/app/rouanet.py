"""Financeiro · Projeto incentivado (CAMP-ROUANET, 24/11/2026). PRONAC 2613864, "Edição do livro Arquitetura Moderna Paulista: Acervo Karazawa".

Rafael: "A CAMP emitirá nota para cobrar o projeto de Rouanet do livro, porque além de prestar serviço pro projeto vamos cobrar pelo uso do
escritório etc." A CAMP (a proponente) emite notas ao projeto, pagas da conta do projeto no Banco do Brasil para a conta da CAMP.

- **Orçamento do projeto**: a planilha orçamentária do SALIC (migração 254; cópia em docs/rouanet/), agrupada como no SALIC (produto → etapa →
  município), com orçado, gasto (despesas ligadas ao item + notas da CAMP pagas), saldo e % usado. O valor APROVADO começa igual ao
  solicitado; o admin muda item a item ou importa a planilha aprovada (mesmo formato, simulada antes) e confirma ("Valores solicitados:
  atualize com a planilha aprovada" até confirmar). Avisos: item com 90% ou mais (âmbar), acima do orçado (vermelho) e o total usado,
  também no gancho de alertas do Financeiro (`financeiro_ia.orcamento_projetos`).
- **Despesas da conta do projeto**: item do orçamento obrigatório ("16 · Impressão") e nota fiscal obrigatória ("Projeto incentivado: nota
  fiscal obrigatória"); a sugestão inteligente aprende o item (mesma contraparte → o item que a equipe escolheu; senão palavras da descrição).
- **Notas da CAMP para o projeto**: planejada → emitida (número, data, PDF) → paga (o débito na conta do projeto e, se veio pelo Mercado
  Pago, o crédito na conta da CAMP). "Preparar nota do mês" monta o rascunho pelo plano mensal (item, meses, valor por mês) e o texto pronto
  para copiar no sistema da prefeitura. **O painel NÃO emite a NFS-e** (precisa de certificado digital): só prepara os dados e acompanha.
- **Efeito contábil**: paga, a nota é despesa da conta do projeto (item N) e receita da conta da CAMP ("Serviços prestados ao projeto
  incentivado", linha própria na DRE). No Consolidado é transferência interna: não entra nem como receita nem como despesa (com nota).
- **Prestação de contas**: planilha orçado × gasto × saldo, as despesas por item (nº da NF, data, fornecedor, valor) e as notas da CAMP; ZIP
  com os comprovantes numa pasta por item e os PDFs das notas.
- O painel não afirma que algo é permitido pela lei: a tela traz o cuidado (AVISO_LEI). Só admin e master.
"""
from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import io
import json
import os
import re
import secrets
import unicodedata
import zipfile
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from . import auth
from .config import settings
from .db import connect

router = APIRouter(prefix="/api/financeiro/projeto", tags=["projeto_incentivado"])

AVISO_LEI = ("Pagamentos do projeto à própria proponente seguem as regras da Lei Rouanet e do MinC (limites e comprovação). "
             "Confirme com o contador/consultoria antes de emitir.")
AVISO_SOLICITADO = "Valores solicitados: atualize com a planilha aprovada"
AVISO_INTERNA = ("As notas da CAMP pagas pelo projeto são despesa da conta do projeto e receita da conta da CAMP. No Consolidado são "
                 "transferência interna: não entram nem como receita nem como despesa.")
AVISO_NFSE = "O painel não emite a nota na prefeitura (precisa de certificado digital): copie estes dados no sistema da NFS-e."
NATUREZA = "servicos_projeto"
NOME_RECEITA = "Serviços prestados ao projeto incentivado"
SITUACOES = ("planejada", "emitida", "paga", "cancelada")
AMBAR = 0.9
COLUNAS_CSV = ["item", "produto", "etapa", "uf", "municipio", "descricao", "unidade", "dias", "qtde", "ocorrencias", "valor_unitario", "valor_solicitado"]
CHAVES_CAMP = {   # dados da CAMP (faturamento.*, migração 253: os mesmos da tela "Pedir nota fiscal"); aqui a CAMP é a prestadora
    "razao_social": ("faturamento.razao_social",),
    "cnpj": ("faturamento.cnpj",),
    "im": ("faturamento.inscricao_municipal",),
    "endereco": ("faturamento.endereco",),
    "email": ("faturamento.email_notas",),
}
PALAVRAS_ITEM = [   # (trecho normalizado na despesa, trecho normalizado na descrição do item)
    ("grafica", "impressao"), ("impress", "impressao"), ("correio", "correios"), ("sedex", "correios"), ("frete", "frete"), ("transport", "frete"),
    ("hotel", "hospedagem"), ("hosped", "hospedagem"), ("pousada", "hospedagem"), ("passage", "passagens"), ("aerea", "passagens"), ("latam", "passagens"),
    ("gol linhas", "passagens"), ("azul linhas", "passagens"), ("contab", "contador"), ("contador", "contador"), ("inss", "recolhimentos"),
    ("darf", "recolhimentos"), ("gps", "recolhimentos"), ("isbn", "isbn"), ("cbl", "isbn"), ("catalog", "isbn"), ("revis", "revisao de texto"),
    ("diagram", "diagramacao"), ("tratamento", "tratamento de imagens"), ("digitaliz", "digitalizacao"), ("video", "videografico"),
    ("filmag", "videografico"), ("ebook", "livro digital"), ("e-book", "livro digital"), ("cartilha", "cartilha"), ("acessib", "acessibilidade"),
    ("libras", "acessibilidade"), ("audiodescri", "acessibilidade"), ("captac", "captacao"), ("palestr", "palestrante"), ("educador", "arte educador"),
]


def _fin():
    from . import financeiro
    return financeiro


def _desp():
    from . import despesas
    return despesas


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _txt(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:n]


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "").lower()) if unicodedata.category(c) != "Mn")


def _r2(v) -> float:
    return round(float(v or 0) + 0.0, 2)


def _ator(u: dict | None) -> str:
    return (u or {}).get("email") or "painel"


def _ev(con, codigo: str, tipo: str, ator: str, detalhe: dict | None = None, entidade: str = "projeto_incentivado") -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)",
                (entidade, str(codigo), tipo, ator, json.dumps(detalhe or {}, ensure_ascii=False)))


def _mes_br(m: str) -> str:
    return f"{m[5:7]}/{m[:4]}" if m and len(m) >= 7 else (m or "")


def _mes_ok(m: str) -> str:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(m or "")):
        raise HTTPException(400, "Mês inválido (AAAA-MM)")
    return m


def _meses_entre(ini: str, fim: str) -> list[str]:
    a, m = int(ini[:4]), int(ini[5:7])
    out = []
    while (a, m) <= (int(fim[:4]), int(fim[5:7])) and len(out) < 60:
        out.append(f"{a}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return out


def pasta_notas() -> Path:
    p = Path(os.environ.get("CAMP_NOTAS_CAMP_DIR") or Path(settings.CAMP_DB_PATH).resolve().parent / "notas_camp")
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------- projeto e itens
def eh_projeto(con, conta_id) -> bool:
    r = con.execute("SELECT tipo FROM financeiro_conta WHERE id=?", (conta_id,)).fetchone()
    return bool(r and r[0] == "projeto_incentivado")


def projetos(con) -> list[dict]:
    out = []
    for c in con.execute("SELECT c.id, c.nome, c.ativa, p.pronac, p.titulo FROM financeiro_conta c LEFT JOIN projeto_incentivado p ON p.conta_id=c.id "
                         "WHERE c.tipo='projeto_incentivado' ORDER BY c.id"):
        n = con.execute("SELECT COUNT(*) FROM orcamento_item WHERE conta_id=?", (c["id"],)).fetchone()[0]
        out.append({"conta_id": c["id"], "nome": c["nome"], "ativa": bool(c["ativa"]), "pronac": c["pronac"] or "", "titulo": c["titulo"] or "", "itens": n})
    return out


def _projeto(con, cid: int) -> dict:
    c = con.execute("SELECT * FROM financeiro_conta WHERE id=?", (cid,)).fetchone()
    if not c or c["tipo"] != "projeto_incentivado":
        raise HTTPException(404, "Conta de projeto incentivado não encontrada")
    p = con.execute("SELECT * FROM projeto_incentivado WHERE conta_id=?", (cid,)).fetchone()
    p = dict(p) if p else {"conta_id": cid, "pronac": "", "titulo": ""}
    p.update({"nome": c["nome"], "ativa": bool(c["ativa"]), "banco": c["banco"] or ""})
    return p


def _itens_rows(con, cid: int) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT * FROM orcamento_item WHERE conta_id=? ORDER BY ordem, item", (cid,))]


def rotulo_item(i: dict) -> str:
    return f"{i['item']} · {i['descricao']}" + (f" ({i['municipio']})" if i.get("municipio") and i.get("municipio") != "São Paulo" else "")


def item_existe(con, cid: int, item) -> bool:
    return bool(item) and bool(con.execute("SELECT 1 FROM orcamento_item WHERE conta_id=? AND item=?", (cid, item)).fetchone())


def _notas_rows(con, cid: int) -> list[dict]:
    out = []
    for r in con.execute("SELECT * FROM nota_camp WHERE conta_id=? ORDER BY competencia DESC, id DESC", (cid,)):
        d = dict(r)
        try:
            d["itens"] = [x for x in json.loads(d["itens"] or "[]") if isinstance(x, dict)]
        except ValueError:
            d["itens"] = []
        out.append(d)
    return out


def despesas_de_notas(con) -> set[int]:
    """Débitos na conta do projeto que pagam notas da CAMP (contam pelo valor da nota, item a item)."""
    return {r[0] for r in con.execute("SELECT despesa_id FROM nota_camp WHERE situacao='paga' AND despesa_id IS NOT NULL")}


def gasto_por_item(con, cid: int) -> dict[int, dict]:
    """item → {valor, n}: despesas da conta ligadas ao item (fora as que pagam nota da CAMP) + as notas da CAMP pagas (valor de cada item)."""
    ligadas = despesas_de_notas(con)
    out: dict[int, dict] = {}
    for r in con.execute("SELECT id, valor, orcamento_item FROM despesa WHERE conta_id=? AND apagado_em IS NULL AND tipo='despesa' AND orcamento_item IS NOT NULL", (cid,)):
        if r["id"] in ligadas:
            continue
        g = out.setdefault(r["orcamento_item"], {"valor": 0.0, "n": 0})
        g["valor"] += r["valor"]
        g["n"] += 1
    for n in _notas_rows(con, cid):
        if n["situacao"] != "paga":
            continue
        for x in n["itens"]:
            g = out.setdefault(int(x.get("item") or 0), {"valor": 0.0, "n": 0})
            g["valor"] += float(x.get("valor") or 0)
            g["n"] += 1
    return {k: {"valor": _r2(v["valor"]), "n": v["n"]} for k, v in out.items()}


def abertas_por_item(con, cid: int, excluir: int | None = None) -> dict[int, float]:
    """Notas da CAMP planejadas ou emitidas (ainda não pagas), por item."""
    out: dict[int, float] = {}
    for n in _notas_rows(con, cid):
        if n["situacao"] in ("planejada", "emitida") and n["id"] != excluir:
            for x in n["itens"]:
                out[int(x.get("item") or 0)] = out.get(int(x.get("item") or 0), 0.0) + float(x.get("valor") or 0)
    return {k: _r2(v) for k, v in out.items()}


def _nivel(gasto: float, orcado: float) -> str:
    if gasto > orcado + 0.005:
        return "vermelho"
    if orcado > 0 and gasto >= AMBAR * orcado - 0.005 and gasto > 0:
        return "ambar"
    return "ok"


def _soma(xs: list[dict]) -> dict:
    o, s, g = _r2(sum(x["orcado"] for x in xs)), _r2(sum(x["solicitado"] for x in xs)), _r2(sum(x["gasto"] for x in xs))
    return {"orcado": o, "solicitado": s, "gasto": g, "saldo": _r2(o - g), "pct": round(g / o, 4) if o else (1.0 if g else 0.0), "nivel": _nivel(g, o)}


def orcamento(con, cid: int) -> dict:
    p = _projeto(con, cid)
    gasto = gasto_por_item(con, cid)
    abertas = abertas_por_item(con, cid)
    itens = []
    for r in _itens_rows(con, cid):
        g = gasto.get(r["item"], {"valor": 0.0, "n": 0})
        orc = _r2(r["valor_aprovado"])
        itens.append({"item": r["item"], "produto": r["produto"], "etapa": r["etapa"], "uf": r["uf"] or "", "municipio": r["municipio"] or "",
                      "descricao": r["descricao"], "unidade": r["unidade"] or "", "dias": r["dias"], "qtde": r["qtde"], "ocorrencias": r["ocorrencias"],
                      "valor_unitario": r["valor_unitario"], "solicitado": _r2(r["valor_solicitado"]), "orcado": orc, "gasto": g["valor"], "n": g["n"],
                      "saldo": _r2(orc - g["valor"]), "pct": round(g["valor"] / orc, 4) if orc else (1.0 if g["valor"] else 0.0),
                      "nivel": _nivel(g["valor"], orc), "em_notas_abertas": abertas.get(r["item"], 0.0),
                      "livre": _r2(orc - g["valor"] - abertas.get(r["item"], 0.0)), "fora_planilha": bool(r["fora_planilha"]),
                      "rotulo": rotulo_item(r)})
    grupos = []
    for it in itens:   # na ordem da planilha: produto → etapa → município
        gp = next((g for g in grupos if g["produto"] == it["produto"]), None)
        if not gp:
            gp = {"produto": it["produto"], "etapas": []}
            grupos.append(gp)
        ge = next((e for e in gp["etapas"] if e["etapa"] == it["etapa"]), None)
        if not ge:
            ge = {"etapa": it["etapa"], "municipios": []}
            gp["etapas"].append(ge)
        gm = next((m for m in ge["municipios"] if m["municipio"] == it["municipio"]), None)
        if not gm:
            gm = {"municipio": it["municipio"], "uf": it["uf"], "itens": []}
            ge["municipios"].append(gm)
        gm["itens"].append(it)
    for gp in grupos:
        tp = []
        for ge in gp["etapas"]:
            te = []
            for gm in ge["municipios"]:
                gm.update(_soma(gm["itens"]))
                te += gm["itens"]
            ge.update(_soma(te))
            tp += te
        gp.update(_soma(tp))
    total = _soma(itens)
    return {"projeto": p, "itens": itens, "grupos": grupos, "total": total, "aprovado_confirmado": bool(p.get("aprovado_em")),
            "banner": "" if p.get("aprovado_em") else AVISO_SOLICITADO, "alertas": _alertas_itens(p, itens, total)}


def _alertas_itens(p: dict, itens: list[dict], total: dict) -> list[dict]:
    br = _fin().brl
    out = []
    for it in itens:
        if it["nivel"] == "vermelho":
            out.append({"tipo": "orcamento", "nivel": "a", "cor": "vermelho", "item": it["item"], "conta_id": p["conta_id"],
                        "titulo": f"Acima do orçamento: item {it['item']} · {it['descricao']} ({br(it['gasto'])} de {br(it['orcado'])})",
                        "motivo": f"passou {br(it['gasto'] - it['orcado'])} do valor {'aprovado' if p.get('aprovado_em') else 'solicitado'} · PRONAC {p.get('pronac') or ''}"})
        elif it["nivel"] == "ambar":
            out.append({"tipo": "orcamento", "nivel": "b", "cor": "ambar", "item": it["item"], "conta_id": p["conta_id"],
                        "titulo": f"Perto do limite: item {it['item']} · {it['descricao']} ({round(it['pct'] * 100)}% usado)",
                        "motivo": f"saldo de {br(it['saldo'])} de {br(it['orcado'])} · PRONAC {p.get('pronac') or ''}"})
    if total["gasto"] > 0:
        out.append({"tipo": "orcamento_total", "nivel": "a" if total["nivel"] == "vermelho" else "b", "cor": total["nivel"], "conta_id": p["conta_id"],
                    "titulo": f"Orçamento do projeto PRONAC {p.get('pronac') or ''}: {str(round(total['pct'] * 100, 1)).replace('.', ',')}% usado",
                    "motivo": f"{br(total['gasto'])} de {br(total['orcado'])}; saldo {br(total['saldo'])}"})
    return out


def alertas(con) -> list[dict]:
    """Para o gancho de alertas do Financeiro: itens com 90% ou mais (âmbar), acima do orçado (vermelho) e o total de cada projeto."""
    out = []
    for p in projetos(con):
        if p["itens"]:
            out += orcamento(con, p["conta_id"])["alertas"]
    return out


def opcoes(con, cid: int) -> list[dict]:
    """Para o seletor "Item do orçamento" (buscável): "16 · Impressão", com o saldo."""
    o = orcamento(con, cid)
    return [{"item": i["item"], "rotulo": i["rotulo"], "saldo": i["saldo"], "orcado": i["orcado"], "produto": i["produto"], "nivel": i["nivel"]} for i in o["itens"]]


def opcoes_todas(con) -> dict[str, list[dict]]:
    return {str(p["conta_id"]): opcoes(con, p["conta_id"]) for p in projetos(con) if p["itens"]}


# ---------------------------------------------------------------- sugestão do item (aprende com a equipe)
def sugerir_item(con, d: dict) -> dict | None:
    cid = d.get("conta_id")
    if not cid or not eh_projeto(con, cid):
        return None
    itens = {r["item"]: r for r in _itens_rows(con, cid)}
    if not itens:
        return None
    from . import financeiro_ia as ia
    ch = ia._chave(d)
    if ch:
        cont: dict[int, int] = {}
        for h in con.execute("SELECT id, contraparte, descricao, orcamento_item FROM despesa WHERE conta_id=? AND apagado_em IS NULL AND orcamento_item IS NOT NULL AND id IS NOT ?",
                             (cid, d.get("id"))):
            if ia._chave(dict(h)) == ch and h["orcamento_item"] in itens:
                cont[h["orcamento_item"]] = cont.get(h["orcamento_item"], 0) + 1
        if cont:
            it, n = max(cont.items(), key=lambda kv: kv[1])
            return {"item": it, "rotulo": rotulo_item(itens[it]), "fonte": "historico", "confianca": round(min(0.95, 0.6 + 0.1 * n), 2),
                    "motivo": f"a equipe escolheu este item {'na última despesa' if n == 1 else f'nas {n} últimas despesas'} com {ia._nome(d)}"}
    txt = sem_acento(" ".join(str(d.get(k) or "") for k in ("contraparte", "descricao", "justificativa")))
    for p, alvo in PALAVRAS_ITEM:
        if p in txt:
            cand = [i for i in itens.values() if alvo in sem_acento(i["descricao"])]
            if cand:
                i = cand[0]
                return {"item": i["item"], "rotulo": rotulo_item(i), "fonte": "palavra", "confianca": 0.6, "motivo": f"a descrição tem “{p}”"}
    return None


# ---------------------------------------------------------------- receita da CAMP e transferência interna
def receitas_livro(con) -> tuple[set[str], list[dict]]:
    """Notas pagas → linhas de receita da CAMP para o livro do Financeiro ("Serviços prestados ao projeto incentivado"). Devolve também os
    pagamentos do Mercado Pago que são esse crédito (para não virarem "Recebido direto no Mercado Pago")."""
    fi = _fin()
    try:
        notas = [dict(r) for r in con.execute("SELECT * FROM nota_camp WHERE situacao='paga'")]
    except Exception:  # noqa: BLE001 (banco sem a migração 254)
        return set(), []
    contas = {c["id"]: c for c in fi.contas(con)}
    padrao = int(_cfg(con, "financeiro.projeto_conta_camp", "1") or 1)
    mp_ids, out = set(), []
    for n in notas:
        mpr = con.execute("SELECT * FROM mp_pagamento WHERE mp_id=?", (n["receita_mp"],)).fetchone() if n["receita_mp"] else None
        cid = n["receita_conta"] or (fi.CONTA_MP if mpr else padrao)
        data = (fi.dia_sp(mpr["aprovado_em"]) if mpr else "") or n["pago_em"] or ""
        tarifa = _r2(mpr["tarifa"]) if mpr and mpr["tarifa"] is not None else (None if mpr else 0.0)
        if mpr:
            mp_ids.add(n["receita_mp"])
        p = con.execute("SELECT pronac FROM projeto_incentivado WHERE conta_id=?", (n["conta_id"],)).fetchone()
        out.append({"id": f"nota_camp:{n['id']}", "conta_id": cid, "conta_nome": contas.get(cid, {}).get("nome", ""), "natureza": NATUREZA, "natureza_nome": NOME_RECEITA,
                    "origem": "nota_projeto", "origem_nome": fi.ORIGENS.get("nota_projeto", "Nota da CAMP para o projeto incentivado"),
                    "descricao": f"Nota da CAMP nº {n['nf_numero'] or ''} · PRONAC {p[0] if p else ''} · competência {_mes_br(n['competencia'])}",
                    "pagador": f"Projeto PRONAC {p[0] if p else ''}", "meio": "transferência", "external_reference": f"CAMP-NOTA-{n['id']}", "mp_id": n["receita_mp"] or "",
                    "fonte": "nota_camp", "registro": n["id"], "fora_mp": not mpr, "sem_par_painel": False, "classificavel": False, "classificado": False, "nota": "",
                    "data": data, "bruto": _r2(n["valor"]), "tarifa": tarifa, "liquido": _r2(n["valor"] - (tarifa or 0)) if tarifa is not None else None,
                    "tarifa_conferir": tarifa is None, "situacao": "confirmado", "estorno": False, "interna": True,
                    "observacao": "transferência interna do projeto para a CAMP (fora do Consolidado)"})
    return mp_ids, out


def eliminar_internas(con, rec: list[dict], desp: list[dict]) -> tuple[list[dict], list[dict], float]:
    """Consolidado: tira a receita da CAMP (notas pagas) e o débito do projeto que a pagou. Devolve o valor tirado (de cada lado)."""
    ids = despesas_de_notas(con)
    r2 = [x for x in rec if x.get("natureza") != NATUREZA]
    d2 = [x for x in desp if x["id"] not in ids]
    return r2, d2, _r2(sum(x["bruto"] for x in rec if x.get("natureza") == NATUREZA))


# ---------------------------------------------------------------- notas da CAMP
def _dados_camp(con) -> dict:
    return {k: next((_cfg(con, ch) for ch in chaves if _cfg(con, ch)), "") for k, chaves in CHAVES_CAMP.items()}


def descricao_padrao(con, cid: int, itens: list[dict], competencia: str) -> str:
    p = _projeto(con, cid)
    nomes = {r["item"]: r["descricao"] for r in _itens_rows(con, cid)}
    its = ", ".join(f"item {int(x['item'])} ({nomes.get(int(x['item']), '')})" for x in itens)
    return f"Projeto PRONAC {p.get('pronac') or ''} · {p.get('titulo') or ''} · {its} · competência {_mes_br(competencia)}"


def _nota_out(con, n: dict, nomes: dict | None = None) -> dict:
    nomes = nomes if nomes is not None else {r["item"]: r["descricao"] for r in _itens_rows(con, n["conta_id"])}
    d = {k: n[k] for k in ("id", "conta_id", "competencia", "descricao", "valor", "situacao", "nf_numero", "nf_data", "nf_nome", "despesa_id", "receita_mp",
                           "receita_conta", "pago_em", "motivo", "criado_por", "criado_em")}
    d["itens"] = [{"item": int(x.get("item") or 0), "valor": _r2(x.get("valor")), "descricao": nomes.get(int(x.get("item") or 0), ""),
                   "rotulo": f"{int(x.get('item') or 0)} · {nomes.get(int(x.get('item') or 0), '')}"} for x in n["itens"]]
    d["tem_pdf"] = bool(n.get("nf_arquivo"))
    if n.get("despesa_id"):
        r = con.execute("SELECT data, valor, contraparte FROM despesa WHERE id=?", (n["despesa_id"],)).fetchone()
        d["debito"] = dict(r) if r else None
    return d


def notas(con, cid: int) -> list[dict]:
    nomes = {r["item"]: r["descricao"] for r in _itens_rows(con, cid)}
    return [_nota_out(con, n, nomes) for n in _notas_rows(con, cid)]


def _nota(con, nid: int) -> dict:
    r = con.execute("SELECT * FROM nota_camp WHERE id=?", (nid,)).fetchone()
    if not r:
        raise HTTPException(404, "Nota não encontrada")
    d = dict(r)
    try:
        d["itens"] = [x for x in json.loads(d["itens"] or "[]") if isinstance(x, dict)]
    except ValueError:
        d["itens"] = []
    return d


def plano(con, cid: int) -> dict[int, dict[str, float]]:
    out: dict[int, dict[str, float]] = {}
    for r in con.execute("SELECT item, mes, valor FROM orcamento_plano WHERE conta_id=? ORDER BY item, mes", (cid,)):
        out.setdefault(r["item"], {})[r["mes"]] = _r2(r["valor"])
    return out


def sugerir_plano(con, cid: int, item: int, meses: list[str]) -> dict:
    """Valor por mês: o saldo livre do item (orçado − gasto − notas abertas) dividido pelos meses; o último mês leva os centavos."""
    o = {i["item"]: i for i in orcamento(con, cid)["itens"]}
    if item not in o:
        raise HTTPException(400, "Item do orçamento desconhecido")
    meses = sorted({_mes_ok(m) for m in meses})
    if not meses:
        raise HTTPException(400, "Escolha os meses")
    livre = max(0.0, o[item]["livre"])
    centavos = int(round(livre * 100))
    por_c = centavos // len(meses)
    por = por_c / 100
    valores = {m: por for m in meses}
    valores[meses[-1]] = (centavos - por_c * (len(meses) - 1)) / 100
    return {"item": item, "livre": _r2(livre), "valor_mes": por, "valores": valores,
            "motivo": f"saldo livre de {_fin().brl(livre)} em {len(meses)} {'mês' if len(meses) == 1 else 'meses'}"}


def preparar_mes(con, cid: int, mes: str) -> dict:
    """Rascunho da nota do mês pelo plano: cada item planejado no mês, menos o que já está em nota (não cancelada) dessa competência."""
    _mes_ok(mes)
    p = _projeto(con, cid)
    o = {i["item"]: i for i in orcamento(con, cid)["itens"]}
    ja: dict[int, float] = {}
    for n in _notas_rows(con, cid):
        if n["competencia"] == mes and n["situacao"] != "cancelada":
            for x in n["itens"]:
                ja[int(x.get("item") or 0)] = ja.get(int(x.get("item") or 0), 0.0) + float(x.get("valor") or 0)
    linhas, avisos = [], []
    for item, meses in sorted(plano(con, cid).items()):
        if mes not in meses or item not in o:
            continue
        v = _r2(meses[mes] - ja.get(item, 0.0))
        lin = {"item": item, "descricao": o[item]["descricao"], "rotulo": o[item]["rotulo"], "planejado": meses[mes], "ja_em_nota": _r2(ja.get(item, 0.0)),
               "valor": max(0.0, v), "livre": o[item]["livre"]}
        if lin["valor"] > 0 and lin["valor"] > o[item]["livre"] + 0.005:
            avisos.append(f"Item {item} · {o[item]['descricao']}: o valor do mês passa do saldo livre do item ({_fin().brl(o[item]['livre'])}).")
        linhas.append(lin)
    devidas = [x for x in linhas if x["valor"] > 0]
    total = _r2(sum(x["valor"] for x in devidas))
    desc = descricao_padrao(con, cid, devidas, mes) if devidas else ""
    camp = _dados_camp(con)
    faltam = [n for k, n in (("razao_social", "razão social da CAMP"), ("cnpj", "CNPJ da CAMP"), ("im", "inscrição municipal da CAMP")) if not camp[k]]
    faltam += [n for k, n in (("tomador_nome", "nome do tomador"), ("tomador_doc", "CNPJ do tomador")) if not p.get(k)]
    br = _fin().brl
    pr = lambda v: v or "(preencher)"   # noqa: E731
    servico, iss = _cfg(con, "financeiro.nfse_servico"), _cfg(con, "financeiro.nfse_iss")
    texto = "\n".join([
        "NOTA FISCAL DE SERVIÇOS ELETRÔNICA (NFS-e) · dados para copiar no sistema da prefeitura",
        f"Prestador: {pr(camp['razao_social'])}",
        f"CNPJ do prestador: {pr(camp['cnpj'])}",
        f"Inscrição municipal: {pr(camp['im'])}",
        f"Endereço do prestador: {pr(camp['endereco'])}",
        f"Tomador: {pr(p.get('tomador_nome'))}",
        f"CNPJ do tomador: {pr(p.get('tomador_doc'))}",
        f"Endereço do tomador: {pr(p.get('tomador_endereco'))}",
        f"E-mail do tomador: {pr(p.get('tomador_email'))}",
        f"Competência: {_mes_br(mes)}",
        f"Código do serviço: {pr(servico)}",
        f"Alíquota do ISS: {pr(iss + '%' if iss else '')}",
        "Discriminação do serviço:",
        desc or "(nada planejado para este mês)",
        "Itens do orçamento cobrados:",
        *[f"  item {x['item']} · {x['descricao']}: {br(x['valor'])}" for x in devidas],
        f"Valor total dos serviços: {br(total)}",
        f"Observação: Projeto PRONAC {p.get('pronac') or ''} (Lei Rouanet). Pagamento pela conta do projeto.",
    ])
    return {"mes": mes, "linhas": linhas, "devidas": devidas, "total": total, "descricao": desc, "texto": texto, "faltam": faltam, "avisos": avisos,
            "aviso_lei": AVISO_LEI, "aviso_nfse": AVISO_NFSE}


def criar_nota(con, cid: int, competencia: str, itens: list[dict], descricao: str, ator: str) -> dict:
    _projeto(con, cid)
    _mes_ok(competencia)
    limpos, avisos = [], []
    o = {i["item"]: i for i in orcamento(con, cid)["itens"]}
    for x in itens or []:
        try:
            it, v = int(x.get("item")), _r2(x.get("valor"))
        except (TypeError, ValueError):
            raise HTTPException(400, "Item ou valor inválido")
        if it not in o:
            raise HTTPException(400, f"Item {it} não está no orçamento deste projeto")
        if v <= 0:
            continue
        if v > o[it]["livre"] + 0.005:
            avisos.append(f"Item {it}: passa do saldo livre ({_fin().brl(o[it]['livre'])}).")
        limpos.append({"item": it, "valor": v})
    if not limpos:
        raise HTTPException(400, "A nota precisa de pelo menos um item com valor")
    desc = _txt(descricao, 1000) or descricao_padrao(con, cid, limpos, competencia)
    total = _r2(sum(x["valor"] for x in limpos))
    nid = con.execute("INSERT INTO nota_camp (conta_id, competencia, itens, descricao, valor, criado_por) VALUES (?,?,?,?,?,?)",
                      (cid, competencia, json.dumps(limpos), desc, total, ator)).lastrowid
    _ev(con, nid, "planejada", ator, {"valor": total, "competencia": competencia, "itens": limpos}, "nota_camp")
    con.commit()
    return dict(_nota_out(con, _nota(con, nid)), avisos=avisos)


def candidatos(con, nid: int) -> dict:
    """O débito na conta do projeto e o crédito na conta da CAMP (Mercado Pago) com o mesmo valor, perto da data da nota."""
    n = _nota(con, nid)
    ref = date.fromisoformat(n["nf_data"]) if n.get("nf_data") else None
    usados = {r[0] for r in con.execute("SELECT despesa_id FROM nota_camp WHERE despesa_id IS NOT NULL AND id!=? AND situacao!='cancelada'", (nid,))}
    deb = []
    for r in con.execute("SELECT id, data, valor, contraparte, descricao, origem FROM despesa WHERE conta_id=? AND apagado_em IS NULL AND tipo='despesa' "
                         "AND abs(valor-?)<=0.01 ORDER BY data", (n["conta_id"], n["valor"])):
        if r["id"] in usados:
            continue
        dist = abs((date.fromisoformat(r["data"]) - ref).days) if ref else 0
        if ref and date.fromisoformat(r["data"]) < ref - timedelta(days=5):
            continue
        deb.append(dict(r, dias=dist, motivo=f"mesmo valor{', ' + str(dist) + ' dia(s) depois da nota' if ref else ''}"))
    usados_mp = {r[0] for r in con.execute("SELECT receita_mp FROM nota_camp WHERE receita_mp IS NOT NULL AND id!=? AND situacao!='cancelada'", (nid,))}
    cre = []
    for r in con.execute("SELECT mp_id, aprovado_em, valor, pagador, descricao FROM mp_pagamento WHERE abs(valor-?)<=0.01 AND COALESCE(direcao,'')<>'saida' ORDER BY aprovado_em", (n["valor"],)):   # saída (paga pela CAMP) não é crédito
        d = _fin().dia_sp(r["aprovado_em"])
        if r["mp_id"] in usados_mp or (ref and d and not (ref - timedelta(days=5) <= date.fromisoformat(d) <= ref + timedelta(days=90))):
            continue
        cre.append({"mp_id": r["mp_id"], "data": d, "valor": r["valor"], "pagador": r["pagador"] or "", "motivo": "mesmo valor no Mercado Pago"})
    deb.sort(key=lambda x: x["dias"])
    return {"debitos": deb, "creditos": cre}


# ---------------------------------------------------------------- importar a planilha (simular antes)
def _num_br(s) -> float:
    t = str(s or "").strip().replace("R$", "").replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return round(float(t or 0), 2)
    except ValueError:
        raise HTTPException(400, f"Valor inválido na planilha: {s}")


def ler_csv(texto: str) -> list[dict]:
    texto = texto.lstrip("﻿")
    linhas = list(csv.DictReader(io.StringIO(texto), delimiter=";"))
    if not linhas or "item" not in (linhas[0].keys()) or not ({"valor_solicitado", "valor_aprovado"} & set(linhas[0].keys())):
        raise HTTPException(400, "Planilha fora do formato: separador ; e as colunas " + "; ".join(COLUNAS_CSV))
    out = []
    for r in linhas:
        if not str(r.get("item") or "").strip():
            continue
        try:
            it = int(str(r["item"]).strip())
        except ValueError:
            raise HTTPException(400, f"Item inválido na planilha: {r.get('item')}")
        valor = _num_br(r.get("valor_aprovado") if r.get("valor_aprovado") not in (None, "") else r.get("valor_solicitado"))
        out.append({"item": it, "produto": _txt(r.get("produto"), 160), "etapa": _txt(r.get("etapa"), 160), "uf": _txt(r.get("uf"), 4),
                    "municipio": _txt(r.get("municipio"), 120), "descricao": _txt(r.get("descricao"), 300), "unidade": _txt(r.get("unidade"), 40),
                    "dias": _num_br(r.get("dias")), "qtde": _num_br(r.get("qtde")), "ocorrencias": _num_br(r.get("ocorrencias")),
                    "valor_unitario": _num_br(r.get("valor_unitario")), "valor": valor})
    if len({x["item"] for x in out}) != len(out):
        raise HTTPException(400, "A planilha tem o mesmo item mais de uma vez")
    return out


def importar(con, cid: int, texto: str, aplicar: bool, confirmar: bool, ator: str) -> dict:
    _projeto(con, cid)
    novos = ler_csv(texto)
    atuais = {r["item"]: r for r in _itens_rows(con, cid)}
    gasto = gasto_por_item(con, cid)
    linhas = []
    for i, x in enumerate(novos, 1):
        a = atuais.get(x["item"])
        if not a:
            linhas.append({"item": x["item"], "descricao": x["descricao"], "situacao": "novo", "antes": None, "depois": x["valor"]})
        elif abs((a["valor_aprovado"] or 0) - x["valor"]) > 0.005 or a["descricao"] != x["descricao"] or a["fora_planilha"]:
            linhas.append({"item": x["item"], "descricao": x["descricao"], "situacao": "muda", "antes": _r2(a["valor_aprovado"]), "depois": x["valor"]})
        else:
            linhas.append({"item": x["item"], "descricao": x["descricao"], "situacao": "igual", "antes": _r2(a["valor_aprovado"]), "depois": x["valor"]})
    no_csv = {x["item"] for x in novos}
    for it, a in atuais.items():
        if it not in no_csv and not a["fora_planilha"]:
            linhas.append({"item": it, "descricao": a["descricao"], "situacao": "sai", "antes": _r2(a["valor_aprovado"]), "depois": 0.0,
                           "gasto": gasto.get(it, {}).get("valor", 0.0)})
    resumo = {k: sum(1 for x in linhas if x["situacao"] == k) for k in ("novo", "muda", "igual", "sai")}
    total_antes = _r2(sum((a["valor_aprovado"] or 0) for a in atuais.values()))
    total_depois = _r2(sum(x["valor"] for x in novos))
    if aplicar:
        for i, x in enumerate(novos, 1):
            if x["item"] in atuais:
                con.execute("""UPDATE orcamento_item SET produto=?, etapa=?, uf=?, municipio=?, descricao=?, unidade=?, dias=?, qtde=?, ocorrencias=?, valor_unitario=?,
                               valor_aprovado=?, ordem=?, fora_planilha=0, alterado_por=?, alterado_em=datetime('now') WHERE conta_id=? AND item=?""",
                            (x["produto"], x["etapa"], x["uf"], x["municipio"], x["descricao"], x["unidade"], x["dias"], x["qtde"], x["ocorrencias"],
                             x["valor_unitario"], x["valor"], i, ator, cid, x["item"]))
            else:
                con.execute("""INSERT INTO orcamento_item (conta_id, item, produto, etapa, uf, municipio, descricao, unidade, dias, qtde, ocorrencias, valor_unitario,
                               valor_solicitado, valor_aprovado, ordem, alterado_por, alterado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,datetime('now'))""",
                            (cid, x["item"], x["produto"], x["etapa"], x["uf"], x["municipio"], x["descricao"], x["unidade"], x["dias"], x["qtde"],
                             x["ocorrencias"], x["valor_unitario"], x["valor"], i, ator))
        for x in linhas:
            if x["situacao"] == "sai":
                con.execute("UPDATE orcamento_item SET valor_aprovado=0, fora_planilha=1, alterado_por=?, alterado_em=datetime('now') WHERE conta_id=? AND item=?",
                            (ator, cid, x["item"]))
        if confirmar:
            con.execute("UPDATE projeto_incentivado SET aprovado_em=datetime('now'), aprovado_por=? WHERE conta_id=?", (ator, cid))
        _ev(con, cid, "planilha_importada", ator, dict(resumo, total_antes=total_antes, total_depois=total_depois, confirmar=confirmar))
        con.commit()
    return {"ok": True, "simulado": not aplicar, "linhas": linhas, "resumo": resumo, "total_antes": total_antes, "total_depois": total_depois,
            "aviso": "Itens que saem da planilha ficam com orçamento zerado; as despesas deles não são apagadas."}


# ---------------------------------------------------------------- prestação de contas
def _despesas_item(con, cid: int) -> list[dict]:
    ligadas = despesas_de_notas(con)
    out = []
    for x in _desp().listar(con, "2000-01-01", "2100-12-31", cid):
        if x["id"] in ligadas:
            continue
        out.append(x)
    return out


def prestacao_xlsx(con, cid: int) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    seg = _fin()._seguro
    o = orcamento(con, cid)
    p = o["projeto"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Orçado × gasto"
    ws.append([f"CAMP — Prestação de contas · Projeto PRONAC {p.get('pronac') or ''} · {p.get('titulo') or ''}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([("Valores aprovados" if o["aprovado_confirmado"] else "Valores SOLICITADOS (atualize com a planilha aprovada)") + f" · gerado em {_fin().hoje().strftime('%d/%m/%Y')}"])
    ws.append([])
    ws.append(["Item", "Produto", "Etapa", "Município", "Descrição", "Unidade", "Qtde", "Ocorrências", "Valor unitário (R$)", "Solicitado (R$)",
               "Orçado/aprovado (R$)", "Gasto (R$)", "Saldo (R$)", "% usado"])
    for i in o["itens"]:
        ws.append([i["item"], i["produto"], i["etapa"], i["municipio"], i["descricao"], i["unidade"], i["qtde"], i["ocorrencias"], i["valor_unitario"],
                   i["solicitado"], i["orcado"], i["gasto"], i["saldo"], round(i["pct"] * 100, 1)])
    t = o["total"]
    ws.append(["Total", "", "", "", "", "", "", "", "", t["solicitado"], t["orcado"], t["gasto"], t["saldo"], round(t["pct"] * 100, 1)])
    ws.append([])
    ws.append(["Por produto", "", "", "", "", "", "", "", "", "Solicitado (R$)", "Orçado/aprovado (R$)", "Gasto (R$)", "Saldo (R$)", "% usado"])
    for g in o["grupos"]:
        ws.append([g["produto"], "", "", "", "", "", "", "", "", g["solicitado"], g["orcado"], g["gasto"], g["saldo"], round(g["pct"] * 100, 1)])
    s2 = wb.create_sheet("Despesas por item")
    s2.append(["Item", "Descrição do item", "Data", "Fornecedor", "Nº da nota fiscal", "Valor (R$)", "Justificativa", "Comprovantes", "Origem"])
    nomes = {i["item"]: i["descricao"] for i in o["itens"]}
    for x in sorted(_despesas_item(con, cid), key=lambda x: (x.get("orcamento_item") or 9999, x["data"])):
        s2.append([seg(v) for v in (x.get("orcamento_item") or "sem item", nomes.get(x.get("orcamento_item"), ""), _fin()._dbr(x["data"]), x["contraparte"],
                                    x.get("nf_numero") or "", x["valor"], x["justificativa"], ", ".join(a["nome"] for a in x["anexos"]), "despesa")])
    for n in notas(con, cid):
        if n["situacao"] == "paga":
            for it in n["itens"]:
                s2.append([seg(v) for v in (it["item"], it["descricao"], _fin()._dbr(n["pago_em"] or ""), "CAMP (nota da proponente)", n["nf_numero"] or "",
                                            it["valor"], n["descricao"], n["nf_nome"] or "", "nota da CAMP")])
    s3 = wb.create_sheet("Notas da CAMP")
    s3.append(["Competência", "Nº da nota", "Data da nota", "Itens", "Valor (R$)", "Situação", "Pago em", "Descrição"])
    for n in notas(con, cid):
        s3.append([seg(v) for v in (_mes_br(n["competencia"]), n["nf_numero"] or "", _fin()._dbr(n["nf_data"] or ""),
                                    "; ".join(f"{i['rotulo']}: {_fin().brl(i['valor'])}" for i in n["itens"]), n["valor"], n["situacao"],
                                    _fin()._dbr(n["pago_em"] or ""), n["descricao"])])
    s3.append([])
    s3.append([AVISO_LEI])
    for sh in wb.worksheets:
        for row in sh.iter_rows():
            for c in row:
                if isinstance(c.value, float):
                    c.number_format = "#,##0.00"
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _pasta_item(i: int, desc: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", sem_acento(desc)).strip("-")[:40]
    return f"item-{i:02d}-{s}"


def prestacao_zip(con, cid: int) -> bytes:
    nomes = {r["item"]: r["descricao"] for r in _itens_rows(con, cid)}
    b = io.BytesIO()
    base = _desp().pasta().resolve()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("prestacao-de-contas.xlsx", prestacao_xlsx(con, cid))
        for x in _despesas_item(con, cid):
            it = x.get("orcamento_item")
            pasta = _pasta_item(it, nomes.get(it, "")) if it else "sem-item"
            for a in x["anexos"]:
                r = con.execute("SELECT arquivo FROM despesa_anexo WHERE id=?", (a["id"],)).fetchone()
                f = (base / (r[0] if r else "")).resolve()
                if r and r[0] and base in f.parents and f.is_file():
                    z.write(f, f"{pasta}/{x['data']}_despesa{x['id']}_nf{re.sub(r'[^0-9A-Za-z]', '', x.get('nf_numero') or '') or 'sem-numero'}_{a['nome']}")
        pn = pasta_notas().resolve()
        for n in _notas_rows(con, cid):
            if n["situacao"] in ("emitida", "paga") and n["nf_arquivo"]:
                f = (pn / n["nf_arquivo"]).resolve()
                if pn in f.parents and f.is_file():
                    z.write(f, f"notas-da-camp/{n['competencia']}_nf{re.sub(r'[^0-9A-Za-z]', '', n['nf_numero'] or '') or n['id']}_{n['nf_nome'] or 'nota.pdf'}")
    return b.getvalue()


# ---------------------------------------------------------------- rotas (só admin e master)
@router.get("")
def ver_projetos(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return {"projetos": projetos(con), "aviso_lei": AVISO_LEI}
    finally:
        con.close()


@router.get("/{cid}")
def ver(cid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        o = orcamento(con, cid)
        pl = plano(con, cid)
        o.update({"notas": notas(con, cid), "plano": [{"item": it, "meses": ms, "total": _r2(sum(ms.values()))} for it, ms in sorted(pl.items())],
                  "aviso_lei": AVISO_LEI, "aviso_interna": AVISO_INTERNA, "aviso_nfse": AVISO_NFSE, "dados_camp": _dados_camp(con),
                  "mes_atual": _fin().hoje().strftime("%Y-%m")})
        return o
    finally:
        con.close()


class Projeto(BaseModel):
    inicio: str | None = None
    fim: str | None = None
    tomador_nome: str | None = None
    tomador_doc: str | None = None
    tomador_endereco: str | None = None
    tomador_email: str | None = None


@router.put("/{cid}")
def mudar_projeto(cid: int, b: Projeto, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        _projeto(con, cid)
        v = {}
        for k in ("inicio", "fim"):
            if getattr(b, k) is not None:
                v[k] = _mes_ok(getattr(b, k)) if getattr(b, k) else None
        for k, n in (("tomador_nome", 200), ("tomador_doc", 30), ("tomador_endereco", 300), ("tomador_email", 160)):
            if getattr(b, k) is not None:
                v[k] = _txt(getattr(b, k), n) or None
        con.execute("INSERT OR IGNORE INTO projeto_incentivado (conta_id) VALUES (?)", (cid,))
        if v:
            con.execute(f"UPDATE projeto_incentivado SET {', '.join(k + '=?' for k in v)}, alterado_por=?, alterado_em=datetime('now') WHERE conta_id=?",
                        (*v.values(), _ator(u), cid))
            _ev(con, cid, "dados_alterados", _ator(u), {k: v[k] for k in v if not k.startswith("tomador_doc")})
        con.commit()
        return _projeto(con, cid)
    finally:
        con.close()


class Aprovado(BaseModel):
    valor_aprovado: float


@router.put("/{cid}/itens/{item}")
def mudar_aprovado(cid: int, item: int, b: Aprovado, u: dict = Depends(auth.exige("admin"))) -> dict:
    if not 0 <= b.valor_aprovado <= 100_000_000:
        raise HTTPException(400, "Valor inválido")
    con = connect()
    try:
        _projeto(con, cid)
        r = con.execute("SELECT valor_aprovado FROM orcamento_item WHERE conta_id=? AND item=?", (cid, item)).fetchone()
        if not r:
            raise HTTPException(404, "Item do orçamento não encontrado")
        con.execute("UPDATE orcamento_item SET valor_aprovado=?, alterado_por=?, alterado_em=datetime('now') WHERE conta_id=? AND item=?",
                    (_r2(b.valor_aprovado), _ator(u), cid, item))
        _ev(con, cid, "aprovado_alterado", _ator(u), {"item": item, "antes": r[0], "depois": _r2(b.valor_aprovado)})
        con.commit()
        return orcamento(con, cid)
    finally:
        con.close()


@router.post("/{cid}/aprovado/confirmar")
def confirmar_aprovado(cid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        _projeto(con, cid)
        con.execute("INSERT OR IGNORE INTO projeto_incentivado (conta_id) VALUES (?)", (cid,))
        con.execute("UPDATE projeto_incentivado SET aprovado_em=datetime('now'), aprovado_por=? WHERE conta_id=?", (_ator(u), cid))
        _ev(con, cid, "aprovado_confirmado", _ator(u))
        con.commit()
        return orcamento(con, cid)
    finally:
        con.close()


@router.post("/{cid}/importar")
def importar_rota(cid: int, b: dict, u: dict = Depends(auth.exige("admin"))) -> dict:
    """{base64 do .csv (ou texto), aplicar: false, confirmar: false} → simulação; com aplicar: true grava (e confirma, se pedido)."""
    texto = b.get("texto")
    if not texto:
        try:
            dados = base64.b64decode(re.sub(r"^data:[^,]*,", "", str(b.get("base64") or "")).strip(), validate=True)
        except (binascii.Error, ValueError) as e:
            raise HTTPException(400, "O arquivo chegou incompleto: escolha de novo.") from e
        if len(dados) > 2 * 1024 * 1024:
            raise HTTPException(400, "Planilha grande demais (até 2 MB)")
        try:
            texto = dados.decode("utf-8")
        except UnicodeDecodeError:
            texto = dados.decode("latin-1")
    con = connect()
    try:
        return importar(con, cid, str(texto), bool(b.get("aplicar")), bool(b.get("confirmar")), _ator(u))
    finally:
        con.close()


class Plano(BaseModel):
    item: int
    meses: list[str]
    valor_mes: float | None = None       # vazio = o painel divide o saldo livre pelos meses


@router.get("/{cid}/plano/sugestao")
def plano_sugestao(cid: int, item: int, meses: str = "", u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        ms = [m for m in meses.split(",") if m.strip()]
        if not ms:
            p = _projeto(con, cid)
            if p.get("inicio") and p.get("fim"):
                ms = _meses_entre(p["inicio"], p["fim"])
        return sugerir_plano(con, cid, item, ms)
    finally:
        con.close()


@router.put("/{cid}/plano")
def definir_plano(cid: int, b: Plano, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        _projeto(con, cid)
        if not item_existe(con, cid, b.item):
            raise HTTPException(400, "Item do orçamento desconhecido")
        meses = sorted({_mes_ok(m) for m in b.meses})
        if b.valor_mes is None and meses:
            valores = sugerir_plano(con, cid, b.item, meses)["valores"]
        else:
            if b.valor_mes is not None and not 0 <= b.valor_mes <= 10_000_000:
                raise HTTPException(400, "Valor inválido")
            valores = {m: _r2(b.valor_mes) for m in meses}
        con.execute("DELETE FROM orcamento_plano WHERE conta_id=? AND item=?", (cid, b.item))
        for m, v in valores.items():
            con.execute("INSERT INTO orcamento_plano (conta_id, item, mes, valor) VALUES (?,?,?,?)", (cid, b.item, m, v))
        _ev(con, cid, "plano_definido", _ator(u), {"item": b.item, "meses": meses, "total": _r2(sum(valores.values()))})
        con.commit()
        return {"ok": True, "item": b.item, "meses": valores, "total": _r2(sum(valores.values()))}
    finally:
        con.close()


@router.get("/{cid}/preparar")
def preparar(cid: int, mes: str = "", u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return preparar_mes(con, cid, mes or _fin().hoje().strftime("%Y-%m"))
    finally:
        con.close()


class NovaNota(BaseModel):
    competencia: str
    itens: list[dict]
    descricao: str = ""


@router.post("/{cid}/notas")
def nova_nota(cid: int, b: NovaNota, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return criar_nota(con, cid, b.competencia, b.itens, b.descricao, _ator(u))
    finally:
        con.close()


class Emitir(BaseModel):
    nf_numero: str
    nf_data: str
    nome: str = ""
    base64: str = ""


@router.post("/notas/{nid}/emitir")
def emitir(nid: int, b: Emitir, u: dict = Depends(auth.exige("admin"))) -> dict:
    from .doacoes_central import _ext, nome_limpo, tipo_pelos_bytes
    con = connect()
    try:
        n = _nota(con, nid)
        if n["situacao"] not in ("planejada", "emitida"):
            raise HTTPException(409, "Só nota planejada ou emitida pode receber os dados da nota fiscal")
        num = _txt(b.nf_numero, 40)
        if not num:
            raise HTTPException(400, "Informe o número da nota fiscal")
        try:
            dnf = date.fromisoformat(b.nf_data)
        except ValueError:
            raise HTTPException(400, "Data da nota inválida (AAAA-MM-DD)")
        if dnf > _fin().hoje() + timedelta(days=1):
            raise HTTPException(400, "A data da nota não pode ser no futuro")
        if not b.base64 and not n["nf_arquivo"]:
            raise HTTPException(400, "Anexe o PDF da nota fiscal")
        arq, nome = n["nf_arquivo"], n["nf_nome"]
        if b.base64:
            try:
                dados = base64.b64decode(re.sub(r"^data:[^,]*,", "", b.base64).strip(), validate=True)
            except (binascii.Error, ValueError) as e:
                raise HTTPException(400, "O arquivo chegou incompleto: escolha de novo.") from e
            if _ext(b.nome) != "pdf" or not tipo_pelos_bytes(dados, "pdf"):
                raise HTTPException(400, "A nota fiscal deve ser um PDF (o arquivo não bate com o tipo).")
            if len(dados) > 15 * 1024 * 1024:
                raise HTTPException(400, "PDF grande demais (até 15 MB).")
            nome = nome_limpo(b.nome, "pdf")
            (pasta_notas() / str(nid)).mkdir(parents=True, exist_ok=True)
            arq = f"{nid}/{secrets.token_hex(4)}_{hashlib.sha256(dados).hexdigest()[:8]}.pdf"
            (pasta_notas() / arq).write_bytes(dados)
        con.execute("UPDATE nota_camp SET situacao='emitida', nf_numero=?, nf_data=?, nf_nome=?, nf_arquivo=?, alterado_por=?, alterado_em=datetime('now') WHERE id=?",
                    (num, dnf.isoformat(), nome, arq, _ator(u), nid))
        _ev(con, nid, "emitida", _ator(u), {"nf_numero": num, "nf_data": dnf.isoformat()}, "nota_camp")
        con.commit()
        return _nota_out(con, _nota(con, nid))
    finally:
        con.close()


@router.get("/notas/{nid}/candidatos")
def ver_candidatos(nid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return candidatos(con, nid)
    finally:
        con.close()


class Pagar(BaseModel):
    despesa_id: int
    receita_mp: str = ""
    receita_conta: int | None = None


@router.post("/notas/{nid}/pagar")
def pagar(nid: int, b: Pagar, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        n = _nota(con, nid)
        if n["situacao"] != "emitida":
            raise HTTPException(409, "Só nota emitida (com número, data e PDF) pode ser marcada como paga")
        d = con.execute("SELECT * FROM despesa WHERE id=? AND apagado_em IS NULL", (b.despesa_id,)).fetchone()
        if not d or d["conta_id"] != n["conta_id"] or d["tipo"] != "despesa":
            raise HTTPException(400, "Escolha o débito na conta do projeto")
        if abs(d["valor"] - n["valor"]) > 0.01:
            raise HTTPException(400, f"O débito ({_fin().brl(d['valor'])}) não tem o valor da nota ({_fin().brl(n['valor'])})")
        if con.execute("SELECT 1 FROM nota_camp WHERE despesa_id=? AND id!=? AND situacao!='cancelada'", (d["id"], nid)).fetchone():
            raise HTTPException(409, "Este débito já paga outra nota da CAMP")
        mp = _txt(b.receita_mp, 60) or None
        if mp:
            r = con.execute("SELECT valor FROM mp_pagamento WHERE mp_id=?", (mp,)).fetchone()
            if not r:
                raise HTTPException(400, "Crédito do Mercado Pago não encontrado")
            if con.execute("SELECT 1 FROM nota_camp WHERE receita_mp=? AND id!=? AND situacao!='cancelada'", (mp, nid)).fetchone():
                raise HTTPException(409, "Este crédito já é de outra nota da CAMP")
        rc = b.receita_conta or (_fin().CONTA_MP if mp else int(_cfg(con, "financeiro.projeto_conta_camp", "1") or 1))
        if not con.execute("SELECT 1 FROM financeiro_conta WHERE id=? AND tipo!='projeto_incentivado'", (rc,)).fetchone():
            raise HTTPException(400, "A conta que recebe precisa ser uma conta da CAMP (não a do projeto)")
        primeiro = int(n["itens"][0]["item"]) if n["itens"] else None
        just = d["justificativa"] or f"Nota da CAMP nº {n['nf_numero']} · competência {_mes_br(n['competencia'])} · {n['descricao']}"
        con.execute("""UPDATE despesa SET orcamento_item=COALESCE(orcamento_item, ?), categoria=COALESCE(categoria, 'servicos'), justificativa=?,
                       nf_numero=COALESCE(nf_numero, ?), contraparte=COALESCE(contraparte, 'CAMP'), alterado_por=?, alterado_em=datetime('now') WHERE id=?""",
                    (primeiro, just[:2000], n["nf_numero"], _ator(u), d["id"]))
        con.execute("UPDATE nota_camp SET situacao='paga', despesa_id=?, receita_mp=?, receita_conta=?, pago_em=?, alterado_por=?, alterado_em=datetime('now') WHERE id=?",
                    (d["id"], mp, rc, d["data"], _ator(u), nid))
        antes = {k: d[k] for k in ("orcamento_item", "categoria", "justificativa", "nf_numero", "contraparte")}
        _ev(con, nid, "paga", _ator(u), {"despesa_id": d["id"], "receita_mp": mp, "receita_conta": rc, "antes": antes}, "nota_camp")
        _desp()._ev(con, d["id"], "nota_camp", _ator(u), {"nota": nid, "nf_numero": n["nf_numero"]})
        con.commit()
        return _nota_out(con, _nota(con, nid))
    finally:
        con.close()


@router.post("/notas/{nid}/desfazer-pagamento")
def desfazer_pagamento(nid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        n = _nota(con, nid)
        if n["situacao"] != "paga":
            raise HTTPException(409, "A nota não está paga")
        ev = con.execute("SELECT detalhe FROM evento WHERE entidade='nota_camp' AND codigo=? AND tipo='paga' ORDER BY id DESC LIMIT 1", (str(nid),)).fetchone()
        antes = (json.loads(ev[0]) if ev and ev[0] else {}).get("antes")
        if antes and n["despesa_id"]:             # o débito volta a ser como era antes de casar com a nota
            con.execute("UPDATE despesa SET orcamento_item=?, categoria=?, justificativa=?, nf_numero=?, contraparte=?, alterado_por=?, alterado_em=datetime('now') WHERE id=?",
                        (antes.get("orcamento_item"), antes.get("categoria"), antes.get("justificativa"), antes.get("nf_numero"), antes.get("contraparte"), _ator(u), n["despesa_id"]))
        con.execute("UPDATE nota_camp SET situacao='emitida', despesa_id=NULL, receita_mp=NULL, receita_conta=NULL, pago_em=NULL, alterado_por=?, alterado_em=datetime('now') WHERE id=?",
                    (_ator(u), nid))
        _ev(con, nid, "pagamento_desfeito", _ator(u), {"despesa_id": n["despesa_id"]}, "nota_camp")
        con.commit()
        return _nota_out(con, _nota(con, nid))
    finally:
        con.close()


class Cancelar(BaseModel):
    motivo: str = ""


@router.post("/notas/{nid}/cancelar")
def cancelar(nid: int, b: Cancelar, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        n = _nota(con, nid)
        if n["situacao"] == "paga":
            raise HTTPException(409, "Nota paga não se cancela: desfaça o pagamento antes")
        motivo = _txt(b.motivo, 300)
        if len(motivo) < 5:
            raise HTTPException(400, "Diga por que cancelar (o motivo fica no histórico)")
        con.execute("UPDATE nota_camp SET situacao='cancelada', motivo=?, alterado_por=?, alterado_em=datetime('now') WHERE id=?", (motivo, _ator(u), nid))
        _ev(con, nid, "cancelada", _ator(u), {"motivo": motivo}, "nota_camp")
        con.commit()
        return _nota_out(con, _nota(con, nid))
    finally:
        con.close()


@router.get("/notas/{nid}/nota.pdf")
def nota_pdf(nid: int, u: dict = Depends(auth.exige("admin"))):
    con = connect()
    try:
        n = _nota(con, nid)
    finally:
        con.close()
    f = (pasta_notas() / (n["nf_arquivo"] or "")).resolve()
    if not n["nf_arquivo"] or pasta_notas().resolve() not in f.parents or not f.is_file():
        raise HTTPException(404, "PDF da nota não encontrado")
    return FileResponse(f, media_type="application/pdf", filename=n["nf_nome"] or "nota.pdf", content_disposition_type="inline")


@router.get("/{cid}/prestacao.xlsx")
def prestacao_xlsx_rota(cid: int, u: dict = Depends(auth.exige("admin"))):
    con = connect()
    try:
        p = _projeto(con, cid)
        b = prestacao_xlsx(con, cid)
    finally:
        con.close()
    return Response(b, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="camp-prestacao-pronac-{p.get("pronac") or cid}.xlsx"'})


@router.get("/{cid}/prestacao.zip")
def prestacao_zip_rota(cid: int, u: dict = Depends(auth.exige("admin"))):
    con = connect()
    try:
        p = _projeto(con, cid)
        b = prestacao_zip(con, cid)
    finally:
        con.close()
    return Response(b, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="camp-prestacao-pronac-{p.get("pronac") or cid}.zip"'})
