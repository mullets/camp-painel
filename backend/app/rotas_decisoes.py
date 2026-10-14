"""Decisões que o painel pede a uma pessoa (projeto parecido, lote com números repetidos, dado diferente do cadastro, mesmo nome em outro fundo).
Ler: todos (leitura vê, sem decidir); decidir: admin."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth, decisoes
from .db import connect

router = APIRouter(prefix="/api", tags=["decisoes"])


def _linha(r) -> dict:
    d = dict(r)
    ctx = json.loads(d.pop("contexto") or "{}")
    d["tipo"] = d.get("tipo") or "projeto_parecido"
    d["pedido"], d["candidatos"] = ctx.get("pedido", {}), ctx.get("candidatos", [])
    d["contexto"] = ctx
    d["pergunta"] = decisoes.pergunta(r, ctx)
    d["tipo_rotulo"] = decisoes.TIPOS.get(d["tipo"], {}).get("rotulo", d["tipo"])
    d["opcoes"] = list(decisoes.TIPOS.get(d["tipo"], {}).get("opcoes", ()))
    d["escolha"] = d.get("escolha") or d.get("resolucao")
    return d


@router.get("/decisoes")
def listar(situacao: str = "pendente", u: dict = Depends(auth.exige("leitura"))) -> dict:
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
def detalhe(did: int, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT * FROM decisao WHERE id=?", (did,)).fetchone()
        if not r:
            raise HTTPException(404, "Decisão não existe")
        d = _linha(r)
        # H11: miniatura de cada candidato (o que já está no site ou a 1ª folha com prévia) e o código que "É outro" vai criar
        for c in (d["candidatos"] if d["tipo"] == "projeto_parecido" else []):
            w = con.execute("SELECT thumb_url FROM wp_item WHERE projeto_detectado=? AND thumb_url IS NOT NULL ORDER BY codigo_detectado LIMIT 1", (c.get("codigo"),)).fetchone()
            i = con.execute("SELECT codigo FROM item WHERE projeto_codigo=? AND pendencias LIKE '%previa%' ORDER BY serie_codigo, sequencial LIMIT 1", (c.get("codigo"),)).fetchone()
            c["capa"] = {"thumb_url": w[0] if w else None, "item": i[0] if i else None}
        if d["tipo"] == "projeto_parecido" and d.get("situacao") == "pendente" and d.get("fundo_codigo"):
            from .projetos_novos import proximo_numero
            try:
                d["proximo_codigo"] = f"{d['fundo_codigo']}-P{proximo_numero(con, d['fundo_codigo'], d['pedido'].get('proximo_p_local')):04d}"
            except Exception:  # noqa: BLE001 - sem contador: o botão fica sem o número
                d["proximo_codigo"] = None
        return d
    finally:
        con.close()


class Resolver(BaseModel):
    acao: str
    projeto_codigo: str | None = None
    valor: str | None = None          # divergência: o valor escolhido entre os candidatos


@router.post("/decisoes/{did}/resolver")
def resolver(did: int, d: Resolver, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        r = decisoes.resolver(con, did, d.acao, (d.projeto_codigo or "").strip() or None, u["email"], (d.valor or "").strip() or None)
        con.commit()
        return r
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()
