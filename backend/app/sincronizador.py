"""Sincronização site → painel (leitura). Preenche o espelho wp_* e gera divergências.

Regras checadas (todas com a tabela de autoridade como referência):
- item sem código detectável no título/slug/metadados
- item com código de fundo que não existe na tabela de autoridade
- item publicado em fundo marcado como fora do ar ou não autorizado
- item publicado sem crédito ("Acervo ... /CAMP")
- termo de taxonomia com código de fundo inexistente
- fundo da tabela de autoridade sem nenhum item/termo no site (informativo)
"""
from __future__ import annotations

import json
import traceback

from .db import connect
from .wp import WP, detectar_codigo, metadados_texto


def _divergencia(con, entidade, codigo, campo, painel, site):
    con.execute("INSERT INTO divergencia_site (entidade, codigo, campo, valor_painel, valor_site) VALUES (?,?,?,?,?)",
                (entidade, codigo, campo, painel, site))


def executar(gravar_espelho: bool = True, log=print) -> dict:
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
            log(f"  taxonomia {tx.get('name')}: {n_tx} termos")

        # coleções e itens
        fundos_vistos = set()
        cols = wp.colecoes()
        log(f"{len(cols)} coleções encontradas")
        for c in cols:
            cid = c["id"]; total = 0
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
                if publicado:
                    tem_credito = any("acervo" in v.lower() and "camp" in v.lower() for v in md.values())
                    if not tem_credito:
                        _divergencia(con, "item", cod or str(it["id"]), "sem_credito", "Acervo {agente}/CAMP", ""); n["divergencias"] += 1
                total += 1; n["itens"] += 1
            con.execute("INSERT INTO wp_colecao (id, nome, slug, url, total_itens, json) VALUES (?,?,?,?,?,?)",
                        (cid, c.get("name"), c.get("slug"), c.get("url"), total, json.dumps(c, ensure_ascii=False)))
            n["colecoes"] += 1
            log(f"  coleção {c.get('name')}: {total} itens gravados")
            con.commit()

        for f, r in fundos.items():
            if f not in fundos_vistos and r["ativo"]:
                _divergencia(con, "fundo", f, "sem_itens_no_site", r["titulo"], None); n["divergencias"] += 1

        # páginas (dossiês, fundos, institucionais)
        for pg in wp.paginas():
            titulo = (pg.get("title") or {}).get("rendered", "") if isinstance(pg.get("title"), dict) else str(pg.get("title"))
            cod, _, _ = detectar_codigo(pg.get("slug", ""), titulo)
            con.execute("INSERT OR REPLACE INTO wp_pagina (id, titulo, slug, url, status, pai_id, codigo_detectado, json) VALUES (?,?,?,?,?,?,?,?)",
                        (pg["id"], titulo, pg.get("slug"), pg.get("link"), pg.get("status"), pg.get("parent"), cod,
                         json.dumps({k: pg.get(k) for k in ("id", "slug", "link", "status", "parent", "modified")}, ensure_ascii=False)))
            n["paginas"] += 1

        con.execute("UPDATE sincronizacao SET terminada_em=datetime('now'), ok=1, colecoes=?, itens=?, termos=?, paginas=?, divergencias=? WHERE id=?",
                    (n["colecoes"], n["itens"], n["termos"], n["paginas"], n["divergencias"], sid))
        con.commit()
        log(f"ok: {n}")
        return {"ok": True, **n}
    except Exception as e:  # noqa: BLE001
        con.execute("UPDATE sincronizacao SET terminada_em=datetime('now'), ok=0, erro=? WHERE id=?", (f"{e}\n{traceback.format_exc()[-800:]}", sid))
        con.commit()
        log(f"ERRO: {e}")
        return {"ok": False, "erro": str(e)}
    finally:
        con.close()
