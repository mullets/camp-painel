"""UX-67 · títulos de projeto que vieram do nome da pasta ("Teatro Piracicaba - 12 Folhas", "F000 - CNV - Convidado").

A regra de "título técnico" é a do UX-15 (similaridade.titulo_tecnico); aqui ficam a correção EM VÁRIOS de uma vez e o desfazer:
- prévia (GET /api/titulos-de-pasta/previa): os projetos com título técnico, a sugestão da pasta limpa e, quando as folhas dizem,
  o nome da obra lido no carimbo pelo CAMP Vision (item.projeto_carimbo). Só lê.
- corrigir (POST /api/titulos-de-pasta/corrigir): modo "simular" é o padrão (diz o que mudaria, não grava); "aplicar" só por um admin,
  com os títulos que ELE conferiu na tela. Cada aplicação é um lote no histórico (tabela titulo_correcao, migração 215).
- desfazer (POST /api/titulos-de-pasta/desfazer): volta o título de antes de um lote (só onde ninguém mudou o título depois).
Nunca muda código F/P (imutáveis): só o título. Projeto que já está no site recebe o título novo pela mesma rotina da edição do projeto.
"""
from __future__ import annotations

import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["projetos"])

MAX_POR_VEZ = 200
MIN_FOLHAS_CARIMBO = 2          # o nome do carimbo só vira sugestão quando pelo menos 2 folhas dizem o mesmo…
FRACAO_CARIMBO = 0.5            # …e são a maioria das folhas que têm o nome da obra no carimbo


def _norm(t: str) -> str:
    from .similaridade import normalizar
    return normalizar(t or "")


def titulo_do_carimbo(con, codigo: str) -> dict | None:
    """O nome da obra que a maioria das folhas diz no carimbo ({titulo, folhas, de}), ou None. Tudo em maiúsculas vira "Teatro Municipal"."""
    from .similaridade import cidade_sem_caixa_alta, titulo_tecnico
    contagem: dict[str, list] = {}
    total = 0
    for (v,) in con.execute("""SELECT projeto_carimbo FROM item WHERE projeto_codigo=? AND duplicata_de IS NULL
                                 AND TRIM(COALESCE(projeto_carimbo,''))<>''""", (codigo,)):
        t = " ".join(str(v).split()).strip(" -–—.,;")
        k = _norm(t)
        if not k:
            continue
        total += 1
        contagem.setdefault(k, [0, t])[0] += 1
    if not contagem:
        return None
    n, t = max(contagem.values(), key=lambda x: x[0])
    if n < MIN_FOLHAS_CARIMBO or n < FRACAO_CARIMBO * total:
        return None
    t = cidade_sem_caixa_alta(t) or t
    if len(t) < 3 or titulo_tecnico(t):
        return None
    return {"titulo": t[:200], "folhas": n, "de": total}


def _previa(con) -> list[dict]:
    from .similaridade import nome_de_subpasta, sugerir_titulo, titulo_tecnico
    out = []
    for p in con.execute("""SELECT p.codigo, p.titulo, p.fundo_codigo, p.status_site, p.tainacan_item_id,
                                   (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo) AS folhas
                              FROM projeto p WHERE p.mesclado_em IS NULL AND p.descartado_em IS NULL ORDER BY p.fundo_codigo, p.codigo""").fetchall():
        motivo = titulo_tecnico(p["titulo"])
        if not motivo or nome_de_subpasta(p["titulo"]):          # subpasta (TIFF/JPG) se junta ao projeto certo; não é troca de título
            continue
        pasta = sugerir_titulo(p["titulo"])
        carimbo = titulo_do_carimbo(con, p["codigo"])
        sug = (carimbo or {}).get("titulo") or pasta
        out.append({"codigo": p["codigo"], "titulo": p["titulo"], "fundo_codigo": p["fundo_codigo"], "folhas": p["folhas"], "motivo": motivo,
                    "titulo_da_pasta": pasta, "titulo_carimbo": carimbo, "sugerido": sug,
                    "fonte": "carimbo" if carimbo else ("pasta" if pasta else None),
                    "tem_no_site": bool(p["tainacan_item_id"]), "status_site": p["status_site"]})
    return out


@router.get("/titulos-de-pasta/previa")
def previa(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Só lê: o que a correção faria. Nada muda até um admin aplicar."""
    con = connect()
    try:
        itens = _previa(con)
        return {"total": len(itens), "com_sugestao": sum(1 for x in itens if x["sugerido"]), "itens": itens, "historico": _historico(con, 10)}
    finally:
        con.close()


class Troca(BaseModel):
    codigo: str
    titulo: str
    fonte: str | None = None          # carimbo | pasta | manual (só para o histórico)


class Correcao(BaseModel):
    itens: list[Troca] = []
    modo: str = "simular"            # simular (padrão) | aplicar


def _analisar(con, itens: list[Troca]) -> tuple[list[dict], list[dict]]:
    from .similaridade import titulo_tecnico
    mudam, recusados, vistos = [], [], set()
    for t in itens[:MAX_POR_VEZ]:
        cod = (t.codigo or "").strip().upper()
        novo = " ".join((t.titulo or "").split())
        if cod in vistos:
            continue
        vistos.add(cod)
        p = con.execute("SELECT codigo, titulo, tainacan_item_id FROM projeto WHERE codigo=? AND mesclado_em IS NULL AND descartado_em IS NULL", (cod,)).fetchone()
        if not p:
            recusados.append({"codigo": cod, "motivo": "projeto não existe"}); continue
        if len(novo) < 3:
            recusados.append({"codigo": cod, "motivo": "título novo vazio ou curto demais"}); continue
        if titulo_tecnico(novo):
            recusados.append({"codigo": cod, "motivo": f"o título novo “{novo}” {titulo_tecnico(novo)}"}); continue
        if novo == (p["titulo"] or "").strip():
            recusados.append({"codigo": cod, "motivo": "o título já é este"}); continue
        mudam.append({"codigo": cod, "antes": p["titulo"], "depois": novo[:200], "fonte": (t.fonte or "manual")[:20], "tem_no_site": bool(p["tainacan_item_id"])})
    if len(itens) > MAX_POR_VEZ:
        recusados.append({"codigo": None, "motivo": f"no máximo {MAX_POR_VEZ} projetos por vez; os outros ficaram para a próxima"})
    return mudam, recusados


def _mandar_ao_site(codigos: list[str], ator: str) -> dict:
    from .publicador import atualizar_dossie_no_site
    site = {}
    for cod in codigos:
        try:
            r = atualizar_dossie_no_site(cod, {"titulo": True}, ator)
        except Exception as e:  # noqa: BLE001 - o título no painel já mudou; a pendência fica registrada
            r = {"erro": str(e)[:200]}
        site[cod] = {"erro": r.get("erro"), "enviados": r.get("enviados") or []}
    return site


@router.post("/titulos-de-pasta/corrigir")
def corrigir(d: Correcao, u: dict = Depends(auth.exige("admin"))) -> dict:
    if d.modo not in ("simular", "aplicar"):
        raise HTTPException(400, "Modo inválido: use simular ou aplicar")
    con = connect()
    try:
        mudam, recusados = _analisar(con, d.itens)
        if d.modo == "simular" or not mudam:
            return {"modo": d.modo, "aplicado": False, "mudam": mudam, "recusados": recusados}
        lote = uuid.uuid4().hex[:12]
        con.execute("BEGIN IMMEDIATE")
        for m in mudam:
            con.execute("INSERT INTO titulo_correcao (lote, projeto_codigo, titulo_antes, titulo_depois, fonte, ator) VALUES (?,?,?,?,?,?)",
                        (lote, m["codigo"], m["antes"], m["depois"], m["fonte"], u["email"]))
            con.execute("UPDATE projeto SET titulo=?, atualizado_em=datetime('now') WHERE codigo=?", (m["depois"], m["codigo"]))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'titulo_corrigido',?,?)",
                        (m["codigo"], u["email"], json.dumps({"antes": m["antes"], "depois": m["depois"], "fonte": m["fonte"], "lote": lote}, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    site = _mandar_ao_site([m["codigo"] for m in mudam if m["tem_no_site"]], u["email"])
    return {"modo": "aplicar", "aplicado": True, "lote": lote, "mudam": mudam, "recusados": recusados, "site": site}


class Desfazer(BaseModel):
    lote: str


@router.post("/titulos-de-pasta/desfazer")
def desfazer(d: Desfazer, u: dict = Depends(auth.exige("admin"))) -> dict:
    if not re.fullmatch(r"[0-9a-f]{6,32}", d.lote or ""):
        raise HTTPException(400, "Lote inválido")
    con = connect()
    try:
        linhas = con.execute("SELECT * FROM titulo_correcao WHERE lote=? AND desfeito_em IS NULL", (d.lote,)).fetchall()
        if not linhas:
            raise HTTPException(404, "Nada a desfazer neste lote (já desfeito ou não existe)")
        voltaram, mantidos = [], []
        con.execute("BEGIN IMMEDIATE")
        for r in linhas:
            p = con.execute("SELECT titulo, tainacan_item_id FROM projeto WHERE codigo=?", (r["projeto_codigo"],)).fetchone()
            if not p or (p["titulo"] or "").strip() != (r["titulo_depois"] or "").strip():
                mantidos.append({"codigo": r["projeto_codigo"], "motivo": "o título mudou depois desta correção: ficou como está"})
            else:
                con.execute("UPDATE projeto SET titulo=?, atualizado_em=datetime('now') WHERE codigo=?", (r["titulo_antes"], r["projeto_codigo"]))
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'titulo_corrigido_desfeito',?,?)",
                            (r["projeto_codigo"], u["email"], json.dumps({"antes": r["titulo_depois"], "depois": r["titulo_antes"], "lote": d.lote}, ensure_ascii=False)))
                voltaram.append({"codigo": r["projeto_codigo"], "titulo": r["titulo_antes"], "tem_no_site": bool(p["tainacan_item_id"])})
            con.execute("UPDATE titulo_correcao SET desfeito_em=datetime('now'), desfeito_por=? WHERE id=?", (u["email"], r["id"]))
        con.commit()
    finally:
        con.close()
    site = _mandar_ao_site([v["codigo"] for v in voltaram if v["tem_no_site"]], u["email"])
    return {"ok": True, "voltaram": voltaram, "mantidos": mantidos, "site": site}


def _historico(con, limite: int = 20) -> list[dict]:
    out = []
    for g in con.execute("""SELECT lote, MIN(em) AS em, MIN(ator) AS ator, COUNT(*) AS n, MAX(desfeito_em) AS desfeito_em,
                                   SUM(CASE WHEN desfeito_em IS NULL THEN 1 ELSE 0 END) AS ativos
                              FROM titulo_correcao GROUP BY lote ORDER BY MIN(id) DESC LIMIT ?""", (limite,)):
        itens = [dict(r) for r in con.execute("SELECT projeto_codigo AS codigo, titulo_antes AS antes, titulo_depois AS depois, fonte, desfeito_em FROM titulo_correcao WHERE lote=? ORDER BY id", (g["lote"],))]
        nome = con.execute("SELECT nome FROM usuario WHERE email=?", (g["ator"],)).fetchone()     # a tela mostra o nome, nunca o e-mail
        out.append({"lote": g["lote"], "em": g["em"], "ator": g["ator"], "ator_nome": nome[0] if nome and nome[0] else None, "n": g["n"], "desfeito": not g["ativos"], "desfeito_em": g["desfeito_em"], "itens": itens})
    return out


@router.get("/titulos-de-pasta/historico")
def historico(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return {"lotes": _historico(con, 50)}
    finally:
        con.close()
