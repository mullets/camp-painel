"""Topo do painel inicial: o que pede a pessoa HOJE e o que aconteceu hoje.

Usa as mesmas regras do resto do painel (publicacao.condicoes_projeto, direitos_permitem_publicar, qnap_coletor.nivel_espaco):
nenhuma regra nova é inventada aqui, para os números nunca divergirem das telas.
"""
from fastapi import APIRouter, Depends, HTTPException

from . import auth, qnap_coletor, qualidade_base as qb
from .db import connect

router = APIRouter(prefix="/api", tags=["hoje"])

# O que cada divergência entre o painel e o site significa, em português (o campo cru nunca aparece na tela).
DIVERGENCIAS = {
    "sem_codigo": ("Item do site sem código CAMP",
                   "O item existe no site, mas o painel não achou o código nele (quase sempre item de teste). Corrija ou apague no WordPress."),
    "fundo_inexistente": ("Aponta para um fundo que não existe no painel",
                          "O termo ou item do site usa um código de fundo que o painel não conhece. Cadastre o fundo ou corrija o código no site."),
    "publicado_em_fundo_fora_do_ar": ("Público no site, mas o fundo está despublicado no painel",
                                      "A folha continua visível no site embora o fundo tenha sido despublicado aqui. Despublique a folha ou publique o fundo de novo."),
    "fundo_trocado": ("No site, o item está no fundo errado",
                      "O código da folha diz um fundo (no painel) e o campo Fundo do item no site diz outro (no site). Corrija o campo Fundo no WordPress: o código é que vale."),
    "sem_itens_no_site": ("Fundo sem nenhuma folha no site",
                          "Normal para fundos ainda não publicados. Só exige ação se o fundo deveria estar no site."),
}
PENDENTE = ("Texto editado no painel que ainda não foi gravado no site",
            "A gravação no site falhou; o painel tenta de novo na próxima sincronização.")
TIPOS_PUBLICACAO = ("site_publicar", "site_rascunho", "site_tirar_do_ar", "site_no_ar", "site_fora_do_ar")


def _rotulo(campo: str) -> tuple[str, str]:
    if campo in DIVERGENCIAS:
        return DIVERGENCIAS[campo]
    if campo.startswith("pendente_"):
        return PENDENTE
    return ("Outra divergência", "Tipo ainda sem explicação no painel; o código do item ajuda a localizar.")


@router.get("/site/divergencias/resumo")
def divergencias_resumo(u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        grupos: dict[str, dict] = {}
        for r in con.execute("SELECT * FROM divergencia_site WHERE resolvida=0 ORDER BY campo, codigo"):
            titulo, explicacao = _rotulo(r["campo"])
            g = grupos.setdefault(titulo, {"titulo": titulo, "explicacao": explicacao, "n": 0, "itens": []})
            g["n"] += 1
            if len(g["itens"]) < 50:
                g["itens"].append({"entidade": r["entidade"], "codigo": r["codigo"], "valor_painel": r["valor_painel"], "valor_site": r["valor_site"]})
        lista = sorted(grupos.values(), key=lambda g: -g["n"])
        return {"total": sum(g["n"] for g in lista), "grupos": lista}
    finally:
        con.close()


@router.get("/hoje")
def hoje(u: dict = Depends(auth.exige("leitura"))) -> dict:
    from .rotas_gestao import direitos_permitem_publicar
    con = connect()
    try:
        # ---------- publicação: o que trava e o que está pronto ----------
        travados, autorizar = [], []
        for f in con.execute("""SELECT f.codigo, f.titulo, f.sigla, COUNT(p.codigo) AS n,
                                       SUM(CASE WHEN p.autorizado_site=0 THEN 1 ELSE 0 END) AS nao_autorizados
                                  FROM fundo f JOIN projeto p ON p.fundo_codigo=f.codigo
                                 WHERE f.ativo=1 AND p.status_site!='no_ar' GROUP BY f.codigo ORDER BY n DESC, f.codigo"""):
            item = {"codigo": f["codigo"], "titulo": f["titulo"], "sigla": f["sigla"], "projetos": f["n"], "nao_autorizados": f["nao_autorizados"] or 0}
            if direitos_permitem_publicar(con, f["codigo"]):
                travados.append(item)
            elif item["nao_autorizados"]:
                autorizar.append(item)
        from .pendencias import contar_pendencias, fundos_travados
        pend = contar_pendencias(con)
        prontos = pend["prontos_publicar"]               # a mesma regra do painel inicial e do botão Publicar (plano da publicação guiada)
        trav = {f["codigo"]: f for f in fundos_travados(con)}       # travado = fundo com FOLHAS esperando (projeto só de inventário não conta)
        travados = [{**f, "projetos": trav[f["codigo"]]["projetos"]} for f in travados if f["codigo"] in trav]
        autorizados = con.execute("SELECT COUNT(*) FROM projeto WHERE autorizado_site=1").fetchone()[0]
        seguram = sum(f["projetos"] for f in travados)

        # ---------- o que aconteceu hoje (e ontem), no horário local do servidor ----------
        def contar(sql: str, deslocamento: str) -> int:
            try:
                return con.execute(sql, (deslocamento,) * sql.count("?")).fetchone()[0]
            except Exception:  # noqa: BLE001  (tabela/coluna ausente num banco antigo: conta zero, nunca derruba o painel)
                return 0
        marcas = ",".join("'" + t + "'" for t in TIPOS_PUBLICACAO)
        SQL = {
            "folhas": "SELECT COUNT(DISTINCT codigo) FROM evento WHERE entidade='item' AND date(quando,'localtime')=date('now','localtime',?)",
            "projetos_novos": "SELECT COUNT(*) FROM projeto WHERE date(criado_em,'localtime')=date('now','localtime',?)",
            "publicacoes": f"SELECT COUNT(*) FROM evento WHERE tipo IN ({marcas}) AND date(quando,'localtime')=date('now','localtime',?)",
            "pedidos_e_erros": "SELECT (SELECT COUNT(*) FROM solicitacao WHERE date(recebida_em,'localtime')=date('now','localtime',?)) + "
                               "(SELECT COUNT(*) FROM erro WHERE date(criado_em,'localtime')=date('now','localtime',?))",
        }
        dia = {k: {"hoje": contar(q, "+0 days"), "ontem": contar(q, "-1 days")} for k, q in SQL.items()}

        # ---------- QNAP e site ----------
        snap = qnap_coletor.ultima(con)
        nivel, livre_pct = qnap_coletor.nivel_espaco(con, snap["total_gb"] if snap else None, snap["livre_gb"] if snap else None)
        sem_imagem = con.execute("SELECT COUNT(*) FROM wp_item WHERE colecao_id=8013 AND COALESCE(documento_url,'')='' AND COALESCE(thumb_url,'')=''").fetchone()[0]
        div_total = con.execute("SELECT COUNT(*) FROM divergencia_site WHERE resolvida=0").fetchone()[0]
        div_tipos = [{"titulo": _rotulo(c)[0], "n": n} for c, n in con.execute("SELECT campo, COUNT(*) FROM divergencia_site WHERE resolvida=0 GROUP BY campo")]
        agrupado: dict[str, int] = {}
        for d in div_tipos:
            agrupado[d["titulo"]] = agrupado.get(d["titulo"], 0) + d["n"]

        # ---------- as ações do dia, da mais importante para a menos ----------
        acoes: list[dict] = []
        if nivel in ("critico", "aviso") and snap:
            acoes.append({"id": "qnap_espaco", "prioridade": 100 if nivel == "critico" else 60, "impacto": 0, "rota": "estacoes",
                          "titulo": "QNAP quase cheio" if nivel == "critico" else "QNAP com pouco espaço",
                          "detalhe": f"{round(snap['livre_gb'])} GB livres ({str(livre_pct).replace('.', ',')}%)"})
        for pb in con.execute("""SELECT p.codigo, p.titulo FROM projeto p WHERE p.status_site='no_ar' AND EXISTS (SELECT 1 FROM erro e WHERE e.gravidade='bloqueia'
                                 AND e.situacao IN ('aberto','em_correcao') AND (e.codigo=p.codigo OR e.codigo LIKE p.codigo||'-%')) ORDER BY p.codigo LIMIT 5"""):
            acoes.append({"id": "pub_bloq_" + pb["codigo"], "prioridade": 98, "impacto": 1, "rota": "projeto/" + pb["codigo"],
                          "titulo": f"{pb['codigo']} está publicado com erro bloqueante", "detalhe": "Resolva o erro ou despublique o projeto"})
        if prontos:
            acoes.append({"id": "publicar", "prioridade": 90, "impacto": prontos, "rota": "projetos",
                          "titulo": f"Publicar {prontos} projeto(s) pronto(s)", "detalhe": "Passam em todos os requisitos; use o painel Publicação do projeto"})
        for f in travados[:3]:
            acoes.append({"id": "direitos_" + f["codigo"], "prioridade": 80, "impacto": f["projetos"], "rota": "fundo/" + f["codigo"],
                          "titulo": f"Definir os direitos de {f['sigla'] or f['codigo']}", "detalhe": f"Segura {f['projetos']} projeto(s) que não podem ser publicados sem isso"})
        for f in autorizar[:3]:
            acoes.append({"id": "autorizar_" + f["codigo"], "prioridade": 70, "impacto": f["nao_autorizados"], "rota": "fundo/" + f["codigo"],
                          "titulo": f"Autorizar projetos de {f['sigla'] or f['codigo']}", "detalhe": f"{f['nao_autorizados']} projeto(s) prontos, mas ainda sem autorização"})
        if snap and (snap["parados"] or 0) > 0:
            acoes.append({"id": "parados", "prioridade": 65, "impacto": snap["parados"], "rota": "estacoes",
                          "titulo": f"{snap['parados']} pasta(s) parada(s) na entrada do QNAP", "detalhe": "Sem alteração há dias: material esquecido ou travado no fluxo"})
        if sem_imagem:
            acoes.append({"id": "sem_imagem", "prioridade": 40, "impacto": sem_imagem, "rota": "estacoes",
                          "titulo": f"{sem_imagem} folha(s) do site sem imagem", "detalhe": "A lista está em Estações → Catálogo local × site"})
        if div_total:
            acoes.append({"id": "divergencias", "prioridade": 30, "impacto": div_total, "rota": None,
                          "titulo": f"{div_total} divergência(s) entre o painel e o site", "detalhe": "Clique para ver o que são, em português"})
        # ---------- qualidade da base, na MESMA fila (prioridade por impacto); "Agora não" esconde por 7 dias, por pessoa ----------
        tq = qb.tarefas_qualidade(con, u["id"])
        acoes += [{**t, "base": True} for t in qb.fila_do_dia(tq)]
        esconder = qb.adiadas(con, u["id"])
        acoes = [a for a in acoes if a["id"] not in esconder]
        acoes.sort(key=lambda a: (-a["prioridade"], -a["impacto"]))
        qual = qb.visao_geral(con)
        return {
            "kpis": {"travados": {"fundos": len(travados), "projetos": seguram},
                     "prontos": {"valor": prontos, "autorizados": autorizados}},
            "hoje": dia, "acoes": acoes,
            "publicacao": {"fundos_travados": travados[:5], "fundos_para_autorizar": autorizar[:5], "prontos": prontos, "autorizados": autorizados},
            "divergencias": {"total": div_total, "tipos": [{"titulo": t, "n": n} for t, n in sorted(agrupado.items(), key=lambda x: -x[1])]},
            "qnap": {"nivel_espaco": nivel, "livre_pct": livre_pct},
            "base": {"total": len(tq), "tipos": qb.resumo_tipos(tq)},
            "qualidade": {"geral": qual["geral"], "fundos": qual["fundos"]},
            "melhorias": qb.melhorias(con),
        }
    finally:
        con.close()


@router.post("/hoje/tarefas/{tarefa_id}/agora-nao")
def agora_nao(tarefa_id: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Esconde esta tarefa só para quem clicou, por 7 dias. Depois ela volta sozinha (se ainda existir)."""
    if not tarefa_id or len(tarefa_id) > 120:
        raise HTTPException(400, "Tarefa inválida")
    con = connect()
    try:
        ate = qb.adiar(con, u["id"], tarefa_id)
        con.commit()
        return {"ok": True, "ate": ate, "mensagem": f"Escondida por {qb.DIAS_ADIAR} dias. Depois ela volta, se ainda precisar."}
    finally:
        con.close()


@router.get("/qualidade-base")
def qualidade_base(u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        return qb.visao_geral(con)
    finally:
        con.close()


@router.get("/qualidade-base/fundo/{codigo}")
def qualidade_base_fundo(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        f = qb.do_fundo(con, codigo)
        if not f:
            raise HTTPException(404, "Fundo não encontrado")
        return f
    finally:
        con.close()


@router.get("/melhorias")
def melhorias(u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        return qb.melhorias(con)
    finally:
        con.close()
