"""Sincronização site → painel (leitura). Preenche o espelho wp_* e gera divergências.

Regras checadas (todas com a tabela de autoridade como referência):
- item sem código detectável no título/slug/metadados
- item com código de fundo que não existe na tabela de autoridade
- item publicado em fundo marcado como fora do ar ou não autorizado
- termo de taxonomia com código de fundo inexistente
- fundo da tabela de autoridade sem nenhum item/termo no site (informativo)
"""
from __future__ import annotations

import json
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
                for tx, termos in taxs:
                    con.execute("INSERT OR REPLACE INTO wp_taxonomia (id, nome, slug, json) VALUES (?,?,?,?)",
                                (tx["id"], tx.get("name"), tx.get("slug"), json.dumps(tx, ensure_ascii=False)))
                    for te in termos:
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
            total = len(linhas)
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
                    for it, md, cod, f, p, doc, thumb_url in linhas:
                        con.execute("INSERT OR REPLACE INTO wp_item (id, colecao_id, status, titulo, slug, url, documento_url, thumb_url, "
                                    "codigo_detectado, fundo_detectado, projeto_detectado, metadados, modificado_em, json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                    (it["id"], cid, it.get("status"), it.get("title"), it.get("slug"), it.get("url"), doc[:500] if doc else None,
                                     thumb_url, cod, f, p, json.dumps(md, ensure_ascii=False), it.get("modification_date"), json.dumps(it, ensure_ascii=False)))
                    con.execute("INSERT OR REPLACE INTO wp_colecao (id, nome, slug, url, total_itens, json) VALUES (?,?,?,?,?,?)",
                                (cid, c.get("name"), c.get("slug"), c.get("url"), total, json.dumps(c, ensure_ascii=False)))
                    ri = resolver_anexos(con, wp, cid, div, log, info=info)   # só banco aqui; confirma a transação ao final
                    log(f"  imagens da coleção {c.get('name')}: {ri['com_miniatura']} com miniatura, {ri['via_documento']} pelo documento, "
                        f"{ri['sem_imagem']} sem imagem, {ri['divergentes']} miniatura diferente do documento")
                    con.commit()
                except Exception:
                    con.rollback(); raise
            n["colecoes"] += 1; n["itens"] += total
            log(f"  coleção {c.get('name')}: {total} itens gravados")

        # ---- 3) páginas (rede antes do lock) ----
        paginas = list(wp.paginas())

        # ---- 4) fecha numa única transação: páginas, remoção do que sumiu, reconciliação, divergências ----
        _inicia_transacao(con)
        try:
            for pg in paginas:
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
            con.execute("""
                UPDATE projeto
                   SET tainacan_item_id = (
                       SELECT w.id FROM wp_item w
                        WHERE w.codigo_detectado = projeto.codigo
                          AND w.colecao_id = ?
                        ORDER BY w.id DESC LIMIT 1
                   )
                 WHERE EXISTS (
                       SELECT 1 FROM wp_item w
                        WHERE w.codigo_detectado = projeto.codigo
                          AND w.colecao_id = ?
                 )
            """, (projetos_cid, projetos_cid))
            con.execute("""
                UPDATE item
                   SET tainacan_item_id = (
                       SELECT w.id FROM wp_item w
                        WHERE w.codigo_detectado = item.codigo
                          AND w.colecao_id = ?
                        ORDER BY w.id DESC LIMIT 1
                   )
                 WHERE EXISTS (
                       SELECT 1 FROM wp_item w
                        WHERE w.codigo_detectado = item.codigo
                          AND w.colecao_id = ?
                 )
            """, (itens_cid, itens_cid))
            # Se o ID salvo aponta para um item cujo código é diferente, limpa o vínculo.
            con.execute("""
                UPDATE projeto
                   SET tainacan_item_id = NULL
                 WHERE tainacan_item_id IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM wp_item w
                        WHERE w.id = projeto.tainacan_item_id
                          AND w.codigo_detectado = projeto.codigo
                          AND w.colecao_id = ?
                   )
            """, (projetos_cid,))
            con.execute("""
                UPDATE item
                   SET tainacan_item_id = NULL
                 WHERE tainacan_item_id IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM wp_item w
                        WHERE w.id = item.tainacan_item_id
                          AND w.codigo_detectado = item.codigo
                          AND w.colecao_id = ?
                   )
            """, (itens_cid,))

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
                    continue   # decisão humana de tirar do ar prevalece enquanto não há nada publicado
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
