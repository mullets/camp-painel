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
ELEGIVEL_LOCAL = "duplicata_de IS NULL AND retida=0 AND (lote_id IS NULL OR revisao<>'pendente')"   # retida = a pessoa decidiu que esta folha não vai ao site


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

    b = con.execute("SELECT itens_autoria_divergente, erros_bloqueantes FROM v_bloqueios_publicacao WHERE codigo=?", (codigo,)).fetchone()
    div, err = ((b[0] or 0), (b[1] or 0)) if b else (0, 0)
    err -= con.execute("""SELECT COUNT(*) FROM erro WHERE (codigo=? OR codigo LIKE ? || '-%') AND situacao IN ('aberto','em_correcao')
                          AND gravidade='bloqueia' AND categoria='autoria_divergente'""", (codigo, codigo)).fetchone()[0] if err else 0   # CAMP-046: base antiga com a view velha: autoria não conta
    livre = not err
    conds.append({"id": "bloqueios", "bloqueia": True, "ok": livre, "texto": "Sem erros bloqueantes",
                  "detalhe": None if livre else f"{err} erro(s) bloqueante(s)",
                  "acao": None if livre else {"tipo": "erros", "rotulo": "Ver erros", "alvo": codigo}})
    if div:   # CAMP-046: autoria não confirmada é AVISO (não trava): a folha sobe com "Autoria não confirmada" no crédito
        conds.append({"id": "autoria_nao_confirmada", "bloqueia": False, "ok": False,
                      "texto": f"{div} folha(s) com autoria não confirmada" if div != 1 else "1 folha com autoria não confirmada",
                      "detalhe": "Sobem ao site com o crédito “Autoria não confirmada”; o nome lido no carimbo não é tratado como fato.",
                      "acao": {"tipo": "autoria", "rotulo": "É de outro autor? Registrar coautoria/terceiros", "alvo": codigo}})

    # CV2 §10 (contrato 9.4): o lote mais recente do projeto com aceite reprovado trava a publicação
    la = con.execute("""SELECT id, aceite_json FROM lista_processamento WHERE projeto_codigo=? AND aceite_json IS NOT NULL
                        ORDER BY id DESC LIMIT 1""", (codigo,)).fetchone()
    if la:
        from .saidas_cv import motivos_aceite
        try:
            ac = json.loads(la["aceite_json"])
        except ValueError:
            ac = {}
        aceito = ac.get("publicavel") is not False
        resolvido_aqui = False
        if not aceito:
            # O aceite é uma foto do momento da leitura. Os pontos que pedem OLHO HUMANO (orientação/série incertas, duplicatas,
            # autoria) a conferência do painel resolve: com o lote APROVADO no painel, eles deixam de travar (aviso de 14/10, F009-P0060).
            from .saidas_cv import itens_aceite
            RESOLVE_CONFERENCIA = {"orientacao_incerta_zerada", "serie_incerta_zerada", "duplicatas_marcadas", "sem_autoria_divergente"}
            falhas = {i["chave"] for i in itens_aceite(ac) if i["ok"] is False}
            aprovado = con.execute("SELECT aprovado_em FROM lista_processamento WHERE id=?", (la["id"],)).fetchone()[0]
            if falhas == {"sem_autoria_divergente"}:      # CAMP-046: CV2 antigo ainda reprova por autoria; no contrato 2.4 isso é só aviso
                aceito = True
            elif aprovado and falhas <= RESOLVE_CONFERENCIA:
                aceito = resolvido_aqui = True
        conds.append({"id": "aceite_cv", "bloqueia": True, "ok": aceito, "texto": "Aceite do lote no CAMP Vision",
                      "detalhe": ("O CAMP Vision pediu olho humano (" + "; ".join(motivos_aceite(ac)) + "): resolvido na conferência do painel") if resolvido_aqui
                      else None if aceito else "O CAMP Vision reprovou o lote: " + "; ".join(motivos_aceite(ac) or ["sem motivo informado"]),
                      "acao": None if aceito else {"tipo": "revisao", "rotulo": "Ver o lote", "alvo": codigo}})

    teste = bool(p["lote_teste"])
    conds.append({"id": "teste", "bloqueia": True, "ok": not teste, "texto": "Não é lote de teste",
                  "detalhe": "Lote de teste não vai ao ar" if teste else None, "acao": None})

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
        conds.append({"id": "pagina_arquiteto", "bloqueia": False, "ok": False,
                      "texto": f"O fundo {fundo} ainda não tem página pública do arquiteto no site",
                      "detalhe": ("Não há arquiteto titular cadastrado neste fundo." if pg.get("sem_arquiteto") else
                                  f"A página existe no site, mas está como {pg['status']} (não publicado)." if pg["existe"] else
                                  "Não achei a página no espelho do site. Use “Enviar fundo ao site” no fundo e ative o arquiteto no WordPress."), "acao": None})
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
