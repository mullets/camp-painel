"""Quantas pessoas estão no site AGORA (Google Analytics, últimos 30 minutos), para o tablet de parede (`/clima`).

Lido em SEGUNDO PLANO a cada N minutos (`parede.site_agora_min`; **0 = desligado, o padrão**) com a mesma conta de serviço das
Visitas ao site (`ga4_direto.py`); a página só lê o guardado. Nunca levanta exceção: o erro fica em `site_agora.erro`.
"""
from __future__ import annotations

from . import ga4_direto
from .db import connect

VALE_S = 20 * 60          # número mais velho que isto não é "agora": a tela mostra um traço


def intervalo_min(con) -> int:
    r = con.execute("SELECT valor FROM configuracao WHERE chave='parede.site_agora_min'").fetchone()
    v = str(r[0]).strip() if r and r[0] is not None else "0"
    return int(v) if v.isdigit() else 0


def coletar() -> dict:
    pessoas, erro = None, None
    try:
        con = connect()
        try:
            cfg = ga4_direto.configurado(con)
        finally:
            con.close()
        if not cfg:
            erro = "o Google Analytics direto não está configurado (ga4.propriedade e ga4.conta_servico)"
        else:
            pessoas = int(ga4_direto.GA4(cfg).agora())
    except Exception as e:  # noqa: BLE001  (sem rede, permissão, cota: fica o motivo, sem a chave)
        erro = f"{type(e).__name__}: {str(e)[:160]}"
    con = connect()
    try:
        con.execute("INSERT INTO site_agora (pessoas, erro) VALUES (?,?)", (pessoas, erro))
        con.execute("DELETE FROM site_agora WHERE quando < datetime('now','-2 days')")
        con.commit()
    finally:
        con.close()
    return {"pessoas": pessoas, "erro": erro}


def ultima(con) -> dict | None:
    """{pessoas, idade_s} da última leitura certa e ainda fresca; None se não há (desligado, erro ou velha)."""
    r = con.execute("""SELECT pessoas, erro, CAST((julianday('now') - julianday(quando)) * 86400 AS INTEGER) AS idade_s
                         FROM site_agora ORDER BY id DESC LIMIT 1""").fetchone()
    if not r or r["erro"] or r["pessoas"] is None or r["idade_s"] > VALE_S:
        return None
    return {"pessoas": r["pessoas"], "idade_s": r["idade_s"]}
