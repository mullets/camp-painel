"""Financeiro · Despesas (CAMP-FIN, 24/11/2026). Rafael: "E o que gastamos? Porque já comprei coisas por Pix e débito que seria bom
justificar." e "Só usamos a Mercado Pago!".

- Caminho principal: as SAÍDAS da conta do Mercado Pago, pelo relatório de liberações (`/v1/account/release_report`), pedido e baixado
  PELO SITE (contrato 1.33: a chave fica lá). É assíncrono: o painel pede o relatório de cada mês (desde `financeiro.mp_inicio`, 2026-01-01)
  e, numa volta seguinte do coletor em segundo plano, baixa o que o Mercado Pago já gerou. O mês corrente (e o anterior) é pedido de novo
  uma vez por dia. Cada saída vira uma despesa única pela chave do movimento (SOURCE_ID + descrição + dia + valor).
  · `payout` (Pix enviado/saque) e compra (`payment` com débito: cartão de débito ou saldo) = despesa a justificar;
  · `withdrawal` (retirada para a conta bancária da CAMP) = **transferência própria**, não é despesa;
  · tarifa/imposto avulso = despesa já na categoria Tarifas; estorno, contestação e reserva NÃO são despesa (já estão nas receitas ou
    voltam para a conta).
- Extrato OFX (mínimo; é o que o Banco do Brasil exporta): simular primeiro, depois importar, numa conta escolhida; só débitos; único pelo
  FITID (sem FITID: data + valor + descrição). CSV fica para depois.
- Lançamento à mão (dinheiro, cartão de outra conta).
- Cada despesa: data, valor, meio, contraparte, conta, categoria (lista em `despesas.categorias`), justificativa, comprovante (PDF/JPG/PNG/
  WEBP até 15 MB, tipo conferido pelos primeiros bytes, pasta despesas_comprovantes/ ao lado do banco), vínculo (doação de acervo e uma
  tarefa dela, patrocínio, evento, projeto), com restrição, projeto/rubrica (texto livre).
- "Precisa justificar": importada sem categoria, justificativa ou comprovante. Também na Home (admin), prioridade baixa.
- Só admin e master; histórico (tabela evento, entidade 'despesa') de quem criou, mudou, justificou e apagou (apagar pede motivo).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import logging
import os
import re
import secrets
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from . import auth
from .config import settings
from .db import connect
from .log_tecnico import registrar

router = APIRouter(prefix="/api/financeiro/despesas", tags=["despesas"])

ROTA_REL = "/wp-json/camp/v1/painel/mp/relatorio"
ROTA_RELS = "/wp-json/camp/v1/painel/mp/relatorios"
CATEGORIAS_PADRAO = {"materiais": "Materiais de conservação e acondicionamento", "frete": "Frete e transporte", "servicos": "Serviços de terceiros (PJ)",
                     "pessoal": "Pessoal e estagiários", "tecnologia": "Tecnologia e software", "tarifas": "Tarifas bancárias e do Mercado Pago",
                     "eventos": "Eventos e visitas", "manutencao": "Manutenção do espaço", "impostos": "Impostos e taxas", "outras": "Outras despesas",
                     # CAMP-FIN contas fixas (migração 252): aluguel, consumo e Pessoal em quatro
                     "aluguel": "Aluguel e condomínio", "consumo": "Contas de consumo (luz, água, internet, telefone)", "salarios": "Salários",
                     "encargos": "Encargos (INSS, FGTS, férias, 13º)", "bolsas": "Bolsas e estágio", "autonomos": "Autônomos e RPA"}
# Pessoal: salário é dado sensível. Na exportação, "agrupar pessoal" (padrão ligado) junta estas categorias numa linha por categoria, sem nomes.
PESSOAL = ("salarios", "encargos", "bolsas", "autonomos", "pessoal")
MEIOS = {"pix": "Pix", "debito": "cartão de débito", "credito": "cartão de crédito", "boleto": "boleto", "dinheiro": "dinheiro", "tarifa": "tarifa",
         "saldo": "saldo do Mercado Pago", "transferencia": "transferência", "outro": "outro"}
VINCULOS = {"doacao": "Doação de acervo", "patrocinio": "Patrocínio", "evento": "Evento", "projeto": "Projeto"}
MAX_ANEXO = 15 * 1024 * 1024
EXT_OK = ("pdf", "jpg", "jpeg", "png", "webp")
NAO_DESPESA = ("refund", "chargeback", "dispute", "mediation", "reserve", "cancel")


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def categorias(con) -> dict[str, str]:
    try:
        d = json.loads(_cfg(con, "despesas.categorias", ""))
    except ValueError:
        d = {}
    d = {str(k): str(v) for k, v in (d or {}).items() if str(k).strip() and str(v).strip()} if isinstance(d, dict) else {}
    return d or dict(CATEGORIAS_PADRAO)


def _txt(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:n]


def _num(v) -> float | None:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _ator(u: dict | None) -> str:
    return (u or {}).get("email") or "painel"


def _ev(con, did: int, tipo: str, ator: str, detalhe: dict | None = None) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('despesa',?,?,?,?)",
                (str(did), tipo, ator, json.dumps(detalhe or {}, ensure_ascii=False)))


def _fin():
    from . import financeiro
    return financeiro


def pasta() -> Path:
    p = Path(os.environ.get("CAMP_DESPESAS_DIR") or Path(settings.CAMP_DB_PATH).resolve().parent / "despesas_comprovantes")
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------- leitura
def _anexos(con, did: int) -> list[dict]:
    return [{"id": r["id"], "nome": r["nome"], "mime": r["mime"] or "", "tamanho": r["tamanho"] or 0}
            for r in con.execute("SELECT id, nome, mime, tamanho FROM despesa_anexo WHERE despesa_id=? ORDER BY id", (did,))]


def pendente(r, n_anexos: int) -> list[str]:
    """O que falta numa despesa importada: categoria, justificativa, comprovante (vazio = justificada)."""
    if r["tipo"] != "despesa" or r["apagado_em"] or r["origem"] == "manual":
        return []
    falta = []
    if not r["categoria"]:
        falta.append("categoria")
    if not (r["justificativa"] or "").strip():
        falta.append("justificativa")
    if not n_anexos and r["categoria"] != "tarifas":
        falta.append("comprovante")
    return falta


def _linha(con, r, cats: dict, contas: dict) -> dict:
    ax = _anexos(con, r["id"])
    return {"id": r["id"], "conta_id": r["conta_id"], "conta_nome": contas.get(r["conta_id"], {}).get("nome", ""), "data": r["data"], "valor": r["valor"],
            "meio": r["meio"] or "", "meio_nome": MEIOS.get(r["meio"] or "", r["meio"] or ""), "contraparte": r["contraparte"] or "", "descricao": r["descricao"] or "",
            "origem": r["origem"], "tipo": r["tipo"], "categoria": r["categoria"] or "", "categoria_nome": cats.get(r["categoria"] or "", "") if r["categoria"] else "",
            "justificativa": r["justificativa"] or "", "projeto": r["projeto"] or "", "restrito": bool(r["restrito"]), "vinculo_tipo": r["vinculo_tipo"] or "",
            "vinculo_ref": r["vinculo_ref"] or "", "tarefa_id": r["tarefa_id"], "mp_ref": r["mp_ref"] or "", "anexos": ax, "falta": pendente(r, len(ax)),
            "criado_por": r["criado_por"] or "", "alterado_por": r["alterado_por"] or "", "conta_restrita": bool(contas.get(r["conta_id"], {}).get("restrito")),
            "nota_pedida_em": r["nota_pedida_em"] if "nota_pedida_em" in r.keys() else None}   # CAMP-FIN pedir nota fiscal (notas_fiscais.py)


def listar(con, de: str, ate: str, conta: int = 0, categoria: str = "", so_pendentes: bool = False, q: str = "", com_transferencias: bool = False) -> list[dict]:
    cats = categorias(con)
    contas = {c["id"]: c for c in _fin().contas(con)}
    sql, args = "SELECT * FROM despesa WHERE apagado_em IS NULL AND data BETWEEN ? AND ?", [de, ate]
    if conta:
        sql += " AND conta_id=?"
        args.append(conta)
    if not com_transferencias:
        sql += " AND tipo='despesa'"
    if categoria:
        sql += " AND categoria IS ?" if categoria == "-" else " AND categoria=?"
        args.append(None if categoria == "-" else categoria)
    out = [_linha(con, r, cats, contas) for r in con.execute(sql + " ORDER BY data, id", args)]
    if so_pendentes:
        out = [x for x in out if x["falta"]]
    if q:
        ql = q.lower()
        out = [x for x in out if ql in (x["contraparte"] + " " + x["descricao"] + " " + x["justificativa"]).lower()]
    return out


def pendentes_total(con) -> int:
    n = 0
    for r in con.execute("SELECT d.*, (SELECT COUNT(*) FROM despesa_anexo a WHERE a.despesa_id=d.id) AS nax FROM despesa d WHERE apagado_em IS NULL AND tipo='despesa' AND origem!='manual'"):
        n += 1 if pendente(r, r["nax"]) else 0
    return n


def resumo_periodo(con, de: str, ate: str, conta: int = 0, tot_receitas: dict | None = None) -> dict:
    """Despesas do período por categoria, mês e conta, e o resultado (receitas líquidas − despesas); conta com restrição à parte."""
    cats = categorias(con)
    ls = listar(con, de, ate, conta)
    tr = listar(con, de, ate, conta, com_transferencias=True)
    transf = [x for x in tr if x["tipo"] == "transferencia_propria"]
    tot = round(sum(x["valor"] for x in ls), 2)
    por_cat = []
    for k, v in list(cats.items()) + [("", "Sem categoria (precisa justificar)")]:
        xs = [x for x in ls if x["categoria"] == k]
        if xs or k:
            por_cat.append({"categoria": k, "nome": v, "valor": round(sum(x["valor"] for x in xs), 2), "n": len(xs)})
    meses = sorted({x["data"][:7] for x in ls})
    por_mes = [{"mes": m, "valor": round(sum(x["valor"] for x in ls if x["data"][:7] == m), 2), "n": sum(1 for x in ls if x["data"][:7] == m)} for m in meses]
    rec = (tot_receitas or {}).get("geral") or {}
    rec_liq = rec.get("liquido", 0.0) or 0.0
    contas = _fin().contas(con)
    restritas = {c["id"] for c in contas if c["restrito"]}
    por_conta = []
    for c in contas:
        xs = [x for x in ls if x["conta_id"] == c["id"]]
        rc = next((p for p in (tot_receitas or {}).get("por_conta") or [] if p["conta_id"] == c["id"]), {})
        por_conta.append({"conta_id": c["id"], "nome": c["nome"], "restrito": bool(c["restrito"]), "despesas": round(sum(x["valor"] for x in xs), 2),
                          "receitas_liquidas": rc.get("liquido", 0.0), "resultado": round((rc.get("liquido", 0.0) or 0.0) - sum(x["valor"] for x in xs), 2)})
    oper = [p for p in por_conta if p["conta_id"] not in restritas]
    return {"total": tot, "n": len(ls), "por_categoria": por_cat, "por_mes": por_mes, "por_conta": por_conta, "pendentes": sum(1 for x in ls if x["falta"]),
            "pendentes_total": pendentes_total(con), "transferencias_proprias": {"valor": round(sum(x["valor"] for x in transf), 2), "n": len(transf)},
            "resultado": round(rec_liq - tot, 2), "receitas_liquidas": rec_liq,
            "resultado_operacional": round(sum(p["resultado"] for p in oper), 2) if not conta else None, "categorias": cats}


def frases_rascunho(d: dict | None, tot: dict) -> list[str]:
    if not d:
        return []
    fr = [f"Despesas no período: {_fin().brl(d['total'])} ({d['n']} lançamentos)."]
    cs = [f"{c['nome']}: {_fin().brl(c['valor'])}" for c in d["por_categoria"] if c["valor"]]
    if cs:
        fr.append("Por categoria: " + "; ".join(cs) + ".")
    fr.append(f"Resultado do período (receitas líquidas menos despesas): {_fin().brl(d['resultado'])}.")
    if d["transferencias_proprias"]["n"]:
        fr.append(f"Transferências para conta própria (não são despesa): {_fin().brl(d['transferencias_proprias']['valor'])}.")
    if d["pendentes"]:
        fr.append(f"{d['pendentes']} despesa(s) ainda sem categoria, justificativa ou comprovante.")
    return fr


COLS = ["Data", "Conta", "Categoria", "Contraparte", "Descrição do extrato", "Justificativa", "Meio", "Valor (R$)", "Projeto/rubrica", "Com restrição",
        "Vínculo", "Comprovantes", "Origem", "Referência"]


def _linha_xlsx(x: dict) -> list:
    seg = _fin()._seguro
    return [seg(v) for v in (f"{x['data'][8:10]}/{x['data'][5:7]}/{x['data'][:4]}", x["conta_nome"], x["categoria_nome"] or "sem categoria", x["contraparte"],
                             x["descricao"], x["justificativa"], x["meio_nome"], x["valor"], x["projeto"], "sim" if x["restrito"] else "não",
                             (VINCULOS.get(x["vinculo_tipo"], "") + " " + x["vinculo_ref"]).strip(), ", ".join(a["nome"] for a in x["anexos"]),
                             {"mp": "Mercado Pago", "ofx": "extrato OFX", "manual": "lançada à mão", "agrupado": "agrupado (pessoal)"}.get(x["origem"], x["origem"]), x["mp_ref"])]


def agrupar_pessoal(ls: list[dict], cats: dict, de: str, ate: str) -> list[dict]:
    """Pessoal sem nomes: as despesas das categorias de PESSOAL viram UMA linha por categoria no período (total), sem contraparte nem
    justificativa (que trazem o nome da pessoa). As outras ficam como estão."""
    fora = [x for x in ls if x["categoria"] not in PESSOAL]
    grupos = []
    for k in PESSOAL:
        xs = [x for x in ls if x["categoria"] == k]
        if xs:
            grupos.append({"id": 0, "data": ate, "conta_nome": "", "categoria": k, "categoria_nome": cats.get(k, k), "contraparte": "",
                           "descricao": f"{len(xs)} {'pagamento' if len(xs) == 1 else 'pagamentos'} de {de[8:10]}/{de[5:7]}/{de[:4]} a {ate[8:10]}/{ate[5:7]}/{ate[:4]}",
                           "justificativa": "Pessoal agrupado: total sem nomes", "meio_nome": "", "valor": round(sum(x["valor"] for x in xs), 2),
                           "projeto": "", "restrito": any(x["restrito"] for x in xs), "vinculo_tipo": "", "vinculo_ref": "", "anexos": [], "origem": "agrupado", "mp_ref": ""})
    return fora + grupos


def abas_xlsx(wb, rel: dict) -> None:
    d = rel.get("despesas")
    if not d:
        return
    con = connect()
    try:
        ls = listar(con, rel["periodo"]["de"], rel["periodo"]["ate"], rel.get("conta") or 0)
        if rel.get("agrupar_pessoal", True):
            ls = agrupar_pessoal(ls, categorias(con), rel["periodo"]["de"], rel["periodo"]["ate"])
    finally:
        con.close()
    p = rel["periodo"]
    db = lambda s: f"{s[8:10]}/{s[5:7]}/{s[:4]}"   # noqa: E731
    sh = wb.create_sheet("Despesas — resumo")
    sh.append([f"Despesas · {db(p['de'])} a {db(p['ate'])} · gerado em {rel['gerado_em']}"])
    sh.append(["Categoria", "Valor (R$)", "Lançamentos"])
    for c in d["por_categoria"]:
        sh.append([c["nome"], c["valor"], c["n"]])
    sh.append(["Total", d["total"], d["n"]])
    sh.append([])
    sh.append(["Mês", "Valor (R$)", "Lançamentos"])
    for m in d["por_mes"]:
        sh.append([f"{m['mes'][5:7]}/{m['mes'][:4]}", m["valor"], m["n"]])
    sh.append([])
    sh.append(["Resultado (receitas líquidas − despesas)", d["resultado"]])
    for c in d["por_conta"]:
        sh.append([f"Resultado · {c['nome']}" + (" (com restrição, separado)" if c["restrito"] else ""), c["resultado"]])
    if d["transferencias_proprias"]["n"]:
        sh.append(["Transferências para conta própria (não são despesa)", d["transferencias_proprias"]["valor"]])
    s2 = wb.create_sheet("Despesas")
    s2.append([f"Despesas · {db(p['de'])} a {db(p['ate'])} · gerado em {rel['gerado_em']}"])
    s2.append(COLS)
    for x in ls:
        s2.append(_linha_xlsx(x))


# ---------------------------------------------------------------- saídas do Mercado Pago (relatório de liberações, pelo site)
def _classificar_mp(desc: str, meio_tipo: str) -> tuple[str | None, str, str | None]:
    """(tipo, meio, categoria automática) de uma linha de saída; tipo None = não é despesa."""
    d = (desc or "").lower()
    if any(k in d for k in NAO_DESPESA):
        return None, "", None
    if d == "withdrawal":
        return "transferencia_propria", "transferencia", None
    if d == "payout":
        return "despesa", "pix", None
    if "fee" in d or "tax" in d or "shipping" in d:
        return "despesa", "tarifa", "tarifas"
    m = (meio_tipo or "").lower()
    return "despesa", {"debit_card": "debito", "credit_card": "credito", "account_money": "saldo", "ticket": "boleto", "bank_transfer": "pix"}.get(m, "outro"), None


def importar_saidas_mp(con, itens: list[dict]) -> dict:
    out = {"lidas": 0, "novas": 0, "ignoradas": 0, "transferencias": 0}
    for x in itens:
        if not isinstance(x, dict):
            continue
        out["lidas"] += 1
        valor = _num(x.get("debito"))
        dia = _fin().dia_sp(x.get("data"))
        tipo, meio, cat = _classificar_mp(str(x.get("descricao") or ""), str(x.get("meio_tipo") or ""))
        if not valor or valor <= 0 or not dia or not tipo:
            out["ignoradas"] += 1
            continue
        sid = _txt(x.get("source_id"), 60) or f"linha{int(x.get('linha') or 0)}"
        chave = f"mp:{sid}:{_txt(x.get('descricao'), 40).lower()}:{dia}:{valor:.2f}"
        desc = {"payout": "Pix enviado ou saque", "withdrawal": "Retirada para a conta bancária da CAMP", "payment": "Compra no Mercado Pago"}.get(
            str(x.get("descricao") or "").lower(), "Tarifa do Mercado Pago" if cat == "tarifas" else (_txt(x.get("descricao"), 80) or "Saída do Mercado Pago"))
        if x.get("external_reference"):
            desc += f" · {_txt(x.get('external_reference'), 80)}"
        n = con.execute("""INSERT OR IGNORE INTO despesa (conta_id, data, valor, meio, contraparte, descricao, origem, chave, tipo, categoria, justificativa, mp_ref, criado_por)
                           VALUES (?,?,?,?,?,?, 'mp', ?,?,?,?,?, 'Mercado Pago')""",
                        (_fin().CONTA_MP, dia, valor, meio, _txt(x.get("contraparte"), 160) or None, desc, chave, tipo, cat,
                         "Tarifa cobrada pelo Mercado Pago" if cat == "tarifas" else None, _txt(x.get("source_id"), 60) or None)).rowcount
        out["novas"] += n
        out["transferencias"] += n if tipo == "transferencia_propria" else 0
    return out


def _meses(inicio: str, fim: date) -> list[tuple[str, str, str]]:
    a, m = int(inicio[:4]), int(inicio[5:7])
    out = []
    while (a, m) <= (fim.year, fim.month):
        ini = date(a, m, 1)
        ult = date(a + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        out.append((f"{a}-{m:02d}", ini.isoformat(), min(ult, fim).isoformat()))
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return out


def rodada_mp(con, wp=None, force: bool = False, max_pedidos: int = 3) -> dict:
    """Uma volta das saídas do Mercado Pago (chamada pelo coletor do Financeiro, nunca numa requisição). Nunca levanta."""
    out = {"pedidos": 0, "baixados": 0, "novas": 0, "sem_rota": False, "desligado": False, "erro": None}
    if _cfg(con, "despesas.mp_relatorio", "1") != "1":
        out["desligado_config"] = True
        return out
    try:
        fi = _fin()
        wp = wp or fi._wp()
        hoje = fi.hoje()
        r = wp.h.get(ROTA_RELS, params={})
        if r.status_code == 404:
            out["sem_rota"] = True
            return out
        if r.status_code == 409:
            out["desligado"] = True
            return out
        if r.status_code >= 400:
            raise RuntimeError(f"O site respondeu {r.status_code} à lista dos relatórios")
        prontos = {}
        for x in (r.json() or {}).get("itens") or []:
            if isinstance(x, dict) and str(x.get("status") or "processed").lower() in ("processed", "ready", "enabled", ""):
                d0 = fi.dia_sp(x.get("begin_date"))
                if d0 and (d0 not in prontos or str(x.get("criado") or "") > str(prontos[d0].get("criado") or "")):
                    prontos[d0] = x
        agora = datetime.now(timezone.utc)
        recentes = {m[0] for m in _meses(fi._cfg(con, "financeiro.mp_inicio", "2026-01-01"), hoje)[-2:]}
        for per, de, ate in _meses(fi._cfg(con, "financeiro.mp_inicio", "2026-01-01"), hoje):
            st = con.execute("SELECT * FROM mp_relatorio WHERE periodo=?", (per,)).fetchone()
            if not st:
                con.execute("INSERT INTO mp_relatorio (periodo, de, ate) VALUES (?,?,?)", (per, de, ate))
                st = con.execute("SELECT * FROM mp_relatorio WHERE periodo=?", (per,)).fetchone()
            arq = prontos.get(de)
            novo = arq and (not st["baixado_em"] or (st["pedido_em"] and str(arq.get("criado") or "9") >= st["pedido_em"][:10] and arq.get("arquivo") != st["arquivo"]))
            if arq and novo:
                rd = wp.h.get(ROTA_REL, params={"arquivo": arq["arquivo"]})
                if rd.status_code < 400:
                    imp = importar_saidas_mp(con, (rd.json() or {}).get("itens") or [])
                    con.execute("UPDATE mp_relatorio SET arquivo=?, baixado_em=?, linhas=?, erro=NULL WHERE periodo=?",
                                (arq["arquivo"], agora.strftime("%Y-%m-%d %H:%M:%S"), imp["lidas"], per))
                    out["baixados"] += 1
                    out["novas"] += imp["novas"]
                    con.commit()
                    continue
            precisa = not st["pedido_em"] or (not st["baixado_em"] and agora - datetime.fromisoformat(st["pedido_em"]).replace(tzinfo=timezone.utc) > timedelta(hours=6)) \
                or (per in recentes and st["baixado_em"] and agora - datetime.fromisoformat(st["baixado_em"]).replace(tzinfo=timezone.utc) > timedelta(hours=20)
                    and (not st["pedido_em"] or st["pedido_em"] < st["baixado_em"]))
            if precisa and out["pedidos"] < max_pedidos:
                rp = wp.h.post(ROTA_REL, json={"desde": de, "ate": ate})
                if rp.status_code < 400:
                    con.execute("UPDATE mp_relatorio SET pedido_em=?, erro=NULL WHERE periodo=?", (agora.strftime("%Y-%m-%d %H:%M:%S"), per))
                    out["pedidos"] += 1
                else:
                    con.execute("UPDATE mp_relatorio SET erro=? WHERE periodo=?", (f"o site respondeu {rp.status_code}", per))
        con.commit()
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:200]
        registrar(logging.WARNING, "despesas_mp", "Saídas do Mercado Pago com problema", erro=type(e).__name__)
    return out


# ---------------------------------------------------------------- extrato OFX (mínimo)
def _ofx_tag(bloco: str, tag: str) -> str:
    m = re.search(rf"<{tag}>([^<\r\n]*)", bloco, re.I)
    return m.group(1).strip() if m else ""


def ler_ofx(texto: str) -> list[dict]:
    """Transações de um OFX (SGML 1.x ou XML 2.x): data, valor (negativo = débito), FITID, nome, memo."""
    out = []
    for b in re.findall(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))", texto, re.I | re.S):
        dt = _ofx_tag(b, "DTPOSTED")[:8]
        try:
            dia = date(int(dt[:4]), int(dt[4:6]), int(dt[6:8])).isoformat()
            valor = float(_ofx_tag(b, "TRNAMT").replace(",", "."))
        except (ValueError, IndexError):
            continue
        out.append({"data": dia, "valor": round(valor, 2), "fitid": _ofx_tag(b, "FITID"), "nome": _ofx_tag(b, "NAME"), "memo": _ofx_tag(b, "MEMO"),
                    "tipo": _ofx_tag(b, "TRNTYPE").upper()})
    return out


def _chave_ofx(conta: int, t: dict) -> str:
    if t["fitid"]:
        return f"ofx:{conta}:{t['fitid']}"
    h = hashlib.sha256(f"{t['data']}|{t['valor']:.2f}|{(t['nome'] + ' ' + t['memo']).strip().lower()}".encode()).hexdigest()[:24]
    return f"ofx:{conta}:h:{h}"


def importar_ofx(con, conta: int, texto: str, aplicar: bool, ator: str) -> dict:
    c = con.execute("SELECT * FROM financeiro_conta WHERE id=?", (conta,)).fetchone()
    if not c:
        raise HTTPException(400, "Escolha a conta do extrato")
    trs = ler_ofx(texto)
    if not trs:
        raise HTTPException(400, "Não achei transações neste arquivo: confira se é um extrato OFX")
    linhas = []
    for t in trs:
        if t["valor"] >= 0:
            linhas.append(dict(t, situacao="credito"))
            continue
        ch = _chave_ofx(conta, t)
        ja = con.execute("SELECT 1 FROM despesa WHERE chave=?", (ch,)).fetchone()
        linhas.append(dict(t, situacao="ja_importada" if ja else "nova", chave=ch))
    novas = [x for x in linhas if x["situacao"] == "nova"]
    if aplicar:
        for x in novas:
            did = con.execute("""INSERT OR IGNORE INTO despesa (conta_id, data, valor, meio, contraparte, descricao, origem, chave, projeto, restrito, criado_por)
                                 VALUES (?,?,?,?,?,?, 'ofx', ?,?,?,?)""",
                              (conta, x["data"], abs(x["valor"]), "tarifa" if x["tipo"] in ("FEE", "SRVCHG") else ("pix" if "PIX" in (x["nome"] + x["memo"]).upper() else "outro"),
                               _txt(x["nome"], 160) or None, _txt(x["memo"], 300) or None, x["chave"], c["projeto"], 1 if c["restrito"] else 0, ator)).lastrowid
            if did:
                _ev(con, did, "importada", ator, {"origem": "ofx", "conta": conta, "valor": abs(x["valor"])})
        con.commit()
    return {"ok": True, "simulado": not aplicar, "conta": c["nome"], "linhas": linhas, "novas": len(novas),
            "ja_importadas": sum(1 for x in linhas if x["situacao"] == "ja_importada"), "creditos": sum(1 for x in linhas if x["situacao"] == "credito")}


# ---------------------------------------------------------------- rotas (só admin e master)
def _periodo(de, ate, mes, ano, tri=""):
    if tri:
        try:
            a, t = tri.split("-T")
            a, t = int(a), int(t)
            if not 1 <= t <= 4:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "Trimestre inválido: use AAAA-T1 a AAAA-T4")
        ini = date(a, 3 * t - 2, 1)
        fim = (date(a + (t == 4), (3 * t) % 12 + 1, 1) - timedelta(days=1))
        return ini.isoformat(), fim.isoformat()
    return _fin().periodo(de, ate, mes, ano)


@router.get("")
def ver(de: str = "", ate: str = "", mes: str = "", ano: str = "", tri: str = "", conta: int = 0, categoria: str = "", pendentes: int = 0, q: str = "",
        u: dict = Depends(auth.exige("admin"))) -> dict:
    d1, d2 = _periodo(de, ate, mes, ano, tri)
    con = connect()
    try:
        ls = listar(con, d1, d2, conta, categoria, bool(pendentes), q)
        fila = listar(con, "2000-01-01", "2100-12-31", so_pendentes=True)
        return {"periodo": {"de": d1, "ate": d2}, "itens": ls, "total": round(sum(x["valor"] for x in ls), 2), "categorias": categorias(con), "meios": MEIOS,
                "vinculos": VINCULOS, "contas": _fin().contas(con), "precisa_justificar": fila, "n_precisa": len(fila),
                "transferencias": [x for x in listar(con, d1, d2, conta, com_transferencias=True) if x["tipo"] == "transferencia_propria"],
                "mp_relatorios": [dict(r) for r in con.execute("SELECT periodo, pedido_em, baixado_em, linhas, erro FROM mp_relatorio ORDER BY periodo")],
                "doacoes": _doacoes(con), "notas_pedidas": _notas_pedidas(con),
                "notas_lembrete_dias": _notas_dias(con)}
    finally:
        con.close()


def _notas_pedidas(con) -> list[dict]:
    """CAMP-FIN pedir nota fiscal: as despesas com nota pedida que ainda não chegou, de qualquer mês (filtro Notas pedidas)."""
    cats, contas = categorias(con), {c["id"]: c for c in _fin().contas(con)}
    return [_linha(con, r, cats, contas) for r in con.execute("SELECT * FROM despesa WHERE apagado_em IS NULL AND nota_pedida_em IS NOT NULL ORDER BY nota_pedida_em, id")]


def _notas_dias(con) -> int:
    from .notas_fiscais import lembrete_dias
    return lembrete_dias(con)


def _doacoes(con) -> list[dict]:
    """Doações de acervo e as tarefas delas, para o vínculo de uma despesa (ex.: "Cotar frete")."""
    out = []
    for r in con.execute("SELECT site_id, protocolo, autor FROM doacao_acervo WHERE anonimizado=0 ORDER BY site_id DESC LIMIT 200"):
        out.append({"site_id": r["site_id"], "protocolo": r["protocolo"] or "", "autor": r["autor"] or "",
                    "tarefas": [dict(t) for t in con.execute("SELECT id, titulo, valor FROM doacao_tarefa WHERE site_id=? ORDER BY ordem, id", (r["site_id"],))]})
    return out


class Despesa(BaseModel):
    data: str | None = None
    valor: float | None = None
    meio: str | None = None
    contraparte: str | None = None
    descricao: str | None = None
    conta_id: int | None = None
    categoria: str | None = None
    justificativa: str | None = None
    projeto: str | None = None
    restrito: bool | None = None
    vinculo_tipo: str | None = None
    vinculo_ref: str | None = None
    tarefa_id: int | None = None
    preencher_tarefa: bool = False
    tipo: str | None = None


def _validar(con, b: Despesa, novo: bool) -> dict:
    v: dict = {}
    cats = categorias(con)
    if b.data is not None or novo:
        try:
            d = date.fromisoformat(b.data or "")
        except ValueError:
            raise HTTPException(400, "Data inválida (AAAA-MM-DD)")
        if d > _fin().hoje() + timedelta(days=1):
            raise HTTPException(400, "A data não pode ser no futuro")
        v["data"] = d.isoformat()
    if b.valor is not None or novo:
        if not b.valor or not 0 < float(b.valor) <= 10_000_000:
            raise HTTPException(400, "Valor inválido")
        v["valor"] = round(float(b.valor), 2)
    if b.meio is not None:
        if b.meio not in MEIOS:
            raise HTTPException(400, "Meio de pagamento inválido")
        v["meio"] = b.meio
    if b.conta_id is not None:
        if not con.execute("SELECT 1 FROM financeiro_conta WHERE id=?", (b.conta_id,)).fetchone():
            raise HTTPException(400, "Conta desconhecida")
        v["conta_id"] = b.conta_id
    if b.categoria is not None:
        if b.categoria and b.categoria not in cats:
            raise HTTPException(400, "Categoria desconhecida")
        v["categoria"] = b.categoria or None
    if b.vinculo_tipo is not None:
        if b.vinculo_tipo and b.vinculo_tipo not in VINCULOS:
            raise HTTPException(400, "Vínculo desconhecido")
        v["vinculo_tipo"] = b.vinculo_tipo or None
    if b.tipo is not None:
        if b.tipo not in ("despesa", "transferencia_propria"):
            raise HTTPException(400, "Tipo inválido")
        v["tipo"] = b.tipo
    for k, n in (("contraparte", 160), ("descricao", 300), ("justificativa", 2000), ("projeto", 120), ("vinculo_ref", 80)):
        if getattr(b, k) is not None:
            v[k] = _txt(getattr(b, k), n) or None
    if b.restrito is not None:
        v["restrito"] = 1 if b.restrito else 0
    if b.tarefa_id is not None:
        if b.tarefa_id and not con.execute("SELECT 1 FROM doacao_tarefa WHERE id=?", (b.tarefa_id,)).fetchone():
            raise HTTPException(400, "Tarefa da doação não encontrada")
        v["tarefa_id"] = b.tarefa_id or None
    return v


def _detalhe(con, did: int) -> dict:
    r = con.execute("SELECT * FROM despesa WHERE id=? AND apagado_em IS NULL", (did,)).fetchone()
    if not r:
        raise HTTPException(404, "Despesa não encontrada")
    x = _linha(con, r, categorias(con), {c["id"]: c for c in _fin().contas(con)})
    x["historico"] = [dict(e) for e in con.execute("SELECT tipo, ator, detalhe, quando FROM evento WHERE entidade='despesa' AND codigo=? ORDER BY id DESC LIMIT 50", (str(did),))]
    if r["tarefa_id"]:
        t = con.execute("SELECT id, site_id, titulo, valor FROM doacao_tarefa WHERE id=?", (r["tarefa_id"],)).fetchone()
        x["tarefa"] = dict(t) if t else None
    return x


def _tarefa(con, did: int, v: dict, preencher: bool, ator: str) -> None:
    tid = v.get("tarefa_id")
    if tid and preencher:
        val = v.get("valor") or con.execute("SELECT valor FROM despesa WHERE id=?", (did,)).fetchone()[0]
        con.execute("UPDATE doacao_tarefa SET valor=?, alterado_em=datetime('now'), alterado_por=? WHERE id=?", (val, ator, tid))


@router.post("")
def criar(b: Despesa, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        v = _validar(con, b, True)
        v.setdefault("conta_id", 1)
        v.setdefault("meio", "dinheiro")
        if "projeto" not in v:
            v["projeto"] = con.execute("SELECT projeto FROM financeiro_conta WHERE id=?", (v["conta_id"],)).fetchone()[0]
        v["chave"] = "manual:" + secrets.token_hex(8)
        cols = list(v)
        did = con.execute(f"INSERT INTO despesa ({', '.join(cols)}, origem, criado_por) VALUES ({','.join('?' * len(cols))}, 'manual', ?)", (*v.values(), _ator(u))).lastrowid
        _tarefa(con, did, v, b.preencher_tarefa, _ator(u))
        _ev(con, did, "criada", _ator(u), {"valor": v["valor"], "data": v["data"], "categoria": v.get("categoria")})
        con.commit()
        return _detalhe(con, did)
    finally:
        con.close()


@router.get("/sugestoes")
def sugestoes(contraparte: str = "", u: dict = Depends(auth.exige("admin"))) -> dict:
    """Categorias mais usadas (primeiro) e justificativas de despesas parecidas (mesma contraparte)."""
    con = connect()
    try:
        cats = categorias(con)
        uso = {r[0]: r[1] for r in con.execute("SELECT categoria, COUNT(*) FROM despesa WHERE categoria IS NOT NULL AND apagado_em IS NULL GROUP BY categoria")}
        ordem = sorted(cats, key=lambda k: (-uso.get(k, 0), list(cats).index(k)))
        js = []
        if contraparte.strip():
            for r in con.execute("""SELECT justificativa, categoria FROM despesa WHERE apagado_em IS NULL AND justificativa IS NOT NULL AND lower(contraparte)=lower(?)
                                    GROUP BY justificativa ORDER BY MAX(id) DESC LIMIT 5""", (contraparte.strip(),)):
                js.append({"justificativa": r[0], "categoria": r[1] or ""})
        return {"categorias": [{"chave": k, "nome": cats[k], "usos": uso.get(k, 0)} for k in ordem], "justificativas": js}
    finally:
        con.close()


@router.post("/ofx")
def ofx(b: dict, u: dict = Depends(auth.exige("admin"))) -> dict:
    """{conta_id, base64 (do arquivo .ofx), aplicar: false} → simulação; com aplicar: true importa só os débitos novos."""
    try:
        dados = base64.b64decode(re.sub(r"^data:[^,]*,", "", str(b.get("base64") or "")).strip(), validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(400, "O arquivo chegou incompleto: escolha de novo.") from e
    if len(dados) > 5 * 1024 * 1024:
        raise HTTPException(400, "Extrato grande demais (até 5 MB)")
    texto = dados.decode("utf-8", errors="ignore") if b"encoding=\"utf" in dados[:300].lower() or b"CHARSET:UTF" in dados[:300].upper() else dados.decode("latin-1")
    con = connect()
    try:
        return importar_ofx(con, int(b.get("conta_id") or 0), texto, bool(b.get("aplicar")), _ator(u))
    finally:
        con.close()


@router.get("/exportar.csv")
def exportar_csv(de: str = "", ate: str = "", mes: str = "", ano: str = "", tri: str = "", conta: int = 0, agrupar_pessoal: int = 1,
                 u: dict = Depends(auth.exige("admin"))):
    """Despesas do período em CSV. "Agrupar pessoal" (padrão ligado): Salários, Encargos, Bolsas e Autônomos numa linha por categoria, sem nomes."""
    import csv
    d1, d2 = _periodo(de, ate, mes, ano, tri)
    con = connect()
    try:
        ls = listar(con, d1, d2, conta)
        if agrupar_pessoal:
            ls = agrupar_pessoal_fn(ls, categorias(con), d1, d2)
    finally:
        con.close()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([f"CAMP — Despesas · {d1[8:10]}/{d1[5:7]}/{d1[:4]} a {d2[8:10]}/{d2[5:7]}/{d2[:4]}" + (" · pessoal agrupado, sem nomes" if agrupar_pessoal else "")])
    w.writerow(COLS)
    num = lambda v: f"{v:.2f}".replace(".", ",") if isinstance(v, float) else v   # noqa: E731
    for x in ls:
        w.writerow([num(v) for v in _linha_xlsx(x)])
    return Response(("\ufeff" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="camp-despesas-{d1}-a-{d2}.csv"'})


agrupar_pessoal_fn = agrupar_pessoal


@router.get("/comprovantes.zip")
def comprovantes_zip(de: str = "", ate: str = "", mes: str = "", ano: str = "", tri: str = "", conta: int = 0, u: dict = Depends(auth.exige("admin"))):
    d1, d2 = _periodo(de, ate, mes, ano, tri)
    con = connect()
    try:
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
            for x in listar(con, d1, d2, conta):
                for a in x["anexos"]:
                    r = con.execute("SELECT arquivo FROM despesa_anexo WHERE id=?", (a["id"],)).fetchone()
                    f = (pasta() / r[0]).resolve()
                    if pasta().resolve() in f.parents and f.is_file():
                        z.write(f, f"{x['data']}_despesa{x['id']}_{a['nome']}")
        return Response(b.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="camp-comprovantes-{d1}-a-{d2}.zip"'})
    finally:
        con.close()


@router.get("/{did}")
def detalhe(did: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return _detalhe(con, did)
    finally:
        con.close()


@router.put("/{did}")
def mudar(did: int, b: Despesa, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        antes = _detalhe(con, did)
        v = _validar(con, b, False)
        if antes["origem"] != "manual":            # do extrato: data, valor e contraparte são os do banco
            for k in ("data", "valor"):
                v.pop(k, None)
        if v:
            con.execute(f"UPDATE despesa SET {', '.join(k + '=?' for k in v)}, alterado_por=?, alterado_em=datetime('now') WHERE id=?", (*v.values(), _ator(u), did))
        _tarefa(con, did, v, b.preencher_tarefa, _ator(u))
        just = ("categoria" in v or "justificativa" in v) and antes["falta"]
        _ev(con, did, "justificada" if just else "alterada", _ator(u), {k: v[k] for k in v if k != "justificativa"} | ({"justificativa": True} if "justificativa" in v else {}))
        con.commit()
        return _detalhe(con, did)
    finally:
        con.close()


class Apagar(BaseModel):
    motivo: str = ""


@router.delete("/{did}")
def apagar(did: int, b: Apagar, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        x = _detalhe(con, did)
        motivo = _txt(b.motivo, 300)
        if len(motivo) < 5:
            raise HTTPException(400, "Diga por que apagar (o motivo fica no histórico)")
        con.execute("UPDATE despesa SET apagado_em=datetime('now'), apagado_por=?, apagado_motivo=? WHERE id=?", (_ator(u), motivo, did))
        _ev(con, did, "apagada", _ator(u), {"motivo": motivo, "valor": x["valor"], "origem": x["origem"]})
        con.commit()
        return {"ok": True}
    finally:
        con.close()


class Comprovante(BaseModel):
    nome: str
    base64: str


@router.post("/{did}/comprovante")
def comprovante(did: int, b: Comprovante, u: dict = Depends(auth.exige("admin"))) -> dict:
    from .doacoes_central import nome_limpo, tipo_pelos_bytes, _ext
    con = connect()
    try:
        _detalhe(con, did)
        try:
            dados = base64.b64decode(re.sub(r"^data:[^,]*,", "", b.base64 or "").strip(), validate=True)
        except (binascii.Error, ValueError) as e:
            raise HTTPException(400, "O arquivo chegou incompleto: escolha de novo.") from e
        ext = _ext(b.nome)
        if ext not in EXT_OK or not tipo_pelos_bytes(dados, ext):
            raise HTTPException(400, "Comprovante aceito: PDF, JPG, PNG ou WEBP (o arquivo não bate com o tipo).")
        if not dados or len(dados) > MAX_ANEXO:
            raise HTTPException(400, "Comprovante grande demais (até 15 MB).")
        nm = nome_limpo(b.nome, "jpg" if ext == "jpeg" else ext)
        mime = {"pdf": "application/pdf", "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")
        aid = con.execute("INSERT INTO despesa_anexo (despesa_id, nome, arquivo, mime, tamanho, sha256, criado_por) VALUES (?,?,?,?,?,?,?)",
                          (did, nm, "", mime, len(dados), hashlib.sha256(dados).hexdigest(), _ator(u))).lastrowid
        (pasta() / str(did)).mkdir(parents=True, exist_ok=True)
        rel = f"{did}/{aid}_{secrets.token_hex(4)}.{ext}"
        (pasta() / rel).write_bytes(dados)
        con.execute("UPDATE despesa_anexo SET arquivo=? WHERE id=?", (rel, aid))
        _ev(con, did, "comprovante", _ator(u), {"anexo": aid, "nome": nm, "tamanho": len(dados)})
        from .notas_fiscais import ao_anexar   # a nota pedida ao fornecedor chegou: limpa "nota pedida"
        ao_anexar(con, did, _ator(u))
        con.commit()
        return _detalhe(con, did)
    finally:
        con.close()


@router.get("/{did}/comprovante/{aid}")
def comprovante_baixar(did: int, aid: int, u: dict = Depends(auth.exige("admin"))):
    con = connect()
    try:
        r = con.execute("SELECT * FROM despesa_anexo WHERE id=? AND despesa_id=?", (aid, did)).fetchone()
    finally:
        con.close()
    if not r:
        raise HTTPException(404, "Comprovante não encontrado")
    f = (pasta() / r["arquivo"]).resolve()
    if not r["arquivo"] or pasta().resolve() not in f.parents or not f.is_file():
        raise HTTPException(404, "Arquivo do comprovante não encontrado")
    return FileResponse(f, media_type=r["mime"] or "application/octet-stream", filename=r["nome"], content_disposition_type="inline")


@router.delete("/{did}/comprovante/{aid}")
def comprovante_apagar(did: int, aid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT * FROM despesa_anexo WHERE id=? AND despesa_id=?", (aid, did)).fetchone()
        if not r:
            raise HTTPException(404, "Comprovante não encontrado")
        con.execute("DELETE FROM despesa_anexo WHERE id=?", (aid,))
        _ev(con, did, "comprovante_apagado", _ator(u), {"anexo": aid, "nome": r["nome"]})
        con.commit()
        try:
            f = (pasta() / r["arquivo"]).resolve()
            if pasta().resolve() in f.parents and f.is_file():
                f.unlink()
        except OSError:
            pass
        return _detalhe(con, did)
    finally:
        con.close()
