"""Modo estante (celular): ler a etiqueta e ir para o lugar certo; conferir o conteúdo de uma caixa.

- GET  /api/resolver-codigo?c=...                     diz se o código é folha, projeto, fundo ou caixa/local e para onde ir
- GET  /api/localizacoes/{id}/conferencia             o que deveria estar no recipiente
- POST /api/localizacoes/{id}/conferencia/previa      classifica as leituras (conferido, faltando, de outro lugar) sem gravar
- POST /api/localizacoes/{id}/conferencia             idem, e registra a conferência no histórico (operador+)
Mover o que é de outro lugar usa a rota que já existe: POST /api/localizacoes/alocar.
UX-25 (etiquetas impressas, guardar ao fim do lote, folhas publicadas sem lugar): no fim do arquivo.
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


# ---------------- UX-25 · etiquetar e guardar ao fim do lote ----------------
# - POST /api/etiquetas/impressas   registra o que saiu no Imprimir (histórico "Impressas", para reimprimir igual)
# - GET  /api/etiquetas/impressas   as últimas impressões, com quem imprimiu
# - POST /api/etiquetas/guardar     guarda as folhas SEM lugar de um projeto numa caixa (cria a caixa se ainda não existe)
# - GET  /api/etiquetas/sem-lugar   quantas folhas publicadas ainda não têm lugar (o contador discreto do Painel inicial)
TIPOS_ETIQUETA = ("projeto", "documento", "caixa", "tubo", "fundo")
RE_FORMATO = re.compile(r"^\d{2,3}x\d{2,3}$")
RE_IDENT_LOCAL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,29}$")
PREFIXO_TIPO = (("CX-", "caixa"), ("GV-", "gaveta"), ("TB-", "tubo"), ("MAP-", "mapoteca"), ("EST-", "estante"))


class Impressao(BaseModel):
    tipo: str
    codigo: str
    quantidade: int = 1
    formato_mm: str = "100x50"
    papel: str | None = None
    lote: str | None = None
    config: dict | None = None


@router.post("/etiquetas/impressas")
def registrar_impressao(d: Impressao, u: dict = Depends(auth.exige("leitura"))) -> dict:
    cod = normalizar(d.codigo)
    if d.tipo not in TIPOS_ETIQUETA:
        raise HTTPException(400, "Tipo de etiqueta desconhecido")
    if not cod or len(cod) > 80:
        raise HTTPException(400, "Código da etiqueta inválido")
    if not RE_FORMATO.match(d.formato_mm or ""):
        raise HTTPException(400, "Formato inválido")
    if d.papel not in (None, "rolo", "a4", "niimbot") or d.lote not in (None, "um", "folhas", "pastas", "material"):
        raise HTTPException(400, "Papel ou lote inválido")
    cfg = json.dumps(d.config, ensure_ascii=False) if d.config else None
    if cfg and len(cfg) > 2000:
        raise HTTPException(400, "Configuração longa demais")
    con = connect()
    try:
        eid = con.execute("INSERT INTO etiqueta_impressao (tipo, codigo, quantidade, formato_mm, usuario_id, papel, lote, config) VALUES (?,?,?,?,?,?,?,?)",
                          (d.tipo, cod, max(1, min(5000, int(d.quantidade or 1))), d.formato_mm, u.get("id"), d.papel, d.lote, cfg)).lastrowid
        con.commit()
    finally:
        con.close()
    return {"id": eid}


@router.get("/etiquetas/impressas")
def impressas(limite: int = 100, u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect()
    try:
        rows = con.execute("""SELECT e.*, us.nome AS usuario, COALESCE(p.titulo, f.titulo) AS titulo
                                FROM etiqueta_impressao e LEFT JOIN usuario us ON us.id=e.usuario_id
                                LEFT JOIN projeto p ON p.codigo=substr(e.codigo,1,10) AND e.tipo IN ('projeto','tubo','documento') AND COALESCE(e.lote,'')<>'pastas'
                                LEFT JOIN fundo f ON f.codigo=substr(e.codigo,1,4) AND (e.tipo IN ('fundo','caixa') OR e.lote='pastas')
                               ORDER BY e.id DESC LIMIT ?""", (max(1, min(500, limite)),)).fetchall()
    finally:
        con.close()
    out = []
    for r in rows:
        x = dict(r)
        try:
            x["config"] = json.loads(x.get("config") or "null")
        except ValueError:
            x["config"] = None
        out.append(x)
    return out


class Guardar(BaseModel):
    projeto_codigo: str
    identificador: str


@router.post("/etiquetas/guardar")
def guardar(d: Guardar, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Guarda numa caixa só as folhas do projeto que ainda NÃO têm lugar: as que já têm continuam onde estão (nada muda de lugar sem querer).
    A caixa é a do fundo do projeto (ou uma compartilhada com o mesmo identificador); se não existe, é criada no fundo do projeto."""
    pc, ident = normalizar(d.projeto_codigo), normalizar(d.identificador)
    if not RE_PROJETO.match(pc):
        raise HTTPException(400, "Código de projeto inválido")
    if not RE_IDENT_LOCAL.match(ident):
        raise HTTPException(400, "Identificador inválido: use letras, números e hífen (ex.: CX-001)")
    con = connect()
    try:
        p = con.execute("SELECT fundo_codigo, titulo FROM projeto WHERE codigo=? AND mesclado_em IS NULL AND descartado_em IS NULL", (pc,)).fetchone()
        if not p:
            raise HTTPException(404, f"Projeto {pc} não existe")
        loc = con.execute("""SELECT id, identificador, tipo FROM localizacao_fisica WHERE upper(identificador)=? AND (fundo_codigo=? OR fundo_codigo IS NULL)
                              ORDER BY fundo_codigo IS NULL LIMIT 1""", (ident, p["fundo_codigo"])).fetchone()
        criada = False
        if loc:
            lid, tipo = loc["id"], loc["tipo"]
        else:
            tipo = next((t for pre, t in PREFIXO_TIPO if ident.startswith(pre)), "caixa")
            lid = con.execute("INSERT INTO localizacao_fisica (fundo_codigo, tipo, identificador) VALUES (?,?,?)", (p["fundo_codigo"], tipo, ident)).lastrowid
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('localizacao',?,'criada',?,?)",
                        (str(lid), u["email"], json.dumps({"identificador": ident, "fundo": p["fundo_codigo"]}, ensure_ascii=False)))
            criada = True
        sem = [r[0] for r in con.execute("""SELECT codigo FROM item i WHERE projeto_codigo=?
                                              AND NOT EXISTS (SELECT 1 FROM item_localizacao il WHERE il.item_codigo=i.codigo) ORDER BY codigo""", (pc,))]
        total = con.execute("SELECT COUNT(*) FROM item WHERE projeto_codigo=?", (pc,)).fetchone()[0]
        for c in sem:
            con.execute("INSERT INTO item_localizacao (item_codigo, localizacao_id) VALUES (?,?)", (c, lid))
        if sem:
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('localizacao',?,'alocacao',?,?)",
                        (str(lid), u["email"], json.dumps({"itens": len(sem), "projeto": pc}, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    ja, nome, nova = total - len(sem), p["titulo"] or pc, f" ({ident} foi criada)" if criada else ""
    if sem:
        msg = f"{_plural(len(sem), 'folha', 'folhas')} de {nome} guardada{'s' if len(sem) != 1 else ''} em {ident}{nova}"
        if ja:
            msg += f"; {_plural(ja, 'folha já tinha', 'folhas já tinham')} lugar e não mudou de lugar"
    elif total:
        msg = f"Todas as folhas de {nome} já tinham lugar: nada mudou{nova}"
    else:
        msg = f"{pc} ainda não tem folhas no painel{nova}"
    return {"localizacao_id": lid, "identificador": ident, "tipo": tipo, "criada": criada, "guardadas": len(sem), "ja_tinham_lugar": ja, "mensagem": msg}


@router.get("/etiquetas/sem-lugar")
def publicadas_sem_lugar(u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Folhas publicadas (qualquer visitante vê) que ainda não têm lugar físico cadastrado."""
    con = connect()
    try:
        r = con.execute("""SELECT COUNT(*), COUNT(DISTINCT i.projeto_codigo) FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo
                            WHERE i.status_site='no_ar' AND p.mesclado_em IS NULL AND p.descartado_em IS NULL
                              AND NOT EXISTS (SELECT 1 FROM item_localizacao il WHERE il.item_codigo=i.codigo)""").fetchone()
    finally:
        con.close()
    return {"folhas": r[0], "projetos": r[1]}
