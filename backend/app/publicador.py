"""Escritas no site que acompanham cadastros do painel. Falha no site nunca desfaz o cadastro local:
registra divergência para tentar de novo."""
from __future__ import annotations

import json

from .db import connect
from .wp import WP

COL_PROJETOS = 8007


def _tax(con, nome):
    r = con.execute("SELECT id FROM wp_taxonomia WHERE nome=?", (nome,)).fetchone()
    return r[0] if r else None


def _meta(con, colecao_id, nome):
    r = con.execute("SELECT id, tipo FROM wp_metadado WHERE colecao_id=? AND nome=?", (colecao_id, nome)).fetchone()
    return (r[0], r[1]) if r else (None, None)


def _pendencia(con, entidade, codigo, campo, detalhe):
    con.execute("INSERT INTO divergencia_site (entidade, codigo, campo, valor_painel, valor_site) VALUES (?,?,?,?,?)",
                (entidade, codigo, campo, detalhe[:300], None))


def criar_fundo_no_site(codigo: str, ator: str) -> dict:
    """Cria termos 'Fundos' e 'Arquitetos' para o fundo. Idempotente (não recria se já há term_id)."""
    con = connect()
    f = con.execute("SELECT * FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    out = {"fundo_termo": f["tainacan_term_id"], "arquiteto_termo": None, "erro": None}
    try:
        wp = WP()
        tf, ta = _tax(con, "Fundos"), _tax(con, "Arquitetos")
        if not tf:
            raise RuntimeError("Taxonomia 'Fundos' não encontrada no espelho; rode a sincronização")
        if not f["tainacan_term_id"]:
            ja = con.execute("SELECT id FROM wp_termo WHERE taxonomia_id=? AND nome=?", (tf, f["titulo"])).fetchone()
            t = {"id": ja[0]} if ja else wp.criar_termo(tf, f["titulo"], f"{codigo} · {f['sigla'] or ''}".strip(" ·"))
            con.execute("UPDATE fundo SET tainacan_term_id=? WHERE codigo=?", (t["id"], codigo))
            con.execute("INSERT OR IGNORE INTO fundo_termo_site (nome_site, fundo_codigo, observacao) VALUES (?,?,?)", (f["titulo"], codigo, "criado pelo painel"))
            con.execute("INSERT OR REPLACE INTO wp_termo (id, taxonomia_id, nome, slug, codigo_detectado, json) VALUES (?,?,?,?,?,?)",
                        (t["id"], tf, f["titulo"], t.get("slug"), codigo, json.dumps(t, ensure_ascii=False)))
            out["fundo_termo"] = t["id"]
        if ta:
            for a in con.execute("SELECT a.id, a.forma_autorizada FROM fundo_agente fa JOIN agente a ON a.id=fa.agente_id WHERE fa.fundo_codigo=? AND fa.papel='produtor'", (codigo,)).fetchall():
                ja = con.execute("SELECT id FROM wp_termo WHERE taxonomia_id=? AND nome=?", (ta, a[1])).fetchone()
                aid = con.execute("SELECT tainacan_term_id FROM agente WHERE id=?", (a[0],)).fetchone()[0]
                if not aid:
                    t = {"id": ja[0]} if ja else wp.criar_termo(ta, a[1])
                    con.execute("UPDATE agente SET tainacan_term_id=? WHERE id=?", (t["id"], a[0]))
                    con.execute("INSERT OR REPLACE INTO wp_termo (id, taxonomia_id, nome, slug, json) VALUES (?,?,?,?,?)", (t["id"], ta, a[1], t.get("slug"), json.dumps(t, ensure_ascii=False)))
                    out["arquiteto_termo"] = t["id"]
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('fundo',?,'site_termo_criado',?,?)", (codigo, ator, json.dumps(out)))
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]
        _pendencia(con, "fundo", codigo, "pendente_criar_no_site", out["erro"])
    con.commit(); con.close()
    return out


def renomear_fundo_no_site(codigo: str, novo_titulo: str, ator: str) -> dict:
    con = connect()
    f = con.execute("SELECT tainacan_term_id FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    out = {"ok": False, "erro": None}
    try:
        if f and f[0]:
            wp = WP()
            wp.atualizar_termo(_tax(con, "Fundos"), f[0], name=novo_titulo)
            con.execute("UPDATE wp_termo SET nome=? WHERE id=?", (novo_titulo, f[0]))
            con.execute("UPDATE fundo_termo_site SET nome_site=? WHERE fundo_codigo=?", (novo_titulo, codigo))
            out["ok"] = True
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]; _pendencia(con, "fundo", codigo, "pendente_renomear_no_site", out["erro"])
    con.commit(); con.close()
    return out


def criar_dossie_no_site(codigo: str, ator: str) -> dict:
    """Cria o item do projeto na coleção 'Projetos CAMP' como rascunho, com os metadados que o site usa."""
    con = connect()
    p = con.execute("SELECT p.*, f.titulo AS fundo_titulo, f.tainacan_term_id AS fundo_termo FROM projeto p JOIN fundo f ON f.codigo=p.fundo_codigo WHERE p.codigo=?", (codigo,)).fetchone()
    out = {"item_id": p["tainacan_item_id"], "metadados": [], "erro": None}
    if p["tainacan_item_id"]:
        con.close(); return out
    try:
        wp = WP()
        titulo = f"{codigo.split('-')[1]} — {p['titulo']}" + (f", {p['cidade']}" if p["cidade"] else "")
        it = wp.criar_item(COL_PROJETOS, titulo, "draft", p["ambito_conteudo"] or "")
        iid = it["id"]
        con.execute("UPDATE projeto SET tainacan_item_id=? WHERE codigo=?", (iid, codigo))
        con.execute("INSERT OR REPLACE INTO wp_item (id, colecao_id, status, titulo, slug, url, codigo_detectado, fundo_detectado, projeto_detectado, metadados, json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (iid, COL_PROJETOS, "draft", titulo, it.get("slug"), it.get("url"), codigo, p["fundo_codigo"], codigo, "{}", json.dumps(it, ensure_ascii=False)))
        arq = con.execute("SELECT a.tainacan_term_id, a.forma_autorizada FROM fundo_agente fa JOIN agente a ON a.id=fa.agente_id WHERE fa.fundo_codigo=? AND fa.papel='produtor' ORDER BY fa.inicio LIMIT 1", (p["fundo_codigo"],)).fetchone()
        valores = {"Código de Catalogação": codigo, "Ano": str(p["ano"]) if p["ano"] else None, "Cidade": p["cidade"],
                   "Programa / uso": p["tipologia"], "Cliente (divulgável)": p["cliente"],
                   "Fundo": p["fundo_termo"] or p["fundo_titulo"], "Arquiteto": (arq[0] or arq[1]) if arq else None}
        for nome, valor in valores.items():
            if valor in (None, ""):
                continue
            mid, tipo = _meta(con, COL_PROJETOS, nome)
            if not mid:
                continue
            try:
                wp.definir_metadado(iid, mid, valor)
                out["metadados"].append(nome)
            except Exception as e:  # noqa: BLE001
                _pendencia(con, "projeto", codigo, f"pendente_metadado_{nome}", str(e)[:200])
        out["item_id"] = iid
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'site_dossie_criado',?,?)", (codigo, ator, json.dumps(out, ensure_ascii=False)))
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]
        _pendencia(con, "projeto", codigo, "pendente_criar_no_site", out["erro"])
    con.commit(); con.close()
    return out
