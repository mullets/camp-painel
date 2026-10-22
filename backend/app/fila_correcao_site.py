"""REF-006: retentativa persistente de alterações de folha no WordPress.

A trigger registra edições no mesmo commit SQLite. O envio existente continua
sendo usado; o worker nunca cria, publica ou exclui uma folha por conta própria.
"""
from __future__ import annotations

import time
from .db import connect

ATOR = "painel (reenvio automático ao site)"


def _reclamar(con):
    """Reserva uma correção disponível; lease expira para sobreviver ao restart."""
    con.execute("BEGIN IMMEDIATE")
    row = con.execute("""SELECT item_codigo, versao, tentativas FROM fila_correcao_site
        WHERE (estado='pendente' AND proxima_em <= datetime('now'))
           OR (estado='executando' AND reservado_ate <= datetime('now'))
        ORDER BY proxima_em, atualizado_em, item_codigo LIMIT 1""").fetchone()
    if not row:
        con.rollback()
        return None
    con.execute("""UPDATE fila_correcao_site SET estado='executando',
            reservado_ate=datetime('now','+15 minutes') WHERE item_codigo=? AND versao=?""",
            (row["item_codigo"], row["versao"]))
    con.commit()
    return dict(row)


def executar_pendentes(limite: int = 12, orcamento_s: float = 25.0) -> dict:
    """Executa correções já autorizadas, sem bloquear requisições do painel."""
    from .alteracoes_site import enviar, enviar_sozinho
    if not enviar_sozinho():
        return {"desligado": True}
    resumo = {"enviadas": [], "falhas": []}
    inicio = time.monotonic()
    for _ in range(max(0, min(50, limite))):
        if time.monotonic() - inicio >= orcamento_s:
            break
        con = connect()
        try:
            item = _reclamar(con)
        finally:
            con.close()
        if not item:
            break
        codigo, versao = item["item_codigo"], item["versao"]
        try:
            r = enviar(codigo[:10], ATOR, [codigo])
            if not r.get("ok", False) or r.get("falhas"):
                falhas = r.get("falhas") or []
                raise RuntimeError(str(falhas[0].get("erro", "Falha ao enviar")) if falhas else "Envio não confirmado")
            sucesso, erro = True, None
        except Exception as e:
            sucesso, erro = False, f"{type(e).__name__}: {str(e)[:180]}"
        con = connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            if sucesso:
                # Edição concorrente muda a versão e permanece na fila.
                con.execute("DELETE FROM fila_correcao_site WHERE item_codigo=? AND versao=?", (codigo, versao))
                resumo["enviadas"].append(codigo)
            else:
                segundos = min(3600, 60 * 2 ** min(int(item["tentativas"]), 6))
                con.execute("""UPDATE fila_correcao_site SET estado='pendente', tentativas=tentativas+1,
                    reservado_ate=NULL, ultimo_erro=?, proxima_em=datetime('now', ?), atualizado_em=datetime('now')
                    WHERE item_codigo=? AND versao=?""", (erro, f"+{segundos} seconds", codigo, versao))
                resumo["falhas"].append({"codigo": codigo, "erro": erro})
            con.commit()
        finally:
            con.close()
    return resumo
