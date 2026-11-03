"""Tela "Visitas ao site" (03/11/2026): lê só o histórico do banco (visitas.py); coletar agora e diagnóstico só para admin."""
from __future__ import annotations

import threading
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from . import auth, visitas
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
