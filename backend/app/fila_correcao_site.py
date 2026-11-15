"""REF-006: retentativa persistente de alterações de folha no site.

A trigger registra edições no mesmo commit SQLite. O envio existente continua
sendo usado; o worker nunca cria, publica ou exclui uma folha por conta própria.
"""
from __future__ import annotations

import threading
import time
from .db import connect

ATOR = "painel (reenvio automático ao site)"
LOTE_MAX = 50                       # teto de envios por rodada (o mesmo para o trabalhador e para o botão)
# UX-40: uma rodada por vez (botão "Enviar as N agora" e trabalhador automático nunca andam juntos)
_RODADA = threading.Lock()
# CAMP-FIX 15/11 (Rafael: 40 folhas "falharam" com "Nada a enviar"): nada diferente do site NÃO é falha. A correção fecha como
# "já estava igual no site" e sai da fila e das contagens. Marca deixada pela rodada antiga, até a próxima rodada fechar a linha:
_MARCA_IGUAL = "Nada a enviar"
_NAO_IGUAL = f"COALESCE(ultimo_erro,'') NOT LIKE '%{_MARCA_IGUAL}:%'"


def reenvio_ativo() -> bool:
    """Nova rotina desligada até ser homologada; o envio imediato legado continua."""
    con = connect()
    try:
        row = con.execute("SELECT valor FROM configuracao WHERE chave='site.reenvio_persistente'").fetchone()
        return bool(row) and str(row[0]).strip() == "1"
    finally:
        con.close()


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


def contar(con) -> dict:
    """UX-40: quantas correções esperam na fila e quantas já podem sair agora (as outras esperam a próxima tentativa).
    UX-47: total/prontas/proxima_em somam as correções de folhas e as escritas pendentes de fundo, projeto e arquiteto que a rodada
    reenvia; `folhas` e `outras` (com `por_entidade`) separam as duas para a tela."""
    try:
        # CAMP-FIX 15/11: a correção que a rodada antiga deu como "Nada a enviar" (sem edição desde então: a trigger zera ultimo_erro)
        # já está igual no site; não conta como esperando (a próxima rodada fecha, ver fechar_sem_diferenca)
        r = con.execute(f"""SELECT COUNT(*) AS total,
                SUM(CASE WHEN (estado='pendente' AND proxima_em <= datetime('now'))
                           OR (estado='executando' AND reservado_ate <= datetime('now')) THEN 1 ELSE 0 END) AS prontas,
                MIN(CASE WHEN estado='pendente' AND proxima_em > datetime('now') THEN proxima_em END) AS proxima_em
              FROM fila_correcao_site WHERE {_NAO_IGUAL}""").fetchone()
        folhas = {"total": r[0] or 0, "prontas": r[1] or 0, "proxima_em": r[2]}
    except Exception:  # noqa: BLE001 — banco antigo, sem a fila
        folhas = {"total": 0, "prontas": 0, "proxima_em": None}
    from .reenvio_pendencias import contar as contar_pendencias
    outras = contar_pendencias(con)
    proximas = [x for x in (folhas["proxima_em"], outras["proxima_em"]) if x]
    return {"total": folhas["total"] + outras["total"], "prontas": folhas["prontas"] + outras["prontas"],
            "proxima_em": min(proximas) if proximas else None, "folhas": folhas["total"], "outras": outras["total"],
            "por_entidade": outras["por_entidade"]}


def executar_pendentes(limite: int = 12, orcamento_s: float = 25.0, forcar_manual: bool = False,
                       ator: str | None = None, ao_terminar_item=None) -> dict:
    """Executa correções já autorizadas, sem bloquear requisições do painel.

    forcar_manual=True (UX-40, só o botão "Enviar as N agora" de um admin): faz esta UMA rodada mesmo com
    `site.reenvio_persistente` desligado. Não liga a configuração: o trabalhador automático continua parado.
    """
    from .alteracoes_site import enviar, enviar_sozinho
    if not enviar_sozinho() or not (forcar_manual or reenvio_ativo()):
        return {"desligado": True}
    if not _RODADA.acquire(blocking=False):
        return {"ocupado": True}
    try:
        # UX-47: na mesma rodada (e sob a mesma trava), primeiro as escritas pendentes de fundo, projeto e arquiteto, depois as folhas;
        # o teto da rodada vale para as duas juntas.
        from . import reenvio_pendencias
        inicio, teto = time.monotonic(), max(0, min(LOTE_MAX, limite))
        iguais0 = fechar_sem_diferenca(ator or ATOR)    # antes de tudo: o que já está igual no site não ocupa lugar na rodada
        r1 = reenvio_pendencias.rodada(teto, orcamento_s, ator or ATOR, ao_terminar_item)
        r2 = _rodada(enviar, teto - r1["tentadas"], orcamento_s - (time.monotonic() - inicio), ator or ATOR, ao_terminar_item)
        try:                    # 15/11: registro antigo de folha movida que o site não deixou privado na hora (app.mover_site)
            from . import mover_site
            mover_site.esconder_pendentes(ator or ATOR, limite=max(1, teto))
        except Exception:  # noqa: BLE001
            pass
        return {"enviadas": r1["enviadas"] + r2["enviadas"], "falhas": r1["falhas"] + r2["falhas"], "na_fila": r1["na_fila"],
                "iguais": iguais0 + r2["iguais"], "teto": teto}
    finally:
        _RODADA.release()


def _rodada(enviar, limite, orcamento_s, ator, ao_terminar_item) -> dict:
    resumo = {"enviadas": [], "falhas": [], "iguais": []}
    inicio = time.monotonic()
    for _ in range(max(0, min(LOTE_MAX, limite))):
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
        igual = False
        try:
            r = enviar(codigo[:10], ator, [codigo])
            if r.get("ok", False) and not r.get("falhas") and r.get("total") == 0:
                # CAMP-FIX 15/11: nada diferente do site nesta folha (ex.: a sincronização gravou o valor do próprio site, ou a correção
                # voltou ao valor de antes). Nada vai ao site; a correção fecha como "já estava igual no site" (não é falha nem envio).
                igual = True
            elif not r.get("ok", False) or r.get("falhas") or codigo not in (r.get("enviadas") or []):
                falhas = r.get("falhas") or []
                detalhe = str(falhas[0].get("erro", "Falha ao enviar")) if falhas else "WordPress não confirmou a folha"
                raise RuntimeError(detalhe)
            sucesso, erro = True, None
        except Exception as e:
            sucesso, erro = False, f"{type(e).__name__}: {str(e)[:180]}"
        con = connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            if sucesso:
                # Edição concorrente muda a versão e permanece na fila.
                # enviar() pode ter quitado a mesma versão antes deste worker.
                # Jamais apagar uma edição posterior: a versão precisa bater.
                con.execute("DELETE FROM fila_correcao_site WHERE item_codigo=? AND versao=?", (codigo, versao))
                if igual:
                    _registrar_igual(con, codigo, ator)
                    resumo["iguais"].append(codigo)
                else:
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
        if ao_terminar_item:
            try:
                if igual:
                    ao_terminar_item(codigo, True, None, igual=True)
                else:
                    ao_terminar_item(codigo, sucesso, erro)
            except Exception:  # noqa: BLE001 — o andamento na tela nunca derruba a rodada
                pass
    return resumo


def _registrar_igual(con, codigo: str, ator: str) -> None:
    """Histórico da folha: a correção fechou sem ir ao site porque o site já tinha os mesmos valores (não é 'site_alteracoes_enviadas')."""
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'site_correcao_ja_igual',?,?)",
                (codigo, ator, '{"motivo": "já estava igual no site"}'))


def fechar_sem_diferenca(ator: str = ATOR) -> list[str]:
    """CAMP-FIX 15/11: fecha (tira da fila) as correções em que o painel não vê diferença nenhuma da folha para o site (alteracoes_site.
    pendentes não lista a folha). Só banco local, nenhuma chamada ao site. Não mexe na que está sendo enviada agora (estado 'executando'
    dentro da reserva) nem em edição feita durante a conta (a versão precisa bater). Devolve os códigos fechados."""
    from .alteracoes_site import pendentes
    con = connect()
    try:
        try:
            rows = con.execute("""SELECT item_codigo, versao FROM fila_correcao_site
                                  WHERE estado='pendente' OR reservado_ate <= datetime('now')""").fetchall()
        except Exception:  # noqa: BLE001 — banco antigo, sem a fila
            return []
        por_projeto: dict = {}
        for r in rows:
            por_projeto.setdefault(r["item_codigo"][:10], []).append((r["item_codigo"], r["versao"]))
        fechar = []
        for pj, lista in por_projeto.items():
            com_diferenca = {x["codigo"] for x in pendentes(con, pj)}
            fechar += [(c, v) for c, v in lista if c not in com_diferenca]
        if not fechar:
            return []
        con.execute("BEGIN IMMEDIATE")
        feitos = []
        for c, v in fechar:
            if con.execute("DELETE FROM fila_correcao_site WHERE item_codigo=? AND versao=? AND (estado='pendente' OR reservado_ate <= datetime('now'))",
                           (c, v)).rowcount:
                _registrar_igual(con, c, ator)
                feitos.append(c)
        con.commit()
        return feitos
    finally:
        con.close()
