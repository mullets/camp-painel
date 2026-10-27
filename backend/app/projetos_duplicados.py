"""UX-29 (27/10, P2): possível duplicata ao criar ou editar um projeto, e o relatório "Possíveis projetos duplicados" em Problemas.

A pergunta "projeto parecido" só existia na reserva da estação e no clique de "Criar projeto". Agora:
- GET /api/projetos/{c}/parecidos?titulo=… (editar): projetos do MESMO fundo parecidos com o nome que está sendo digitado, sem o
  próprio projeto e sem os pares que uma pessoa já disse que "não são o mesmo" (par_nao_duplicado, migração 059);
- POST /api/projetos/verificar (novo projeto) ganha a miniatura de cada parecido (campo novo, opcional);
- GET /api/duplicados/projetos: os pares de TODOS os fundos (o mesmo motor de B7/UX-01: similaridade.pontuar), para Problemas.
  "Não é duplicata" é o mesmo POST /api/fundos/{f}/duplicados/nao-sao de B7: o par não volta.
Nada é juntado nem apagado: é só aviso; juntar é o "Mesclar" do projeto, com simulação.
"""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException

from . import auth
from .db import connect
from difflib import SequenceMatcher

from .similaridade import buscar_parecidos, nivel, normalizar, pontuar, tokens_distintivos

router = APIRouter(prefix="/api", tags=["duplicados"])

_CACHE: dict = {}
_TRAVA = threading.Lock()


def _nao_sao(con) -> set[tuple[str, str]]:
    return {(r[0], r[1]) for r in con.execute("SELECT a, b FROM par_nao_duplicado")}


def capas(con, cods) -> dict:
    """Miniatura de cada projeto (o que já está no site ou a 1ª folha com prévia): a mesma regra das Decisões."""
    from .rotas_decisoes import _resumo_projetos
    return {c: r.get("capa") for c, r in _resumo_projetos(con, set(cods)).items()}


def parecidos(con, fundo: str, titulo: str, ano=0, cidade=None, identificacao_original=None, ignorar: str | None = None) -> list[dict]:
    """buscar_parecidos sem o próprio projeto (editar) e sem os pares já marcados "não são o mesmo"; cada um com a miniatura."""
    nao = _nao_sao(con) if ignorar else set()
    out = [p for p in buscar_parecidos(con, fundo, titulo, ano, cidade, identificacao_original, limite=8)
           if p["codigo"] != ignorar and tuple(sorted((p["codigo"], ignorar or ""))) not in nao]
    out = [p for p in out if not con.execute("SELECT 1 FROM projeto WHERE codigo=? AND (mesclado_em IS NOT NULL OR descartado_em IS NOT NULL)", (p["codigo"],)).fetchone()][:5]
    cp = capas(con, [p["codigo"] for p in out])
    for p in out:
        p["capa"] = cp.get(p["codigo"])
    return out


def _assinatura(con) -> tuple:
    return tuple(con.execute("""SELECT (SELECT COUNT(*) FROM projeto), (SELECT COALESCE(MAX(rowid),0) FROM projeto),
                                       (SELECT COALESCE(SUM(LENGTH(COALESCE(titulo,'')) + COALESCE(ano,0) + LENGTH(COALESCE(cidade,''))),0) FROM projeto),
                                       (SELECT COUNT(*) FROM projeto WHERE mesclado_em IS NOT NULL OR descartado_em IS NOT NULL),
                                       (SELECT COUNT(*) FROM par_nao_duplicado)""").fetchone())


def _pre(p: dict) -> dict:
    t = tokens_distintivos(p.get("titulo"))
    return {"set": set(t), "txt": " ".join(t), "ident": normalizar(p.get("identificacao_original"))}


def _pode_ser_parecido(a: dict, b: dict) -> bool:
    """Filtro rápido e SEGURO antes de pontuar (400 projetos = 80 mil pares): sem identificação igual, sem palavra em comum e com
    quick_ratio (teto do ratio de pontuar) abaixo de 0,65, a nota não chega a 0,75 nem com ano e cidade (+0,10)."""
    if a["ident"] and a["ident"] == b["ident"]:
        return True
    if a["set"] & b["set"]:
        return True
    return SequenceMatcher(None, a["txt"], b["txt"]).quick_ratio() >= 0.65


def _calcular(con, ass) -> list[dict]:
    """A conta pesada (todos os pares de cada fundo). Cede a vez a outras threads de tempos em tempos: com fundos de 300 projetos
    são dezenas de milhares de pares em Python puro, e sem ceder a conta prende o servidor (a Home passava de 30 s, 27/10)."""
    import time as _t
    nao = _nao_sao(con)
    por_fundo: dict[str, list[dict]] = {}
    for r in con.execute("""SELECT p.codigo, p.titulo, p.ano, p.cidade, p.identificacao_original, p.fundo_codigo,
                                   (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo) AS folhas
                              FROM projeto p WHERE p.mesclado_em IS NULL AND p.descartado_em IS NULL ORDER BY p.codigo"""):
        por_fundo.setdefault(r["fundo_codigo"], []).append(dict(r))
    pares, k = [], 0
    for ps in por_fundo.values():
        pre = [_pre(x) for x in ps]
        for i, x in enumerate(ps):
            for j in range(i + 1, len(ps)):
                k += 1
                if k % 300 == 0:
                    _t.sleep(0.002)            # cede o GIL: as requisições do painel seguem respondendo durante a conta
                y = ps[j]
                if (x["codigo"], y["codigo"]) in nao or not _pode_ser_parecido(pre[i], pre[j]):
                    continue
                score, motivos = pontuar(x, y)
                n = nivel(score)
                if n:
                    pares.append({"fundo": x["fundo_codigo"], "a": x, "b": y, "score": score, "nivel": n, "motivos": motivos})
    pares.sort(key=lambda p: (-p["score"], p["a"]["codigo"]))
    return pares


def _rodar_conta(ass) -> None:
    con = connect()
    try:
        pares = _calcular(con, ass)
        with _TRAVA:
            _CACHE.update({"ass": ass, "pares": pares})
    finally:
        con.close()
        with _TRAVA:
            _CACHE.pop("em_curso", None)


def todos_os_pares(con, espera_s: float | None = None) -> tuple[list[dict], bool]:
    """(pares, calculando). A conta roda UMA vez por vez, numa thread própria, nunca repetida em paralelo (antes, cada página que
    abria começava a sua: recarregar 5× = 5 contas ao mesmo tempo, e o painel inteiro parava). Quem pede espera no máximo
    `espera_s` (None = até acabar); se não acabou, recebe o último resultado guardado (ou nenhum) com calculando=True."""
    ass = _assinatura(con)
    with _TRAVA:
        if _CACHE.get("ass") == ass:
            return _CACHE["pares"], False
        t = _CACHE.get("em_curso")
        if t is None or not t.is_alive():
            t = threading.Thread(target=_rodar_conta, args=(ass,), name="duplicados-projetos", daemon=True)
            _CACHE["em_curso"] = t
            t.start()
    t.join(espera_s)
    with _TRAVA:
        if _CACHE.get("ass") == ass:
            return _CACHE["pares"], False
        return list(_CACHE.get("pares") or []), True


@router.get("/projetos/{codigo}/parecidos")
def parecidos_do_projeto(codigo: str, titulo: str = "", u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Editando o nome: projetos do mesmo fundo parecidos com `titulo` (sem `titulo`: com o nome atual)."""
    con = connect()
    try:
        p = con.execute("SELECT codigo, fundo_codigo, titulo, ano, cidade, identificacao_original FROM projeto WHERE codigo=?", (codigo,)).fetchone()
        if not p:
            raise HTTPException(404, "Projeto não existe")
        t = (titulo or p["titulo"] or "").strip()
        return {"projeto": codigo, "fundo": p["fundo_codigo"], "titulo": t,
                "parecidos": parecidos(con, p["fundo_codigo"], t, p["ano"], p["cidade"], None, ignorar=codigo) if t else []}
    finally:
        con.close()


@router.get("/duplicados/projetos")
def possiveis_duplicatas(limite: int = 50, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Relatório de Problemas: possíveis projetos duplicados em todos os fundos, com a miniatura de cada um."""
    limite = max(1, min(int(limite or 50), 200))
    con = connect()
    try:
        pares, calculando = todos_os_pares(con, espera_s=2.0)   # nunca prende a requisição: no máximo 2 s
        vis = [dict(x) for x in pares[:limite]]
        cp = capas(con, {c for x in vis for c in (x["a"]["codigo"], x["b"]["codigo"])})
        for x in vis:
            x["a"] = {**x["a"], "capa": cp.get(x["a"]["codigo"])}
            x["b"] = {**x["b"], "capa": cp.get(x["b"]["codigo"])}
        return {"total": len(pares), "pares": vis, "calculando": calculando}
    finally:
        con.close()
