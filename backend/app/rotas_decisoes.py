"""Decisões que o painel pede a uma pessoa (projeto parecido: é o mesmo?). Ler: operador; decidir: admin."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth, decisoes
from .db import connect

router = APIRouter(prefix="/api", tags=["decisoes"])


def _linha(r) -> dict:
    d = dict(r)
    ctx = json.loads(d.pop("contexto") or "{}")
    d["pedido"], d["candidatos"] = ctx.get("pedido", {}), ctx.get("candidatos", [])
    return d


@router.get("/decisoes")
def listar(situacao: str = "pendente", u: dict = Depends(auth.exige("operador"))) -> dict:
    if situacao not in ("pendente", "resolvida"):
        raise HTTPException(400, "situacao deve ser pendente ou resolvida")
    con = connect()
    try:
        ordem = "criada_em, id" if situacao == "pendente" else "resolvida_em DESC, id DESC LIMIT 30"
        itens = [_linha(r) for r in con.execute(f"SELECT * FROM decisao WHERE situacao=? ORDER BY {ordem}", (situacao,))]
        return {"itens": itens, "total": len(itens)}
    finally:
        con.close()


@router.get("/decisoes/{did}")
def detalhe(did: int, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT * FROM decisao WHERE id=?", (did,)).fetchone()
        if not r:
            raise HTTPException(404, "Decisão não existe")
        return _linha(r)
    finally:
        con.close()


class Resolver(BaseModel):
    acao: str
    projeto_codigo: str | None = None


@router.post("/decisoes/{did}/resolver")
def resolver(did: int, d: Resolver, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        r = decisoes.resolver(con, did, d.acao, (d.projeto_codigo or "").strip() or None, u["email"])
        con.commit()
        return r
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()
