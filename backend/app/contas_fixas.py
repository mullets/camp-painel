"""Financeiro · contas fixas (CAMP-FIN, 24/11/2026). Rafael: "Aluguel, funcionário?".

Compromissos que se repetem: aluguel da sede, salário de cada pessoa, INSS, internet… Cada um tem nome, categoria, valor esperado (ou
faixa), dia do vencimento, periodicidade (mensal, anual, 13º em dezembro), a PISTA (o nome ou o CNPJ que aparece na descrição do Mercado
Pago) e o começo e o fim.

- Todo mês o painel procura a saída da conta do Mercado Pago que pagou cada uma: a pista na contraparte/descrição + valor (± 5%, ou dentro
  da faixa) + data perto do vencimento (de 12 dias antes a 15 depois). Nada é gravado sozinho: a fila "Precisa justificar" mostra
  "Parece a conta fixa X" com a categoria e a justificativa prontas ("Aluguel da sede · novembro/2026") e um clique confirma.
- Situação de cada mês: **pago** (com a despesa; "confirmar" enquanto ninguém confirmou), **a vencer**, **atrasado** (vencimento + 3 dias
  sem pagamento; alerta na Home do admin) e **valor diferente** (achou a pista na data, mas o valor não bate).
- O detector de recorrentes sugere "Parece um pagamento mensal: transformar em conta fixa?". A projeção de 3 meses usa as contas fixas.
- Salário é dado sensível: só admin e master (a API dá 403 aos outros); na Home o alerta de pessoal não traz o nome; a exportação agrupa o
  pessoal sem nomes (padrão); a exclusão LGPD de uma pessoa tira o nome dela daqui e das despesas ligadas, e os valores ficam.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api/financeiro/contas-fixas", tags=["contas_fixas"])

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
PERIODICIDADES = {"mensal": "mensal", "anual": "anual", "decimo_terceiro": "13º (em dezembro)"}
SITUACOES = {"pago": "pago", "a_vencer": "a vencer", "atrasado": "atrasado", "valor_diferente": "valor diferente"}
ANTES, DEPOIS = 12, 15          # janela de datas em volta do vencimento (dias)
REMOVIDO = "(nome removido)"
TEXTO_SUGESTAO = "Parece um pagamento mensal: transformar em conta fixa?"


def _fin():
    from . import financeiro
    return financeiro


def _desp():
    from . import despesas
    return despesas


def _ia():
    from . import financeiro_ia
    return financeiro_ia


def _cfg_n(con, chave: str, padrao: float) -> float:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    try:
        return float(r[0]) if r and r[0] not in (None, "") else padrao
    except ValueError:
        return padrao


def pessoal(cat: str) -> bool:
    return cat in _desp().PESSOAL


# ---------------------------------------------------------------- vencimentos
def _ultimo_dia(a: int, m: int) -> int:
    return ((date(a + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)).day


def vencimento(cf: dict, a: int, m: int) -> date | None:
    """A data em que a conta fixa vence no mês a-m (None = não vence neste mês)."""
    comp = f"{a}-{m:02d}"
    if comp < (cf["inicio"] or "0000")[:7] or (cf.get("fim") and comp > cf["fim"][:7]):
        return None
    per = cf["periodicidade"]
    if per == "decimo_terceiro" and m != 12:
        return None
    if per == "anual" and m != (cf.get("mes_anual") or int((cf["inicio"] or "2000-01")[5:7])):
        return None
    return date(a, m, min(max(int(cf["dia"] or 1), 1), _ultimo_dia(a, m)))


def _meses_entre(d1: date, d2: date) -> list[tuple[int, int]]:
    out, a, m = [], d1.year, d1.month
    while (a, m) <= (d2.year, d2.month):
        out.append((a, m))
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return out


def esperado(cf: dict) -> float:
    return round((cf["valor"] + cf["valor_max"]) / 2, 2) if cf.get("valor_max") else cf["valor"]


def justificativa(cf: dict, comp: str) -> str:
    a, m = int(comp[:4]), int(comp[5:7])
    return f"{cf['nome']} · 13º de {a}" if cf["periodicidade"] == "decimo_terceiro" else f"{cf['nome']} · {MESES[m - 1]}/{a}"


# ---------------------------------------------------------------- casar com as saídas
def _palavras(s: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]+", " ", _ia().sem_acento(s)).split())


def bate_pista(cf: dict, d: dict) -> bool:
    pista = (cf.get("pista") or "").strip()
    if not pista:
        return False
    alvo = f"{d.get('contraparte') or ''} {d.get('descricao') or ''}"
    dig = re.sub(r"\D", "", pista)
    if len(dig) in (11, 14) and len(dig) >= len(re.sub(r"[\d./-]", "", pista)):    # CNPJ/CPF
        return dig in re.sub(r"\D", "", alvo)
    pn = _ia().normalizar(pista).split() or _ia().sem_acento(pista).split()
    return bool(pn) and set(pn) <= _palavras(alvo)


def valor_ok(cf: dict, v: float, tol: float) -> bool:
    return cf["valor"] * (1 - tol) - 0.005 <= v <= (cf.get("valor_max") or cf["valor"]) * (1 + tol) + 0.005


def contas(con, com_inativas: bool = True) -> list[dict]:
    sql = "SELECT * FROM conta_fixa WHERE apagado_em IS NULL" + ("" if com_inativas else " AND ativa=1")
    return [dict(r) for r in con.execute(sql + " ORDER BY ativa DESC, nome COLLATE NOCASE, id")]


def casamentos(con, d1: date, d2: date, cfs: list[dict] | None = None) -> dict[tuple[int, str], dict]:
    """{(conta_fixa_id, AAAA-MM): {despesa, confirmado, valor_ok, motivo}} para os vencimentos entre d1 e d2. Primeiro o que uma pessoa já
    confirmou; depois as saídas que batem (pista + valor + data, cada saída usada uma vez, a mais parecida primeiro). Nada é gravado."""
    tol = _cfg_n(con, "contas_fixas.tolerancia", 5) / 100
    cfs = cfs if cfs is not None else contas(con, com_inativas=False)
    por_id = {c["id"]: c for c in cfs}
    out: dict[tuple[int, str], dict] = {}
    usados: set[int] = set()
    for r in con.execute("SELECT p.conta_fixa_id, p.competencia, p.despesa_id, p.confirmado_por, d.* FROM conta_fixa_pagamento p JOIN despesa d ON d.id=p.despesa_id "
                         "WHERE d.apagado_em IS NULL"):
        usados.add(r["despesa_id"])
        cf = por_id.get(r["conta_fixa_id"])
        if cf:
            dd = {k: r[k] for k in ("id", "data", "valor", "contraparte", "descricao", "categoria", "justificativa", "conta_id")}
            out[(cf["id"], r["competencia"])] = {"despesa": dd, "confirmado": True, "valor_ok": valor_ok(cf, r["valor"], tol),
                                                 "motivo": f"confirmado por {r['confirmado_por'] or 'uma pessoa'}"}
    venc = []
    for cf in cfs:
        for a, m in _meses_entre(d1, d2):
            v = vencimento(cf, a, m)
            if v and (cf["id"], f"{a}-{m:02d}") not in out:
                venc.append((cf, f"{a}-{m:02d}", v))
    if not venc:
        return out
    ini = min(v for _, _, v in venc) - timedelta(days=ANTES)
    fim = max(v for _, _, v in venc) + timedelta(days=DEPOIS)
    ds = [dict(r) for r in con.execute("SELECT id, data, valor, contraparte, descricao, categoria, justificativa, conta_id FROM despesa "
                                       "WHERE apagado_em IS NULL AND tipo='despesa' AND data BETWEEN ? AND ?", (ini.isoformat(), fim.isoformat()))
          if r["id"] not in usados]
    pares = []
    for cf, comp, v in venc:
        for d in ds:
            if d["conta_id"] != cf["conta_id"]:
                continue
            dist = (date.fromisoformat(d["data"]) - v).days
            if not -ANTES <= dist <= DEPOIS:
                continue
            ok_v = valor_ok(cf, d["valor"], tol)
            pista = bate_pista(cf, d)
            if not pista and not (not (cf.get("pista") or "").strip() and ok_v and (d["categoria"] or cf["categoria"]) == cf["categoria"]):
                continue
            if not ok_v and not 0.5 * cf["valor"] <= d["valor"] <= 2 * (cf.get("valor_max") or cf["valor"]):
                continue
            pares.append(((0 if ok_v else 1, abs(d["valor"] - esperado(cf)), abs(dist)), cf, comp, d, ok_v, pista, dist))
    pares.sort(key=lambda p: p[0])
    for _, cf, comp, d, ok_v, pista, dist in pares:
        if (cf["id"], comp) in out or d["id"] in usados:
            continue
        usados.add(d["id"])
        quando = "no dia do vencimento" if dist == 0 else (f"{-dist} dia(s) antes do vencimento" if dist < 0 else f"{dist} dia(s) depois do vencimento")
        motivo = (f"“{cf['pista']}” na descrição do Mercado Pago, " if pista else "sem pista: só valor e data, ") + \
                 (f"valor perto do esperado ({_fin().brl(esperado(cf))})" if ok_v else f"mas o valor é diferente do esperado ({_fin().brl(esperado(cf))})") + f", {quando}"
        out[(cf["id"], comp)] = {"despesa": d, "confirmado": False, "valor_ok": ok_v, "motivo": motivo}
    return out


def situacao(cf: dict, venc: date, cas: dict | None, hoje: date, atraso: int) -> str:
    if cas:
        return "pago" if cas["valor_ok"] else "valor_diferente"
    return "atrasado" if hoje > venc + timedelta(days=atraso) else "a_vencer"


def _cel(cf: dict, comp: str, v: date, cas: dict | None, hoje: date, atraso: int) -> dict:
    st = situacao(cf, v, cas, hoje, atraso)
    d = (cas or {}).get("despesa") or {}
    return {"competencia": comp, "vence": v.isoformat(), "situacao": st, "situacao_nome": SITUACOES[st], "esperado": esperado(cf),
            "despesa_id": d.get("id"), "valor": d.get("valor"), "data": d.get("data"), "confirmado": bool((cas or {}).get("confirmado")),
            "motivo": (cas or {}).get("motivo") or ""}


def grade(con, ano: int) -> dict:
    """Jan–dez × conta fixa: situação de cada mês, o total comprometido e o pago por mês, e o "Este mês"."""
    hoje = _fin().hoje()
    atraso = int(_cfg_n(con, "contas_fixas.atraso_dias", 3))
    cats = _desp().categorias(con)
    todas = contas(con)
    ativas = [c for c in todas if c["ativa"]]
    cas = casamentos(con, date(ano, 1, 1), date(ano, 12, 31), ativas)
    linhas = []
    tot = [{"mes": f"{ano}-{m:02d}", "comprometido": 0.0, "pago": 0.0, "n": 0, "pagas": 0, "atrasadas": 0} for m in range(1, 13)]
    for cf in todas:
        cels = []
        for m in range(1, 13):
            v = vencimento(cf, ano, m) if cf["ativa"] else None
            if not v:
                cels.append(None)
                continue
            comp = f"{ano}-{m:02d}"
            c = _cel(cf, comp, v, cas.get((cf["id"], comp)), hoje, atraso)
            cels.append(c)
            t = tot[m - 1]
            t["comprometido"] += c["esperado"]
            t["n"] += 1
            if c["valor"] is not None:
                t["pago"] += c["valor"]
                t["pagas"] += 1
            t["atrasadas"] += c["situacao"] == "atrasado"
        linhas.append(_publica(cf, cats) | {"meses": cels})
    for t in tot:
        t["comprometido"], t["pago"] = round(t["comprometido"], 2), round(t["pago"], 2)
    este = este_mes(con, hoje, ativas, cas if hoje.year == ano else None)
    return {"ano": ano, "contas": linhas, "totais": tot, "este_mes": este, "categorias": cats, "periodicidades": PERIODICIDADES, "situacoes": SITUACOES,
            "sugeridas": sugeridas(con, todas), "hoje": hoje.isoformat(), "atraso_dias": atraso, "tolerancia": _cfg_n(con, "contas_fixas.tolerancia", 5)}


def este_mes(con, hoje: date, ativas: list[dict] | None = None, cas: dict | None = None) -> dict:
    ativas = ativas if ativas is not None else contas(con, com_inativas=False)
    cas = cas if cas is not None else casamentos(con, date(hoje.year, hoje.month, 1), date(hoje.year, hoje.month, _ultimo_dia(hoje.year, hoje.month)), ativas)
    atraso = int(_cfg_n(con, "contas_fixas.atraso_dias", 3))
    comp = f"{hoje.year}-{hoje.month:02d}"
    n = pagas = atrasadas = 0
    a_pagar = 0.0
    for cf in ativas:
        v = vencimento(cf, hoje.year, hoje.month)
        if not v:
            continue
        n += 1
        st = situacao(cf, v, cas.get((cf["id"], comp)), hoje, atraso)
        if st in ("pago", "valor_diferente"):
            pagas += 1
        else:
            a_pagar += esperado(cf)
            atrasadas += st == "atrasado"
    a_pagar = round(a_pagar, 2)
    txt = (f"Este mês: {pagas} {'conta fixa paga' if pagas == 1 else 'contas fixas pagas'} de {n} · {_fin().brl(a_pagar)} a pagar") if n else ""
    return {"mes": comp, "total": n, "pagas": pagas, "atrasadas": atrasadas, "a_pagar": a_pagar, "texto": txt}


def _publica(cf: dict, cats: dict) -> dict:
    return {"id": cf["id"], "nome": cf["nome"], "categoria": cf["categoria"], "categoria_nome": cats.get(cf["categoria"], cf["categoria"]), "valor": cf["valor"],
            "valor_max": cf["valor_max"], "esperado": esperado(cf), "dia": cf["dia"], "periodicidade": cf["periodicidade"], "mes_anual": cf["mes_anual"],
            "periodicidade_nome": PERIODICIDADES.get(cf["periodicidade"], cf["periodicidade"]), "pista": cf["pista"] or "", "pessoa_nome": cf["pessoa_nome"] or "",
            "pessoa_email": cf["pessoa_email"] or "", "conta_id": cf["conta_id"], "inicio": cf["inicio"], "fim": cf["fim"] or "", "ativa": bool(cf["ativa"]),
            "pessoal": pessoal(cf["categoria"])}


def atrasadas(con, hoje: date | None = None) -> list[dict]:
    """Meses atrasados (este e o anterior) para a Home do admin."""
    hoje = hoje or _fin().hoje()
    atraso = int(_cfg_n(con, "contas_fixas.atraso_dias", 3))
    ini = (date(hoje.year, hoje.month, 1) - timedelta(days=1)).replace(day=1)
    ativas = contas(con, com_inativas=False)
    cas = casamentos(con, ini, hoje, ativas)
    cats = _desp().categorias(con)
    out = []
    for cf in ativas:
        for a, m in _meses_entre(ini, hoje):
            v = vencimento(cf, a, m)
            comp = f"{a}-{m:02d}"
            if v and situacao(cf, v, cas.get((cf["id"], comp)), hoje, atraso) == "atrasado":
                out.append({"id": cf["id"], "competencia": comp, "vence": v.isoformat(), "esperado": esperado(cf), "pessoal": pessoal(cf["categoria"]),
                            # pessoal: a Home não traz o nome da pessoa (salário é dado sensível); a tela do Financeiro traz
                            "rotulo": cats.get(cf["categoria"], cf["categoria"]) if pessoal(cf["categoria"]) else cf["nome"]})
    return out


def sugestao_para(con, d: dict) -> dict | None:
    """A conta fixa que esta despesa parece pagar (para a fila "Precisa justificar"): categoria e justificativa prontas e o porquê."""
    try:
        dia = date.fromisoformat(d["data"])
    except (KeyError, TypeError, ValueError):
        return None
    cas = casamentos(con, dia - timedelta(days=DEPOIS + 31), dia + timedelta(days=ANTES + 31))
    cats = _desp().categorias(con)
    por_id = {c["id"]: c for c in contas(con, com_inativas=False)}
    for (cid, comp), c in cas.items():
        if c["despesa"]["id"] == d.get("id") and cid in por_id:
            cf = por_id[cid]
            return {"conta_fixa_id": cid, "nome": cf["nome"], "competencia": comp, "categoria": cf["categoria"], "categoria_nome": cats.get(cf["categoria"], cf["categoria"]),
                    "justificativa": justificativa(cf, comp), "valor_ok": c["valor_ok"], "confirmado": c["confirmado"], "motivo": c["motivo"],
                    "esperado": esperado(cf)}
    return None


def _cobre(cf: dict, r: dict) -> bool:
    p = (cf.get("pista") or "").strip()
    return bool(p) and (_ia().normalizar(p) == r["chave"] or re.sub(r"\D", "", p) == r["chave"] or bate_pista(cf, {"contraparte": r["nome"]}))


def sugeridas(con, todas: list[dict] | None = None) -> list[dict]:
    """Do detector de recorrentes: padrão mensal que nenhuma conta fixa cobre → "transformar em conta fixa?"."""
    todas = todas if todas is not None else contas(con)
    out = []
    for r in _ia().recorrentes(con):
        if any(_cobre(cf, r) for cf in todas):
            continue
        out.append({"nome": r["nome"], "pista": r["nome"], "valor": r["valor"], "dia": int(r["ultima"][8:10]), "categoria": r["categoria"], "meses": r["meses"],
                    "texto": TEXTO_SUGESTAO, "motivo": r["motivo"]})
    return out


def previsao(con, mes: str) -> tuple[float, list[str], list[dict]]:
    """Projeção: o esperado das contas fixas que vencem no mês AAAA-MM (valor, explicações, contas)."""
    a, m = int(mes[:4]), int(mes[5:7])
    tot, ex, cs = 0.0, [], []
    for cf in contas(con, com_inativas=False):
        if vencimento(cf, a, m):
            tot += esperado(cf)
            ex.append(f"conta fixa ({cf['nome']}): {_fin().brl(esperado(cf))}")
            cs.append(cf)
    return round(tot, 2), ex, cs


# ---------------------------------------------------------------- LGPD
def anonimizar_por_email(con, email: str) -> int:
    """Tira o nome da pessoa das contas fixas dela e das despesas ligadas (contraparte e justificativa). Os valores ficam."""
    em = (email or "").strip().lower()
    if not em:
        return 0
    n = 0
    for cf in [dict(r) for r in con.execute("SELECT * FROM conta_fixa WHERE lower(pessoa_email)=?", (em,))]:
        nome = (cf["pessoa_nome"] or "").strip()
        troca = (lambda s: s.replace(nome, REMOVIDO) if s and nome else s)
        pista = cf["pista"]
        if pista and nome and (_ia().normalizar(pista) == _ia().normalizar(nome) or nome.lower() in pista.lower()):
            pista = None
        con.execute("UPDATE conta_fixa SET pessoa_nome=NULL, pessoa_email=NULL, nome=?, pista=?, alterado_por='LGPD', alterado_em=datetime('now') WHERE id=?",
                    (troca(cf["nome"]) if nome and nome in cf["nome"] else cf["nome"], pista, cf["id"]))
        n += 1
        ids = {r[0] for r in con.execute("SELECT despesa_id FROM conta_fixa_pagamento WHERE conta_fixa_id=?", (cf["id"],))}
        if nome:
            alvo = _ia().normalizar(nome)
            ids |= {r[0] for r in con.execute("SELECT id, contraparte FROM despesa WHERE contraparte IS NOT NULL") if alvo and _ia().normalizar(r[1]) == alvo}
        for did in ids:
            r = con.execute("SELECT contraparte, justificativa FROM despesa WHERE id=?", (did,)).fetchone()
            if not r:
                continue
            cp = REMOVIDO if r[0] and (not nome or nome.lower() in r[0].lower() or _ia().normalizar(r[0]) == _ia().normalizar(nome)) else r[0]
            con.execute("UPDATE despesa SET contraparte=?, justificativa=?, alterado_por='LGPD', alterado_em=datetime('now') WHERE id=?", (cp, troca(r[1]), did))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('despesa',?,'lgpd_nome_removido','LGPD','{}')", (str(did),))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('conta_fixa',?,'lgpd_nome_removido','LGPD',?)",
                    (str(cf["id"]), json.dumps({"despesas": len(ids)})))
    return n


# ---------------------------------------------------------------- rotas (só admin e master)
class ContaFixa(BaseModel):
    nome: str | None = None
    categoria: str | None = None
    valor: float | None = None
    valor_max: float | None = None
    dia: int | None = None
    periodicidade: str | None = None
    mes_anual: int | None = None
    pista: str | None = None
    pessoa_nome: str | None = None
    pessoa_email: str | None = None
    conta_id: int | None = None
    inicio: str | None = None
    fim: str | None = None
    ativa: bool | None = None


def _txt(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:n]


def _validar(con, b: ContaFixa, novo: bool, atual: dict | None = None) -> dict:
    v: dict = {}
    cats = _desp().categorias(con)
    if b.nome is not None or novo:
        if len(_txt(b.nome, 120)) < 2:
            raise HTTPException(400, "Dê um nome à conta fixa (ex.: Aluguel da sede)")
        v["nome"] = _txt(b.nome, 120)
    if b.categoria is not None or novo:
        if b.categoria not in cats:
            raise HTTPException(400, "Escolha a categoria")
        v["categoria"] = b.categoria
    if b.valor is not None or novo:
        if not b.valor or not 0 < float(b.valor) <= 10_000_000:
            raise HTTPException(400, "Valor esperado inválido")
        v["valor"] = round(float(b.valor), 2)
    if b.valor_max is not None:
        vm = round(float(b.valor_max), 2) if b.valor_max else None
        if vm is not None and vm < v.get("valor", (atual or {}).get("valor", 0)):
            raise HTTPException(400, "O valor máximo da faixa é menor que o mínimo")
        v["valor_max"] = vm
    if novo and b.dia is None and b.periodicidade == "decimo_terceiro":
        v["dia"] = 20                                        # 13º: até 20 de dezembro
    elif b.dia is not None or novo:
        if not b.dia or not 1 <= int(b.dia) <= 31:
            raise HTTPException(400, "Dia do vencimento: de 1 a 31")
        v["dia"] = int(b.dia)
    if b.periodicidade is not None or novo:
        per = b.periodicidade or "mensal"
        if per not in PERIODICIDADES:
            raise HTTPException(400, "Periodicidade: mensal, anual ou 13º")
        v["periodicidade"] = per
    if b.mes_anual is not None:
        if b.mes_anual and not 1 <= int(b.mes_anual) <= 12:
            raise HTTPException(400, "Mês do vencimento anual: de 1 a 12")
        v["mes_anual"] = int(b.mes_anual) or None
    for k, n in (("pista", 120), ("pessoa_nome", 120), ("pessoa_email", 160)):
        if getattr(b, k) is not None:
            v[k] = _txt(getattr(b, k), n) or None
    if v.get("pessoa_email") and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v["pessoa_email"]):
        raise HTTPException(400, "E-mail da pessoa inválido")
    if b.conta_id is not None:
        if not con.execute("SELECT 1 FROM financeiro_conta WHERE id=?", (b.conta_id,)).fetchone():
            raise HTTPException(400, "Conta desconhecida")
        v["conta_id"] = b.conta_id
    for k in ("inicio", "fim"):
        val = getattr(b, k)
        if val is not None or (novo and k == "inicio"):
            if not val and k == "fim":
                v["fim"] = None
                continue
            try:
                v[k] = date.fromisoformat(val or "").isoformat()
            except ValueError:
                raise HTTPException(400, "Data de começo inválida (AAAA-MM-DD)" if k == "inicio" else "Data de fim inválida (AAAA-MM-DD)")
    ini, fim = v.get("inicio", (atual or {}).get("inicio")), v.get("fim", (atual or {}).get("fim"))
    if ini and fim and fim < ini:
        raise HTTPException(400, "O fim é antes do começo")
    if b.ativa is not None:
        v["ativa"] = 1 if b.ativa else 0
    return v


def _ator(u: dict | None) -> str:
    return (u or {}).get("email") or "painel"


def _ev(con, cid: int, tipo: str, ator: str, det: dict | None = None) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('conta_fixa',?,?,?,?)", (str(cid), tipo, ator, json.dumps(det or {}, ensure_ascii=False)))


def _sem_nome(v: dict, cat: str) -> dict:
    """O que vai para o histórico: sem a pessoa; em conta de pessoal, também sem o nome e a pista (que costumam ter o nome dela)."""
    fora = ("pessoa_nome", "pessoa_email") + (("nome", "pista") if pessoal(cat) else ())
    return {k: x for k, x in v.items() if k not in fora}


def _uma(con, cid: int) -> dict:
    r = con.execute("SELECT * FROM conta_fixa WHERE id=? AND apagado_em IS NULL", (cid,)).fetchone()
    if not r:
        raise HTTPException(404, "Conta fixa não encontrada")
    return dict(r)


@router.get("")
def ver(ano: int = 0, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return grade(con, ano or _fin().hoje().year)
    finally:
        con.close()


@router.post("")
def criar(b: ContaFixa, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        v = _validar(con, b, True)
        cols = list(v)
        cid = con.execute(f"INSERT INTO conta_fixa ({', '.join(cols)}, criado_por) VALUES ({','.join('?' * len(cols))}, ?)", (*v.values(), _ator(u))).lastrowid
        _ev(con, cid, "criada", _ator(u), _sem_nome(v, v["categoria"]))
        con.commit()
        return _publica(_uma(con, cid), _desp().categorias(con))
    finally:
        con.close()


@router.put("/{cid}")
def mudar(cid: int, b: ContaFixa, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        atual = _uma(con, cid)
        v = _validar(con, b, False, atual)
        if v:
            con.execute(f"UPDATE conta_fixa SET {', '.join(k + '=?' for k in v)}, alterado_por=?, alterado_em=datetime('now') WHERE id=?", (*v.values(), _ator(u), cid))
            _ev(con, cid, "alterada", _ator(u), _sem_nome(v, v.get("categoria") or atual["categoria"]))
        con.commit()
        return _publica(_uma(con, cid), _desp().categorias(con))
    finally:
        con.close()


@router.delete("/{cid}")
def apagar(cid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        _uma(con, cid)
        con.execute("UPDATE conta_fixa SET apagado_em=datetime('now'), apagado_por=? WHERE id=?", (_ator(u), cid))
        _ev(con, cid, "apagada", _ator(u))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


class Confirmar(BaseModel):
    despesa_id: int
    competencia: str
    justificativa: str | None = None


@router.post("/{cid}/confirmar")
def confirmar(cid: int, b: Confirmar, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Um clique: liga a despesa ao mês da conta fixa e preenche a categoria e a justificativa ("Aluguel da sede · novembro/2026")."""
    con = connect()
    try:
        cf = _uma(con, cid)
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", b.competencia or "") or not vencimento(cf, int(b.competencia[:4]), int(b.competencia[5:7])):
            raise HTTPException(400, "Esta conta fixa não vence neste mês")
        d = con.execute("SELECT * FROM despesa WHERE id=? AND apagado_em IS NULL AND tipo='despesa'", (b.despesa_id,)).fetchone()
        if not d:
            raise HTTPException(404, "Despesa não encontrada")
        ja = con.execute("SELECT conta_fixa_id, competencia FROM conta_fixa_pagamento WHERE despesa_id=? OR (conta_fixa_id=? AND competencia=?)",
                         (b.despesa_id, cid, b.competencia)).fetchone()
        if ja and (ja[0], ja[1]) != (cid, b.competencia):
            raise HTTPException(409, "Esta despesa ou este mês já estão ligados a outra conta fixa: desfaça antes")
        if not ja:
            con.execute("INSERT INTO conta_fixa_pagamento (conta_fixa_id, competencia, despesa_id, confirmado_por) VALUES (?,?,?,?)",
                        (cid, b.competencia, b.despesa_id, _ator(u)))
        just = _txt(b.justificativa, 2000) or (d["justificativa"] or "").strip() or justificativa(cf, b.competencia)
        con.execute("UPDATE despesa SET categoria=?, justificativa=?, alterado_por=?, alterado_em=datetime('now') WHERE id=?", (cf["categoria"], just, _ator(u), b.despesa_id))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('despesa',?,'justificada',?,?)",
                    (str(b.despesa_id), _ator(u), json.dumps({"categoria": cf["categoria"], "justificativa": True, "conta_fixa": cid, "competencia": b.competencia})))
        _ev(con, cid, "pagamento_confirmado", _ator(u), {"despesa": b.despesa_id, "competencia": b.competencia})
        con.commit()
        return {"ok": True, "categoria": cf["categoria"], "justificativa": just}
    finally:
        con.close()


@router.delete("/{cid}/confirmar/{competencia}")
def desfazer(cid: int, competencia: str, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        _uma(con, cid)
        n = con.execute("DELETE FROM conta_fixa_pagamento WHERE conta_fixa_id=? AND competencia=?", (cid, competencia)).rowcount
        if not n:
            raise HTTPException(404, "Este mês não estava confirmado")
        _ev(con, cid, "pagamento_desfeito", _ator(u), {"competencia": competencia})
        con.commit()
        return {"ok": True}
    finally:
        con.close()
