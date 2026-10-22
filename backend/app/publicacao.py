"""Regras de publicação num só lugar.

Usadas pelo botão "Publicar" do projeto, pela publicação em lote e pela do fundo inteiro, para que NUNCA divirjam
(antes o fundo inteiro ignorava erros bloqueantes e lote de teste e publicava folhas duplicadas).
Vocabulário: docs/vocabulario.md.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time

from .db import connect

# Uma folha só vai ao site se: não é duplicata, não foi retida e, quando veio da revisão do CAMP Vision (tem lote), já foi conferida/corrigida.
# CAMP-046 (contrato 2.4): autoria divergente NÃO é mais motivo para ficar de fora; vira AVISO ("autoria não confirmada") e a folha sobe com esse texto no crédito.
# 21/10 ("publicar sem travar", 4.1): problema que BLOQUEIA numa folha deixa só aquela folha de fora (não trava o projeto inteiro)
SEM_BLOQUEIO_NA_FOLHA = ("NOT EXISTS (SELECT 1 FROM erro eb WHERE eb.codigo=item.codigo AND eb.situacao IN ('aberto','em_correcao') "
                         "AND eb.gravidade='bloqueia' AND eb.categoria<>'autoria_divergente')")
ELEGIVEL_LOCAL = f"duplicata_de IS NULL AND retida=0 AND (lote_id IS NULL OR revisao<>'pendente') AND {SEM_BLOQUEIO_NA_FOLHA}"   # retida = a pessoa decidiu que esta folha não vai ao site
# O que ainda para o projeto inteiro (lista fechada): direitos, projeto sem título e um bloqueio no PRÓPRIO projeto registrado por uma
# pessoa (ou arquivo corrompido apontado pelo CAMP Vision sem dizer a folha). Bloqueio em folha nunca para o projeto.
# a mesma regra para as contas gerais (Painel inicial): o bloqueio que trava um projeto (no próprio projeto ou no fundo, não numa folha)
TRAVA_SQL = ("gravidade='bloqueia' AND categoria<>'autoria_divergente' AND length(codigo)<=10 "
             "AND origem<>'campvision'")
BLOQUEIO_DO_PROJETO = ("SELECT COUNT(*) FROM erro WHERE codigo=? AND situacao IN ('aberto','em_correcao') AND gravidade='bloqueia' "
                       "AND categoria<>'autoria_divergente' AND origem<>'campvision'")


def _outros_bloqueantes(con, codigo: str) -> int:
    """B4: erros bloqueantes em aberto do projeto que NÃO são de autoria divergente (esses o "Registrar coautoria" resolve)."""
    return con.execute("""SELECT COUNT(*) FROM erro WHERE (codigo=? OR codigo LIKE ? || '-%') AND situacao IN ('aberto','em_correcao')
                          AND gravidade='bloqueia' AND categoria<>'autoria_divergente'""", (codigo, codigo)).fetchone()[0]   # (CAMP-046: autoria nunca bloqueia; mantida só por compatibilidade)
ELEGIVEL = f"tainacan_item_id IS NOT NULL AND {ELEGIVEL_LOCAL}"


def condicoes_projeto(con, p) -> dict:
    """Lista de requisitos para publicar um projeto (cada um com o que resolve) e se pode publicar agora."""
    from .rotas_gestao import direitos_permitem_publicar   # import tardio: evita ciclo entre módulos
    codigo, fundo = p["codigo"], p["fundo_codigo"]
    conds: list[dict] = []

    msg = direitos_permitem_publicar(con, fundo)
    conds.append({"id": "direitos", "bloqueia": True, "ok": msg is None, "texto": f"Direitos do fundo {fundo} autorizados",
                  "detalhe": msg, "acao": None if msg is None else {"tipo": "direitos", "rotulo": "Definir direitos do fundo", "alvo": fundo}})

    autorizado = bool(p["autorizado_site"])
    conds.append({"id": "autorizado", "bloqueia": True, "ok": autorizado, "texto": "Projeto autorizado para publicação",
                  "detalhe": None if autorizado else "O projeto ainda não foi autorizado para publicação (autorizar não publica sozinho)",
                  "acao": None if autorizado else {"tipo": "autorizar", "rotulo": "Autorizar publicação", "alvo": codigo}})

    b = con.execute("SELECT itens_autoria_divergente FROM v_bloqueios_publicacao WHERE codigo=?", (codigo,)).fetchone()
    div = (b[0] or 0) if b else 0
    err = con.execute(BLOQUEIO_DO_PROJETO, (codigo,)).fetchone()[0]          # 21/10 (4.1): só o bloqueio no próprio projeto
    livre = not err
    conds.append({"id": "bloqueios", "bloqueia": True, "ok": livre, "texto": "Nenhum bloqueio no projeto",
                  "detalhe": None if livre else f"Não dá para publicar porque há {err} bloqueio(s) registrado(s) no projeto",
                  "acao": None if livre else {"tipo": "erros", "rotulo": "Ver o bloqueio", "alvo": codigo}})
    titulo_ok = bool((p["titulo"] or "").strip())
    if not titulo_ok:
        conds.append({"id": "titulo", "bloqueia": True, "ok": False, "texto": "Projeto com título",
                      "detalhe": "Não dá para publicar porque o projeto está sem título", "acao": {"tipo": "editar_projeto", "rotulo": "Dar o título", "alvo": f"{codigo}:titulo"}})
    fora_bloq = con.execute(f"SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND NOT ({SEM_BLOQUEIO_NA_FOLHA})", (codigo,)).fetchone()[0]
    if fora_bloq:                       # 21/10 (4.1): a folha com problema que bloqueia fica de fora; o resto publica
        conds.append({"id": "folhas_com_bloqueio", "bloqueia": False, "ok": False,
                      "texto": f"{fora_bloq} folha(s) com problema ficam fora desta publicação; as outras publicam",
                      "detalhe": None, "acao": {"tipo": "erros", "rotulo": "Ver as folhas", "alvo": codigo}})
    if div:   # CAMP-046: autoria não confirmada é AVISO (não trava): a folha sobe com "Autoria não confirmada" no crédito
        conds.append({"id": "autoria_nao_confirmada", "bloqueia": False, "ok": False,
                      "texto": f"{div} folha(s) com autoria não confirmada" if div != 1 else "1 folha com autoria não confirmada",
                      "detalhe": "Sobem ao site com o crédito “Autoria não confirmada”; o nome lido no carimbo não é tratado como fato.",
                      "acao": {"tipo": "autoria", "rotulo": "É de outro autor? Registrar coautoria/terceiros", "alvo": codigo}})

    # CV2 §10 (contrato 9.4): o lote mais recente do projeto com aceite reprovado trava a publicação
    la = con.execute("""SELECT id, aceite_json FROM lista_processamento WHERE projeto_codigo=? AND aceite_json IS NOT NULL
                        ORDER BY id DESC LIMIT 1""", (codigo,)).fetchone()
    if la:
        from .saidas_cv import motivos_aceite, avaliar_aceite, conferencia_do_lote
        try:
            ac = json.loads(la["aceite_json"])
        except ValueError:
            ac = {}
        # Regra única com a tela (saidas_cv.avaliar_aceite): o aceite é uma foto do momento da leitura. Os pontos que pedem OLHO HUMANO
        # (orientação/série incertas, duplicatas) a conferência do painel resolve: lote APROVADO ou todas as folhas do lote conferidas
        # (aviso de 14/10, F009-P0060; 19/10: antes só valia com o lote aprovado e a tela dizia "reprovado" com tudo conferido).
        # CAMP-046: autoria divergente é só aviso (CV2 antigo ainda reprova por ela).
        av = avaliar_aceite(ac, conferencia_do_lote(con, la["id"])) if isinstance(ac, dict) and ac else None
        aceito = av is None or av["situacao"] != "reprovado"
        resolvido_aqui = bool(av and av["situacao"] == "resolvido")
        # 21/10 ("publicar sem travar", 4.1/4.5): o aceite do CAMP Vision é aviso; não trava o projeto (as folhas com dúvida ficam de fora)
        conds.append({"id": "aceite_cv", "bloqueia": False, "ok": aceito, "texto": "Aceite do lote no CAMP Vision",
                      "detalhe": ("O CAMP Vision pediu olho humano (" + "; ".join(motivos_aceite(ac)) + "): resolvido na conferência do painel") if resolvido_aqui
                      else None if aceito else "O CAMP Vision reprovou o lote" + (lambda m: f" ({'; '.join(m)})" if m else "")(
                          [m for m in motivos_aceite(ac) if m not in {i["rotulo"] for i in av["itens"] if i["estado"] != "falta"} and m not in {f["rotulo"] for f in av["faltam"]}]) + ". Falta: " + "; ".join(f"{f['rotulo']} ({f['como']})" for f in av["faltam"]),
                      "acao": None if aceito else {"tipo": "revisao", "rotulo": "Ver o lote", "alvo": codigo}})

    teste = bool(p["lote_teste"])
    # CAMP-114: o lote de teste do CAMP Vision é ignorado (não importa folhas); o projeto que a estação reservou para ele ficava "pronto"
    # com "Publicar" e criava uma página vazia no site. Sem nenhuma folha e com lote de teste anotado, é lote de teste.
    so_teste = not teste and bool(con.execute("SELECT 1 FROM evento WHERE entidade='projeto' AND codigo=? AND tipo='lote_teste_ignorado' LIMIT 1", (codigo,)).fetchone()) \
        and not con.execute("SELECT 1 FROM item WHERE projeto_codigo=? LIMIT 1", (codigo,)).fetchone()
    teste = teste or so_teste
    conds.append({"id": "teste", "bloqueia": True, "ok": not teste, "texto": "Não é lote de teste",
                  "detalhe": ("Só chegou lote de teste do CAMP Vision para este projeto: o painel não importa nem publica" if so_teste
                              else "Lote de teste não vai ao ar" if teste else None), "acao": None})

    # REVISÃO (a mesma regra do plano da publicação guiada): folha vinda do CAMP Vision precisa estar conferida e o lote aprovado
    nao_conf = con.execute("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND lote_id IS NOT NULL AND revisao='pendente' AND duplicata_de IS NULL", (codigo,)).fetchone()[0]
    prontas = con.execute(f"SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND {ELEGIVEL_LOCAL}", (codigo,)).fetchone()[0]
    lote_sem_aprovar = con.execute("""SELECT COUNT(*) FROM lista_processamento l WHERE l.projeto_codigo=? AND l.aprovado_em IS NULL AND l.etapa IN ('revisao','rascunho')
                                       AND EXISTS (SELECT 1 FROM item i WHERE i.lote_id=l.id)""", (codigo,)).fetchone()[0]
    if nao_conf and prontas == 0:
        rev_msg, rev_rot = (f"1 folha espera" if nao_conf == 1 else f"{nao_conf} folhas esperam") + " conferência na Revisão do lote", "Conferir as folhas"
    elif lote_sem_aprovar:
        rev_msg, rev_rot = "O lote ainda não foi aprovado na Revisão do lote", "Aprovar o lote"
    else:
        rev_msg, rev_rot = None, None
    conds.append({"id": "revisao", "bloqueia": True, "ok": rev_msg is None, "texto": "Folhas conferidas e lote aprovado" if rev_msg is None else ("Nenhuma folha conferida ainda" if nao_conf and prontas == 0 else "Lote não aprovado"),
                  "detalhe": rev_msg, "acao": None if rev_msg is None else {"tipo": "revisao", "rotulo": rev_rot, "alvo": codigo}})

    total = con.execute("SELECT COUNT(*) FROM item WHERE projeto_codigo=?", (codigo,)).fetchone()[0]
    elegiveis = con.execute(f"SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND {ELEGIVEL}", (codigo,)).fetchone()[0]
    vinculados = con.execute("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL", (codigo,)).fetchone()[0]
    dossie = bool(p["tainacan_item_id"])
    # #95: ✔ só com pelo menos uma folha no site (o dossiê sozinho dava um verde enganoso com "0 de N folhas");
    # projeto sem nenhuma folha que possa ir ao site (só o dossiê) continua ok com o dossiê
    ok_site = elegiveis > 0 or (dossie and prontas == 0)
    sem_folha = dossie and not ok_site
    conds.append({"id": "site", "bloqueia": True, "ok": ok_site,
                  "texto": (f"Existe no site: dossiê sim · nenhuma folha no site ({total} no painel)" if sem_folha else
                            f"Existe no site: dossiê {'sim' if dossie else 'não'} · {elegiveis} de {total} folha(s)"),
                  "detalhe": None if ok_site else ("Envie as folhas ao site (ficam como rascunho) antes de publicar" if sem_folha else
                                                   "O projeto ainda não tem nenhum registro no site. Envie as folhas ao site (ficam como rascunho) antes de publicar"),
                  "acao": None if ok_site else {"tipo": "subir_folhas", "rotulo": "Enviar folhas ao site" if dossie else "Criar no site e enviar folhas", "alvo": codigo}})

    # avisos: não bloqueiam
    retidas = con.execute("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND retida=1", (codigo,)).fetchone()[0]
    retidas_sem_site = con.execute("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND retida=1 AND tainacan_item_id IS NULL", (codigo,)).fetchone()[0]
    fora = total - vinculados - retidas_sem_site
    if retidas:
        conds.append({"id": "folhas_retidas", "bloqueia": False, "ok": False, "texto": f"{retidas} folha(s) retida(s) por você: ficam só no painel, não vão ao site", "detalhe": None, "acao": None})
    # 21/10: retida que está publicada no site (vinha do "Publicar" que não olhava a retenção): publicar de novo a esconde
    retidas_no_ar = con.execute("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND retida=1 AND tainacan_item_id IS NOT NULL AND status_site IN ('no_ar','rascunho')", (codigo,)).fetchone()[0]
    if retidas_no_ar:
        conds.append({"id": "retidas_no_site", "bloqueia": False, "ok": False,
                      "texto": f"{retidas_no_ar} folha(s) retida(s) estão no site: ao publicar, elas ficam escondidas (privadas)", "detalhe": None, "acao": None})
    if ok_site and fora > 0:
        conds.append({"id": "folhas_fora", "bloqueia": False, "ok": False, "texto": f"{fora} folha(s) ainda não estão no site e não serão publicadas",
                      "detalhe": None, "acao": {"tipo": "subir_folhas", "rotulo": "Enviar folhas ao site", "alvo": codigo}})
    excluidas = vinculados - elegiveis - con.execute("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND retida=1 AND tainacan_item_id IS NOT NULL", (codigo,)).fetchone()[0]
    if excluidas > 0:
        conds.append({"id": "folhas_excluidas", "bloqueia": False, "ok": False,
                      "texto": f"{excluidas} folha(s) duplicadas ou não conferidas ficam de fora da publicação", "detalhe": None, "acao": None})
    conds += avisos_qualidade(p)
    from .fundo_site import pagina_arquiteto   # CAMP-015: aviso (não bloqueia) quando o fundo não tem página pública do arquiteto no site
    pg = pagina_arquiteto(con, fundo)
    if not pg["publica"]:
        conds.append({"id": "pagina_arquiteto", "bloqueia": False, "ok": False, "sem_arquiteto": bool(pg.get("sem_arquiteto")),
                      "texto": f"A página do arquiteto (fundo {fundo}) não está pública no site: sem ela, os projetos do fundo não aparecem",
                      "detalhe": ("Não há arquiteto titular cadastrado neste fundo." if pg.get("sem_arquiteto") else
                                  "Ela é publicada junto com o projeto, ou pelo quadro “Página do arquiteto no site”, no fundo."),
                      "acao": None if pg.get("sem_arquiteto") else {"tipo": "publicar_arquiteto", "rotulo": "Publicar a página do arquiteto", "alvo": fundo}})
    from .imagem_site import lado_maximo_do_fundo   # B2: o limite de resolução do fundo aparece no checklist quando é mais apertado que o padrão
    lado = lado_maximo_do_fundo(con, fundo)
    if lado and lado < 3000:
        conds.append({"id": "resolucao", "bloqueia": False, "ok": True, "texto": f"Imagens no site com no máximo {lado} px no lado maior (regra do fundo {fundo})",
                      "detalhe": None, "acao": None})
    return {"condicoes": conds, "pode_publicar": all(c["ok"] for c in conds if c["bloqueia"]),
            "folhas_total": total, "folhas_elegiveis": elegiveis, "dossie_no_site": dossie}


# B10 · avisos de qualidade da ficha: não bloqueiam a publicação, mas mostram o que falta e levam ao campo
TITULO_GENERICO = re.compile(r"^\s*(F\d{3}-)?P\d{3,4}\s*$|\[TESTE\]|DADO FICT[IÍ]CIO|completar com|sem t[ií]tulo|^\s*projeto\s*\d*\s*$", re.I)


def avisos_qualidade(p) -> list[dict]:
    chaves = p.keys() if hasattr(p, "keys") else []
    v = lambda k: (p[k] if k in chaves else None)  # noqa: E731
    codigo, out = v("codigo"), []
    for campo, texto in (("ano", "Ano vazio"), ("cidade", "Cidade vazia"), ("tipologia", "Programa / uso vazio"), ("natureza", "Natureza do trabalho vazia")):
        if v(campo) in (None, "", 0):
            out.append({"id": f"q_{campo}", "bloqueia": False, "ok": False, "texto": texto,
                        "detalhe": "Não impede a publicação, mas a ficha no site fica incompleta e é mais difícil de achar.",
                        "acao": {"tipo": "editar_projeto", "rotulo": "Preencher", "alvo": f"{codigo}:{campo}"}})
    t = str(v("titulo") or "")
    if not t.strip() or TITULO_GENERICO.search(t) or t.strip().upper() == str(codigo or "").upper():
        out.append({"id": "q_titulo", "bloqueia": False, "ok": False, "texto": f"Título genérico: “{t.strip() or 'vazio'}”",
                    "detalhe": "Um título que diga o que é o projeto (ex.: Residência Tarumã) ajuda quem busca no site e no Google.",
                    "acao": {"tipo": "editar_projeto", "rotulo": "Corrigir o título", "alvo": f"{codigo}:titulo"}})
    return out


def motivos_bloqueio(c: dict) -> list[str]:
    return [x["detalhe"] or x["texto"] for x in c["condicoes"] if x["bloqueia"] and not x["ok"]]


def persistir_resultado(sucessos, status_painel, status_wp, entidade, codigo, tipo_evento, ator, detalhe) -> str | None:
    """Grava o resultado LOCAL numa conexão nova e curta, DEPOIS das chamadas de rede (nunca segura transação durante a rede:
    isso travava login e sincronização). Devolve a mensagem de erro do banco, ou None."""
    ultimo = None
    for tentativa in range(4):
        con = connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            for tipo, cod, wid in sucessos:
                con.execute(f"UPDATE {tipo} SET status_site=?, atualizado_em=datetime('now'), "
                            "publicado_em=CASE WHEN ?='no_ar' THEN COALESCE(publicado_em, datetime('now')) ELSE publicado_em END WHERE codigo=?",
                            (status_painel, status_painel, cod))   # publicado_em: 1ª publicação (relatórios)
                con.execute("UPDATE wp_item SET status=? WHERE id=?", (status_wp, wid))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)",
                        (entidade, codigo, tipo_evento, ator, json.dumps(detalhe, ensure_ascii=False)))
            con.commit()
            return None
        except sqlite3.OperationalError as e:
            con.rollback()
            ultimo = str(e)
            if "locked" not in ultimo.lower() or tentativa == 3:
                return ultimo
            time.sleep(0.5 * (tentativa + 1))
        finally:
            con.close()
    return ultimo
