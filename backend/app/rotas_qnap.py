"""Informações do QNAP para o painel (lidas do que o coletor guardou; nunca varre o QNAP na requisição)."""
import threading

from fastapi import APIRouter, Depends

from . import auth, qnap_coletor
from .db import connect

router = APIRouter(prefix="/api", tags=["qnap"])


@router.get("/qnap")
def qnap(u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        return qnap_coletor.resumo(con)
    finally:
        con.close()


@router.post("/qnap/coletar")
def coletar_agora(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Pede uma coleta agora (admin). Roda em segundo plano: a tela espera alguns segundos e relê /api/qnap."""
    if qnap_coletor.em_andamento():
        return {"ok": True, "ja_em_andamento": True}
    threading.Thread(target=qnap_coletor.coletar, daemon=True).start()
    return {"ok": True, "iniciada": True}
