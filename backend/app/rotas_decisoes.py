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


def _codigos_citados(d: dict) -> set[str]:
    ctx = d.get("contexto") or {}
    cods = {d.get("projeto_codigo"), ctx.get("projeto_codigo"), (ctx.get("outro") or {}).get("codigo")}
    cods |= {c.get("codigo") for c in (d.get("candidatos") or []) if isinstance(c, dict)}
    return {c for c in cods if c}


def _resumo_projetos(con, cods: set[str]) -> dict:
    """Para a pessoa decidir sem decorar código: nome, fundo, ano, cidade, quantas folhas e uma capa de cada projeto citado."""
    out = {}
    for cod in cods:
        p = con.execute("""SELECT p.codigo, p.titulo, p.ano, p.cidade, p.fundo_codigo, f.titulo AS fundo_titulo, f.sigla, p.capa_item,
                                  (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo) AS folhas
                             FROM projeto p LEFT JOIN fundo f ON f.codigo=p.fundo_codigo WHERE p.codigo=?""", (cod,)).fetchone()
        if not p:
            continue
        w = con.execute("SELECT thumb_url FROM wp_item WHERE projeto_detectado=? AND thumb_url IS NOT NULL ORDER BY codigo_detectado LIMIT 1", (cod,)).fetchone()
        i = p["capa_item"] or (con.execute("SELECT codigo FROM item WHERE projeto_codigo=? AND (pendencias LIKE '%previa%' OR arquivo_jpg IS NOT NULL) ORDER BY serie_codigo, sequencial LIMIT 1", (cod,)).fetchone() or [None])[0]
        from .similaridade import nome_de_subpasta
        out[cod] = {"codigo": cod, "titulo": p["titulo"], "ano": p["ano"] or None, "cidade": p["cidade"], "fundo_codigo": p["fundo_codigo"],
                    "fundo_titulo": p["fundo_titulo"], "sigla": p["sigla"], "folhas": p["folhas"], "subpasta": nome_de_subpasta(p["titulo"]),
                    "capa": {"thumb_url": w[0] if w else None, "item": i}}
    return out


@router.get("/decisoes")
def listar(situacao: str = "pendente", u: dict = Depends(auth.exige("leitura"))) -> dict:
    if situacao not in ("pendente", "resolvida"):
        raise HTTPException(400, "situacao deve ser pendente ou resolvida")
    con = connect()
    try:
        ordem = "criada_em, id" if situacao == "pendente" else "resolvida_em DESC, id DESC LIMIT 30"
        itens = [_linha(r) for r in con.execute(f"SELECT * FROM decisao WHERE situacao=? ORDER BY {ordem}", (situacao,))]
        for d in itens:
            d["projetos"] = _resumo_projetos(con, _codigos_citados(d))
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
        d["projetos"] = _resumo_projetos(con, _codigos_citados(d))
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
