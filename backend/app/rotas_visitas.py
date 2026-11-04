"""Tela "Visitas ao site" (03/11/2026): lê só o histórico do banco (visitas.py); coletar agora e diagnóstico só para admin."""
from __future__ import annotations

import threading
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from . import auth, visitas, visitas_relatorio as vr
from .db import connect

router = APIRouter(prefix="/api", tags=["visitas"])


@router.get("/visitas")
def ver(periodo: str = "28d", de: str | None = None, ate: str | None = None, u: dict = Depends(auth.exige("leitura"))) -> dict:
    pers = visitas.periodos(date.today())
    if periodo in pers:
        de, ate = pers[periodo]
    elif not (de and ate):
        raise HTTPException(400, "Escolha um período")
    try:
        date.fromisoformat(de); date.fromisoformat(ate)
    except ValueError:
        raise HTTPException(400, "Datas no formato AAAA-MM-DD")
    con = connect()
    try:
        r = visitas.resumo(con, de, ate, periodo if periodo in pers else None)
        r["periodo"] = periodo
        return r
    finally:
        con.close()


@router.post("/visitas/coletar")
def coletar_agora(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Busca agora no Google (em segundo plano: a primeira coleta pode levar alguns minutos)."""
    threading.Thread(target=visitas.coletar, kwargs={"por": u["email"]}, daemon=True).start()
    return {"ok": True, "mensagem": "Coleta iniciada. Atualize a tela em alguns minutos."}


@router.get("/visitas/diagnostico")
def diagnostico(u: dict = Depends(auth.exige("admin"))) -> dict:
    return {"itens": visitas.diagnostico()}


# ---------------------------------------------------------------- 04/11 (especificação do Rafael): evolução + projetos mais visitados
def _periodo(periodo: str | None, de: str | None, ate: str | None) -> dict:
    try:
        return vr.intervalo(periodo, de, ate)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _site() -> str:
    try:
        from .config import settings
        return settings.WP_BASE_URL or "https://camp.arq.br"
    except Exception:  # noqa: BLE001
        return "https://camp.arq.br"


@router.get("/visitas/evolucao")
def evolucao(periodo: str | None = None, de: str | None = None, ate: str | None = None, comparar: int = 0,
             u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Visitas (sessões do site público) por dia/semana/mês no período, total, média, variação e a última sincronização. Só o banco."""
    per = _periodo(periodo, de, ate)
    con = connect()
    try:
        return vr.evolucao(con, per, bool(comparar))
    finally:
        con.close()


def _projetos(periodo, de, ate, ordem, busca, limite, fundo="", autor="") -> dict:
    per = _periodo(periodo, de, ate)
    con = connect()
    try:
        return vr.projetos(con, per, ordem, busca or "", max(0, min(int(limite), 5000)), _site(), fundo=fundo or "", autor=autor or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        con.close()


@router.get("/visitas/projetos")
def projetos(periodo: str | None = None, de: str | None = None, ate: str | None = None, ordem: str = "mais", busca: str = "",
             limite: int = 10, fundo: str = "", autor: str = "", u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Ranking dos projetos pelas visualizações da página pública de cada um (só o vínculo real projeto ↔ página; limite=0 = todos).
    fundo / autor (opcionais): só os projetos daquele fundo / com aquele arquiteto na autoria cadastrada."""
    return _projetos(periodo, de, ate, ordem, busca, limite, fundo, autor)


@router.get("/visitas/projetos.csv")
def projetos_csv(periodo: str | None = None, de: str | None = None, ate: str | None = None, ordem: str = "mais", busca: str = "",
                 fundo: str = "", autor: str = "", u: dict = Depends(auth.exige("leitura"))) -> Response:
    r = _projetos(periodo, de, ate, ordem, busca, 0, fundo, autor)
    nome = f"visitas-projetos-{r['de']}-a-{r['ate']}.csv"
    return Response(vr.csv_projetos(r), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
