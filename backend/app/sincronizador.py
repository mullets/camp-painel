"""Sincronização site → painel (leitura). Preenche o espelho wp_* e gera divergências.

Regras checadas (todas com a tabela de autoridade como referência):
- item sem código detectável no título/slug/metadados
- item com código de fundo que não existe na tabela de autoridade
- item publicado em fundo marcado como despublicado ou não autorizado
- termo de taxonomia com código de fundo inexistente
- fundo da tabela de autoridade sem nenhum item/termo no site (informativo)
"""
from __future__ import annotations

import json
import time
import re
import traceback
import threading

from .db import connect
from .wp import WP, detectar_codigo, metadados_texto
from .imagens import documento_do_item, resolver_anexos, thumb_do_item


def _divergencia(con, entidade, codigo, campo, painel, site):
    con.execute("INSERT INTO divergencia_site (entidade, codigo, campo, valor_painel, valor_site) VALUES (?,?,?,?,?)",
                (entidade, codigo, campo, painel, site))


def _colecao_config(con, chave: str, padrao: int) -> int:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    try:
        return int(r[0]) if r and str(r[0]).strip() else padrao
    except (TypeError, ValueError):
        return padrao


class ColecaoVaziaSuspeita(Exception):
    """A coleção devolveu 0 itens e o espelho tinha N: é falha do site/da API, não coleção esvaziada. A rodada para; nada é apagado."""

    def __init__(self, cid: int, nome: str, antes: int):
        self.cid, self.nome, self.antes = cid, nome, antes
        super().__init__(f"a coleção {nome} (id {cid}) devolveu 0 itens, mas o espelho tinha {antes}: sincronização interrompida e nada foi apagado")


LOTE_ESCRITA = 250   # linhas por transação na gravação do espelho: cada lote leva poucos ms e deixa as telas gravarem entre um e outro


def _respiro(con) -> None:
    """Confirma o lote, dá uma folga curta para quem está esperando o banco (a revisão, as estações) e reabre a escrita."""
    con.commit()
    time.sleep(0.08)
    _inicia_transacao(con)


def _inicia_transacao(con) -> None:
    """Escrita curta e atômica: pega o lock de uma vez (espera até o busy_timeout) e o solta no commit."""
    if con.in_transaction:
        con.commit()
    con.execute("BEGIN IMMEDIATE")


def _varre_o_que_sumiu(con, inicio: str, colecoes_com_metadados: list) -> None:
    """Remove do espelho só o que a rodada atual NÃO viu (o site não tem mais). Roda na transação final."""
    for t in ("wp_colecao", "wp_taxonomia", "wp_termo", "wp_item", "wp_pagina"):
        con.execute(f"DELETE FROM {t} WHERE visto_em < ?", (inicio,))
    if colecoes_com_metadados:   # metadados de uma coleção cuja busca falhou ficam como estavam
        marcas = ",".join("?" * len(colecoes_com_metadados))
        con.execute(f"DELETE FROM wp_metadado WHERE visto_em < ? AND colecao_id IN ({marcas})", (inicio, *colecoes_com_metadados))


def _reconciliar_vinculos(con, tabela: str, colecao_id: int) -> int:
    """projeto/item.tainacan_item_id = o maior id do site com o mesmo código na coleção certa (ou NULL se o site não tem).
    Só grava o que muda, em lotes de LOTE_ESCRITA (solta o banco entre um e outro). Devolve quantas linhas mudaram."""
    mapa = dict(con.execute("SELECT codigo_detectado, MAX(id) FROM wp_item WHERE colecao_id=? AND codigo_detectado IS NOT NULL "
                            "GROUP BY codigo_detectado", (colecao_id,)).fetchall())
    mudar = [(mapa.get(cod), cod) for cod, atual in con.execute(f"SELECT codigo, tainacan_item_id FROM {tabela}").fetchall()
             if mapa.get(cod) != atual]
    for k in range(0, len(mudar), LOTE_ESCRITA):
        if k:
            _respiro(con)
        con.executemany(f"UPDATE {tabela} SET tainacan_item_id=? WHERE codigo=?", mudar[k:k + LOTE_ESCRITA])
    return len(mudar)


def fundos_do_termo(texto, equiv: dict, titulos: dict) -> set[str]:
    """B8 · Fundo(s) que o campo "Fundo" do item no site indica: código no início do termo ("F023 · OCG"),
    o nome do termo na tabela de equivalência (fundo_termo_site) ou o título do fundo no painel."""
    out = set()
    for parte in str(texto or "").split(";"):
        p = parte.strip()
        if not p:
            continue
        m = re.match(r"^(F\d{3})\b", p)
        c = m.group(1) if m else (equiv.get(p) or titulos.get(p.lower()))
        if c:
            out.add(c)
    return out


def _executar_impl(gravar_espelho: bool = True, log=print) -> dict:
    """Sincroniza o espelho do site SEM nunca deixá-lo vazio ou pela metade.

    Antes, o espelho era apagado no início e repovoado ao longo de ~8 minutos. Nesse intervalo o painel
    mostrava "0 reconhecidos", "Sem imagem" e listas de termos vazias. Agora:
      1. toda a rede (a parte lenta) roda ANTES de qualquer escrita, coleção por coleção, em memória;
      2. cada coleção é gravada de uma vez, numa transação curta, já com as imagens resolvidas;
      3. só no fim, na mesma transação, saem do espelho as linhas que o site não tem mais;
      4. se algo falhar no meio, o espelho anterior continua valendo.
    As divergências da rodada substituem as antigas de uma vez, preservando as pendências de escrita ('pendente_*').
    """
    con = connect()
    sid = con.execute("INSERT INTO sincronizacao DEFAULT VALUES").lastrowid
    con.commit()
    n = {"colecoes": 0, "itens": 0, "termos": 0, "paginas": 0, "divergencias": 0}
    divs: list[tuple] = []

    def div(_con, entidade, codigo, campo, painel, site):
        divs.append((entidade, codigo, campo, painel, site))

    try:
        wp = WP(log=log)
        eu = wp.quem_sou()
        log(f"conectado a {wp.base} como {eu.get('name')} ({', '.join(eu.get('roles', []))})")
        fundos = {r["codigo"]: dict(r) for r in con.execute("SELECT * FROM fundo")}
        inicio = con.execute("SELECT datetime('now')").fetchone()[0]
        con.commit()   # nenhum lock aberto enquanto esperamos a rede/WordPress

        # ---- 1) taxonomias e termos ----
        taxs = []
        for tx in wp.taxonomias():
            termos = list(wp.termos(tx["id"]))
            taxs.append((tx, termos))
            log(f"  taxonomia {tx.get('name')}: {len(termos)} termos")
        if gravar_espelho:
            _inicia_transacao(con)
            try:
                k_ = 0
                for tx, termos in taxs:
                    con.execute("INSERT OR REPLACE INTO wp_taxonomia (id, nome, slug, json) VALUES (?,?,?,?)",
                                (tx["id"], tx.get("name"), tx.get("slug"), json.dumps(tx, ensure_ascii=False)))
                    for te in termos:
                        k_ += 1
                        if k_ % LOTE_ESCRITA == 0:
                            _respiro(con)
                        cod, _f, _ = detectar_codigo(te.get("slug", ""), te.get("name", ""))
                        con.execute("INSERT OR REPLACE INTO wp_termo (id, taxonomia_id, nome, slug, pai_id, codigo_detectado, json) VALUES (?,?,?,?,?,?,?)",
                                    (te["id"], tx["id"], te.get("name"), te.get("slug"), te.get("parent"), cod, json.dumps(te, ensure_ascii=False)))
                con.commit()
            except Exception:
                con.rollback(); raise
        for tx, termos in taxs:
            for te in termos:
                _cod, f, _ = detectar_codigo(te.get("slug", ""), te.get("name", ""))
                if f and f not in fundos:
                    div(con, "termo", te.get("slug"), "fundo_inexistente", None, f)
                n["termos"] += 1

        # ---- 2) coleções e itens: rede -> memória -> uma transação por coleção ----
        fundos_vistos = set()
        equiv_fundo = {r[0]: r[1] for r in con.execute("SELECT nome_site, fundo_codigo FROM fundo_termo_site")}
        titulos_fundo = {str(r["titulo"] or "").lower(): c for c, r in fundos.items()}
        cols = wp.colecoes()
        log(f"{len(cols)} coleções encontradas")
        metas_ok: list[int] = []
        for c in cols:
            cid = c["id"]
            try:
                metas = list(wp.metadados_da_colecao(cid))
                metas_ok.append(cid)
            except Exception as e:  # noqa: BLE001
                metas = []
                log(f"  (metadados da coleção {cid}: {e})")
            log(f"  coleção {c.get('name')} (id {cid})…")
            linhas, ids = [], set()
            for it in wp.itens(cid):
                md = metadados_texto(it)
                cod, f, p = detectar_codigo(it.get("title", ""), it.get("slug", ""), *md.values())
                doc, anexo = documento_do_item(it)
                linhas.append((it, md, cod, f, p, doc, thumb_do_item(it)))
                if anexo:
                    ids.add(anexo)
                publicado = it.get("status") == "publish"
                if not cod:
                    div(con, "item", str(it["id"]), "sem_codigo", None, it.get("title"))
                elif f not in fundos:
                    div(con, "item", cod, "fundo_inexistente", None, f)
                else:
                    fundos_vistos.add(f)
                    if publicado and fundos[f]["status_site"] == "fora_do_ar":
                        div(con, "item", cod, "publicado_em_fundo_fora_do_ar", "fora_do_ar", "publish")
                    no_site = fundos_do_termo(md.get("Fundo") or md.get("Fundos"), equiv_fundo, titulos_fundo)
                    if no_site and f not in no_site:   # B8: ex. F023-P0013 publicado com Fundo = Marcos Acayaba
                        div(con, "item", cod, "fundo_trocado", f, md.get("Fundo") or md.get("Fundos"))
            total = len(linhas)
            if gravar_espelho and total == 0:                 # CAMP-042: 0 itens onde antes havia N → para e avisa, NÃO apaga o espelho
                antes = con.execute("SELECT COUNT(*) FROM wp_item WHERE colecao_id=?", (cid,)).fetchone()[0]
                if antes > 0:
                    raise ColecaoVaziaSuspeita(cid, c.get("name") or str(cid), antes)
            info: dict = {}
            if ids and gravar_espelho:   # anexos: também rede, ANTES do lock
                try:
                    info = wp.anexos(sorted(ids))
                except Exception as e:  # noqa: BLE001
                    log(f"  (anexos da coleção {cid}: {e})")
            if gravar_espelho:
                _inicia_transacao(con)
                try:
                    for m in metas:
                        mo = m.get("metadata_type_options") or {}
                        con.execute("INSERT OR REPLACE INTO wp_metadado (id, colecao_id, nome, tipo, taxonomia_id, json) VALUES (?,?,?,?,?,?)",
                                    (m["id"], cid, m.get("name"), (m.get("metadata_type") or "").split("\\")[-1],
                                     int(mo["taxonomy_id"]) if str(mo.get("taxonomy_id", "")).isdigit() else None,
                                     json.dumps({k: m.get(k) for k in ("slug", "required", "multiple", "status")}, ensure_ascii=False)))
                    for k_, (it, md, cod, f, p, doc, thumb_url) in enumerate(linhas):
                        if k_ and k_ % LOTE_ESCRITA == 0:   # 19/10: solta o banco a cada lote (antes: milhares de linhas numa transação só, e
                            _respiro(con)   # conferências e heartbeats esperavam até 30 s)
                        con.execute("INSERT OR REPLACE INTO wp_item (id, colecao_id, status, titulo, slug, url, documento_url, thumb_url, "
                                    "codigo_detectado, fundo_detectado, projeto_detectado, metadados, modificado_em, json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                    (it["id"], cid, it.get("status"), it.get("title"), it.get("slug"), it.get("url"), doc[:500] if doc else None,
                                     thumb_url, cod, f, p, json.dumps(md, ensure_ascii=False), it.get("modification_date"), json.dumps(it, ensure_ascii=False)))
                    con.execute("INSERT OR REPLACE INTO wp_colecao (id, nome, slug, url, total_itens, json) VALUES (?,?,?,?,?,?)",
                                (cid, c.get("name"), c.get("slug"), c.get("url"), total, json.dumps(c, ensure_ascii=False)))
                    ri = resolver_anexos(con, wp, cid, div, log, info=info, respiro=_respiro, lote=LOTE_ESCRITA)   # só banco aqui; confirma a transação ao final
                    log(f"  imagens da coleção {c.get('name')}: {ri['com_miniatura']} com miniatura, {ri['via_documento']} pelo documento, "
                        f"{ri['sem_imagem']} sem imagem, {ri['divergentes']} miniatura diferente do documento")
                    con.commit()
                except Exception:
                    con.rollback(); raise
            n["colecoes"] += 1; n["itens"] += total
            log(f"  coleção {c.get('name')}: {total} itens gravados")

        # ---- 3) páginas (rede antes do lock) ----
        paginas = list(wp.paginas())

        # ---- 4) páginas em lotes curtos (cada lote solta o banco); depois, numa transação só: remoção do que sumiu, reconciliação, divergências ----
        _inicia_transacao(con)
        try:
            for k_, pg in enumerate(paginas):
                if k_ and k_ % LOTE_ESCRITA == 0:
                    _respiro(con)
                titulo = (pg.get("title") or {}).get("rendered", "") if isinstance(pg.get("title"), dict) else str(pg.get("title"))
                cod, _, _ = detectar_codigo(pg.get("slug", ""), titulo)
                con.execute("INSERT OR REPLACE INTO wp_pagina (id, titulo, slug, url, status, pai_id, codigo_detectado, json) VALUES (?,?,?,?,?,?,?,?)",
                            (pg["id"], titulo, pg.get("slug"), pg.get("link"), pg.get("status"), pg.get("parent"), cod,
                             json.dumps({k: pg.get(k) for k in ("id", "slug", "link", "status", "parent", "modified")}, ensure_ascii=False)))
                n["paginas"] += 1
            if gravar_espelho:
                _varre_o_que_sumiu(con, inicio, metas_ok)

            # Reconcilia os vínculos por código exato E pela coleção correta.
            # Projeto nunca pode apontar para uma folha/documento e vice-versa.
            projetos_cid = _colecao_config(con, "tainacan.projetos_collection_id", 8007)
            itens_cid = _colecao_config(con, "tainacan.itens_collection_id", 8013)
            # 27/10: antes eram 4 UPDATEs com subconsulta por linha; o SQLite escolhia o índice da coleção (idx_wp_item_colecao) e
            # varria a coleção inteira para CADA folha (6.000 × 6.000): ~20 s com a escrita presa. Agora: um mapa código -> id e só
            # as linhas que mudam, em lotes curtos. Mesmo resultado: vínculo = o maior id do código na coleção certa, ou nenhum.
            _reconciliar_vinculos(con, "projeto", projetos_cid)
            _reconciliar_vinculos(con, "item", itens_cid)

            for f, r in fundos.items():
                if f not in fundos_vistos and r["ativo"]:
                    div(con, "fundo", f, "sem_itens_no_site", r["titulo"], None)

            # situação real de cada fundo a partir do que está no site + id do termo
            equiv = {r[0]: r[1] for r in con.execute("SELECT nome_site, fundo_codigo FROM fundo_termo_site")}
            for r in con.execute("SELECT x.id, x.nome FROM wp_termo x JOIN wp_taxonomia t ON t.id=x.taxonomia_id WHERE t.nome='Fundos'").fetchall():
                if equiv.get(r[1]):
                    con.execute("UPDATE fundo SET tainacan_term_id=? WHERE codigo=?", (r[0], equiv[r[1]]))
            for f in fundos:
                pub, dr, pr = [con.execute("SELECT COUNT(*) FROM wp_item WHERE fundo_detectado=? AND status=?", (f, st)).fetchone()[0]
                               for st in ("publish", "draft", "private")]
                novo = "no_ar" if pub else ("rascunho" if dr else ("fora_do_ar" if pr else "nao_publicado"))
                atual = fundos[f]["status_site"]
                if atual == "fora_do_ar" and fundos[f]["motivo_fora_do_ar"] and novo != "no_ar":
                    continue   # decisão humana de despublicar prevalece enquanto não há nada publicado
                if novo != atual:
                    con.execute("UPDATE fundo SET status_site=? WHERE codigo=?", (novo, f))


            # divergências da rodada substituem as antigas; pendências de escrita no site ('pendente_*') não são da sincronização
            con.execute("DELETE FROM divergencia_site WHERE resolvida=0 AND campo NOT LIKE 'pendente\\_%' ESCAPE '\\'")
            con.executemany("INSERT INTO divergencia_site (entidade, codigo, campo, valor_painel, valor_site) VALUES (?,?,?,?,?)", divs)
            n["divergencias"] = len(divs)
            con.execute("UPDATE sincronizacao SET terminada_em=datetime('now'), ok=1, colecoes=?, itens=?, termos=?, paginas=?, divergencias=? WHERE id=?",
                        (n["colecoes"], n["itens"], n["termos"], n["paginas"], n["divergencias"], sid))
            con.commit()
        except Exception:
            con.rollback(); raise
        log(f"ok: {n}")
        return {"ok": True, **n}
    except Exception as e:  # noqa: BLE001
        # Qualquer escrita em andamento é desfeita; o espelho da rodada anterior continua intacto.
        if con.in_transaction:
            con.rollback()
        if isinstance(e, ColecaoVaziaSuspeita):               # alerta visível: Estações mostra a divergência e o histórico guarda o evento
            con.execute("DELETE FROM divergencia_site WHERE resolvida=0 AND campo='colecao_vazia_suspeita' AND codigo=?", (str(e.cid),))
            con.execute("INSERT INTO divergencia_site (entidade, codigo, campo, valor_painel, valor_site) VALUES ('colecao',?,'colecao_vazia_suspeita',?,?)",
                        (str(e.cid), f"{e.antes} itens no espelho", "0 itens no site"))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('sistema','sync','sincronizacao_abortada_colecao_vazia','site',?)",
                        (json.dumps({"colecao_id": e.cid, "nome": e.nome, "itens_no_espelho": e.antes}, ensure_ascii=False),))
        con.execute("UPDATE sincronizacao SET terminada_em=datetime('now'), ok=0, erro=? WHERE id=?", (f"{e}\n{traceback.format_exc()[-800:]}", sid))
        con.commit()
        log(f"ERRO: {e}")
        return {"ok": False, "erro": str(e)}
    finally:
        con.close()


# Uma única sincronização por processo. Evita sobreposição entre o ciclo automático
# e o botão manual, que antes podiam disputar o SQLite e o espelho do site.
_SYNC_LOCK = threading.Lock()


def executar(gravar_espelho: bool = True, log=print) -> dict:
    if not _SYNC_LOCK.acquire(blocking=False):
        log("sincronização ignorada: já existe uma em andamento")
        return {"ok": False, "em_andamento": True, "erro": "Já existe uma sincronização em andamento."}
    try:
        return _executar_impl(gravar_espelho=gravar_espelho, log=log)
    finally:
        _SYNC_LOCK.release()


# ---- 27/10 ("a sincronização fica em loop"): a automática e a manual são a MESMA tarefa, uma por vez ----
# Antes: a automática rodava fora das tarefas (a manual não a via e virava outra tarefa que falhava com "já existe uma"),
# começava 60 s depois de cada reinício do serviço (cada deploy = uma rodada completa de ~9 min), contava o intervalo só a
# partir do fim da PRÓPRIA rodada (uma manual que acabou de terminar não adiava a automática) e rodava no meio de publicações.
ATOR_AUTOMATICO = "painel (automático)"          # o autor no Histórico (docs/vocabulario.md: "O painel (automático)")
INTERVALO_PADRAO_MIN = 60                         # sem 'sync.intervalo_min' configurado; 15 min é pouco para uma rodada de ~9 min
INTERVALO_RECOMENDADO_MIN = 60
ADIAR_S = 120                                     # publicação/envio ao site em andamento: tenta de novo em 2 min
TIPOS_QUE_ESCREVEM_NO_SITE = ("publicar", "enviar_folhas", "enviar_correcoes", "reprocessar_recorte")


def intervalo_min(con) -> int:
    r = con.execute("SELECT valor FROM configuracao WHERE chave='sync.intervalo_min'").fetchone()
    v = str(r[0]).strip() if r and r[0] is not None else ""
    return int(v) if v.isdigit() else INTERVALO_PADRAO_MIN


def segundos_desde_a_ultima(con) -> float | None:
    """Segundos desde o FIM da última sincronização (automática ou manual, deu certo ou não). None = nunca terminou nenhuma."""
    r = con.execute("SELECT (julianday('now') - julianday(MAX(terminada_em))) * 86400 FROM sincronizacao WHERE terminada_em IS NOT NULL").fetchone()
    return None if not r or r[0] is None else max(0.0, float(r[0]))


def motivo_para_adiar(con) -> str | None:
    """A automática não começa com publicação ou envio ao site em andamento (as duas disputariam o site e o banco)."""
    from .rotas_publicar_tudo import _THREADS
    marcas = ",".join("?" * len(TIPOS_QUE_ESCREVEM_NO_SITE))
    for tid, tipo, alvo in con.execute(f"SELECT id, COALESCE(tipo,'publicar'), projeto_codigo FROM tarefa_publicacao "
                                       f"WHERE estado='rodando' AND COALESCE(tipo,'publicar') IN ({marcas})", TIPOS_QUE_ESCREVEM_NO_SITE).fetchall():
        th = _THREADS.get(tid)
        if th and th.is_alive():
            return f"{tipo} {alvo} em andamento"
    try:
        from .fila_correcao_site import _RODADA
        if _RODADA.locked():
            return "envio de correções ao site em andamento"
    except ImportError:
        pass
    return None


def _rodar_como_tarefa(p) -> dict:
    import logging
    from .log_tecnico import registrar
    p.passo("Lendo coleções, folhas e páginas do site")
    r = executar(log=lambda msg: registrar(logging.INFO, "sync_msg", str(msg)[:1000]))
    if r.get("em_andamento"):
        return {**r, "mensagem": "Já há uma sincronização com o site em andamento. Nada foi feito de novo."}
    if not r.get("ok"):
        return {**r, "mensagem": f"A sincronização falhou: {r.get('erro') or 'sem resposta do site'}"}
    def qtd(n, um, varios):
        return f"{n:,}".replace(",", ".") + " " + (um if n == 1 else varios)
    return {**r, "mensagem": f"Sincronizado: {qtd(r['itens'], 'item', 'itens')} do site, {qtd(r['divergencias'], 'divergência', 'divergências')}."}


_INICIO = threading.Lock()


def iniciar(u: dict):
    """Começa a sincronização como tarefa ou devolve a que já está rodando (a automática ou a de outra pessoa): nunca duas."""
    from . import tarefas
    with _INICIO:
        return tarefas.iniciar("sincronizar", "site", u, _rodar_como_tarefa)


def passo_automatico() -> dict:
    """Uma volta do ciclo automático. Devolve {acao, espera_s, ...}: quanto o ciclo dorme até a próxima volta.
    - desligada ('sync.intervalo_min' = 0): confere de novo em 5 min;
    - o intervalo conta do FIM da última sincronização, automática ou manual (reiniciar o serviço não força outra rodada);
    - publicação/envio ao site em andamento: adia ADIAR_S;
    - senão começa (ou entra na que já está rodando) e espera ela terminar."""
    import json as _json
    con = connect()
    try:
        minutos = intervalo_min(con)
        if minutos <= 0:
            return {"acao": "desligada", "espera_s": 300}
        desde = segundos_desde_a_ultima(con)
        if desde is not None and desde < minutos * 60:
            return {"acao": "esperar", "espera_s": min(300.0, minutos * 60 - desde) or 1, "intervalo_min": minutos}
        motivo = motivo_para_adiar(con)
        if motivo:
            return {"acao": "adiada", "motivo": motivo, "espera_s": ADIAR_S, "intervalo_min": minutos}
    finally:
        con.close()
    import logging
    from .log_tecnico import registrar
    registrar(logging.INFO, "sync_start", "Sincronização automática iniciada", intervalo_min=minutos)
    resp = iniciar({"email": ATOR_AUTOMATICO, "papel": "admin"})
    tid = _json.loads(resp.body)["tarefa_id"]
    from .rotas_publicar_tudo import _THREADS
    th = _THREADS.get(tid)
    if th:
        th.join()
    return {"acao": "rodou", "tarefa_id": tid, "espera_s": minutos * 60, "intervalo_min": minutos}
