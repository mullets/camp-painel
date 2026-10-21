"""CAMP-015 · "Enviar fundo ao site": termo da taxonomia + página-hub do arquiteto com os campos preenchidos no painel (inclusive biografia, fontes e foto).

- Só vão os campos PREENCHIDOS (a rota do hub do site ignora vazio, para não apagar texto escrito à mão no WordPress). Para LIMPAR um campo de
  propósito, o painel manda o valor especial "__limpar__" (publicador.HUB_LIMPAR) e o site apaga só esse campo.
- Divergência painel × site: o painel não lê o hub no site; compara o que há agora no painel com o ÚLTIMO envio (fundo_envio_site).
- Página pública do arquiteto: leitura do espelho do site (wp_pagina /acervo/arquitetos/…); o plano de publicação avisa quando não existe."""
from __future__ import annotations

import json

from .db import connect

ROTULOS = {"_camp_bio": "Biografia", "_camp_bio_fontes": "Fontes da biografia", "_camp_foto_id": "Foto"}


def _produtor(con, codigo: str):
    return con.execute("""SELECT a.* FROM fundo_agente fa JOIN agente a ON a.id=fa.agente_id WHERE fa.fundo_codigo=? AND fa.papel='produtor'
                          ORDER BY fa.inicio, a.id LIMIT 1""", (codigo,)).fetchone()


def meta_desejado(con, codigo: str) -> dict:
    """{campo do site: texto} do que o painel quer no site agora (só o que está preenchido)."""
    from .publicador import campos_hub_fundo
    meta, _ = campos_hub_fundo(con, codigo)
    out = {k: v for k, v in meta.items() if (v or "").strip()}
    a = _produtor(con, codigo)
    if a:
        if (a["historia"] or "").strip():
            out["_camp_bio"] = a["historia"].strip()
        if (a["fonte_historia"] or "").strip():
            out["_camp_bio_fontes"] = a["fonte_historia"].strip()
        r = con.execute("SELECT atualizado_em FROM agente_retrato WHERE agente_id=?", (a["id"],)).fetchone()
        if r:
            out["_camp_foto_id"] = f"retrato:{r[0]}"
    return out


def campos_hub_filtrados(con, codigo: str) -> dict:
    """Só os campos do hub (texto do fundo) que estão preenchidos."""
    from .publicador import campos_hub_fundo
    meta, _ = campos_hub_fundo(con, codigo)
    return {k: v for k, v in meta.items() if (v or "").strip()}


def rotulo(campo: str) -> str:
    from .publicador import HUB_CAMPOS
    return ROTULOS.get(campo) or next((r for k, r, _s in HUB_CAMPOS if k == campo), campo)


def divergencia(con, codigo: str) -> dict:
    """Mudanças do painel que o site ainda não recebeu. {enviado_em, pendente, mudancas:[{campo, rotulo, tipo: novo|mudou|saiu}]}"""
    agora = meta_desejado(con, codigo)
    r = con.execute("SELECT enviado_em, campos_json, ok FROM fundo_envio_site WHERE fundo_codigo=?", (codigo,)).fetchone()
    if not r:
        return {"enviado_em": None, "pendente": bool(agora), "mudancas": [{"campo": k, "rotulo": rotulo(k), "tipo": "novo"} for k in agora], "nunca_enviado": True}
    antes = json.loads(r["campos_json"] or "{}")
    mud = [{"campo": k, "rotulo": rotulo(k), "tipo": "novo" if k not in antes else "mudou"} for k in agora if antes.get(k) != agora[k]]
    mud += [{"campo": k, "rotulo": rotulo(k), "tipo": "saiu"} for k in antes if k not in agora]
    return {"enviado_em": r["enviado_em"], "pendente": bool(mud) or not r["ok"], "mudancas": mud, "nunca_enviado": False}


def _slugs_candidatos(con, codigo: str) -> list[str]:
    """Slugs possíveis da página do arquiteto: o do termo do fundo no site (é o que o plugin usa), o do nome do fundo e o do arquiteto."""
    from .rotas_projetos import _slug_publico
    out = []
    for (sl,) in con.execute("SELECT slug FROM wp_termo WHERE codigo_detectado=? AND slug IS NOT NULL AND slug<>''", (codigo,)):
        out.append(sl.lower())
    f = con.execute("SELECT titulo FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    if f and f["titulo"]:
        out.append(_slug_publico(f["titulo"]))
    a = _produtor(con, codigo)
    if a and a["forma_autorizada"]:
        out.append(_slug_publico(a["forma_autorizada"]))
    return [x for x in dict.fromkeys(out) if x]


def pagina_arquiteto(con, codigo: str) -> dict:
    """A página pública do arquiteto (a página-hub do fundo) no espelho do site: {existe, publica, url, status, id}."""
    a = _produtor(con, codigo)
    slugs = _slugs_candidatos(con, codigo)
    pag = None
    for slug in slugs:
        pag = con.execute("""SELECT id, url, status FROM wp_pagina WHERE url LIKE '%/acervo/arquitetos/%' AND (lower(slug)=? OR lower(slug) LIKE ?)
                             ORDER BY (status='publish') DESC, id DESC LIMIT 1""", (slug, slug + "-%")).fetchone()
        if pag:
            break
    base = {"sem_arquiteto": True} if not a else {}
    if not pag:
        return {**base, "existe": False, "publica": False, "url": None, "status": None, "id": None}
    return {**base, "existe": True, "publica": pag["status"] == "publish", "url": pag["url"], "status": pag["status"], "id": pag["id"]}


def _achar_no_site(con, wp, codigo: str) -> dict | None:
    """A página do arquiteto direto no site (para quando o espelho ainda não a tem, ex.: acabou de ser criada). Só aceita página sob /acervo/arquitetos/."""
    for slug in _slugs_candidatos(con, codigo):
        for pg in wp.pagina_por_slug(slug):
            link = str(pg.get("link") or "")
            if "/acervo/arquitetos/" in link:
                titulo = (pg.get("title") or {}).get("raw") or (pg.get("title") or {}).get("rendered") or ""
                con.execute("INSERT OR REPLACE INTO wp_pagina (id, titulo, slug, url, status, pai_id, codigo_detectado, json, visto_em) VALUES (?,?,?,?,?,?,?,?,datetime('now'))",
                            (pg["id"], titulo, pg.get("slug"), link, pg.get("status"), pg.get("parent"), codigo, json.dumps({"id": pg["id"], "link": link}, ensure_ascii=False)))
                return {"id": pg["id"], "url": link, "status": pg.get("status")}
    return None


def mudar_pagina_arquiteto(codigo: str, publicar: bool, ator: str, motivo: str | None = None) -> dict:
    """21/10 (Rafa: "muito confuso publicar um arquiteto"): o painel publica (ou tira do público) a página do arquiteto, sem passar pelo wp-admin.

    Publicar: cria/atualiza antes o fundo no site (termo, página, biografia, retrato) e então põe a página como publicada. Sem ela pública o site
    esconde TODOS os projetos do fundo, mesmo os publicados. Tirar: a página volta a rascunho (e os projetos do fundo somem do público junto).
    Devolve {ok, url, status, erro}; nunca levanta."""
    from . import publicador
    from .rotas_gestao import direitos_permitem_publicar
    out = {"ok": False, "url": None, "status": None, "erro": None}
    con = connect()
    con.isolation_level = None
    try:
        if publicar:
            msg = direitos_permitem_publicar(con, codigo)
            if msg:
                out["erro"], out["bloqueio"] = msg, "direitos"; return out
        con.close()
        if publicar:
            r = enviar_fundo(codigo, ator)
            if r.get("erros") and not r.get("ok"):
                out["aviso"] = "O site não recebeu tudo do fundo (texto, biografia ou retrato): " + "; ".join(r["erros"])[:300]
        con = connect(); con.isolation_level = None
        from . import wp as _wpmod      # o mesmo ponto que a publicação do projeto usa (os testes trocam o site por um falso aqui)
        wp = _wpmod.WP()
        pg = pagina_arquiteto(con, codigo)
        alvo = {"id": pg["id"], "url": pg["url"], "status": pg["status"]} if pg["existe"] else None
        if not alvo:
            alvo = _achar_no_site(con, wp, codigo)
        if not alvo:
            out["erro"] = ("O site ainda não criou a página deste arquiteto. Ela nasce quando o fundo vai ao site: espere um minuto e tente de novo."
                           if publicar else "Não achei a página do arquiteto no site.")
            out["bloqueio"] = "sem_pagina"
            return out
        novo = "publish" if publicar else "draft"
        if alvo["status"] != novo:
            j = wp.mudar_status_pagina(alvo["id"], novo)
            alvo["status"] = j.get("status") or novo
            alvo["url"] = j.get("link") or alvo["url"]
        con.execute("UPDATE wp_pagina SET status=?, url=COALESCE(?, url), visto_em=datetime('now') WHERE id=?", (alvo["status"], alvo["url"], alvo["id"]))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('fundo',?,?,?,?)",
                    (codigo, "site_arquiteto_publicado" if publicar else "site_arquiteto_tirado", ator,
                     json.dumps({"pagina": alvo["id"], "url": alvo["url"], "motivo": motivo}, ensure_ascii=False)))
        out.update(ok=alvo["status"] == novo, url=alvo["url"], status=alvo["status"], erro=None if alvo["status"] == novo else f"O site deixou a página como {alvo['status']}")
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:300]
        try:
            publicador._pendencia(con, "fundo", codigo, "pendente_pagina_arquiteto", out["erro"])
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass
    return out


def resumo_arquiteto(con, codigo: str) -> dict:
    """Uma frase e um botão: a página do arquiteto deste fundo está pública? o que falta? (fundo e arquiteto mostram o mesmo quadro)."""
    from .rotas_gestao import direitos_permitem_publicar
    pg = pagina_arquiteto(con, codigo)
    a = _produtor(con, codigo)
    pub = con.execute("SELECT COUNT(*) FROM projeto WHERE fundo_codigo=? AND status_site='no_ar' AND mesclado_em IS NULL AND descartado_em IS NULL", (codigo,)).fetchone()[0]
    direitos = direitos_permitem_publicar(con, codigo)
    falta = []
    if not a:
        falta.append("cadastrar o arquiteto titular do fundo")
    if a and not ((a["historia"] or "").strip() and (a["fonte_historia"] or "").strip()):
        falta.append("biografia com fonte")
    if a and not con.execute("SELECT 1 FROM agente_retrato WHERE agente_id=?", (a["id"],)).fetchone():
        falta.append("retrato")
    if pg["publica"]:
        estado = "publica" if pub else "publica_vazia"
    else:
        estado = "rascunho" if pg["existe"] else "nao_existe"
    return {"fundo": codigo, "arquiteto": a["forma_autorizada"] if a else None, "agente_id": a["id"] if a else None,
            "estado": estado, "url": pg["url"], "projetos_publicados": pub, "direitos": direitos,
            "pode_publicar": direitos is None and not pg["publica"], "falta_opcional": falta}


def estado(con, codigo: str) -> dict:
    f = con.execute("SELECT codigo, tainacan_term_id FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    return {"no_site": bool(f and f["tainacan_term_id"]), "termo": f["tainacan_term_id"] if f else None,
            "pagina": pagina_arquiteto(con, codigo), "divergencia": divergencia(con, codigo)}


def enviar_fundo(codigo: str, ator: str) -> dict:
    """Cria/atualiza o termo e o hub do fundo com tudo o que está preenchido (inclusive biografia, fontes e foto do titular). Nunca levanta (menos F000)."""
    from . import publicador
    out = {"ok": False, "passos": [], "erros": []}
    r = publicador.criar_fundo_no_site(codigo, ator)
    out["passos"].append("termo do fundo e do arquiteto")
    if r.get("erro"):
        out["erros"].append(r["erro"]); return out
    con = connect()
    try:
        f = con.execute("SELECT tainacan_term_id FROM fundo WHERE codigo=?", (codigo,)).fetchone()
        termo = f["tainacan_term_id"] if f else None
        hub = {k: v for k, v in campos_hub_filtrados(con, codigo).items()}
    finally:
        con.close()
    out["passos"].append("campos do hub (procedência, entrada, acesso...)")
    if termo and hub:
        try:
            publicador.WP().gravar_hub(termo, hub)       # só o preenchido: o site ignora vazio, então nada de texto à mão é sobrescrito
        except Exception as e:  # noqa: BLE001
            out["erros"].append(str(e)[:300])
            c2 = connect()
            try:
                publicador._pendencia(c2, "fundo", codigo, "pendente_descricao_no_site", str(e)[:300]); c2.commit()
            finally:
                c2.close()
    con = connect()
    try:
        a = _produtor(con, codigo)
        tem_retrato = bool(a and con.execute("SELECT 1 FROM agente_retrato WHERE agente_id=?", (a["id"],)).fetchone())
        meta = {}
        if a:
            if (a["historia"] or "").strip():
                meta["_camp_bio"] = a["historia"].strip()
            if (a["fonte_historia"] or "").strip():
                meta["_camp_bio_fontes"] = a["fonte_historia"].strip()
            if tem_retrato:
                meta["_camp_foto_id"] = "subir"
        aid = a["id"] if a else None
    finally:
        con.close()
    if meta and aid is not None:
        h = publicador.enviar_agente_ao_hub(aid, meta, ator)
        out["passos"].append("biografia, fontes e foto")
        if h.get("erro"):
            out["erros"].append(h["erro"])
    out["ok"] = not out["erros"]
    con = connect()
    try:
        con.execute("""INSERT INTO fundo_envio_site (fundo_codigo, enviado_por, campos_json, ok, erro) VALUES (?,?,?,?,?)
                       ON CONFLICT(fundo_codigo) DO UPDATE SET enviado_em=datetime('now'), enviado_por=excluded.enviado_por, campos_json=excluded.campos_json, ok=excluded.ok, erro=excluded.erro""",
                    (codigo, ator, json.dumps(meta_desejado(con, codigo), ensure_ascii=False), int(out["ok"]), "; ".join(out["erros"])[:300] or None))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('fundo',?,'site_fundo_enviado',?,?)",
                    (codigo, ator, json.dumps({"ok": out["ok"], "passos": out["passos"], "erros": out["erros"]}, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    return out
