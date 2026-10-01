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


def _divergencia(con, entidade, codigo, campo, painel, site):
    con.execute("INSERT INTO divergencia_site (entidade, codigo, campo, valor_painel, valor_site) VALUES (?,?,?,?,?)",
                (entidade, codigo, campo, painel, site))


def _executar_impl(gravar_espelho: bool = True, log=print) -> dict:
    con = connect()
    sid = con.execute("INSERT INTO sincronizacao DEFAULT VALUES").lastrowid
    con.commit()
    n = {"colecoes": 0, "itens": 0, "termos": 0, "paginas": 0, "divergencias": 0}
    try:
        wp = WP(log=log)
        eu = wp.quem_sou()
        log(f"conectado a {wp.base} como {eu.get('name')} ({', '.join(eu.get('roles', []))})")

        fundos = {r["codigo"]: dict(r) for r in con.execute("SELECT * FROM fundo")}
        con.execute("DELETE FROM divergencia_site WHERE resolvida=0")
        if gravar_espelho:
            for t in ("wp_colecao", "wp_taxonomia", "wp_termo", "wp_item", "wp_pagina"):
                con.execute(f"DELETE FROM {t}")
        # Não manter um write lock aberto enquanto esperamos a rede/WordPress.
        con.commit()

        # taxonomias e termos
        for tx in wp.taxonomias():
            n_tx = 0
            con.execute("INSERT INTO wp_taxonomia (id, nome, slug, json) VALUES (?,?,?,?)",
                        (tx["id"], tx.get("name"), tx.get("slug"), json.dumps(tx, ensure_ascii=False)))
            for te in wp.termos(tx["id"]):
                cod, f, _ = detectar_codigo(te.get("slug", ""), te.get("name", ""))
                con.execute("INSERT OR REPLACE INTO wp_termo (id, taxonomia_id, nome, slug, pai_id, codigo_detectado, json) VALUES (?,?,?,?,?,?,?)",
                            (te["id"], tx["id"], te.get("name"), te.get("slug"), te.get("parent"), cod, json.dumps(te, ensure_ascii=False)))
                if f and f not in fundos:
                    _divergencia(con, "termo", te.get("slug"), "fundo_inexistente", None, f); n["divergencias"] += 1
                n_tx += 1; n["termos"] += 1
                if n_tx % 100 == 0:
                    con.commit()
            con.commit()
            log(f"  taxonomia {tx.get('name')}: {n_tx} termos")

        # coleções e itens
        fundos_vistos = set()
        cols = wp.colecoes()
        log(f"{len(cols)} coleções encontradas")
        con.execute("DELETE FROM wp_metadado")
        con.commit()
        for c in cols:
            cid = c["id"]; total = 0
            try:
                for m in wp.metadados_da_colecao(cid):
                    mo = m.get("metadata_type_options") or {}
                    con.execute("INSERT OR REPLACE INTO wp_metadado (id, colecao_id, nome, tipo, taxonomia_id, json) VALUES (?,?,?,?,?,?)",
                                (m["id"], cid, m.get("name"), (m.get("metadata_type") or "").split("\\")[-1],
                                 int(mo["taxonomy_id"]) if str(mo.get("taxonomy_id", "")).isdigit() else None,
                                 json.dumps({k: m.get(k) for k in ("slug", "required", "multiple", "status")}, ensure_ascii=False)))
            except Exception as e:  # noqa: BLE001
                log(f"  (metadados da coleção {cid}: {e})")
            log(f"  coleção {c.get('name')} (id {cid})…")
            for it in wp.itens(cid):
                md = metadados_texto(it)
                cod, f, p = detectar_codigo(it.get("title", ""), it.get("slug", ""), *md.values())
                doc = it.get("document") if isinstance(it.get("document"), str) else (it.get("document_as_html") or "")
                thumb = it.get("thumbnail", {})
                thumb_url = ""
                if isinstance(thumb, dict):
                    for k in ("large", "tainacan-medium", "medium", "full"):
                        if isinstance(thumb.get(k), list) and thumb[k]:
                            thumb_url = thumb[k][0]; break
                if gravar_espelho:
                    con.execute("INSERT OR REPLACE INTO wp_item (id, colecao_id, status, titulo, slug, url, documento_url, thumb_url, "
                                "codigo_detectado, fundo_detectado, projeto_detectado, metadados, modificado_em, json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (it["id"], cid, it.get("status"), it.get("title"), it.get("slug"), it.get("url"), doc[:500] if doc else None,
                                 thumb_url, cod, f, p, json.dumps(md, ensure_ascii=False), it.get("modification_date"), json.dumps(it, ensure_ascii=False)))
                publicado = it.get("status") == "publish"
                if not cod:
                    _divergencia(con, "item", str(it["id"]), "sem_codigo", None, it.get("title")); n["divergencias"] += 1
                elif f not in fundos:
                    _divergencia(con, "item", cod, "fundo_inexistente", None, f); n["divergencias"] += 1
                else:
                    fundos_vistos.add(f)
                    if publicado and fundos[f]["status_site"] == "fora_do_ar":
                        _divergencia(con, "item", cod, "publicado_em_fundo_fora_do_ar", "fora_do_ar", "publish"); n["divergencias"] += 1
                total += 1; n["itens"] += 1
                if total % 100 == 0:
                    con.commit()
            con.execute("INSERT INTO wp_colecao (id, nome, slug, url, total_itens, json) VALUES (?,?,?,?,?,?)",
                        (cid, c.get("name"), c.get("slug"), c.get("url"), total, json.dumps(c, ensure_ascii=False)))
            n["colecoes"] += 1
            log(f"  coleção {c.get('name')}: {total} itens gravados")
            con.commit()

        # Reconcilia os vínculos locais exclusivamente por código exato.
        # Isso corrige IDs antigos/errados e evita miniaturas de outro item.
        con.execute("""
            UPDATE projeto
               SET tainacan_item_id = (
                   SELECT w.id FROM wp_item w
                    WHERE w.codigo_detectado = projeto.codigo
                    ORDER BY w.id DESC LIMIT 1
               )
             WHERE EXISTS (
                   SELECT 1 FROM wp_item w
                    WHERE w.codigo_detectado = projeto.codigo
             )
        """)
        con.execute("""
            UPDATE item
               SET tainacan_item_id = (
                   SELECT w.id FROM wp_item w
                    WHERE w.codigo_detectado = item.codigo
                    ORDER BY w.id DESC LIMIT 1
               )
             WHERE EXISTS (
                   SELECT 1 FROM wp_item w
                    WHERE w.codigo_detectado = item.codigo
             )
        """)
        # Se o ID salvo aponta para um item cujo código é diferente, limpa o vínculo.
        con.execute("""
            UPDATE projeto
               SET tainacan_item_id = NULL
             WHERE tainacan_item_id IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM wp_item w
                    WHERE w.id = projeto.tainacan_item_id
                      AND w.codigo_detectado = projeto.codigo
               )
        """)
        con.execute("""
            UPDATE item
               SET tainacan_item_id = NULL
             WHERE tainacan_item_id IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM wp_item w
                    WHERE w.id = item.tainacan_item_id
                      AND w.codigo_detectado = item.codigo
               )
        """)
        con.commit()

        for f, r in fundos.items():
            if f not in fundos_vistos and r["ativo"]:
                _divergencia(con, "fundo", f, "sem_itens_no_site", r["titulo"], None); n["divergencias"] += 1

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
        con.commit()

        # páginas (dossiês, fundos, institucionais)
        for pg in wp.paginas():
            titulo = (pg.get("title") or {}).get("rendered", "") if isinstance(pg.get("title"), dict) else str(pg.get("title"))
            cod, _, _ = detectar_codigo(pg.get("slug", ""), titulo)
            con.execute("INSERT OR REPLACE INTO wp_pagina (id, titulo, slug, url, status, pai_id, codigo_detectado, json) VALUES (?,?,?,?,?,?,?,?)",
                        (pg["id"], titulo, pg.get("slug"), pg.get("link"), pg.get("status"), pg.get("parent"), cod,
                         json.dumps({k: pg.get(k) for k in ("id", "slug", "link", "status", "parent", "modified")}, ensure_ascii=False)))
            n["paginas"] += 1
            if n["paginas"] % 100 == 0:
                con.commit()

        con.execute("UPDATE sincronizacao SET terminada_em=datetime('now'), ok=1, colecoes=?, itens=?, termos=?, paginas=?, divergencias=? WHERE id=?",
                    (n["colecoes"], n["itens"], n["termos"], n["paginas"], n["divergencias"], sid))
        con.commit()
        log(f"ok: {n}")
        return {"ok": True, **n}
    except Exception as e:  # noqa: BLE001
        # Desfaz qualquer lote incompleto antes de registrar a falha.
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
