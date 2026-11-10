"""CAMP-DUP (10/11/2026): folhas RETIRADAS do sistema (cópias de outro formato, scripts/retirar_copias.py). Ficam como lápide em
`item_retirado` (migração 220). Regras que valem para o painel inteiro:
  - o número D de uma folha retirada NUNCA é reusado: o maior D do projeto conta as lápides (`maior_sequencial`);
  - a importação do lote (releitura do CAMP Vision) e a importação do site não trazem de volta uma folha retirada (`chaves`/`retirado`).
Sem a tabela (banco antes da migração 220) tudo segue como antes."""
from __future__ import annotations

import sqlite3


def _tem(con) -> bool:
    try:
        return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_retirado'").fetchone())
    except sqlite3.Error:
        return False


def maior_sequencial(con, projeto: str, acima: int | None = None) -> int:
    """O maior D já usado no projeto, contando as folhas retiradas (0 se nenhum). `acima`: só os D maiores que este (faixa do painel)."""
    filtro, args = ("AND sequencial>?", (projeto, acima)) if acima is not None else ("", (projeto,))
    m = con.execute(f"SELECT COALESCE(MAX(sequencial),0) FROM item WHERE projeto_codigo=? {filtro}", args).fetchone()[0] or 0
    if _tem(con):
        m = max(m, con.execute(f"SELECT COALESCE(MAX(sequencial),0) FROM item_retirado WHERE projeto_codigo=? {filtro}", args).fetchone()[0] or 0)
    return int(m)


def maiores_por_projeto(con) -> dict[str, int]:
    """{projeto: maior D entre as folhas retiradas} (para quem calcula o maior D de vários projetos numa consulta só)."""
    if not _tem(con):
        return {}
    return {r[0]: int(r[1] or 0) for r in con.execute("SELECT projeto_codigo, MAX(sequencial) FROM item_retirado GROUP BY projeto_codigo")}


def chaves(con, projeto: str) -> dict:
    """O que identifica as folhas retiradas do projeto: {codigos, sequenciais, md5, origens}."""
    out = {"codigos": set(), "sequenciais": set(), "md5": set(), "origens": set()}
    if not _tem(con):
        return out
    for cod, seq, md5, origem in con.execute("SELECT codigo, sequencial, md5, arquivo_origem FROM item_retirado WHERE projeto_codigo=?", (projeto,)):
        out["codigos"].add(cod)
        if seq is not None:
            out["sequenciais"].add(int(seq))
        if (md5 or "").strip():
            out["md5"].add(md5.strip().lower())
        for o in str(origem or "").split(" | "):
            if o.strip():
                out["origens"].add(o.strip())
    return out


def retirado(con, codigo: str) -> bool:
    return _tem(con) and bool(con.execute("SELECT 1 FROM item_retirado WHERE codigo=?", (codigo,)).fetchone())
