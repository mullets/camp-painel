"""15/11/2026 · O registro ANTIGO no site de uma folha movida sai do público e nunca volta ao painel como "só no site".

Pedido do Rafael: "Movi um lote inteiro de um projeto para outro; no antigo ficaram as imagens no site, e no painel ficam como 'só no site'.
Devia tirar de ambos." Antes, só o "Mover folhas" (POST /api/itens/mover) escondia no site — e só a folha marcada 'no_ar' no painel. O mover
lote, o mesclar e o CAMP Vision desligavam a folha do item do site (tainacan_item_id=NULL) e o item continuava público com o código antigo;
a importação do site (importador_site) depois o trazia de volta ao projeto antigo como folha "só no site".

Regras:
  - `registrar(con, ...)`: quem move (rotas_mesclar._mover, dentro da transação) grava cada registro antigo em `site_registro_antigo`
    (migração 222), seja qual for a situação da folha no painel (status velho não importa: o site pode estar público).
  - `esconder(ids)` / `esconder_pendentes()`: FORA da transação, deixa cada registro privado no site (nada é apagado) e marca
    escondido_em. Site sem resposta = fica pendente com tentativas/ultimo_erro/proxima_em; nunca levanta, nunca desfaz o mover.
    O coletor de 10 min (main), a rodada de reenvio (fila_correcao_site) e o envio dos redirecionamentos tentam de novo.
  - `nao_voltam(con)`: o mapa explícito do que a importação do site NUNCA recria (ids de registros antigos — desta tabela e dos eventos
    'folha_movida' anteriores a ela — e códigos com redirecionamento 301 para outro código).
Sem a tabela (banco antes da migração 222) tudo segue como antes; os eventos continuam valendo para a importação."""
from __future__ import annotations

import json
import sqlite3
import threading

from .db import connect

ATE_NA_HORA = 8            # até tantas folhas, a rota esconde na hora (na própria requisição); mais que isso, em segundo plano
_TRAVA = threading.Lock()


def tem_tabela(con) -> bool:
    try:
        return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='site_registro_antigo'").fetchone())
    except sqlite3.Error:
        return False


def registrar(con, wp_id, codigo_antigo: str, codigo_novo: str | None, motivo: str | None, ator: str | None) -> bool:
    """Grava (ou reabre) o registro antigo como pendente de esconder. Não faz commit (transação de quem chama)."""
    if not wp_id or not tem_tabela(con):
        return False
    con.execute("""INSERT INTO site_registro_antigo (wp_id, codigo_antigo, codigo_novo, motivo, ator) VALUES (?,?,?,?,?)
                   ON CONFLICT(wp_id) DO UPDATE SET codigo_novo=excluded.codigo_novo, motivo=excluded.motivo, ator=excluded.ator,
                        escondido_em=NULL, proxima_em=NULL""", (int(wp_id), codigo_antigo, codigo_novo, (motivo or "")[:300], ator))
    return True


def ids_de_eventos(con) -> dict[int, dict]:
    """{wp_id: {de, para}} dos eventos 'folha_movida' que tinham registro no site (cobre os movimentos de antes da migração 222)."""
    out = {}
    for (det,) in con.execute("SELECT detalhe FROM evento WHERE tipo='folha_movida' AND detalhe LIKE '%tainacan_item_id_antigo%' ORDER BY id"):
        try:
            d = json.loads(det or "{}")
        except ValueError:
            continue
        w = d.get("tainacan_item_id_antigo")
        if str(w or "").isdigit() and int(w):
            out[int(w)] = {"de": d.get("de"), "para": d.get("para")}
    return out


def nao_voltam(con) -> dict:
    """O que a importação do site não recria: {"ids": {wp_id: código antigo}, "codigos": {código antigo: código novo}}.
    ids = registros antigos de folhas movidas (tabela + eventos); codigos = redirecionamentos 301 de folha para outro código."""
    ids = {w: (x.get("de") or "") for w, x in ids_de_eventos(con).items()}
    if tem_tabela(con):
        ids.update({int(r[0]): r[1] for r in con.execute("SELECT wp_id, codigo_antigo FROM site_registro_antigo")})
    codigos = {}
    try:
        codigos = {r[0]: r[1] for r in con.execute(
            "SELECT codigo_antigo, codigo_novo FROM redirecionamento WHERE entidade='item' AND codigo_novo IS NOT NULL AND codigo_novo<>codigo_antigo")}
    except sqlite3.Error:
        pass
    return {"ids": ids, "codigos": codigos}


def antigo_do_site(con, wp_id, cod: str | None) -> str | None:
    """Versão de UMA linha (barata, para a página do projeto): o item `wp_id` do site, com o código `cod`, é registro antigo de folha que
    mudou de código? Devolve o porquê ou None. Usa a tabela, a folha ligada ao item e o redirecionamento 301 (os movimentos de antes da
    migração 222 sempre registraram o 301 da folha que tinha registro no site)."""
    wid = int(wp_id) if str(wp_id or "").isdigit() else None
    if wid is not None:
        dono = con.execute("SELECT codigo FROM item WHERE tainacan_item_id=? LIMIT 1", (wid,)).fetchone()
        if dono:
            return None if dono[0] == cod else f"o item do site já é da folha {dono[0]}"
        if tem_tabela(con):
            r = con.execute("SELECT codigo_antigo, codigo_novo FROM site_registro_antigo WHERE wp_id=?", (wid,)).fetchone()
            if r:
                return f"registro antigo da folha {r[0]}, que foi movida para {r[1]}"
    if cod:
        try:
            r = con.execute("SELECT codigo_novo FROM redirecionamento WHERE codigo_antigo=? AND entidade='item' AND codigo_novo<>codigo_antigo", (cod,)).fetchone()
        except sqlite3.Error:
            r = None
        if r:
            return f"o código {cod} redireciona para {r[0]}"
    return None


def pendentes(con, ids=None, prontos: bool = True) -> list[dict]:
    if not tem_tabela(con):
        return []
    sql = "SELECT * FROM site_registro_antigo WHERE escondido_em IS NULL"
    args: list = []
    if ids is not None:
        ids = [int(x) for x in ids]
        if not ids:
            return []
        sql += f" AND wp_id IN ({','.join('?' * len(ids))})"
        args += ids
    if prontos:
        sql += " AND (proxima_em IS NULL OR proxima_em <= datetime('now'))"
    return [dict(r) for r in con.execute(sql + " ORDER BY criado_em, wp_id", args)]


def contar(con) -> dict:
    if not tem_tabela(con):
        return {"pendentes": 0, "escondidos": 0}
    p = con.execute("SELECT COUNT(*) FROM site_registro_antigo WHERE escondido_em IS NULL").fetchone()[0]
    e = con.execute("SELECT COUNT(*) FROM site_registro_antigo WHERE escondido_em IS NOT NULL").fetchone()[0]
    return {"pendentes": p, "escondidos": e}


def _um(wid: int) -> None:
    from . import publicador
    publicador.WP().atualizar_status_item(publicador.COL_ACERVO, int(wid), "private")


def esconder(ids=None, ator: str = "painel", limite: int | None = None, forcar: bool = False) -> dict:
    """Deixa privados no site os registros antigos pendentes (`ids`: só estes; None: todos os prontos). NUNCA levanta.
    `forcar`: ignora a espera entre tentativas (a rota acabou de mover). Devolve {escondidos:[...], pendentes:[...], falhas:[...]}."""
    out = {"escondidos": [], "pendentes": [], "falhas": []}
    if not _TRAVA.acquire(timeout=5 if forcar else 0.01):      # outra rodada já está escondendo: o que sobrar fica pendente
        con = connect()
        try:
            out["pendentes"] = [r["codigo_antigo"] for r in pendentes(con, ids, prontos=False)]
        finally:
            con.close()
        return out
    try:
        con = connect()
        try:
            fila = pendentes(con, ids, prontos=not forcar)
        finally:
            con.close()
        if limite is not None:
            fila = fila[:limite]
        for r in fila:
            wid = int(r["wp_id"])
            try:
                _um(wid)
                erro = None
            except Exception as e:  # noqa: BLE001 — site sem resposta ou recusa: fica pendente, o mover já valeu
                erro = str(e)[:300] or type(e).__name__
            con = connect()
            try:
                if erro is None:
                    con.execute("UPDATE site_registro_antigo SET escondido_em=datetime('now'), ultimo_erro=NULL, proxima_em=NULL WHERE wp_id=?", (wid,))
                    con.execute("UPDATE wp_item SET status='private' WHERE id=?", (wid,))      # o espelho já mostra privado
                    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'site_registro_antigo_escondido',?,?)",
                                (r["codigo_novo"] or r["codigo_antigo"], ator, json.dumps(
                                    {"wp_id": wid, "codigo_antigo": r["codigo_antigo"], "codigo_novo": r["codigo_novo"]}, ensure_ascii=False)))
                    out["escondidos"].append(r["codigo_antigo"])
                else:
                    n = int(r["tentativas"] or 0)
                    segundos = min(3600, 60 * 2 ** min(n, 6))
                    con.execute("""UPDATE site_registro_antigo SET tentativas=tentativas+1, ultimo_erro=?, proxima_em=datetime('now', ?)
                                   WHERE wp_id=?""", (erro, f"+{segundos} seconds", wid))
                    out["pendentes"].append(r["codigo_antigo"])
                    out["falhas"].append({"codigo": r["codigo_antigo"], "wp_id": wid, "erro": erro})
                con.commit()
            finally:
                con.close()
    except Exception:  # noqa: BLE001 — nunca derruba quem chama
        pass
    finally:
        _TRAVA.release()
    return out


def esconder_pendentes(ator: str = "painel (automático)", limite: int = 50) -> dict:
    """Rodada automática (coletor de 10 min, reenvio, envio dos redirecionamentos). NUNCA levanta."""
    try:
        return esconder(None, ator, limite=limite)
    except Exception:  # noqa: BLE001
        return {"escondidos": [], "pendentes": [], "falhas": []}


def depois_de_mover(movidos: list[dict], ator: str, tarefas=None) -> dict:
    """Chamado pelas rotas depois do COMMIT do mover. Poucas folhas: esconde na hora; muitas: em segundo plano (BackgroundTasks),
    para um lote grande não passar do limite de 60 s da tela. Devolve o resumo para a resposta: {escondidas, pendentes, em_segundo_plano}."""
    resumo = {"escondidas": 0, "pendentes": 0, "em_segundo_plano": 0}
    novos = [m["para"] for m in movidos or [] if m.get("tinha_registro_no_site")]
    if not novos:
        return resumo
    con = connect()
    try:
        if not tem_tabela(con):
            return resumo
        ids = []
        for i in range(0, len(novos), 400):
            parte = novos[i:i + 400]
            ids += [int(r[0]) for r in con.execute(f"SELECT wp_id FROM site_registro_antigo WHERE escondido_em IS NULL AND codigo_novo IN ({','.join('?' * len(parte))})", parte)]
    finally:
        con.close()
    if not ids:
        return resumo
    if len(ids) > ATE_NA_HORA and tarefas is not None:
        tarefas.add_task(esconder, ids, ator, None, True)
        resumo["em_segundo_plano"] = len(ids)
        return resumo
    r = esconder(ids, ator, forcar=True)
    resumo["escondidas"], resumo["pendentes"] = len(r["escondidos"]), len(r["pendentes"])
    resumo["lista_escondidas"] = r["escondidos"]
    return resumo
