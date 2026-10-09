"""Publicar com um clique: o painel conhece a receita e faz sozinho o que dá, parando só no que é decisão de gente.

A receita (antes, cada passo era um botão solto): dossiê do projeto no site -> folhas no site (rascunho) -> autorizar -> publicar.
- plano(): mostra o que vai ser feito, o que fica de fora e o que SÓ uma pessoa resolve (direitos do fundo, autoria divergente/erros bloqueantes,
  lote de teste, nenhuma folha conferida). Não muda nada.
- executar(): faz a sequência. Idempotente (repetir continua de onde parou) e dividido em fatias de tempo: um projeto com muitas folhas devolve
  `parcial` e a tela chama de novo, com progresso. Todos os portões de `publicar` continuam valendo (ele revalida no fim).
"""
from __future__ import annotations

import json
import threading
import time

from fastapi import HTTPException

from .db import connect
from .publicacao import ELEGIVEL_LOCAL, condicoes_projeto

ORCAMENTO_S = 40.0             # tempo máximo de envio de folhas por chamada (a tela repete até acabar)
_trava = threading.Lock()
_em_andamento: set[str] = set()


def plano(con, p) -> dict:
    """O que o botão Publicar vai fazer. Só lê."""
    codigo = p["codigo"]
    cond = condicoes_projeto(con, p)
    por_id = {c["id"]: c for c in cond["condicoes"]}
    q = lambda sql: con.execute(sql, (codigo,)).fetchone()[0]
    elegiveis = q(f"SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND {ELEGIVEL_LOCAL}")
    a_enviar = q(f"SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NULL AND {ELEGIVEL_LOCAL}")
    nao_conferidas = q("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND lote_id IS NOT NULL AND revisao='pendente' AND autoria_divergente=0 AND duplicata_de IS NULL")
    duplicadas = q("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND duplicata_de IS NOT NULL")
    divergentes = q("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND autoria_divergente=1")

    bloqueios = [{"id": i, "texto": por_id[i]["texto"], "detalhe": por_id[i]["detalhe"], "acao": por_id[i]["acao"]}
                 for i in ("direitos", "bloqueios", "teste") if not por_id[i]["ok"]]
    if nao_conferidas and elegiveis == 0:
        bloqueios.append({"id": "revisao", "texto": "Nenhuma folha conferida ainda", "detalhe": f"{nao_conferidas} folha(s) esperam conferência na Revisão do lote",
                          "acao": {"tipo": "revisao", "rotulo": "Conferir as folhas", "alvo": codigo}})
    dossie = bool(p["tainacan_item_id"])
    passos = [
        {"id": "dossie", "texto": "Criar o dossiê do projeto no site (rascunho)" if not dossie else "Dossiê do projeto no site", "estado": "feito" if dossie else "sera_feito"},
        {"id": "folhas", "texto": f"Enviar {a_enviar} folha(s) ao site (rascunho)" if a_enviar else "Folhas no site", "estado": "sera_feito" if a_enviar else "feito"},
        {"id": "autorizar", "texto": "Autorizar o projeto para publicação" if not p["autorizado_site"] else "Projeto autorizado para publicação", "estado": "feito" if p["autorizado_site"] else "sera_feito"},
        {"id": "publicar", "texto": f"Publicar o dossiê e {elegiveis} folha(s)", "estado": "sera_feito"},
    ]
    return {"passos": passos, "bloqueios": bloqueios, "pode_executar": not bloqueios, "ja_publicado": p["status_site"] == "no_ar",
            "folhas_a_enviar": a_enviar, "folhas_a_publicar": elegiveis,
            "fora": {"duplicadas": duplicadas, "autoria_divergente": divergentes, "nao_conferidas": nao_conferidas}}


def executar(codigo: str, u: dict) -> dict:
    """Faz a sequência. Devolve {ok, parcial, etapa, mensagem, ...}. Levanta 400 (com o plano) se algo que só uma pessoa resolve impede."""
    from . import publicador
    from .rotas_projetos import Publicacao, publicar

    with _trava:
        if codigo in _em_andamento:
            raise HTTPException(409, "Este projeto já está sendo publicado agora. Aguarde terminar.")
        _em_andamento.add(codigo)
    try:
        con = connect()
        try:
            p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
            if not p:
                raise HTTPException(404, "Projeto não existe")
            pl = plano(con, p)
            pend = [r[0] for r in con.execute(f"SELECT codigo FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NULL AND {ELEGIVEL_LOCAL} ORDER BY sequencial", (codigo,))]
        finally:
            con.close()
        if pl["bloqueios"]:
            raise HTTPException(400, "Não dá para publicar ainda: " + " | ".join(b["detalhe"] or b["texto"] for b in pl["bloqueios"]))
        feitos: list[str] = []

        if not p["tainacan_item_id"]:                                                       # 1) dossiê
            r = publicador.criar_dossie_no_site(codigo, u["email"])
            if r.get("erro") or not r.get("item_id"):
                return {"ok": False, "parcial": False, "etapa": "dossie", "feitos": feitos, "mensagem": f"Não consegui criar o dossiê no site: {r.get('erro') or 'sem resposta'}. Nada foi publicado."}
            feitos.append("dossie")

        t0, criadas, falhas = time.monotonic(), 0, []                                      # 2) folhas, em fatias de tempo (sempre avança ao menos uma)
        for c in pend:
            if criadas + len(falhas) > 0 and time.monotonic() - t0 >= ORCAMENTO_S:
                break
            r = publicador.criar_folha_no_site(c, u["email"])
            if r.get("erro"):
                falhas.append({"codigo": c, "erro": r["erro"]})
            else:
                criadas += 1
        restam = len(pend) - criadas - len(falhas)
        if falhas:
            return {"ok": False, "parcial": False, "etapa": "folhas", "feitos": feitos, "folhas_criadas": criadas, "falhas": falhas,
                    "mensagem": f"{len(falhas)} folha(s) não subiram ao site; nada foi publicado. Corrija e clique de novo: o que já subiu não se repete."}
        if restam > 0:
            return {"ok": False, "parcial": True, "etapa": "folhas", "feitos": feitos, "folhas_criadas": criadas, "restam": restam,
                    "mensagem": f"Enviadas {criadas} folha(s); faltam {restam}."}

        con = connect()                                                                     # 3) autorizar (os requisitos já foram checados no plano)
        try:
            if not con.execute("SELECT autorizado_site FROM projeto WHERE codigo=?", (codigo,)).fetchone()[0]:
                con.execute("UPDATE projeto SET autorizado_site=1, atualizado_em=datetime('now') WHERE codigo=?", (codigo,))
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'autorizado_ao_publicar',?,NULL)", (codigo, u["email"]))
                con.commit()
                feitos.append("autorizar")
        finally:
            con.close()

        res = publicar(codigo, Publicacao(acao="publicar"), u)                              # 4) publicar (revalida TODOS os portões)
        con = connect()
        try:
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'publicacao_guiada',?,?)",
                        (codigo, u["email"], json.dumps({"feitos": feitos, "folhas_criadas": criadas, "publicados": res.get("alterados"), "ok": res.get("ok")}, ensure_ascii=False)))
            if res.get("ok"):          # a Fila deixa de pedir ação: as listas JÁ APROVADAS deste projeto passam a "publicadas"
                for (lid,) in con.execute("SELECT id FROM lista_processamento WHERE projeto_codigo=? AND aprovado_em IS NOT NULL AND etapa IN ('revisao','rascunho')", (codigo,)).fetchall():
                    con.execute("UPDATE lista_processamento SET etapa='publicado', atualizado_em=datetime('now') WHERE id=?", (lid,))
                    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('lista',?,'etapa_publicado',?,?)", (str(lid), u["email"], json.dumps({"pela": "publicacao_guiada"})))
            con.commit()
        finally:
            con.close()
        return {**res, "parcial": False, "etapa": "publicar", "feitos": feitos, "folhas_criadas": criadas, "publicados": res.get("alterados", 0)}
    finally:
        with _trava:
            _em_andamento.discard(codigo)
