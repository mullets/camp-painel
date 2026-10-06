"""Catálogo local × site: prévia fiel do que a importação faria e execução protegida.

A prévia roda o MESMO código do importador em modo simulação (desfaz tudo no fim). A execução recusa se os números
mudaram desde a prévia, para ninguém importar algo diferente do que viu.
"""
import collections
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect
from .importador_site import COL_ACERVO, executar

router = APIRouter(prefix="/api", tags=["importacao"])
LIMITE = 60


def _previa() -> dict:
    n = executar(log=lambda *a, **k: None, simular=True)
    por_fundo: dict = collections.defaultdict(lambda: {"itens": 0, "projetos": 0})
    for _c, _t, _p, f in n["itens_novos_lista"]:
        por_fundo[f]["itens"] += 1
    for _p, _t, f in n["projetos_novos_lista"]:
        por_fundo[f]["projetos"] += 1
    con = connect()
    try:
        sem_img = con.execute("""SELECT id, codigo_detectado, status, titulo FROM wp_item
                                  WHERE colecao_id=? AND COALESCE(documento_url,'')='' AND COALESCE(thumb_url,'')=''
                                  ORDER BY codigo_detectado, id""", (COL_ACERVO,)).fetchall()
        locais_sem_site = con.execute("""SELECT COUNT(*) FROM item WHERE codigo NOT IN
                                  (SELECT codigo_detectado FROM wp_item WHERE colecao_id=? AND codigo_detectado IS NOT NULL)""", (COL_ACERVO,)).fetchone()[0]
        ult = con.execute("SELECT MAX(visto_em) FROM wp_item").fetchone()[0]
        total_local = con.execute("SELECT COUNT(*) FROM item").fetchone()[0]
        total_site = con.execute("SELECT COUNT(*) FROM wp_item WHERE colecao_id=?", (COL_ACERVO,)).fetchone()[0]
    finally:
        con.close()
    corte = lambda l: l[:LIMITE]  # noqa: E731
    return {
        "projetos_novos": n["projetos_novos"], "projetos_atualizados": n["projetos_atualizados"],
        "itens_novos": n["itens_novos"], "itens_atualizados": n["itens_atualizados"],
        "novos_por_fundo": [{"fundo": f, **v} for f, v in sorted(por_fundo.items())],
        "itens_novos_amostra": [{"codigo": c, "titulo": t, "projeto": p} for c, t, p, _f in corte(n["itens_novos_lista"])],
        "projetos_novos_amostra": [{"codigo": c, "titulo": t, "fundo": f} for c, t, f in corte(n["projetos_novos_lista"])],
        "sem_codigo_total": len(n["sem_codigo"]),
        "sem_codigo": [{"id": i, "titulo": t, "fundo": f} for i, t, f in corte(n["sem_codigo"])],
        "fundo_desconhecido": [{"id": i, "titulo": t, "fundo": f} for i, t, f in corte(n["fundo_desconhecido"])],
        "item_sem_projeto": [{"id": i, "codigo": c} for i, c in corte(n["item_sem_projeto"])],
        "site_sem_imagem_total": len(sem_img),
        "site_sem_imagem": [{"id": r["id"], "codigo": r["codigo_detectado"], "status": r["status"], "titulo": r["titulo"]} for r in corte(sem_img)],
        "locais_sem_item_no_site": locais_sem_site, "total_local": total_local, "total_site": total_site, "espelho_em": ult,
        "limite_listas": LIMITE,
    }


@router.get("/importacao/previa")
def previa(u: dict = Depends(auth.exige("admin"))) -> dict:
    return _previa()


class Execucao(BaseModel):
    esperado_itens_novos: int
    esperado_projetos_novos: int


@router.post("/importacao/executar")
def executar_importacao(d: Execucao, u: dict = Depends(auth.exige("admin"))) -> dict:
    atual = _previa()
    if (atual["itens_novos"], atual["projetos_novos"]) != (d.esperado_itens_novos, d.esperado_projetos_novos):
        raise HTTPException(409, f"A prévia mudou (agora: {atual['projetos_novos']} projetos e {atual['itens_novos']} itens novos). "
                                 "Veja a prévia de novo antes de importar.")
    n = executar(log=lambda *a, **k: None)
    con = connect()
    try:
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('sistema','importacao','importacao_site',?,?)",
                    (u["email"], json.dumps({k: n[k] for k in ("projetos_novos", "projetos_atualizados", "itens_novos", "itens_atualizados")})))
        con.commit()
    finally:
        con.close()
    return {"ok": True, **{k: n[k] for k in ("projetos_novos", "projetos_atualizados", "itens_novos", "itens_atualizados")}}
