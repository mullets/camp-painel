"""Relatório do CAMP Vision e gasto por fundo (02/11/2026).

Rafael: "esses relatórios do campvision, consigo acessar no meu painel? / seria bom saber tudo que ele fez resumidamente e o valor
gasto / no painel de um fundo, o quanto já gastamos com ele".

Fonte: o diário de eventos do CV2 (o mesmo do relatório diário dele), copiado para ACERVOS_CAMP/_campvision/eventos.jsonl (contrato
2.6). `ler` roda no coletor do QNAP, em segundo plano (nunca numa requisição): só relê quando o arquivo mudou. `resumo` e `gasto_fundo`
leem só o banco.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

ARQUIVO = Path("_campvision") / "eventos.jsonl"
_FUNDO = re.compile(r"^(F\d{3})-")


def ler(con, prontos: Path) -> dict:
    """Traz as linhas novas do diário. {lidas, novas} ou {pulado: True} se o arquivo não mudou / não existe."""
    arq = Path(prontos) / ARQUIVO
    try:
        st = arq.stat()
    except OSError:
        return {"pulado": True, "motivo": "o CAMP Vision ainda não copiou o diário para o acervo"}
    ult = con.execute("SELECT mtime, tamanho FROM cv_evento_leitura WHERE id=1").fetchone()
    if ult and ult[0] == st.st_mtime and ult[1] == st.st_size:
        return {"pulado": True}
    lidas = novas = 0
    for linha in arq.read_text(encoding="utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            e = json.loads(linha)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        lidas += 1
        quando, projeto = str(e.get("quando") or "")[:19], str(e.get("projeto") or "")[:200]
        if not quando or not projeto:
            continue
        m = _FUNDO.match(projeto)

        def n(k):
            try:
                return max(0, int(e.get(k) or 0))
            except (TypeError, ValueError):
                return 0
        try:
            custo = max(0.0, float(e.get("custo_usd") or 0))
        except (TypeError, ValueError):
            custo = 0.0
        novas += con.execute("""INSERT OR IGNORE INTO cv_evento (quando, dia, projeto, fundo, pasta, pranchas, com_carimbo, erros,
                                   campos_a_revisar, custo_usd, duracao_s, falha) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (quando, quando[:10], projeto, m.group(1) if m else None, str(e.get("pasta") or "")[:500], n("pranchas"),
                              n("com_carimbo"), n("erros"), n("campos_a_revisar"), custo, n("duracao_segundos"),
                              (str(e.get("falha") or "")[:300] or None))).rowcount
    con.execute("INSERT OR REPLACE INTO cv_evento_leitura (id, mtime, tamanho, linhas, lido_em) VALUES (1,?,?,?,datetime('now'))",
                (st.st_mtime, st.st_size, lidas))
    con.commit()
    return {"lidas": lidas, "novas": novas}


def _cotacao(con) -> float | None:
    r = con.execute("SELECT valor FROM configuracao WHERE chave='custos.cotacao_dolar'").fetchone()
    try:
        v = float(str((r[0] if r else "") or "").replace(",", "."))
        return v if v > 0 else None
    except ValueError:
        return None


def _soma(con, onde: str = "1=1", args: tuple = ()) -> dict:
    # "pranchas" = lidas pelo modelo (leitura com custo). A releitura que reaproveita a leitura salva (ex.: o lote passando do
    # provisório P9xxx para o projeto definitivo) aparece no diário com custo 0 e não conta de novo.
    r = con.execute(f"""SELECT COUNT(*) AS projetos, COALESCE(SUM(CASE WHEN custo_usd>0 THEN pranchas ELSE 0 END),0) AS pranchas, COALESCE(SUM(CASE WHEN custo_usd>0 THEN com_carimbo ELSE 0 END),0) AS com_carimbo,
                               COALESCE(SUM(erros),0) AS erros, COALESCE(SUM(falha IS NOT NULL),0) AS falhas,
                               ROUND(COALESCE(SUM(custo_usd),0),4) AS custo_usd, COALESCE(SUM(duracao_s),0) AS duracao_s,
                               MIN(dia) AS desde, MAX(quando) AS ultimo FROM cv_evento WHERE {onde}""", args).fetchone()
    return dict(r)


def resumo(con, dias: int = 30) -> dict:
    """O que o CAMP Vision fez: totais (hoje, 7 dias, 30 dias, tudo), dia a dia (com os projetos de cada dia) e por fundo."""
    dias = max(1, min(365, int(dias)))
    hoje = date.today()
    desde = (hoje - timedelta(days=dias - 1)).isoformat()
    por_dia = []
    for d in con.execute("""SELECT dia, COUNT(*) AS projetos, SUM(CASE WHEN custo_usd>0 THEN pranchas ELSE 0 END) AS pranchas, SUM(CASE WHEN custo_usd>0 THEN com_carimbo ELSE 0 END) AS com_carimbo, SUM(erros) AS erros,
                                   SUM(falha IS NOT NULL) AS falhas, ROUND(SUM(custo_usd),4) AS custo_usd, SUM(duracao_s) AS duracao_s
                              FROM cv_evento WHERE dia>=? GROUP BY dia ORDER BY dia DESC""", (desde,)):
        projs = [dict(p) for p in con.execute("""SELECT quando, projeto, fundo, pranchas, com_carimbo, erros, custo_usd, duracao_s, falha
                                                   FROM cv_evento WHERE dia=? ORDER BY quando""", (d["dia"],))]
        por_dia.append({**dict(d), "lista": projs})
    fundos = [dict(r) for r in con.execute("""SELECT e.fundo, f.titulo, COUNT(*) AS projetos, SUM(CASE WHEN e.custo_usd>0 THEN e.pranchas ELSE 0 END) AS pranchas,
                                                     ROUND(SUM(e.custo_usd),4) AS custo_usd, MIN(e.dia) AS desde
                                                FROM cv_evento e LEFT JOIN fundo f ON f.codigo=e.fundo
                                               WHERE e.fundo IS NOT NULL GROUP BY e.fundo ORDER BY SUM(e.custo_usd) DESC""")]
    leitura = con.execute("SELECT lido_em, linhas FROM cv_evento_leitura WHERE id=1").fetchone()
    return {"hoje": _soma(con, "dia=?", (hoje.isoformat(),)),
            "dias_7": _soma(con, "dia>=?", ((hoje - timedelta(days=6)).isoformat(),)),
            "dias_30": _soma(con, "dia>=?", ((hoje - timedelta(days=29)).isoformat(),)),
            "tudo": _soma(con), "por_dia": por_dia, "por_fundo": fundos, "cotacao_dolar": _cotacao(con),
            "lido_em": leitura["lido_em"] if leitura else None}


def gasto_fundo(con, fundo: str) -> dict:
    s = _soma(con, "fundo=?", (fundo,))
    meses = [dict(r) for r in con.execute("""SELECT substr(dia,1,7) AS mes, SUM(CASE WHEN custo_usd>0 THEN pranchas ELSE 0 END) AS pranchas, ROUND(SUM(custo_usd),4) AS custo_usd
                                               FROM cv_evento WHERE fundo=? GROUP BY 1 ORDER BY 1 DESC LIMIT 12""", (fundo,))]
    return {**s, "por_mes": meses, "cotacao_dolar": _cotacao(con),
            "custo_por_prancha": round(s["custo_usd"] / s["pranchas"], 4) if s["pranchas"] else None}
