"""CAMP-050 · LGPD: resumo da guarda de dados e execução manual da rotina (só admin)."""
from fastapi import APIRouter, Depends

from . import auth, lgpd
from .db import connect

router = APIRouter(prefix="/api", tags=["lgpd"])


@router.get("/lgpd")
def resumo(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return lgpd.resumo(con)
    finally:
        con.close()


@router.post("/lgpd/executar")
def executar(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Roda a rotina agora, respeitando lgpd.modo (padrão simular: só conta), e repete o que o site ainda não confirmou."""
    con = connect()
    try:
        r = lgpd.rodar(con, u["email"])
        return {**r, **lgpd.repetir_pendentes(con)}
    finally:
        con.close()
