"""Conferência de duplicatas de um projeto (19/10/2026: "teria como checar melhor quem é duplicata? porque tá complexo quando tem
50 folhas lá e 25 são duplicatas").

Antes, cada duplicata apontada pelo CAMP Vision era vista folha a folha (na revisão), sem ver a original ao lado. Aqui:
- GET  /api/projetos/{c}/duplicatas: os GRUPOS (a folha que vai ao site + as cópias dela), com o porquê do CAMP Vision, quem já
  conferiu, e sugestões de duplicatas que ninguém marcou ("Talvez sejam duplicatas": mesmo tipo + mesma folha + mesmo título,
  ou o mesmo arquivo pelo md5). Sugestão é só sugestão: nada muda sem a pessoa decidir.
- POST /api/projetos/{c}/duplicatas/decisoes: várias decisões de uma vez (cada uma num SAVEPOINT: uma recusada não desfaz as outras).
  confirmar  {original, copias}  são cópias; publica a original. Conta como folha conferida na revisão do lote (a cópia não precisa
                                 de mais nada: não vai ao site), igual ao "conferir" da revisão.
  trocar     {original, nova}    "Publicar esta em vez daquela": a cópia `nova` passa a ser a que vai ao site; a antiga original e as
                                 outras cópias passam a ser cópias dela (todas conferidas).
  nao_e      {codigo}            "Não é duplicata": a mesma regra do DELETE /api/itens/{c}/duplicata-de (solta o bloqueio do CAMP Vision).
  marcar     {original, copias}  aceitar uma sugestão: as `copias` viram duplicatas de `original` (já conferidas).
  dispensar  {codigos}           a sugestão está errada: as folhas não voltam a ser sugeridas.
Nada é apagado. Tudo fica no histórico (duplicata_marcada / duplicata_desmarcada / duplicatas_sugestao_dispensada).
A marcação só conta como conferida enquanto duplicata_de = duplicata_conferida_de (migração 139): se uma reimportação do CAMP
Vision apontar para outra folha, o grupo volta a pedir conferência.
"""
from __future__ import annotations

import json
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["duplicatas"])

TIPO_ROTULO = {"exata": "o CAMP Vision achou a imagem idêntica", "perceptual": "o CAMP Vision achou a imagem quase igual",
               "mesma_folha": "mesma folha (mesmo número e título)"}
_COLS = """i.codigo, i.projeto_codigo, i.serie_codigo, i.sequencial, i.titulo, COALESCE(i.tipos_documento, i.tipo_documento) AS tipo_documento,
           i.folha, i.revisao, i.lote_id, i.status_site, i.retida, i.pendencias, i.giro_manual, COALESCE(i.espelho_manual, i.espelhado) AS espelhar,
           i.recorte, i.alinhamento, i.duplicata_de, i.tipo_duplicata, i.md5, i.tainacan_item_id,
           i.duplicata_conferida_em, i.duplicata_conferida_por, i.duplicata_conferida_de"""


def _norm(t) -> str:
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/]+", " ", t)).strip()


def _folha_norm(t) -> str:
    """'03/12', '3 / 12' e 'folha 3/12' são a mesma folha."""
    return "/".join(str(int(x)) if x.isdigit() else x for x in re.findall(r"[a-z]+|\d+", _norm(t)) if x != "folha")


def _json(v):
    if not isinstance(v, str):
        return v
    try:
        return json.loads(v)
    except ValueError:
        return None


def _item(r, thumbs: dict, motivos: dict) -> dict:
    d = dict(r)
    d["pendencias"] = _json(d.get("pendencias"))
    d["recorte"] = _json(d.get("recorte"))
    d["thumb_url"], d["documento_url"] = thumbs.get(d["codigo"], (None, None))
    d["motivos"] = motivos.get(d["codigo"], [])
    d["conferida"] = bool(d["duplicata_de"] and d["duplicata_conferida_em"] and d["duplicata_conferida_de"] == d["duplicata_de"])
    d["no_site"] = d["status_site"] in ("rascunho", "no_ar") and bool(d["tainacan_item_id"])
    d.pop("md5", None)
    return d


def _raiz(cod: str, dup: dict) -> str:
    """A folha que vai ao site: segue duplicata_de até uma folha que não é cópia (cadeias antigas A→B→C viram um grupo só)."""
    vistos = {cod}
    while dup.get(cod):
        cod = dup[cod]
        if cod in vistos:
            break
        vistos.add(cod)
    return cod


def montar(con, codigo: str) -> dict:
    p = con.execute("SELECT codigo, titulo, fundo_codigo FROM projeto WHERE codigo=?", (codigo,)).fetchone()
    if not p:
        raise HTTPException(404, "Projeto não existe")
    linhas = con.execute(f"SELECT {_COLS} FROM item i WHERE i.projeto_codigo=? ORDER BY i.serie_codigo, i.sequencial", (codigo,)).fetchall()
    por_cod = {r["codigo"]: r for r in linhas}
    fora = [r["duplicata_de"] for r in linhas if r["duplicata_de"] and r["duplicata_de"] not in por_cod]
    for cod in dict.fromkeys(fora):                                     # original em outro projeto (raro): aparece, sem decisão
        r = con.execute(f"SELECT {_COLS} FROM item i WHERE i.codigo=?", (cod,)).fetchone()
        if r:
            por_cod[cod] = r
    cods = list(por_cod)
    thumbs, motivos = {}, {}
    q = ",".join("?" * len(cods))
    if cods:
        for w in con.execute(f"SELECT codigo_detectado, thumb_url, documento_url FROM wp_item WHERE codigo_detectado IN ({q}) ORDER BY id", cods):
            thumbs.setdefault(w[0], (w[1], w[2]))
        for e in con.execute(f"SELECT codigo, descricao FROM erro WHERE categoria='duplicata' AND codigo IN ({q}) ORDER BY id DESC", cods):
            if e["descricao"]:
                motivos.setdefault(e["codigo"], []).append(e["descricao"])
    for r in por_cod.values():                                          # o que o CAMP Vision escreveu nos bloqueios da folha
        pend = _json(r["pendencias"]) or {}
        for b in (pend.get("bloqueios") or []) if isinstance(pend, dict) else []:
            if "duplicat" in str(b).lower() and str(b) not in motivos.get(r["codigo"], []):
                motivos.setdefault(r["codigo"], []).append(str(b))
    dup = {c: r["duplicata_de"] for c, r in por_cod.items()}
    grupos: dict[str, list] = {}
    for r in linhas:
        if r["duplicata_de"]:
            grupos.setdefault(_raiz(r["codigo"], dup), []).append(r)
    saida = []
    for orig, copias in grupos.items():
        o = por_cod.get(orig)
        if not o:
            continue
        cs = [_item(c, thumbs, motivos) for c in copias]
        saida.append({"original": _item(o, thumbs, motivos), "copias": cs, "conferido": all(c["conferida"] for c in cs),
                      "fora_do_projeto": o["projeto_codigo"] != codigo})
    ordem = {c: k for k, c in enumerate(r["codigo"] for r in linhas)}
    saida.sort(key=lambda g: ordem.get(g["original"]["codigo"], -1))
    total = sum(len(g["copias"]) for g in saida)
    conferidas = sum(1 for g in saida for c in g["copias"] if c["conferida"])
    return {"projeto": {"codigo": p["codigo"], "titulo": p["titulo"], "fundo_codigo": p["fundo_codigo"]},
            "grupos": saida, "total_copias": total, "conferidas": conferidas,
            "grupos_a_conferir": sum(1 for g in saida if not g["conferido"]),
            "sugestoes": sugestoes(linhas, thumbs, motivos)}


def sugestoes(linhas, thumbs: dict, motivos: dict) -> list[dict]:
    """Folhas que NINGUÉM marcou como duplicata mas parecem ser: o mesmo arquivo (md5) ou mesmo tipo + mesma folha + mesmo título.
    Folha que uma pessoa já disse que não é duplicata (duplicata_conferida_em sem duplicata_de) não volta a ser sugerida."""
    livres = [r for r in linhas if not r["duplicata_de"] and not r["duplicata_conferida_em"]]
    usados, out = set(), []
    por_md5: dict[str, list] = {}
    for r in livres:
        if (r["md5"] or "").strip():
            por_md5.setdefault(r["md5"].strip().lower(), []).append(r)
    for g in por_md5.values():
        if len(g) > 1:
            out.append({"motivo": "o arquivo é idêntico (mesmo md5)", "folhas": [_item(r, thumbs, motivos) for r in g]})
            usados.update(r["codigo"] for r in g)
    chaves: dict[tuple, list] = {}
    for r in livres:
        if r["codigo"] in usados:
            continue
        tipo, folha = _norm(r["tipo_documento"]), _folha_norm(r["folha"])
        if tipo and folha:
            chaves.setdefault((tipo, folha, _norm(r["titulo"])), []).append(r)
    for (_, _, tit), g in chaves.items():
        if len(g) > 1:
            out.append({"motivo": "mesmo tipo, mesmo número de folha" + (" e mesmo título" if tit else ""), "folhas": [_item(r, thumbs, motivos) for r in g]})
    return out


@router.get("/projetos/{codigo}/duplicatas")
def listar(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        r = montar(con, codigo)
        r["pode_decidir"] = auth.PAPEIS[u["papel"]] >= auth.PAPEIS["operador"]
        return r
    finally:
        con.close()


class Decisao(BaseModel):
    acao: str
    original: str | None = None
    copias: list[str] | None = None
    nova: str | None = None
    codigo: str | None = None
    codigos: list[str] | None = None


class Decisoes(BaseModel):
    decisoes: list[Decisao]


def _ev(con, tipo: str, codigo: str, ator: str, det: dict, entidade: str = "item") -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)", (entidade, codigo, tipo, ator, json.dumps(det, ensure_ascii=False)))


def _folha(con, projeto: str, cod: str | None):
    if not cod:
        raise HTTPException(400, "Falta o código da folha.")
    r = con.execute("SELECT i.*, l.aprovado_em AS lote_aprovado FROM item i LEFT JOIN lista_processamento l ON l.id=i.lote_id WHERE i.codigo=?", (cod,)).fetchone()
    if not r:
        raise HTTPException(404, f"A folha {cod} não existe.")
    if r["projeto_codigo"] != projeto:
        raise HTTPException(409, f"A folha {cod} não é do projeto {projeto}.")
    return r


def _dup_map(con, projeto: str) -> dict:
    return {r[0]: r[1] for r in con.execute("SELECT codigo, duplicata_de FROM item WHERE projeto_codigo=? AND duplicata_de IS NOT NULL", (projeto,))}


def _publica_no_site(r) -> bool:
    return r["status_site"] == "no_ar" and bool(r["tainacan_item_id"])


def _conferir(con, r, original: str, ator: str) -> bool:
    """Registra que uma pessoa conferiu a cópia. Se a folha ainda esperava conferência na revisão do lote (e o lote não foi aprovado
    nem a folha está no site), ela passa a 'conferida': a cópia não vai ao site, então não há mais o que conferir nela.
    Devolve se a revisão mudou."""
    con.execute("""UPDATE item SET duplicata_conferida_em=datetime('now'), duplicata_conferida_por=?, duplicata_conferida_de=?,
                   atualizado_em=datetime('now') WHERE codigo=?""", (ator, original, r["codigo"]))
    if r["lote_id"] and r["revisao"] == "pendente" and not r["lote_aprovado"] and r["status_site"] not in ("rascunho", "no_ar"):
        con.execute("UPDATE item SET revisao='conferida', revisado_por=?, revisado_em=datetime('now') WHERE codigo=?", (ator, r["codigo"]))
        return True
    return False


def _confirmar(con, projeto: str, d: Decisao, ator: str) -> dict:
    o = _folha(con, projeto, d.original)
    if o["duplicata_de"]:
        raise HTTPException(409, f"{d.original} é cópia de {o['duplicata_de']}: atualize a tela.")
    if not d.copias:
        raise HTTPException(400, "Diga quais cópias você conferiu.")
    dup = _dup_map(con, projeto)
    feitas = []
    for c in dict.fromkeys(d.copias):
        r = _folha(con, projeto, c)
        if not r["duplicata_de"] or _raiz(c, dup) != d.original:
            raise HTTPException(409, f"{c} não é mais cópia de {d.original}: atualize a tela.")
        if r["duplicata_de"] != d.original:                                  # cadeia antiga: aponta direto para a que vai ao site
            con.execute("UPDATE item SET duplicata_de=? WHERE codigo=?", (d.original, c))
        rev = _conferir(con, r, d.original, ator)
        _ev(con, "duplicata_marcada", c, ator, {"original": d.original, "tipo": r["tipo_duplicata"], "trocou": False, "conferida": True,
                                                "revisao_conferida": rev, "via": "tela de duplicatas"})
        feitas.append(c)
    return {"conferidas": feitas}


def _trocar(con, projeto: str, d: Decisao, ator: str) -> dict:
    o, n = _folha(con, projeto, d.original), _folha(con, projeto, d.nova)
    dup = _dup_map(con, projeto)
    if o["duplicata_de"] or not n["duplicata_de"] or _raiz(n["codigo"], dup) != o["codigo"]:
        raise HTTPException(409, f"{d.nova} não é mais cópia de {d.original}: atualize a tela.")
    if _publica_no_site(o):
        raise HTTPException(409, f"A folha {d.original} está publicada. Despublique antes de publicar outra no lugar dela.")
    from .rotas_mesclar import _e_de_duplicata
    pend = _json(n["pendencias"]) or {}
    tirados = []
    if isinstance(pend, dict) and any(_e_de_duplicata(b) for b in pend.get("bloqueios") or []):   # a nova original deixa de estar presa por ser cópia
        tirados = [b for b in pend["bloqueios"] if _e_de_duplicata(b)]
        pend["bloqueios"] = [b for b in pend["bloqueios"] if not _e_de_duplicata(b)]
        con.execute("UPDATE item SET pendencias=? WHERE codigo=?", (json.dumps(pend, ensure_ascii=False), n["codigo"]))
    if n["status_site"] == "bloqueado" and not (pend.get("bloqueios") if isinstance(pend, dict) else None) and not n["autoria_divergente"]:
        con.execute("UPDATE item SET status_site='nao_publicado' WHERE codigo=?", (n["codigo"],))
    outras = [c for c in dup if c != n["codigo"] and _raiz(c, dup) == o["codigo"]]
    con.execute("""UPDATE item SET duplicata_de=NULL, tipo_duplicata=NULL, duplicata_conferida_em=NULL, duplicata_conferida_por=NULL,
                   duplicata_conferida_de=NULL, atualizado_em=datetime('now') WHERE codigo=?""", (n["codigo"],))
    con.execute("UPDATE item SET duplicata_de=?, tipo_duplicata=?, atualizado_em=datetime('now') WHERE codigo=?", (n["codigo"], n["tipo_duplicata"], o["codigo"]))
    for c in [o["codigo"], *outras]:
        con.execute("UPDATE item SET duplicata_de=? WHERE codigo=?", (n["codigo"], c))
        r = _folha(con, projeto, c)
        rev = _conferir(con, r, n["codigo"], ator)
        _ev(con, "duplicata_marcada", c, ator, {"original": n["codigo"], "tipo": r["tipo_duplicata"], "trocou": c == o["codigo"], "conferida": True,
                                                "revisao_conferida": rev, "via": "tela de duplicatas", **({"bloqueios_tirados_da_nova": tirados} if tirados and c == o["codigo"] else {})})
    return {"publica": n["codigo"], "copias": [o["codigo"], *outras]}


def _nao_e(con, projeto: str, d: Decisao, ator: str) -> dict:
    from .rotas_mesclar import liberar_bloqueios_de_duplicata
    a = _folha(con, projeto, d.codigo)
    if not a["duplicata_de"]:
        raise HTTPException(409, f"{d.codigo} não está marcada como duplicata: atualize a tela.")
    liberou = liberar_bloqueios_de_duplicata(con, a["codigo"], a, ator)
    con.execute("""UPDATE item SET duplicata_de=NULL, tipo_duplicata=NULL, duplicata_conferida_em=datetime('now'), duplicata_conferida_por=?,
                   duplicata_conferida_de=?, atualizado_em=datetime('now') WHERE codigo=?""", (ator, a["duplicata_de"], a["codigo"]))
    con.execute("UPDATE item SET duplicata_de=? WHERE duplicata_de=?", (a["duplicata_de"], a["codigo"]))   # quem apontava para esta (cadeia antiga) fica no grupo
    _ev(con, "duplicata_desmarcada", a["codigo"], ator, {"era_de": a["duplicata_de"], "tipo": a["tipo_duplicata"], "via": "tela de duplicatas", **liberou})
    return {"era_de": a["duplicata_de"], **liberou}


def _marcar(con, projeto: str, d: Decisao, ator: str) -> dict:
    o = _folha(con, projeto, d.original)
    if o["duplicata_de"]:
        raise HTTPException(409, f"{d.original} já é cópia de {o['duplicata_de']}: escolha a que vai ao site.")
    if not d.copias:
        raise HTTPException(400, "Diga quais folhas são cópias.")
    feitas = []
    for c in dict.fromkeys(d.copias):
        if c == d.original:
            raise HTTPException(400, "Uma folha não pode ser duplicata dela mesma.")
        r = _folha(con, projeto, c)
        if r["duplicata_de"]:
            raise HTTPException(409, f"{c} já é cópia de {r['duplicata_de']}: atualize a tela.")
        if _publica_no_site(r):
            raise HTTPException(409, f"A folha {c} está publicada. Despublique antes de marcar como duplicata.")
        con.execute("UPDATE item SET duplicata_de=?, tipo_duplicata='mesma_folha', atualizado_em=datetime('now') WHERE codigo=?", (d.original, c))
        con.execute("UPDATE item SET duplicata_de=? WHERE duplicata_de=?", (d.original, c))
        rev = _conferir(con, r, d.original, ator)
        _ev(con, "duplicata_marcada", c, ator, {"original": d.original, "tipo": "mesma_folha", "trocou": False, "conferida": True,
                                                "revisao_conferida": rev, "via": "sugestão da tela de duplicatas"})
        feitas.append(c)
    return {"marcadas": feitas}


def _dispensar(con, projeto: str, d: Decisao, ator: str) -> dict:
    cods = list(dict.fromkeys(d.codigos or []))
    if len(cods) < 2:
        raise HTTPException(400, "Diga quais folhas não são duplicatas.")
    for c in cods:
        r = _folha(con, projeto, c)
        if r["duplicata_de"]:
            raise HTTPException(409, f"{c} é cópia de {r['duplicata_de']}: atualize a tela.")
        con.execute("UPDATE item SET duplicata_conferida_em=datetime('now'), duplicata_conferida_por=?, duplicata_conferida_de=NULL WHERE codigo=?", (ator, c))
    _ev(con, "duplicatas_sugestao_dispensada", projeto, ator, {"folhas": cods}, entidade="projeto")
    return {"dispensadas": cods}


ACOES = {"confirmar": _confirmar, "trocar": _trocar, "nao_e": _nao_e, "marcar": _marcar, "dispensar": _dispensar}


@router.post("/projetos/{codigo}/duplicatas/decisoes")
def decidir(codigo: str, corpo: Decisoes, u: dict = Depends(auth.exige("operador"))) -> dict:
    if not corpo.decisoes:
        raise HTTPException(400, "Nenhuma decisão enviada.")
    if len(corpo.decisoes) > 500:
        raise HTTPException(400, "Decisões demais de uma vez (máximo 500).")
    for d in corpo.decisoes:
        if d.acao not in ACOES:
            raise HTTPException(400, f"Ação desconhecida: {d.acao}")
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM projeto WHERE codigo=?", (codigo,)).fetchone():
            raise HTTPException(404, "Projeto não existe")
        con.execute("BEGIN IMMEDIATE")
        resultados = []
        for k, d in enumerate(corpo.decisoes):
            con.execute(f"SAVEPOINT d{k}")
            try:
                r = ACOES[d.acao](con, codigo, d, u["email"])
                con.execute(f"RELEASE d{k}")
                resultados.append({"ok": True, "acao": d.acao, **r})
            except HTTPException as e:
                con.execute(f"ROLLBACK TO d{k}"); con.execute(f"RELEASE d{k}")
                resultados.append({"ok": False, "acao": d.acao, "erro": e.detail})
        from .problemas import fechar_resolvidos
        fechados = fechar_resolvidos(con, u["email"])        # o problema "duplicata" da folha decidida fecha (com registro)
        con.commit()
        feitas = sum(1 for r in resultados if r["ok"])
        return {"ok": feitas > 0, "feitas": feitas, "falhas": len(resultados) - feitas, "resultados": resultados, "problemas_fechados": len(fechados),
                **{k: v for k, v in montar(con, codigo).items() if k in ("total_copias", "conferidas", "grupos_a_conferir")}}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
