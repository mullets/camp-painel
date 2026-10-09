"""Publicar com um clique: o plano (leitura) e a execução (admin). A lógica está em publicacao_guiada.py."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from . import auth, publicacao_guiada
from .db import connect

router = APIRouter(prefix="/api", tags=["publicacao"])


@router.get("/projetos/{codigo}/publicar/plano")
def plano(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
        if not p:
            raise HTTPException(404, "Projeto não existe")
        return {**publicacao_guiada.plano(con, p), "pode_agir": u["papel"] in ("admin", "master")}
    finally:
        con.close()


@router.post("/projetos/{codigo}/publicar-tudo")
def publicar_tudo(codigo: str, u: dict = Depends(auth.exige("admin"))):
    try:
        return publicacao_guiada.executar(codigo, u)
    except HTTPException as e:
        if e.status_code != 400:
            raise
        con = connect()                                  # 400 = algo que só uma pessoa resolve: devolve o plano para a tela mostrar
        try:
            p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
            pl = publicacao_guiada.plano(con, p) if p else None
        finally:
            con.close()
        return JSONResponse(status_code=400, content={"detail": e.detail, "plano": pl})
