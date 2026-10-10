"""Regras de publicação num só lugar.

Usadas pelo botão "Publicar" do projeto, pela publicação em lote e pela do fundo inteiro, para que NUNCA divirjam
(antes o fundo inteiro ignorava erros bloqueantes e lote de teste e publicava folhas duplicadas).
Vocabulário: docs/vocabulario.md.
"""
from __future__ import annotations

import json
import sqlite3
import time

from .db import connect

# Uma folha só vai ao site se: não tem autoria divergente, não é duplicata e, quando veio da revisão do CAMP Vision (tem lote), já foi conferida/corrigida.
ELEGIVEL_LOCAL = "autoria_divergente=0 AND duplicata_de IS NULL AND (lote_id IS NULL OR revisao<>'pendente')"
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
    livre = not (div or err)
    conds.append({"id": "bloqueios", "bloqueia": True, "ok": livre, "texto": "Sem autoria divergente nem erros bloqueantes",
                  "detalhe": None if livre else f"{div} folha(s) com autoria divergente e {err} erro(s) bloqueante(s)",
                  "acao": None if livre else {"tipo": "erros", "rotulo": "Ver erros", "alvo": codigo}})

    teste = bool(p["lote_teste"])
    conds.append({"id": "teste", "bloqueia": True, "ok": not teste, "texto": "Não é lote de teste",
                  "detalhe": "Lote de teste não vai ao ar" if teste else None, "acao": None})

    # REVISÃO (a mesma regra do plano da publicação guiada): folha vinda do CAMP Vision precisa estar conferida e o lote aprovado
    nao_conf = con.execute("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND lote_id IS NOT NULL AND revisao='pendente' AND autoria_divergente=0 AND duplicata_de IS NULL", (codigo,)).fetchone()[0]
    prontas = con.execute(f"SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND {ELEGIVEL_LOCAL}", (codigo,)).fetchone()[0]
    lote_sem_aprovar = con.execute("""SELECT COUNT(*) FROM lista_processamento l WHERE l.projeto_codigo=? AND l.aprovado_em IS NULL AND l.etapa IN ('revisao','rascunho')
                                       AND EXISTS (SELECT 1 FROM item i WHERE i.lote_id=l.id)""", (codigo,)).fetchone()[0]
    if nao_conf and prontas == 0:
        rev_msg, rev_rot = f"{nao_conf} folha(s) esperam conferência na Revisão do lote", "Conferir as folhas"
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
    ok_site = dossie or elegiveis > 0
    conds.append({"id": "site", "bloqueia": True, "ok": ok_site,
                  "texto": f"Existe no site: dossiê {'sim' if dossie else 'não'} · {elegiveis} de {total} folha(s)",
                  "detalhe": None if ok_site else "O projeto ainda não tem nenhum registro no site. Envie as folhas ao site (ficam como rascunho) antes de publicar",
                  "acao": None if ok_site else {"tipo": "subir_folhas", "rotulo": "Enviar folhas ao site" if dossie else "Criar no site e enviar folhas", "alvo": codigo}})

    # avisos: não bloqueiam
    fora = total - vinculados
    if ok_site and fora > 0:
        conds.append({"id": "folhas_fora", "bloqueia": False, "ok": False, "texto": f"{fora} folha(s) ainda não estão no site e não serão publicadas",
                      "detalhe": None, "acao": {"tipo": "subir_folhas", "rotulo": "Enviar folhas ao site", "alvo": codigo}})
    excluidas = vinculados - elegiveis
    if excluidas > 0:
        conds.append({"id": "folhas_excluidas", "bloqueia": False, "ok": False,
                      "texto": f"{excluidas} folha(s) com autoria divergente ou duplicadas ficam de fora da publicação", "detalhe": None, "acao": None})
    return {"condicoes": conds, "pode_publicar": all(c["ok"] for c in conds if c["bloqueia"]),
            "folhas_total": total, "folhas_elegiveis": elegiveis, "dossie_no_site": dossie}


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
                con.execute(f"UPDATE {tipo} SET status_site=?, atualizado_em=datetime('now') WHERE codigo=?", (status_painel, cod))
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
