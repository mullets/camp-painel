"""Checklists vivos de publicação para FUNDO e ARQUITETO (o painel mostra o que falta e o botão que resolve).

Fundo: usa a mesma regra única dos projetos (publicacao.condicoes_projeto).
Arquiteto: o painel NÃO publica arquiteto no site. O arquiteto aparece quando algum fundo dele tem projeto publicado e
está ativo no plugin do WordPress (CAMP Acervo > Arquitetos: foto, biografia, ativar). O campo "status" do agente no painel
é só um marcador interno. O checklist diz isso com todas as letras e mostra o que o painel consegue verificar.
"""
from fastapi import APIRouter, Depends, HTTPException

from . import auth
from .db import connect
from .publicacao import condicoes_projeto

router = APIRouter(prefix="/api", tags=["guia"])
LIMITE_PROJETOS = 3000   # acima disso a contagem de "prontos" fica aproximada (nunca aconteceu)



def texto_projetos(publicados: int, a_publicar: int, total: int) -> str:
    """Uma frase por situação (e não 'N de M... (X autorizados, Y já publicados)', que não dizia QUAL estava pronto): '1 publicado · 1 pronto para publicar · 1 com pendência'."""
    if total == 0:
        return "Nenhum projeto ainda"
    pend = total - publicados - a_publicar
    partes = [f"{publicados} publicado{'s' if publicados != 1 else ''}" if publicados else "",
              f"{a_publicar} pronto{'s' if a_publicar != 1 else ''} para publicar" if a_publicar else "",
              f"{pend} com pendência" if pend else ""]
    return " · ".join(x for x in partes if x)

def _c(id_, bloqueia, ok, texto, detalhe=None, acao=None) -> dict:
    return {"id": id_, "bloqueia": bloqueia, "ok": bool(ok), "texto": texto, "detalhe": None if ok else detalhe, "acao": None if ok else acao}


def _acao(tipo, rotulo, alvo) -> dict:
    return {"tipo": tipo, "rotulo": rotulo, "alvo": str(alvo)}


def _proximo(conds: list[dict], estado: str, depois: str) -> str:
    for c in conds:
        if c["bloqueia"] and not c["ok"]:
            return (c["acao"]["rotulo"] + ": " if c["acao"] else "") + (c["detalhe"] or c["texto"])
    return depois


@router.get("/fundos/{codigo}/publicacao")
def guia_fundo(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    from .rotas_gestao import direitos_permitem_publicar
    con = connect()
    try:
        f = con.execute("SELECT * FROM fundo WHERE codigo=?", (codigo,)).fetchone()
        if not f:
            raise HTTPException(404, "Fundo não existe")
        msg = direitos_permitem_publicar(con, codigo)
        n_ag = con.execute("SELECT COUNT(*) FROM fundo_agente WHERE fundo_codigo=?", (codigo,)).fetchone()[0]
        hist, fonte = bool((f["historia_arquivistica"] or "").strip()), bool((f["fonte_historia"] or "").strip())
        projetos = con.execute("SELECT * FROM projeto WHERE fundo_codigo=? ORDER BY codigo LIMIT ?", (codigo, LIMITE_PROJETOS)).fetchall()
        autor = sum(1 for p in projetos if p["autorizado_site"])
        publicados = sum(1 for p in projetos if p["status_site"] == "no_ar")
        pode = {p["codigo"]: condicoes_projeto(con, p)["pode_publicar"] for p in projetos}
        prontos = sum(1 for p in projetos if pode[p["codigo"]])
        a_publicar = sum(1 for p in projetos if pode[p["codigo"]] and p["status_site"] != "no_ar")
        total = len(projetos)
        conds = [
            _c("direitos", True, msg is None, f"Direitos do fundo {codigo} autorizados", msg, _acao("direitos", "Definir direitos do fundo", codigo)),
            _c("agente", False, n_ag > 0, "Arquiteto ou produtor vinculado (proveniência)", "Nenhum agente vinculado a este fundo", _acao("vincular", "Vincular arquiteto", codigo)),
            _c("historia", False, hist and fonte, "História e procedência com fonte citada",
               "A história ainda não foi escrita (o painel só aceita história com a fonte citada)", _acao("editar", "Editar o fundo", codigo)),
            _c("sigla", False, bool(f["sigla"]), "Sigla de 3 letras definida", "Sem sigla não há etiquetas nem nomes de arquivo", _acao("editar", "Definir a sigla", codigo)),
            _c("projetos", True, prontos > 0, texto_projetos(publicados, a_publicar, total),
               "O fundo ainda não tem projetos" if total == 0 else
               "Nenhum projeto está pronto: em cada projeto, autorize a publicação e envie as folhas ao site (o checklist do projeto mostra o que falta)",
               _acao("projetos", "Ver os projetos", codigo)),
        ]
        estado = f["status_site"]
        return {"estado": estado, "condicoes": conds, "pode_publicar": all(c["ok"] for c in conds if c["bloqueia"]),
                "contagem": {"projetos": total, "autorizados": autor, "prontos": prontos, "publicados": publicados},
                "pode_agir": u["papel"] in ("admin", "master"),
                "proximo_passo": _proximo(conds, estado, "Tudo pronto: publique projeto por projeto (painel Publicação do projeto) ou o fundo inteiro (admin master). Depois confira as páginas públicas."
                                          if estado != "no_ar" else "O fundo está publicado. Confira as páginas públicas e as folhas novas.")}
    finally:
        con.close()


@router.get("/agentes/{aid}/publicacao")
def guia_agente(aid: int, u: dict = Depends(auth.exige("leitura"))) -> dict:
    from .rotas_projetos import _slug_publico
    con = connect()
    try:
        a = con.execute("SELECT * FROM agente WHERE id=?", (aid,)).fetchone()
        if not a:
            raise HTTPException(404, "Agente não existe")
        fundos = [r[0] for r in con.execute("SELECT fundo_codigo FROM fundo_agente WHERE agente_id=? ORDER BY fundo_codigo", (aid,))]
        pub = con.execute("""SELECT COUNT(*) FROM projeto p JOIN fundo_agente fa ON fa.fundo_codigo=p.fundo_codigo
                              WHERE fa.agente_id=? AND p.status_site='no_ar'""", (aid,)).fetchone()[0]
        hist, fonte = bool((a["historia"] or "").strip()), bool((a["fonte_historia"] or "").strip())
        slug = _slug_publico(a["forma_autorizada"] or "")
        pag = con.execute("""SELECT url, status FROM wp_pagina WHERE url LIKE '%/acervo/arquitetos/%'
                              AND (lower(slug)=? OR lower(slug) LIKE ?) ORDER BY (status='publish') DESC, id DESC LIMIT 1""", (slug, slug + "-%")).fetchone()
        conds = [
            _c("vinculo", True, bool(fundos), "Vinculado a um fundo (proveniência)", "O arquiteto precisa estar vinculado a pelo menos um fundo",
               _acao("vincular", "Vincular a um fundo", fundos[0] if fundos else "")),
            _c("publicado", True, pub > 0, f"Algum fundo dele tem projeto publicado ({pub} projeto(s))",
               "O arquiteto só aparece no site quando um fundo dele tem projeto publicado. Publique projetos do fundo primeiro",
               _acao("fundo", "Abrir o fundo", fundos[0]) if fundos else None),
            _c("historia", False, hist and fonte, "Biografia/história com fonte citada",
               "A biografia ainda não foi escrita (o painel só aceita biografia com a fonte citada)", _acao("editar_agente", "Editar o arquiteto", aid)),
            _c("termo", False, bool(a["tainacan_term_id"]), "Termo do arquiteto criado no Tainacan", "Criado automaticamente ao salvar o arquiteto; se faltar, salve-o de novo"),
            _c("pagina", False, bool(pag and pag["status"] == "publish"), "Página pública do arquiteto existe no site",
               ("A página existe no site, mas está como " + str(pag["status"]) + " (não publicado)") if pag else
               "Não achei a página no espelho do site. Ela é gerada pelo plugin quando o arquiteto está ativo e tem algo publicado"),
            _c("wpadmin", False, False, "Foto e biografia do arquiteto no WordPress (feito FORA do painel)",
               "No wp-admin: CAMP Acervo > Arquitetos > enviar foto, escrever a biografia e ativar. O painel não faz isso",
               _acao("wpadmin", "Abrir o wp-admin", "https://camp.arq.br/wp-admin/")),
        ]
        return {"condicoes": conds, "pode_publicar": all(c["ok"] for c in conds if c["bloqueia"]), "fundos": fundos,
                "pagina_url": pag["url"] if pag else None, "pagina_status": pag["status"] if pag else None,
                "pode_agir": u["papel"] in ("admin", "master"),
                "proximo_passo": _proximo(conds, a["status_site"], "O painel já fez a sua parte. Falta no wp-admin: foto, biografia e ativar o arquiteto (CAMP Acervo > Arquitetos).")}
    finally:
        con.close()
