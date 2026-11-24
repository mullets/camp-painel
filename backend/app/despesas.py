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


def pendente(r, n_anexos: int, projeto: bool = False) -> list[str]:
    """O que falta numa despesa importada: categoria, justificativa, comprovante (vazio = justificada). Conta de projeto incentivado
    (CAMP-ROUANET): também a lançada à mão, com o item do orçamento e a nota fiscal ("Projeto incentivado: nota fiscal obrigatória")."""
    if r["tipo"] != "despesa" or r["apagado_em"] or (r["origem"] == "manual" and not projeto):
        return []
    falta = []
    if projeto:
        if not r["orcamento_item"]:
            falta.append("item do orçamento")
        if not r["categoria"]:
            falta.append("categoria")
        if not (r["justificativa"] or "").strip():
            falta.append("justificativa")
        if not n_anexos and r["categoria"] != "tarifas":
            falta.append("nota fiscal")
        return falta
    if not r["categoria"]:
        falta.append("categoria")
    if not (r["justificativa"] or "").strip():
        falta.append("justificativa")
    if not n_anexos and r["categoria"] != "tarifas":
        falta.append("comprovante")
    return falta


def _linha(con, r, cats: dict, contas: dict) -> dict:
    ax = _anexos(con, r["id"])
    proj = contas.get(r["conta_id"], {}).get("tipo") == "projeto_incentivado"
    nota_pdf = proj and bool(con.execute("SELECT 1 FROM nota_camp WHERE despesa_id=? AND situacao='paga' AND nf_arquivo IS NOT NULL", (r["id"],)).fetchone())
    return {"id": r["id"], "conta_id": r["conta_id"], "conta_nome": contas.get(r["conta_id"], {}).get("nome", ""), "data": r["data"], "valor": r["valor"],
            "meio": r["meio"] or "", "meio_nome": MEIOS.get(r["meio"] or "", r["meio"] or ""), "contraparte": r["contraparte"] or "", "descricao": r["descricao"] or "",
            "origem": r["origem"], "tipo": r["tipo"], "categoria": r["categoria"] or "", "categoria_nome": cats.get(r["categoria"] or "", "") if r["categoria"] else "",
            "justificativa": r["justificativa"] or "", "projeto": r["projeto"] or "", "restrito": bool(r["restrito"]), "vinculo_tipo": r["vinculo_tipo"] or "",
            "vinculo_ref": r["vinculo_ref"] or "", "tarefa_id": r["tarefa_id"], "mp_ref": r["mp_ref"] or "", "anexos": ax, "falta": pendente(r, len(ax) + nota_pdf, proj),
            "criado_por": r["criado_por"] or "", "alterado_por": r["alterado_por"] or "", "conta_restrita": bool(contas.get(r["conta_id"], {}).get("restrito")),
            "conta_projeto": proj, "orcamento_item": r["orcamento_item"], "nf_numero": r["nf_numero"] or "", "nota_camp": bool(nota_pdf),
            "nota_pedida_em": r["nota_pedida_em"] if "nota_pedida_em" in r.keys() else None,   # CAMP-FIN pedir nota fiscal (notas_fiscais.py)
            "pode_ser_entrada": r["origem"] == "mp" and bool(r["mp_ref"]) and r["tipo"] == "despesa" and (r["categoria"] or "") not in ("tarifas", "impostos")}


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
    for r in con.execute("""SELECT d.*, (SELECT COUNT(*) FROM despesa_anexo a WHERE a.despesa_id=d.id)
                                + (SELECT COUNT(*) FROM nota_camp nc WHERE nc.despesa_id=d.id AND nc.situacao='paga' AND nc.nf_arquivo IS NOT NULL) AS nax,
                                (SELECT tipo FROM financeiro_conta c WHERE c.id=d.conta_id) = 'projeto_incentivado' AS proj
                            FROM despesa d WHERE apagado_em IS NULL AND tipo='despesa'"""):
        n += 1 if pendente(r, r["nax"], bool(r["proj"])) else 0
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
def _classificar_mp(desc: str, meio_tipo: str, meio: str = "", tags: str = "") -> tuple[str | None, str, str | None, str]:
    """(tipo, meio, categoria automática, rótulo como no Extrato do Mercado Pago) de uma linha de saída do relatório; tipo None = não é despesa.
    CAMP-FIN-CONSERTOS (Rafael: "saída de Pix, boleto, transferências"): o rótulo segue o Extrato (Pix enviado, Pagamento com Pix,
    Pagamento de boleto/conta, Compra no cartão de débito, Transferência enviada, Saque, Tarifa)."""
    d = (desc or "").lower().strip()
    m = (meio_tipo or "").lower()
    mm = (meio or "").lower()
    tg = (tags or "").upper()
    if any(k in d for k in NAO_DESPESA):
        return None, "", None, ""
    if d == "withdrawal":
        return "transferencia_propria", "transferencia", None, "Saque (transferência para a conta bancária da CAMP)"
    if d == "payout":   # "saque em dinheiro ou transferência por PIX de saldo disponível" (glossário do relatório de liberações)
        return "despesa", "pix", None, "Pix enviado"
    if d.startswith("tax") or "imposto" in d:
        return "despesa", "tarifa", "impostos", "Imposto retido pelo Mercado Pago"
    if "fee" in d or "shipping" in d or "tarifa" in d:
        return "despesa", "tarifa", "tarifas", "Tarifa do Mercado Pago"
    if d in ("money_transfer", "transfer", "bank_transfer"):
        return "despesa", "transferencia", None, "Transferência enviada"
    if d == "credit_payment":
        return "despesa", "outro", None, "Pagamento de crédito do Mercado Pago"
    if "PIX" in tg or m == "bank_transfer" or mm == "pix":
        return "despesa", "pix", None, "Pagamento com Pix"
    if m == "ticket" or "bol" in mm or "boleto" in d or "bill" in d or "utility" in d:
        return "despesa", "boleto", None, "Pagamento de boleto/conta"
    if m in ("debit_card", "prepaid_card"):
        return "despesa", "debito", None, "Compra no cartão de débito"
    if m == "credit_card":
        return "despesa", "credito", None, "Compra no cartão de crédito"
    if m == "account_money":
        return "despesa", "saldo", None, "Pagamento com o saldo do Mercado Pago"
    return "despesa", "outro", None, "Pagamento" if d == "payment" else (_txt(desc, 80) or "Saída do Mercado Pago")


def importar_saidas_mp(con, itens: list[dict]) -> dict:
    """Linhas de SAÍDA do relatório (o site já tirou as entradas: vendas e liberações nunca viram receita por aqui; as receitas vêm de
    payments/search). Única pelo movimento; se o movimento já veio pelo Extrato importado (mesma referência e valor), não duplica."""
    out = {"lidas": 0, "novas": 0, "ignoradas": 0, "transferencias": 0, "ja_no_extrato": 0}
    for x in itens:
        if not isinstance(x, dict):
            continue
        out["lidas"] += 1
        valor = _num(x.get("debito"))
        dia = _fin().dia_sp(x.get("data"))
        tipo, meio, cat, rotulo = _classificar_mp(str(x.get("descricao") or ""), str(x.get("meio_tipo") or ""), str(x.get("meio") or ""), str(x.get("tags") or ""))
        if not valor or valor <= 0 or not dia or not tipo:
            out["ignoradas"] += 1
            continue
        sid = _txt(x.get("source_id"), 60) or f"linha{int(x.get('linha') or 0)}"
        if x.get("source_id") and con.execute("SELECT 1 FROM despesa WHERE mp_ref=? AND chave LIKE 'mpx:%' AND ABS(valor-?)<0.005", (sid, valor)).fetchone():
            out["ja_no_extrato"] += 1
            continue
        if x.get("source_id") and con.execute("SELECT 1 FROM despesa WHERE mp_ref=? AND chave LIKE 'mpp:%'", (sid,)).fetchone():
            out["ja_nos_pagamentos"] = out.get("ja_nos_pagamentos", 0) + 1      # contrato 1.35: a saída já veio da busca de pagamentos (mesmo id)
            continue
        chave = f"mp:{sid}:{_txt(x.get('descricao'), 40).lower()}:{dia}:{valor:.2f}"
        desc = rotulo
        if x.get("external_reference"):
            desc += f" · {_txt(x.get('external_reference'), 80)}"
        n = con.execute("""INSERT OR IGNORE INTO despesa (conta_id, data, valor, meio, contraparte, descricao, origem, chave, tipo, categoria, justificativa, mp_ref, criado_por)
                           VALUES (?,?,?,?,?,?, 'mp', ?,?,?,?,?, 'Mercado Pago')""",
                        (_fin().CONTA_MP, dia, valor, meio, _txt(x.get("contraparte"), 160) or None, desc, chave, tipo, cat,
                         {"tarifas": "Tarifa cobrada pelo Mercado Pago", "impostos": "Imposto retido pelo Mercado Pago"}.get(cat), _txt(x.get("source_id"), 60) or None)).rowcount
        out["novas"] += n
        out["transferencias"] += n if tipo == "transferencia_propria" else 0
    return out


# ---------------------------------------------------------------- Extrato da conta do Mercado Pago (CSV baixado pelo Rafael)
_EXTRATO_COLS = {"data": ("RELEASE_DATE", "DATA", "DATA DE LIBERACAO", "DATE"), "tipo": ("TRANSACTION_TYPE", "DESCRICAO", "TIPO DE TRANSACAO", "DESCRIPTION"),
                 "ref": ("REFERENCE_ID", "ID DA OPERACAO", "REFERENCIA", "ID DA OPERACAO NO MERCADO PAGO", "SOURCE_ID"),
                 "valor": ("TRANSACTION_NET_AMOUNT", "VALOR", "VALOR LIQUIDO", "NET_AMOUNT")}


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def _valor_br(v) -> float | None:
    t = str(v or "").strip().replace("R$", "").replace("\u00a0", "").replace(" ", "")
    if not t:
        return None
    if re.fullmatch(r"[-+]?\d{1,3}(\.\d{3})*,\d+|[-+]?\d+,\d+", t):
        t = t.replace(".", "").replace(",", ".")
    try:
        return round(float(t), 2)
    except ValueError:
        return None


def _data_br(v) -> str:
    t = str(v or "").strip()
    m = re.match(r"(\d{2})[/-](\d{2})[/-](\d{4})", t)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            return ""
    return _fin().dia_sp(t) if re.match(r"\d{4}-\d{2}-\d{2}", t) else ""


# (começo do texto do Extrato, sem acento e minúsculo) → (tipo, meio, categoria, rótulo). A ordem importa: o mais específico primeiro.
_EXTRATO_TIPOS = [
    ("pagamento com pix", ("despesa", "pix", None, "Pagamento com Pix")),
    ("pix enviado", ("despesa", "pix", None, "Pix enviado")),
    ("transferencia pix enviada", ("despesa", "pix", None, "Pix enviado")),
    ("pagamento de boleto", ("despesa", "boleto", None, "Pagamento de boleto/conta")),
    ("pagamento de conta", ("despesa", "boleto", None, "Pagamento de boleto/conta")),
    ("pagamento de contas", ("despesa", "boleto", None, "Pagamento de boleto/conta")),
    ("boleto pago", ("despesa", "boleto", None, "Pagamento de boleto/conta")),
    ("compra com cartao de debito", ("despesa", "debito", None, "Compra no cartão de débito")),
    ("compra no cartao", ("despesa", "debito", None, "Compra no cartão de débito")),
    ("compra", ("despesa", "debito", None, "Compra no cartão de débito")),
    ("transferencia enviada", ("despesa", "transferencia", None, "Transferência enviada")),
    ("transferencia para", ("despesa", "transferencia", None, "Transferência enviada")),
    ("saque", ("transferencia_propria", "transferencia", None, "Saque (transferência para a conta bancária da CAMP)")),
    ("retirada", ("transferencia_propria", "transferencia", None, "Saque (transferência para a conta bancária da CAMP)")),
    ("tarifa", ("despesa", "tarifa", "tarifas", "Tarifa do Mercado Pago")),
    ("imposto", ("despesa", "tarifa", "impostos", "Imposto retido pelo Mercado Pago")),
    ("pagamento", ("despesa", "debito", None, "Compra no cartão de débito")),   # "Pagamento Anthropic* claude sub"; "Pagamento" sozinho = conta (abaixo)
]


def classificar_extrato(texto: str) -> tuple[str | None, str, str | None, str, str]:
    """Uma linha de SAÍDA do Extrato → (tipo, meio, categoria, rótulo, contraparte). Aceita "Pix enviado Fulano", "Fulano · Pix enviado" e
    "Fulano - Pagamento com Pix". "Pagamento" sozinho (com o logo do Mercado Pago) é pagamento de conta/boleto."""
    bruto = re.sub(r"\s+", " ", str(texto or "")).strip()
    nome, tipo_txt = "", bruto
    for sep in (" · ", " | "):
        if sep in bruto:
            a, b = bruto.rsplit(sep, 1)
            if any(_sem_acento(b).lower().startswith(k) for k, _ in _EXTRATO_TIPOS):
                nome, tipo_txt = a.strip(), b.strip()
            break
    t = _sem_acento(tipo_txt).lower()
    for k, v in _EXTRATO_TIPOS:
        if t.startswith(k):
            resto = tipo_txt[len(k):].strip(" -·:") if not nome else ""
            quem = (nome or resto).strip()
            if k == "pagamento" and not quem:
                return "despesa", "boleto", None, "Pagamento de boleto/conta", ""
            return v[0], v[1], v[2], v[3], quem
    return "despesa", "outro", None, _txt(bruto, 80) or "Saída do Mercado Pago", ""


def ler_extrato_mp(texto: str) -> list[dict]:
    """CSV do Extrato da conta do Mercado Pago (RELEASE_DATE;TRANSACTION_TYPE;REFERENCE_ID;TRANSACTION_NET_AMOUNT;PARTIAL_BALANCE, ou os nomes
    em português). As linhas de resumo antes do cabeçalho (saldo inicial, créditos, débitos) são puladas."""
    import csv
    linhas = [l for l in re.split(r"\r\n|\n|\r", (texto or "").lstrip("\ufeff")) if l.strip()]
    for i, l in enumerate(linhas):
        sep = ";" if l.count(";") >= l.count(",") else ","
        cab = [_sem_acento(c).strip().strip('"').upper() for c in next(csv.reader([l], delimiter=sep))]
        idx = {k: next((cab.index(n) for n in nomes if n in cab), None) for k, nomes in _EXTRATO_COLS.items()}
        if idx["data"] is not None and idx["tipo"] is not None and idx["valor"] is not None:
            break
    else:
        return []
    out = []
    for n, l in enumerate(linhas[i + 1:], start=i + 2):
        v = next(csv.reader([l], delimiter=sep))
        g = lambda k: v[idx[k]].strip() if idx[k] is not None and idx[k] < len(v) else ""   # noqa: E731
        valor, dia = _valor_br(g("valor")), _data_br(g("data"))
        if valor is None or not dia:
            continue
        out.append({"linha": n, "data": dia, "texto": g("tipo"), "ref": _txt(g("ref"), 60), "valor": valor})
    return out


def importar_extrato_mp(con, texto: str, aplicar: bool, ator: str) -> dict:
    """Simular primeiro, depois importar. Só as SAÍDAS (valor negativo) viram despesa; entradas (Liberação de dinheiro, Venda com Pix, Pix
    recebido) ficam de fora: as receitas já vêm de payments/search e não podem contar duas vezes. Única pela referência do movimento; se o
    relatório de liberações já trouxe o mesmo movimento, completa o nome de quem recebeu e o tipo, sem duplicar."""
    trs = ler_extrato_mp(texto)
    if not trs:
        raise HTTPException(400, "Não achei as colunas do Extrato do Mercado Pago (data, descrição, referência e valor): confira se é o CSV do Extrato")
    linhas = []
    for t in trs:
        if t["valor"] >= 0:
            linhas.append(dict(t, situacao="entrada"))
            continue
        tipo, meio, cat, rotulo, quem = classificar_extrato(t["texto"])
        valor = abs(t["valor"])
        chave = f"mpx:{t['ref']}" if t["ref"] else "mpx:h:" + hashlib.sha256(f"{t['data']}|{valor:.2f}|{t['texto'].lower()}".encode()).hexdigest()[:24]
        ja = con.execute("SELECT id FROM despesa WHERE chave=?", (chave,)).fetchone()
        rel = None if ja or not t["ref"] else con.execute("SELECT id, contraparte FROM despesa WHERE mp_ref=? AND chave LIKE 'mp:%' AND ABS(valor-?)<0.005", (t["ref"], valor)).fetchone()
        if not ja and not rel and t["ref"]:       # contrato 1.35: a mesma saída já veio da busca de pagamentos (id do pagamento ou referência)
            rel = con.execute("""SELECT d.id, d.contraparte FROM despesa d WHERE d.chave LIKE 'mpp:%' AND (d.mp_ref=? OR d.mp_ref IN
                                 (SELECT mp_id FROM mp_pagamento WHERE external_reference=?))""", (t["ref"], t["ref"])).fetchone()
        linhas.append(dict(t, valor=valor, tipo=tipo, meio=meio, categoria=cat, descricao=rotulo, contraparte=quem, chave=chave,
                           situacao="ja_importada" if ja else ("completa" if rel else "nova"), despesa_id=(ja or rel or [None])[0]))
    if aplicar:
        for x in linhas:
            if x["situacao"] == "nova":
                did = con.execute("""INSERT OR IGNORE INTO despesa (conta_id, data, valor, meio, contraparte, descricao, origem, chave, tipo, categoria, justificativa, mp_ref, criado_por)
                                     VALUES (?,?,?,?,?,?, 'mp', ?,?,?,?,?,?)""",
                                  (_fin().CONTA_MP, x["data"], x["valor"], x["meio"], _txt(x["contraparte"], 160) or None, x["descricao"], x["chave"], x["tipo"], x["categoria"],
                                   {"tarifas": "Tarifa cobrada pelo Mercado Pago", "impostos": "Imposto retido pelo Mercado Pago"}.get(x["categoria"] or ""), x["ref"] or None, ator)).lastrowid
                if did:
                    _ev(con, did, "importada", ator, {"origem": "extrato do Mercado Pago", "ref": x["ref"]})
            elif x["situacao"] == "completa":
                con.execute("UPDATE despesa SET contraparte=COALESCE(NULLIF(contraparte,''), ?), descricao=CASE WHEN chave LIKE 'mpp:%' THEN descricao ELSE ? END, "
                            "meio=CASE WHEN chave LIKE 'mpp:%' THEN meio ELSE ? END, alterado_por=? WHERE id=?",   # da busca de pagamentos: o meio exato fica
                            (_txt(x["contraparte"], 160) or None, x["descricao"], x["meio"], ator, x["despesa_id"]))
                _ev(con, x["despesa_id"], "alterada", ator, {"origem": "extrato do Mercado Pago", "ref": x["ref"]})
        con.commit()
    sai = [x for x in linhas if x["situacao"] != "entrada"]
    return {"simulado": not aplicar, "linhas": linhas[:500], "novas": sum(1 for x in sai if x["situacao"] == "nova"),
            "completadas": sum(1 for x in sai if x["situacao"] == "completa"), "ja_importadas": sum(1 for x in sai if x["situacao"] == "ja_importada"),
            "entradas_ignoradas": sum(1 for x in linhas if x["situacao"] == "entrada"), "total_saidas": round(sum(x["valor"] for x in sai), 2)}


def _meses(inicio: str, fim: date) -> list[tuple[str, str, str]]:
    a, m = int(inicio[:4]), int(inicio[5:7])
    out = []
    while (a, m) <= (fim.year, fim.month):
        ini = date(a, m, 1)
        ult = date(a + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        out.append((f"{a}-{m:02d}", ini.isoformat(), min(ult, fim).isoformat()))
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return out


ROTA_CFG = "/wp-json/camp/v1/painel/mp/relatorio/config"   # contrato 1.34 (plugin 1.43.0): ver e criar a configuração do relatório


def _erro_site(r, acao: str) -> tuple[str, str]:
    """(código, mensagem exata) de uma resposta de erro do site/Mercado Pago, para mostrar na tela do jeito que veio."""
    try:
        j = r.json() or {}
    except Exception:  # noqa: BLE001
        j = {}
    j = j if isinstance(j, dict) else {}
    cod = _txt(j.get("code"), 60)
    msg = _txt(j.get("message"), 240)
    dados = j.get("data") if isinstance(j.get("data"), dict) else {}
    mp = _txt(dados.get("mp_mensagem"), 200)
    if dados.get("mp_http") is not None:
        msg += f" (Mercado Pago: HTTP {int(dados.get('mp_http') or 0)}{', ' + mp if mp else ''})"
    if r.status_code in (401, 403):
        return "senha_site", f"O site recusou a senha do painel ao {acao} (HTTP {r.status_code}). Confira a senha do site em Configurações."
    if r.status_code == 404 and not cod.startswith("camp_mp"):
        return "sem_rota", f"O site ainda não tem a rota para {acao} (HTTP 404): atualize o plugin da CAMP no site."
    if r.status_code == 409 or cod == "camp_mp_desligado":
        return "desligado", msg or "O Mercado Pago está desligado ou sem a chave no site."
    if cod == "camp_mp_sem_config":
        return "sem_config", msg or "Falta configurar o relatório no Mercado Pago."
    return cod or f"http_{r.status_code}", msg or f"O site respondeu {r.status_code} ao {acao}."


def _est(con, k: str, v) -> None:
    _fin()._estado_set(con, "saidas_" + k, "" if v is None else str(v))


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def rodada_mp(con, wp=None, force: bool = False, max_pedidos: int = 3) -> dict:
    """Uma volta das saídas do Mercado Pago (chamada pelo coletor do Financeiro ou pelo botão "Buscar saídas agora", nunca dentro de uma
    requisição). force: pede de novo o mês corrente e o anterior sem esperar as 6 h/20 h. Grava o estado e o erro EXATO para a tela
    (CAMP-FIN-CONSERTOS: Rafael não achava as saídas e nada dizia por quê). Nunca levanta."""
    out = {"pedidos": 0, "baixados": 0, "novas": 0, "sem_rota": False, "desligado": False, "erro": None, "codigo": ""}
    if _cfg(con, "despesas.mp_relatorio", "1") != "1":
        out["desligado_config"] = True
        return out
    fi = _fin()
    try:
        _est(con, "ultima_volta", _agora())
        con.commit()
        wp = wp or fi._wp()
        hoje = fi.hoje()
        r = wp.h.get(ROTA_RELS, params={})
        if r.status_code >= 400:
            cod, msg = _erro_site(r, "listar os relatórios do Mercado Pago")
            out.update(codigo=cod, erro=msg, sem_rota=cod == "sem_rota", desligado=cod == "desligado")
            if cod == "sem_config":
                _est(con, "config", "falta")
            _est(con, "erro", msg)
            _est(con, "erro_codigo", cod)
            con.commit()
            return out
        prontos = {}
        for x in (r.json() or {}).get("itens") or []:
            if isinstance(x, dict) and str(x.get("status") or "processed").lower() in ("processed", "ready", "enabled", ""):
                d0 = fi.dia_sp(x.get("begin_date"))
                if d0 and (d0 not in prontos or str(x.get("criado") or "") > str(prontos[d0].get("criado") or "")):
                    prontos[d0] = x
        agora = datetime.now(timezone.utc)
        recentes = {m[0] for m in _meses(fi._cfg(con, "financeiro.mp_inicio", "2026-01-01"), hoje)[-2:]}
        erros = []
        for per, de, ate in reversed(_meses(fi._cfg(con, "financeiro.mp_inicio", "2026-01-01"), hoje)):   # o mês corrente primeiro: é o que o Rafael procura
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
                    _est(con, "ultimo_recebido", agora.strftime("%Y-%m-%d %H:%M:%S"))
                    con.commit()
                    continue
                cod, msg = _erro_site(rd, f"baixar o relatório de {per[5:7]}/{per[:4]}")
                con.execute("UPDATE mp_relatorio SET erro=? WHERE periodo=?", (msg, per))
                erros.append((cod, msg))
            precisa = not st["pedido_em"] or (not st["baixado_em"] and agora - datetime.fromisoformat(st["pedido_em"]).replace(tzinfo=timezone.utc) > timedelta(hours=6)) \
                or (per in recentes and st["baixado_em"] and agora - datetime.fromisoformat(st["baixado_em"]).replace(tzinfo=timezone.utc) > timedelta(hours=20)
                    and (not st["pedido_em"] or st["pedido_em"] < st["baixado_em"])) \
                or (force and per in recentes and not (arq and novo))
            if precisa and out["pedidos"] < max_pedidos:
                rp = wp.h.post(ROTA_REL, json={"desde": de, "ate": ate})
                if rp.status_code < 400:
                    con.execute("UPDATE mp_relatorio SET pedido_em=?, erro=NULL WHERE periodo=?", (agora.strftime("%Y-%m-%d %H:%M:%S"), per))
                    out["pedidos"] += 1
                    _est(con, "ultimo_pedido", agora.strftime("%Y-%m-%d %H:%M:%S"))
                    _est(con, "config", "ok")
                else:
                    cod, msg = _erro_site(rp, f"pedir o relatório de {per[5:7]}/{per[:4]}")
                    con.execute("UPDATE mp_relatorio SET erro=? WHERE periodo=?", (msg, per))
                    erros.append((cod, msg))
                    if cod == "sem_config":
                        _est(con, "config", "falta")
                        break                      # sem configuração, nenhum mês sai: não adianta pedir os outros
        if erros:
            out["codigo"], out["erro"] = erros[0]
        _est(con, "erro", out["erro"] or "")
        _est(con, "erro_codigo", out["codigo"] or "")
        _est(con, "novas_ultima", out["novas"])
        con.commit()
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:200]
        out["codigo"] = "falha"
        try:
            _est(con, "erro", "A busca das saídas falhou: " + out["erro"])
            _est(con, "erro_codigo", "falha")
            con.commit()
        except Exception:  # noqa: BLE001
            pass
        registrar(logging.WARNING, "despesas_mp", "Saídas do Mercado Pago com problema", erro=type(e).__name__)
    return out


def estado_saidas(con) -> dict:
    """A linha de situação das saídas do Mercado Pago (Despesas): pedido, recebido, quantas, próxima volta, erro exato, configuração."""
    fi = _fin()
    g = lambda k: fi._estado(con, "saidas_" + k)   # noqa: E731
    m = fi.mp_coleta_min(con)
    ult = fi._estado(con, "ultima_rodada")
    prox = None
    if m > 0 and ult:
        try:
            prox = (datetime.fromisoformat(ult) + timedelta(minutes=m)).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            prox = None
    pend = [dict(r) for r in con.execute("SELECT periodo, pedido_em, baixado_em, linhas, erro FROM mp_relatorio ORDER BY periodo")]
    return {"ligado": _cfg(con, "despesas.mp_relatorio", "1") == "1", "tem_site": fi._tem_site(con), "coleta_min": m,
            "em_andamento": _BUSCA.locked(), "ultima_volta": g("ultima_volta") or None, "ultimo_pedido": g("ultimo_pedido") or None,
            "ultimo_recebido": g("ultimo_recebido") or None, "proxima": prox,
            "importadas": con.execute("SELECT COUNT(*) FROM despesa WHERE origem='mp' AND apagado_em IS NULL").fetchone()[0],
            "novas_ultima": int(g("novas_ultima") or 0), "erro": g("erro") or None, "erro_codigo": g("erro_codigo") or None,
            "config": g("config") or None, "aguardando": [p["periodo"] for p in pend if p["pedido_em"] and not p["baixado_em"]], "meses": pend}


import threading as _threading   # noqa: E402
_BUSCA = _threading.Lock()


def _buscar_fundo() -> None:
    if not _BUSCA.acquire(blocking=False):
        return
    try:
        con = connect()
        try:
            rodada_mp(con, force=True)
        finally:
            con.close()
    finally:
        _BUSCA.release()


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
        _fin().reprocessar_saidas_mp(con)        # pagamentos feitos pela CAMP (busca do Mercado Pago) viram despesa; idempotente
        ls = listar(con, d1, d2, conta, categoria, bool(pendentes), q)
        fila = listar(con, "2000-01-01", "2100-12-31", so_pendentes=True)
        return {"periodo": {"de": d1, "ate": d2}, "itens": ls, "total": round(sum(x["valor"] for x in ls), 2), "categorias": categorias(con), "meios": MEIOS,
                "vinculos": VINCULOS, "contas": _fin().contas(con), "precisa_justificar": fila, "n_precisa": len(fila),
                "transferencias": [x for x in listar(con, d1, d2, conta, com_transferencias=True) if x["tipo"] == "transferencia_propria"],
                "mp_relatorios": [dict(r) for r in con.execute("SELECT periodo, pedido_em, baixado_em, linhas, erro FROM mp_relatorio ORDER BY periodo")], "saidas_mp": estado_saidas(con),
                "doacoes": _doacoes(con), "notas_pedidas": _notas_pedidas(con),
                "notas_lembrete_dias": _notas_dias(con), "orcamento": _orcamento_opcoes(con)}
    finally:
        con.close()


def _orcamento_opcoes(con) -> dict:
    """CAMP-ROUANET: itens do orçamento de cada conta de projeto, para o seletor "Item do orçamento" ("16 · Impressão")."""
    try:
        from . import rouanet
        return rouanet.opcoes_todas(con)
    except Exception:  # noqa: BLE001 (banco sem a migração 254)
        return {}


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
    orcamento_item: int | None = None      # CAMP-ROUANET: item do orçamento (conta de projeto; obrigatório nela)
    nf_numero: str | None = None           # número da nota fiscal (prestação de contas)


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
    if b.orcamento_item is not None:
        v["orcamento_item"] = b.orcamento_item or None
    for k, n in (("contraparte", 160), ("descricao", 300), ("justificativa", 2000), ("projeto", 120), ("vinculo_ref", 80), ("nf_numero", 40)):
        if getattr(b, k) is not None:
            v[k] = _txt(getattr(b, k), n) or None
    if b.restrito is not None:
        v["restrito"] = 1 if b.restrito else 0
    if b.tarefa_id is not None:
        if b.tarefa_id and not con.execute("SELECT 1 FROM doacao_tarefa WHERE id=?", (b.tarefa_id,)).fetchone():
            raise HTTPException(400, "Tarefa da doação não encontrada")
        v["tarefa_id"] = b.tarefa_id or None
    return v


def _item_projeto(con, conta_id: int, v: dict, antes: dict | None, justificando: bool) -> None:
    """CAMP-ROUANET: na conta de projeto incentivado, o item do orçamento é obrigatório e precisa existir no orçamento da conta."""
    from . import rouanet
    if not rouanet.eh_projeto(con, conta_id):
        return
    item = v["orcamento_item"] if "orcamento_item" in v else (antes or {}).get("orcamento_item")
    if item and not rouanet.item_existe(con, conta_id, item):
        raise HTTPException(400, f"O item {item} não está no orçamento deste projeto")
    if not item and (justificando or antes is None or "orcamento_item" in v):
        raise HTTPException(400, "Projeto incentivado: escolha o item do orçamento")


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
        _item_projeto(con, v["conta_id"], v, None, True)
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


@router.post("/extrato-mp")
def extrato_mp(b: dict, u: dict = Depends(auth.exige("admin"))) -> dict:
    """{base64 (do CSV do Extrato do Mercado Pago), aplicar: false} → simulação (o que entra, o que completa, o que já está); com aplicar: true
    importa só as SAÍDAS novas (CAMP-FIN-CONSERTOS: o Extrato tem o nome de quem recebeu, como o Rafael vê no aplicativo)."""
    try:
        dados = base64.b64decode(re.sub(r"^data:[^,]*,", "", str(b.get("base64") or "")).strip(), validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(400, "O arquivo chegou incompleto: escolha de novo.") from e
    if len(dados) > 5 * 1024 * 1024:
        raise HTTPException(400, "Extrato grande demais (até 5 MB)")
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError:
        texto = dados.decode("latin-1")
    con = connect()
    try:
        return importar_extrato_mp(con, texto, bool(b.get("aplicar")), _ator(u))
    finally:
        con.close()


@router.get("/mp/estado")
def mp_estado(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return estado_saidas(con)
    finally:
        con.close()


@router.post("/mp/buscar")
def mp_buscar(u: dict = Depends(auth.exige("admin"))) -> dict:
    """"Buscar saídas agora": uma volta em segundo plano (pede de novo o mês corrente e o anterior; baixa o que já estiver pronto)."""
    con = connect()
    try:
        if _cfg(con, "despesas.mp_relatorio", "1") != "1":
            raise HTTPException(409, "A busca das saídas do Mercado Pago está desligada (despesas.mp_relatorio)")
        if not _fin()._tem_site(con):
            raise HTTPException(409, "Falta a senha do site em Configurações: sem ela o painel não lê a conta do Mercado Pago")
    finally:
        con.close()
    ja = _BUSCA.locked()
    if not ja:
        _threading.Thread(target=_buscar_fundo, daemon=True).start()
    return {"ok": True, "ja_rodando": ja}


@router.post("/mp/config")
def mp_config(b: dict, u: dict = Depends(auth.exige("admin"))) -> dict:
    """"Configurar relatório no Mercado Pago" (pelo site; contrato 1.34). Sem aplicar: só mostra o que será configurado (simular). Com
    aplicar: true (admin confirmou), o site cria ou ajusta a configuração do relatório de liberações."""
    aplicar = bool(b.get("aplicar"))
    con = connect()
    try:
        try:
            r = _fin()._wp().h.post(ROTA_CFG, json={"simular": not aplicar})
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Não consegui falar com o site: {type(e).__name__}") from e
        if r.status_code >= 400:
            cod, msg = _erro_site(r, "configurar o relatório no Mercado Pago")
            raise HTTPException(409 if cod in ("sem_rota", "desligado") else 502, msg)
        d = r.json() or {}
        if aplicar:
            _est(con, "config", "ok")
            _est(con, "erro", "")
            _est(con, "erro_codigo", "")
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('despesa','mp_config','mp_config',?,?)",
                        (_ator(u), json.dumps({"acao": d.get("acao") or "", "colunas": len(d.get("colunas") or [])}, ensure_ascii=False)))
            con.commit()
        return {"simulado": not aplicar, "acao": d.get("acao") or "", "colunas": d.get("colunas") or [], "existia": bool(d.get("existia")),
                "prefixo": d.get("prefixo") or "", "faltavam": d.get("faltavam") or []}
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
        _item_projeto(con, v.get("conta_id", antes["conta_id"]), v, antes, "categoria" in v or "justificativa" in v)
        if v:
            con.execute(f"UPDATE despesa SET {', '.join(k + '=?' for k in v)}, alterado_por=?, alterado_em=datetime('now') WHERE id=?", (*v.values(), _ator(u), did))
        _tarefa(con, did, v, b.preencher_tarefa, _ator(u))
        just = ("categoria" in v or "justificativa" in v) and antes["falta"]
        _ev(con, did, "justificada" if just else "alterada", _ator(u), {k: v[k] for k in v if k != "justificativa"} | ({"justificativa": True} if "justificativa" in v else {}))
        con.commit()
        return _detalhe(con, did)
    finally:
        con.close()


@router.post("/{did}/entrada")
def marcar_entrada(did: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """"Isto é uma entrada" numa saída do Mercado Pago: sai das despesas (fica no histórico) e o pagamento volta às receitas. Lembrado: nem a
    busca seguinte nem o relatório/Extrato trazem de volta como despesa."""
    con = connect()
    try:
        x = _detalhe(con, did)
        if not x["pode_ser_entrada"]:
            raise HTTPException(400, "Só para saídas da conta do Mercado Pago (com a referência do pagamento). Lançamento à mão ou do OFX: use Apagar")
        fi = _fin()
        fi.gravar_direcao(con, x["mp_ref"], "entrada", None, _ator(u), {"despesa": did})
        con.execute("UPDATE despesa SET apagado_em=datetime('now'), apagado_por=?, apagado_motivo=? WHERE id=?", (_ator(u), fi.MOTIVO_ENTRADA, did))
        _ev(con, did, "apagada", _ator(u), {"motivo": fi.MOTIVO_ENTRADA, "mp_id": x["mp_ref"]})
        con.commit()
        fi.reprocessar_saidas_mp(con, _ator(u))
        na = bool(con.execute("SELECT 1 FROM mp_pagamento WHERE mp_id=?", (x["mp_ref"],)).fetchone())
        return {"ok": True, "direcao": "entrada", "na_receita": na}
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
