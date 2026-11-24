"""DRE gerencial (CAMP-FIN, 24/11/2026). Rafael: "Já podemos fazer DRE nisso tudo?".

"Demonstração do resultado do período" de entidade sem fins lucrativos (superávit ou déficit, nunca "lucro"), feita SÓ com o livro do
Financeiro (receitas de `financeiro.livro` e despesas de `despesas.listar`). **DRE gerencial, por regime de caixa (data do pagamento). Não
substitui a demonstração oficial do contador (regime de competência, ITG 2002).**

- Cada natureza de receita e cada categoria de despesa cai numa linha da DRE pelo mapa `dre.mapa` (admin muda); o que não está no mapa vai
  para "Outras" com aviso. Receita de conta de projeto incentivado vai sempre para "Projeto incentivado (Rouanet)", com restrição.
- Colunas: o período escolhido, o período anterior (do mesmo tamanho) e o acumulado do ano. Visão mensal: janeiro a dezembro e o total.
- Visões: Consolidado, Operacional (contas sem restrição) e cada conta com restrição, sempre separada e com o rótulo.
- Clicar numa linha abre os lançamentos que a formam.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api/financeiro/dre", tags=["dre"])

AVISO = ("DRE gerencial, por regime de caixa (data do pagamento). Não substitui a demonstração oficial do contador "
         "(regime de competência, ITG 2002).")
TITULO = "Demonstração do resultado do período"
# (chave, rótulo, tipo, nível): tipo grupo = título; rec/desp = linha com valor; soma = subtotal calculado
LINHAS = [
    ("g_receitas", "RECEITAS", "grupo", 0),
    ("g_sem", "Sem restrição", "grupo", 1),
    ("rec_doacoes", "Doações", "rec", 2),
    ("rec_contribuicoes", "Contribuições dos Amigos", "rec", 2),
    ("rec_patrocinios", "Patrocínios", "rec", 2),
    ("rec_servicos", "Ingressos e serviços", "rec", 2),
    ("rec_outras", "Outras receitas", "rec", 2),
    ("g_com", "Com restrição", "grupo", 1),
    ("rec_vinculadas", "Doações vinculadas (ex.: preservação de acervo doado)", "rec", 2),
    ("rec_projeto", "Projeto incentivado (Rouanet)", "rec", 2),
    ("receita_bruta", "(=) Receita bruta", "soma", 0),
    ("tarifas_receb", "(−) Tarifas e taxas de recebimento (Mercado Pago)", "tarifa", 1),
    ("receita_liquida", "(=) Receita líquida", "soma", 0),
    ("g_despesas", "DESPESAS", "grupo", 0),
    ("desp_atividades", "Com atividades e projetos (conservação, frete, serviços ligados ao acervo e a eventos)", "desp", 1),
    ("desp_admin", "Administrativas (tecnologia, manutenção, impostos e taxas, outras)", "desp", 1),
    ("desp_pessoal", "Pessoal e estagiários", "desp", 1),
    ("desp_financeiras", "Financeiras (tarifas bancárias que não são de recebimento)", "desp", 1),
    ("desp_outras", "Outras (sem classificação)", "desp", 1),
    ("despesas_total", "(=) Total das despesas", "soma", 0),
    ("resultado", "(=) Superávit / Déficit do período", "soma", 0),
]
ROTULO = {k: r for k, r, _, _ in LINHAS}
REC = [k for k, _, t, _ in LINHAS if t == "rec"]
DESP = [k for k, _, t, _ in LINHAS if t == "desp"]
MAPA_PADRAO = {
    "natureza:doacoes": "rec_doacoes", "natureza:contribuicoes": "rec_contribuicoes", "natureza:patrocinios": "rec_patrocinios",
    "natureza:servicos": "rec_servicos", "natureza:outras": "rec_outras", "natureza:doacoes_restricao": "rec_vinculadas",
    "categoria:materiais": "desp_atividades", "categoria:frete": "desp_atividades", "categoria:servicos": "desp_atividades",
    "categoria:eventos": "desp_atividades", "categoria:tecnologia": "desp_admin", "categoria:manutencao": "desp_admin",
    "categoria:impostos": "desp_admin", "categoria:outras": "desp_admin", "categoria:pessoal": "desp_pessoal", "categoria:tarifas": "desp_financeiras",
}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _fin():
    from . import financeiro
    return financeiro


def _desp():
    from . import despesas
    return despesas


def mapa(con) -> dict[str, str]:
    m = dict(MAPA_PADRAO)
    r = con.execute("SELECT valor FROM configuracao WHERE chave='dre.mapa'").fetchone()
    try:
        extra = json.loads(r[0]) if r and r[0] else {}
    except ValueError:
        extra = {}
    for k, v in (extra if isinstance(extra, dict) else {}).items():
        if v in REC + DESP:
            m[str(k)] = v
    return m


def _visoes(con) -> list[dict]:
    cs = _fin().contas(con)
    out = [{"chave": "consolidado", "nome": "Consolidado", "restrito": False}, {"chave": "operacional", "nome": "Operacional (Mercado Pago)", "restrito": False}]
    out += [{"chave": str(c["id"]), "nome": c["nome"], "restrito": True, "ativa": bool(c["ativa"])} for c in cs if c["restrito"]]
    return out


def _contas_da_visao(con, visao: str) -> set[int] | None:
    cs = _fin().contas(con)
    if visao in ("", "consolidado"):
        return None
    if visao == "operacional":
        return {c["id"] for c in cs if not c["restrito"]}
    try:
        cid = int(visao)
    except ValueError:
        raise HTTPException(400, "Visão inválida")
    if not any(c["id"] == cid for c in cs):
        raise HTTPException(400, "Conta desconhecida")
    return {cid}


def _lancamentos(con, de: str, ate: str, contas: set[int] | None) -> tuple[list[dict], list[dict]]:
    rec = [x for x in _fin().livro(con, de, ate)["linhas"] if contas is None or x.get("conta_id") in contas]
    desp = [x for x in _desp().listar(con, de, ate) if contas is None or x["conta_id"] in contas]
    return rec, desp


def classificar(con, rec: list[dict], desp: list[dict]) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]], dict]:
    m = mapa(con)
    projeto = {c["id"] for c in _fin().contas(con) if c["tipo"] == "projeto_incentivado"}
    avisos = {"receitas_fora_do_mapa": 0, "despesas_fora_do_mapa": 0, "sem_categoria": 0}
    r_out, d_out = [], []
    for x in rec:
        if x.get("conta_id") in projeto:
            r_out.append(("rec_projeto", x))
            continue
        k = m.get(f"natureza:{x['natureza']}")
        if not k:
            avisos["receitas_fora_do_mapa"] += 1
            k = "rec_outras"
        r_out.append((k, x))
    for x in desp:
        if not x["categoria"]:
            avisos["sem_categoria"] += 1
            d_out.append(("desp_outras", x))
            continue
        k = m.get(f"categoria:{x['categoria']}")
        if not k:
            avisos["despesas_fora_do_mapa"] += 1
            k = "desp_outras"
        d_out.append((k, x))
    return r_out, d_out, avisos


def valores(con, de: str, ate: str, visao: str = "consolidado") -> dict:
    rec, desp = _lancamentos(con, de, ate, _contas_da_visao(con, visao))
    r_cl, d_cl, avisos = classificar(con, rec, desp)
    v = {k: 0.0 for k, _, t, _ in LINHAS if t != "grupo"}
    for k, x in r_cl:
        v[k] += x["bruto"]
    for k, x in d_cl:
        v[k] += x["valor"]
    v["tarifas_receb"] = sum(x["tarifa"] or 0 for x in rec)
    v["receita_bruta"] = sum(v[k] for k in REC)
    v["receita_liquida"] = v["receita_bruta"] - v["tarifas_receb"]
    v["despesas_total"] = sum(v[k] for k in DESP)
    v["resultado"] = v["receita_liquida"] - v["despesas_total"]
    v = {k: round(x, 2) for k, x in v.items()}
    avisos["tarifa_a_conferir"] = sum(1 for x in rec if x["tarifa_conferir"] and not x["estorno"])
    return {"valores": v, "avisos": avisos}


def periodo_anterior(de: str, ate: str) -> tuple[str, str]:
    d1, d2 = date.fromisoformat(de), date.fromisoformat(ate)
    if d1.day == 1 and (d2 + timedelta(days=1)).day == 1:          # meses inteiros: volta o mesmo número de meses
        n = (d2.year - d1.year) * 12 + d2.month - d1.month + 1
        a, m = d1.year, d1.month - n
        while m < 1:
            a, m = a - 1, m + 12
        ini = date(a, m, 1)
        fim = d1 - timedelta(days=1)
        return ini.isoformat(), fim.isoformat()
    dias = (d2 - d1).days + 1
    return (d1 - timedelta(days=dias)).isoformat(), (d1 - timedelta(days=1)).isoformat()


def montar(con, de: str, ate: str, visao: str = "consolidado") -> dict:
    a1, a2 = periodo_anterior(de, ate)
    y1 = date.fromisoformat(ate).replace(month=1, day=1).isoformat()
    atual, ant, ytd = valores(con, de, ate, visao), valores(con, a1, a2, visao), valores(con, y1, ate, visao)
    tem_projeto = any(c["tipo"] == "projeto_incentivado" and (c["ativa"] or True) for c in _fin().contas(con))
    linhas = []
    for k, rot, t, nv in LINHAS:
        if k == "rec_projeto" and not tem_projeto:
            continue
        if k == "desp_outras" and not any(x["valores"]["desp_outras"] for x in (atual, ant, ytd)):
            continue
        if k == "resultado":
            rv = atual["valores"]["resultado"]
            rot = "(=) Superávit do período" if rv > 0 else ("(=) Déficit do período" if rv < 0 else "(=) Resultado do período (zero)")
        linhas.append({"chave": k, "rotulo": rot, "tipo": t, "nivel": nv, "atual": atual["valores"].get(k), "anterior": ant["valores"].get(k),
                       "ytd": ytd["valores"].get(k), "clicavel": t in ("rec", "desp", "tarifa")})
    pend = _desp().listar(con, de, ate, so_pendentes=True)
    sem_cat = sum(1 for x in pend if not x["categoria"])
    return {"titulo": TITULO, "aviso": AVISO, "periodo": {"de": de, "ate": ate}, "anterior": {"de": a1, "ate": a2}, "ytd": {"de": y1, "ate": ate},
            "visao": visao or "consolidado", "visoes": _visoes(con), "linhas": linhas, "resultado": atual["valores"]["resultado"],
            "situacao": "superavit" if atual["valores"]["resultado"] > 0 else ("deficit" if atual["valores"]["resultado"] < 0 else "zero"),
            "avisos": dict(atual["avisos"], despesas_sem_categoria=sem_cat,
                           texto=(f"{sem_cat} despesas sem categoria: o resultado pode mudar." if sem_cat > 1 else
                                  ("1 despesa sem categoria: o resultado pode mudar." if sem_cat == 1 else ""))),
            "resumo_visoes": [{"chave": vz["chave"], "nome": vz["nome"], "restrito": vz["restrito"], "resultado": valores(con, de, ate, vz["chave"])["valores"]["resultado"]}
                              for vz in _visoes(con)]}


def mensal(con, ano: int, visao: str = "consolidado") -> dict:
    cols = []
    for m in range(1, 13):
        ini = date(ano, m, 1)
        fim = date(ano + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        cols.append(valores(con, ini.isoformat(), fim.isoformat(), visao)["valores"])
    tot = valores(con, f"{ano}-01-01", f"{ano}-12-31", visao)["valores"]
    linhas = [{"chave": k, "rotulo": r, "tipo": t, "nivel": nv, "meses": [c.get(k) for c in cols], "total": tot.get(k)} for k, r, t, nv in LINHAS]
    return {"ano": ano, "meses": MESES, "linhas": linhas, "aviso": AVISO, "visao": visao}


def detalhe_linha(con, linha: str, de: str, ate: str, visao: str) -> list[dict]:
    rec, desp = _lancamentos(con, de, ate, _contas_da_visao(con, visao))
    if linha == "tarifas_receb":
        return [dict(x, tipo_lanc="receita") for x in rec if x["tarifa"]]
    r_cl, d_cl, _ = classificar(con, rec, desp)
    return [dict(x, tipo_lanc="receita") for k, x in r_cl if k == linha] + [dict(x, tipo_lanc="despesa") for k, x in d_cl if k == linha]


# ---------------------------------------------------------------- exportação
def _per(d: dict) -> str:
    f = lambda s: f"{s[8:10]}/{s[5:7]}/{s[:4]}"   # noqa: E731
    return f"{f(d['de'])} a {f(d['ate'])}"


def exportar_xlsx(dre: dict, men: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    wb = Workbook()
    ws = wb.active
    ws.title = "DRE"
    nome_visao = next((v["nome"] for v in dre["visoes"] if v["chave"] == dre["visao"]), dre["visao"])
    for t in ("CAMP", TITULO, f"Período: {_per(dre['periodo'])} · {nome_visao}", dre["aviso"]):
        ws.append([t])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    ws.append(["", f"Período ({_per(dre['periodo'])})", f"Anterior ({_per(dre['anterior'])})", f"Acumulado do ano ({_per(dre['ytd'])})"])
    for l in dre["linhas"]:
        ws.append([("    " * l["nivel"]) + l["rotulo"]] + ([] if l["tipo"] == "grupo" else [l["atual"], l["anterior"], l["ytd"]]))
        if l["tipo"] in ("soma", "grupo"):
            ws.cell(ws.max_row, 1).font = Font(bold=True)
    if dre["avisos"]["texto"]:
        ws.append([])
        ws.append([dre["avisos"]["texto"]])
    sm = wb.create_sheet("DRE mensal")
    sm.append([f"{TITULO} · {men['ano']} · mês a mês · {nome_visao}"])
    sm.append([dre["aviso"]])
    sm.append([""] + [m.capitalize() for m in men["meses"]] + ["Total"])
    for l in men["linhas"]:
        sm.append([("    " * l["nivel"]) + l["rotulo"]] + ([] if l["tipo"] == "grupo" else l["meses"] + [l["total"]]))
    for sh in wb.worksheets:
        sh.column_dimensions["A"].width = 70
        for row in sh.iter_rows():
            for c in row:
                if isinstance(c.value, float):
                    c.number_format = "#,##0.00;-#,##0.00"
                if c.column == 1:
                    c.alignment = Alignment(wrap_text=False)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def exportar_csv(dre: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["CAMP — " + TITULO])
    w.writerow([f"Período: {_per(dre['periodo'])}"])
    w.writerow([dre["aviso"]])
    w.writerow([])
    w.writerow(["Linha", "Período", "Anterior", "Acumulado do ano"])
    n = lambda v: "" if v is None else f"{v:.2f}".replace(".", ",")   # noqa: E731
    for l in dre["linhas"]:
        w.writerow([("  " * l["nivel"]) + l["rotulo"]] + ([] if l["tipo"] == "grupo" else [n(l["atual"]), n(l["anterior"]), n(l["ytd"])]))
    return ("﻿" + buf.getvalue()).encode("utf-8")


# ---------------------------------------------------------------- rotas (só admin e master)
def _periodo(de, ate, mes, ano, tri):
    from .despesas import _periodo as p
    return p(de, ate, mes, ano, tri)


@router.get("")
def ver(de: str = "", ate: str = "", mes: str = "", ano: str = "", tri: str = "", visao: str = "consolidado", u: dict = Depends(auth.exige("admin"))) -> dict:
    d1, d2 = _periodo(de, ate, mes, ano, tri)
    con = connect()
    try:
        out = montar(con, d1, d2, visao)
        out["mensal"] = mensal(con, int(d2[:4]), visao)
        out["mapa"] = mapa(con)
        out["linhas_opcoes"] = [{"chave": k, "rotulo": ROTULO[k], "tipo": "rec" if k in REC else "desp"} for k in REC + DESP]
        return out
    finally:
        con.close()


@router.get("/linha")
def linha(linha: str, de: str = "", ate: str = "", mes: str = "", ano: str = "", tri: str = "", visao: str = "consolidado", u: dict = Depends(auth.exige("admin"))) -> dict:
    if linha not in REC + DESP + ["tarifas_receb"]:
        raise HTTPException(400, "Linha da DRE desconhecida")
    d1, d2 = _periodo(de, ate, mes, ano, tri)
    con = connect()
    try:
        ls = detalhe_linha(con, linha, d1, d2, visao)
        return {"linha": linha, "rotulo": ROTULO[linha], "periodo": {"de": d1, "ate": d2}, "itens": ls,
                "total": round(sum((x["tarifa"] if linha == "tarifas_receb" else x.get("bruto", x.get("valor"))) or 0 for x in ls), 2)}
    finally:
        con.close()


@router.get("/exportar.xlsx")
def exp_xlsx(de: str = "", ate: str = "", mes: str = "", ano: str = "", tri: str = "", visao: str = "consolidado", u: dict = Depends(auth.exige("admin"))):
    d1, d2 = _periodo(de, ate, mes, ano, tri)
    con = connect()
    try:
        b = exportar_xlsx(montar(con, d1, d2, visao), mensal(con, int(d2[:4]), visao))
    finally:
        con.close()
    return Response(b, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="camp-dre-{d1}-a-{d2}.xlsx"'})


@router.get("/exportar.csv")
def exp_csv(de: str = "", ate: str = "", mes: str = "", ano: str = "", tri: str = "", visao: str = "consolidado", u: dict = Depends(auth.exige("admin"))):
    d1, d2 = _periodo(de, ate, mes, ano, tri)
    con = connect()
    try:
        b = exportar_csv(montar(con, d1, d2, visao))
    finally:
        con.close()
    return Response(b, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="camp-dre-{d1}-a-{d2}.csv"'})


class Mapa(BaseModel):
    mapa: dict[str, str]


@router.put("/mapa")
def gravar_mapa(b: Mapa, u: dict = Depends(auth.exige("admin"))) -> dict:
    ruins = [k for k, v in b.mapa.items() if not (k.startswith("natureza:") or k.startswith("categoria:")) or v not in REC + DESP]
    if ruins:
        raise HTTPException(400, "Item ou linha da DRE desconhecida: " + ", ".join(ruins[:5]))
    con = connect()
    try:
        novo = dict(mapa(con), **b.mapa)
        con.execute("INSERT INTO configuracao (chave, valor, descricao, sensivel) VALUES ('dre.mapa', ?, 'DRE gerencial: linha de cada natureza e categoria', 0) "
                    "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (json.dumps(novo, ensure_ascii=False),))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('financeiro','dre','mapa_dre',?,?)",
                    (u.get("email") or "painel", json.dumps(b.mapa, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "mapa": novo}
    finally:
        con.close()
