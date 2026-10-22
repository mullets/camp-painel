"""CAMP-151 (22/10/2026, decidido pelo Rafa): importar sozinho quando o CAMP Vision termina o lote.

- Configuração importacao.automatica (migração 149, padrão 0 = desligado: alguém clica "Importar folhas").
- Quem roda é o laço do coletor do QNAP (main._coleta_qnap_periodica), em segundo plano: NUNCA dentro de uma requisição (CLAUDE.md).
- Importa o lote que espera importação (etapa revisao, sem folhas, não aprovado, não descartado) pelo MESMO importador do botão
  (importador_lote.importar_lote), com as mesmas condições (rotas_revisao._pode_importar).
- Não importa: o CAMP Vision ainda lendo (sem pacote), lote com decisão pendente (números que colidem).
- Não deu (QNAP fora, pacote de outro projeto, pacote quebrado...): vira um problema do projeto com o motivo, um só por lote (chave),
  que fecha sozinho quando a importação der certo.
"""
from __future__ import annotations

import json
import time

from fastapi import HTTPException

from .db import connect

ATOR = "painel (importação automática)"


def ligado(con) -> bool:
    r = con.execute("SELECT valor FROM configuracao WHERE chave='importacao.automatica'").fetchone()
    return bool(r) and str(r[0]).strip() == "1"


def _chave(lote_id: int) -> str:
    return f"importar_sozinho:{lote_id}"


def _problema(con, l, motivo: str) -> None:
    """Um problema por lote (chave única): reabre/atualiza o motivo se mudou; nunca duplica."""
    ch = _chave(l["id"])
    desc = f"A importação automática das folhas não deu: {motivo}"
    r = con.execute("SELECT id, situacao, descricao FROM erro WHERE chave=?", (ch,)).fetchone()
    if r is None:
        con.execute("""INSERT INTO erro (gravidade, categoria, origem, codigo, descricao, relatado_por, chave)
                       VALUES ('corrigir','outro','revisao',?,?,?,?)""", (l["projeto_codigo"], desc, ATOR, ch))
    elif r["situacao"] not in ("aberto", "em_correcao") or r["descricao"] != desc:
        con.execute("UPDATE erro SET situacao='aberto', descricao=?, resolucao=NULL WHERE id=?", (desc, r["id"]))


def _fechar_problema(con, lote_id: int) -> None:
    con.execute("""UPDATE erro SET situacao='corrigido', resolucao='A importação automática deu certo depois.'
                    WHERE chave=? AND situacao IN ('aberto','em_correcao')""", (_chave(lote_id),))


# o que só quer dizer "ainda não": o CAMP Vision não terminou de gravar (não vira problema)
_AINDA_NAO = ("ainda está lendo", "não gravou o pacote")


def importar_prontos(orcamento_s: float = 20.0) -> dict:
    """Uma passada. Nunca levanta. {desligado} | {importados:[...], esperando:[...], problemas:[...]}."""
    from .importador_lote import importar_lote
    from .rotas_revisao import _pode_importar
    out = {"importados": [], "esperando": [], "problemas": []}
    con = connect()
    try:
        if not ligado(con):
            return {"desligado": True}
        lotes = con.execute("""SELECT * FROM lista_processamento l
                                WHERE l.descartado_em IS NULL AND l.aprovado_em IS NULL AND l.etapa='revisao'
                                  AND NOT EXISTS (SELECT 1 FROM item i WHERE i.lote_id=l.id) ORDER BY l.id""").fetchall()
    finally:
        con.close()
    t0 = time.monotonic()
    for l in lotes:
        if time.monotonic() - t0 > orcamento_s:
            break
        con = connect()
        try:
            if con.execute("SELECT 1 FROM decisao WHERE situacao='pendente' AND tipo='lote_colide' AND chave LIKE ? LIMIT 1", (f"lote_colide:{l['id']}:%",)).fetchone():
                out["esperando"].append({"lote_id": l["id"], "projeto": l["projeto_codigo"], "motivo": "decisão pendente"}); continue
            pode, motivo = _pode_importar(con, l)
            if not pode:
                if any(x in (motivo or "") for x in _AINDA_NAO) and "Peça a releitura" not in (motivo or ""):
                    out["esperando"].append({"lote_id": l["id"], "projeto": l["projeto_codigo"], "motivo": motivo}); continue
                _problema(con, l, motivo or "motivo desconhecido"); con.commit()
                out["problemas"].append({"lote_id": l["id"], "projeto": l["projeto_codigo"], "motivo": motivo}); continue
            con.execute("BEGIN IMMEDIATE")
            try:
                r = importar_lote(con, l["id"], ATOR)
            except HTTPException as e:
                con.rollback()
                _problema(con, l, str(e.detail)); con.commit()
                out["problemas"].append({"lote_id": l["id"], "projeto": l["projeto_codigo"], "motivo": str(e.detail)}); continue
            _fechar_problema(con, l["id"])
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'importado_sozinho',?,?)",
                        (l["projeto_codigo"], ATOR, json.dumps({"lote_id": l["id"], "criadas": r.get("criadas")}, ensure_ascii=False)))
            con.commit()
            out["importados"].append({"lote_id": l["id"], "projeto": l["projeto_codigo"], "criadas": r.get("criadas")})
        except Exception as e:  # noqa: BLE001 - nunca derruba o laço do coletor
            try:
                con.rollback()
                _problema(con, l, f"erro inesperado ({str(e)[:160]})"); con.commit()
            except Exception:  # noqa: BLE001
                pass
            out["problemas"].append({"lote_id": l["id"], "projeto": l["projeto_codigo"], "motivo": str(e)[:160]})
        finally:
            con.close()
    return out
