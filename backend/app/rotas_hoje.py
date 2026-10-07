"""Topo do painel inicial: o que pede a pessoa HOJE e o que aconteceu hoje.

Usa as mesmas regras do resto do painel (publicacao.condicoes_projeto, direitos_permitem_publicar, qnap_coletor.nivel_espaco):
nenhuma regra nova é inventada aqui, para os números nunca divergirem das telas.
"""
from fastapi import APIRouter, Depends

from . import auth, qnap_coletor
from .db import connect
from .publicacao import condicoes_projeto

router = APIRouter(prefix="/api", tags=["hoje"])

# O que cada divergência entre o painel e o site significa, em português (o campo cru nunca aparece na tela).
DIVERGENCIAS = {
    "sem_codigo": ("Item do site sem código CAMP",
                   "O item existe no site, mas o painel não achou o código nele (quase sempre item de teste). Corrija ou apague no WordPress."),
    "fundo_inexistente": ("Aponta para um fundo que não existe no painel",
                          "O termo ou item do site usa um código de fundo que o painel não conhece. Cadastre o fundo ou corrija o código no site."),
    "publicado_em_fundo_fora_do_ar": ("Público no site, mas o fundo está despublicado no painel",
                                      "A folha continua visível no site embora o fundo tenha sido despublicado aqui. Despublique a folha ou publique o fundo de novo."),
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
        candidatos = con.execute("SELECT * FROM projeto WHERE autorizado_site=1 AND status_site!='no_ar'").fetchall()
        prontos = sum(1 for p in candidatos if condicoes_projeto(con, p)["pode_publicar"])
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
        if prontos:
            acoes.append({"id": "publicar", "prioridade": 90, "impacto": prontos, "rota": "projetos",
                          "titulo": f"Publicar {prontos} projeto(s) pronto(s)", "detalhe": "Passam em todos os requisitos; use o painel Publicação do projeto"})
        for f in travados[:3]:
            acoes.append({"id": "direitos_" + f["codigo"], "prioridade": 80, "impacto": f["projetos"], "rota": "fundo/" + f["codigo"],
                          "titulo": f"Definir os direitos de {f['sigla'] or f['codigo']}", "detalhe": f"Segura {f['projetos']} projeto(s) que não podem ser publicados sem isso"})
        for f in autorizar[:3]:
            acoes.append({"id": "autorizar_" + f["codigo"], "prioridade": 70, "impacto": f["nao_autorizados"], "rota": "fundo/" + f["codigo"],
                          "titulo": f"Autorizar projetos de {f['sigla'] or f['codigo']}", "detalhe": f"{f['nao_autorizados']} projeto(s) com direitos ok, mas ainda sem autorização"})
        if snap and (snap["parados"] or 0) > 0:
            acoes.append({"id": "parados", "prioridade": 65, "impacto": snap["parados"], "rota": "estacoes",
                          "titulo": f"{snap['parados']} pasta(s) parada(s) na entrada do QNAP", "detalhe": "Sem alteração há dias: material esquecido ou travado no fluxo"})
        if sem_imagem:
            acoes.append({"id": "sem_imagem", "prioridade": 40, "impacto": sem_imagem, "rota": "estacoes",
                          "titulo": f"{sem_imagem} folha(s) do site sem imagem", "detalhe": "A lista está em Estações → Catálogo local × site"})
        if div_total:
            acoes.append({"id": "divergencias", "prioridade": 30, "impacto": div_total, "rota": None,
                          "titulo": f"{div_total} divergência(s) entre o painel e o site", "detalhe": "Clique para ver o que são, em português"})
        acoes.sort(key=lambda a: (-a["prioridade"], -a["impacto"]))
        return {
            "kpis": {"travados": {"fundos": len(travados), "projetos": seguram},
                     "prontos": {"valor": prontos, "autorizados": autorizados}},
            "hoje": dia, "acoes": acoes,
            "publicacao": {"fundos_travados": travados[:5], "fundos_para_autorizar": autorizar[:5], "prontos": prontos, "autorizados": autorizados},
            "divergencias": {"total": div_total, "tipos": [{"titulo": t, "n": n} for t, n in sorted(agrupado.items(), key=lambda x: -x[1])]},
            "qnap": {"nivel_espaco": nivel, "livre_pct": livre_pct},
        }
    finally:
        con.close()
