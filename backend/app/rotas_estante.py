"""Modo estante (celular): ler a etiqueta e ir para o lugar certo; conferir o conteúdo de uma caixa.

- GET  /api/resolver-codigo?c=...                     diz se o código é folha, projeto, fundo ou caixa/local e para onde ir
- GET  /api/localizacoes/{id}/conferencia             o que deveria estar no recipiente
- POST /api/localizacoes/{id}/conferencia/previa      classifica as leituras (conferido, faltando, de outro lugar) sem gravar
- POST /api/localizacoes/{id}/conferencia             idem, e registra a conferência no histórico (operador+)
Mover o que é de outro lugar usa a rota que já existe: POST /api/localizacoes/alocar.
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["estante"])

RE_FUNDO = re.compile(r"^F\d{3}$")
RE_PROJETO = re.compile(r"^F\d{3}-P\d{4}$")
RE_PASTA = re.compile(r"^([A-Z]{3})-P(\d{1,4})(?:\.(\d+))?$")    # etiqueta da pasta: SBU-P011.1 (sigla, nº do projeto, volume)
RE_PREFIXO_FUNDO = re.compile(r"^(F\d{3})-(.+)$")               # etiqueta da caixa: F026-CX-001


def normalizar(c: str | None) -> str:
    """O que o leitor devolve: tira espaços, asteriscos de início/fim do Code 39 e o que vier de um link (…#item/X)."""
    t = str(c or "").strip().upper()
    if "#" in t:
        t = t.rsplit("#", 1)[1]
        t = t.split("/", 1)[1] if "/" in t else t
    return t.strip("* \t\r\n")


def _local_dict(r) -> dict:
    return {"id": r["id"], "identificador": r["identificador"], "tipo": r["tipo"], "fundo_codigo": r["fundo_codigo"], "descricao": r["descricao"]}


def resolver(con, bruto: str) -> dict | None:
    c = normalizar(bruto)
    if not c:
        return None
    # folha
    r = con.execute("""SELECT i.codigo, i.titulo, i.folha, i.projeto_codigo, p.titulo AS projeto FROM item i
                         JOIN projeto p ON p.codigo=i.projeto_codigo WHERE upper(i.codigo)=?""", (c,)).fetchone()
    if r:
        lo = con.execute("SELECT l.* FROM item_localizacao il JOIN localizacao_fisica l ON l.id=il.localizacao_id WHERE il.item_codigo=?", (r["codigo"],)).fetchone()
        return {"codigo": r["codigo"], "tipo": "folha", "rota": f"item/{r['codigo']}", "titulo": r["titulo"] or r["projeto"],
                "folha": r["folha"], "projeto_codigo": r["projeto_codigo"], "projeto": r["projeto"], "localizacao": _local_dict(lo) if lo else None}
    # projeto (código completo, ou a etiqueta da pasta SBU-P011.1)
    pc, volume = None, None
    if RE_PROJETO.match(c):
        pc = c
    else:
        m = RE_PASTA.match(c)
        if m:
            f = con.execute("SELECT codigo FROM fundo WHERE upper(sigla)=?", (m.group(1),)).fetchone()
            if f:
                pc, volume = f"{f[0]}-P{int(m.group(2)):04d}", (int(m.group(3)) if m.group(3) else None)
    if pc:
        p = con.execute("SELECT codigo, titulo, fundo_codigo, mesclado_em FROM projeto WHERE codigo=?", (pc,)).fetchone()
        if p and p["mesclado_em"]:
            p2 = con.execute("SELECT codigo, titulo, fundo_codigo, mesclado_em FROM projeto WHERE codigo=?", (p["mesclado_em"],)).fetchone()
            if p2:
                return {"codigo": p2["codigo"], "tipo": "projeto", "rota": f"projeto/{p2['codigo']}", "titulo": p2["titulo"],
                        "fundo_codigo": p2["fundo_codigo"], "volume": volume, "aviso": f"{pc} foi juntado a {p2['codigo']}"}
        if p:
            return {"codigo": p["codigo"], "tipo": "projeto", "rota": f"projeto/{p['codigo']}", "titulo": p["titulo"],
                    "fundo_codigo": p["fundo_codigo"], "volume": volume}
    # fundo
    if RE_FUNDO.match(c):
        f = con.execute("SELECT codigo, titulo FROM fundo WHERE codigo=?", (c,)).fetchone()
        if f:
            return {"codigo": f["codigo"], "tipo": "fundo", "rota": f"fundo/{f['codigo']}", "titulo": f["titulo"]}
    # caixa / local: "CX-001" ou "F026-CX-001" (como sai na etiqueta da caixa)
    achados = con.execute("SELECT * FROM localizacao_fisica WHERE upper(identificador)=? ORDER BY id", (c,)).fetchall()
    m = RE_PREFIXO_FUNDO.match(c)
    if m:
        achados += con.execute("SELECT * FROM localizacao_fisica WHERE upper(identificador)=? AND fundo_codigo=? ORDER BY id", (m.group(2), m.group(1))).fetchall()
    vistos, locais = set(), []
    for l in achados:
        if l["id"] not in vistos:
            vistos.add(l["id"]); locais.append(l)
    if len(locais) == 1:
        l = locais[0]
        return {"codigo": l["identificador"], "tipo": "caixa", "rota": f"estante/caixa/{l['id']}", "titulo": l["descricao"] or l["identificador"],
                "localizacao": _local_dict(l)}
    if len(locais) > 1:
        return {"codigo": c, "tipo": "varios", "rota": None, "titulo": f"{len(locais)} lugares com o nome {c}",
                "opcoes": [{**_local_dict(l), "rota": f"estante/caixa/{l['id']}"} for l in locais]}
    # sigla do fundo sozinha (SBU)
    if re.fullmatch(r"[A-Z]{3}", c):
        f = con.execute("SELECT codigo, titulo FROM fundo WHERE upper(sigla)=?", (c,)).fetchone()
        if f:
            return {"codigo": f["codigo"], "tipo": "fundo", "rota": f"fundo/{f['codigo']}", "titulo": f["titulo"]}
    return None


@router.get("/resolver-codigo")
def resolver_codigo(c: str = "", u: dict = Depends(auth.exige("leitura"))) -> dict:
    if not normalizar(c):
        raise HTTPException(400, "Digite ou leia um código.")
    con = connect()
    try:
        r = resolver(con, c)
    finally:
        con.close()
    if not r:   # 200 de propósito: leitura errada é parte do uso (o celular não deve registrar erro a cada etiqueta mal lida)
        return {"codigo": normalizar(c), "tipo": "desconhecido", "rota": None,
                "mensagem": f"Não achei nada com o código {normalizar(c)}. Confira se a etiqueta foi lida inteira."}
    return r


# ---------------- conferência de caixa ----------------
def _local(con, lid: int):
    l = con.execute("SELECT l.*, f.titulo AS fundo FROM localizacao_fisica l LEFT JOIN fundo f ON f.codigo=l.fundo_codigo WHERE l.id=?", (lid,)).fetchone()
    if not l:
        con.close()
        raise HTTPException(404, "Esse lugar não existe mais. Confira a etiqueta da caixa.")
    return l


def _esperados(con, lid: int) -> list[dict]:
    return [dict(r) for r in con.execute("""SELECT i.codigo, i.titulo, i.folha, i.projeto_codigo, p.titulo AS projeto
                                               FROM item_localizacao il JOIN item i ON i.codigo=il.item_codigo JOIN projeto p ON p.codigo=i.projeto_codigo
                                              WHERE il.localizacao_id=? ORDER BY i.codigo""", (lid,))]


def classificar(con, lid: int, lidos: list[str]) -> dict:
    l = _local(con, lid)
    esperados = _esperados(con, lid)
    por_codigo = {e["codigo"]: e for e in esperados}
    conferidos: dict[str, str] = {}          # codigo da folha -> o que foi lido
    de_outro, nao_rec, leituras = [], [], []
    vistos = set()
    for bruto in lidos:
        c = normalizar(bruto)
        if not c or c in vistos:
            continue
        vistos.add(c)
        r = resolver(con, c)
        if r and r["tipo"] == "folha":
            if r["codigo"] in por_codigo:
                conferidos.setdefault(r["codigo"], c)
                leituras.append({"lido": c, "resultado": "conferido", "codigo": r["codigo"]})
            else:
                lo = r.get("localizacao")
                de_outro.append({"lido": c, "tipo": "folha", "codigo": r["codigo"], "titulo": r["titulo"], "projeto_codigo": r["projeto_codigo"],
                                 "local": lo["identificador"] if lo else None, "local_id": lo["id"] if lo else None})
                leituras.append({"lido": c, "resultado": "de_outro_local", "codigo": r["codigo"]})
        elif r and r["tipo"] == "projeto":
            daqui = [e["codigo"] for e in esperados if e["projeto_codigo"] == r["codigo"]]
            if daqui:
                for x in daqui:
                    conferidos.setdefault(x, c)
                leituras.append({"lido": c, "resultado": "conferido", "codigo": r["codigo"], "folhas": len(daqui)})
            else:
                locs = [x[0] for x in con.execute("""SELECT DISTINCT l.identificador FROM item i JOIN item_localizacao il ON il.item_codigo=i.codigo
                                                       JOIN localizacao_fisica l ON l.id=il.localizacao_id WHERE i.projeto_codigo=? ORDER BY 1""", (r["codigo"],))]
                n = con.execute("SELECT COUNT(*) FROM item WHERE projeto_codigo=?", (r["codigo"],)).fetchone()[0]
                de_outro.append({"lido": c, "tipo": "projeto", "codigo": r["codigo"], "titulo": r["titulo"], "folhas": n,
                                 "local": ", ".join(locs) or None, "local_id": None})
                leituras.append({"lido": c, "resultado": "de_outro_local", "codigo": r["codigo"]})
        else:
            motivo = ("é a etiqueta de um lugar, não de uma folha" if r and r["tipo"] in ("caixa", "varios")
                      else "é a etiqueta de um fundo, não de uma folha" if r and r["tipo"] == "fundo" else "código não encontrado")
            nao_rec.append({"lido": c, "motivo": motivo})
            leituras.append({"lido": c, "resultado": "nao_reconhecido"})
    faltando = [e for e in esperados if e["codigo"] not in conferidos]
    return {"localizacao": {**_local_dict(l), "fundo": l["fundo"]}, "esperados": len(esperados),
            "conferidos": [{**por_codigo[k], "lido": v} for k, v in conferidos.items()], "faltando": faltando,
            "de_outro_local": de_outro, "nao_reconhecidos": nao_rec, "leituras": leituras}


class Leituras(BaseModel):
    lidos: list[str] = []


@router.get("/localizacoes/{lid}/conferencia")
def conferencia_abrir(lid: int, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    l = _local(con, lid)
    out = {"localizacao": {**_local_dict(l), "fundo": l["fundo"]}, "esperados": _esperados(con, lid)}
    ult = con.execute("SELECT quando, ator, detalhe FROM evento WHERE entidade='localizacao' AND codigo=? AND tipo='conferencia_caixa' ORDER BY id DESC LIMIT 1", (str(lid),)).fetchone()
    out["ultima"] = {"quando": ult["quando"], "ator": ult["ator"], **(json.loads(ult["detalhe"] or "{}"))} if ult else None
    con.close()
    return out


@router.post("/localizacoes/{lid}/conferencia/previa")
def conferencia_previa(lid: int, d: Leituras, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        return classificar(con, lid, d.lidos)
    finally:
        con.close()


def _plural(n: int, s: str, p: str) -> str:
    return f"{n} {s if n == 1 else p}"


@router.post("/localizacoes/{lid}/conferencia")
def conferencia_registrar(lid: int, d: Leituras, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    r = classificar(con, lid, d.lidos)
    tot = {"esperados": r["esperados"], "conferidos": len(r["conferidos"]), "faltando": len(r["faltando"]),
           "de_outro_local": len(r["de_outro_local"]), "nao_reconhecidos": len(r["nao_reconhecidos"]), "leituras": len(r["leituras"])}
    detalhe = {"identificador": r["localizacao"]["identificador"], **tot,
               "faltando_codigos": [x["codigo"] for x in r["faltando"]][:100],
               "de_outro_local_codigos": [x["codigo"] for x in r["de_outro_local"]][:100]}
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('localizacao',?,'conferencia_caixa',?,?)",
                (str(lid), u["email"], json.dumps(detalhe, ensure_ascii=False)))
    con.commit(); con.close()
    ident = r["localizacao"]["identificador"]
    partes = [f"{tot['conferidos']} de {_plural(tot['esperados'], 'folha conferida', 'folhas conferidas')}"]
    if tot["faltando"]:
        partes.append(f"{tot['faltando']} faltando")
    if tot["de_outro_local"]:
        partes.append(f"{tot['de_outro_local']} de outro lugar")
    return {**r, "totais": tot, "mensagem": f"Conferência de {ident} registrada: " + ", ".join(partes)}
