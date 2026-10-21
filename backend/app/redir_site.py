"""CAMP-014 · Enviar ao site os redirecionamentos (código antigo → novo).

A tabela `redirecionamento` é a fila: aplicado_no_site=0 = falta enviar. Quem muda o código (recodificar, mesclar, mover folha com registro no site,
migração de série) grava a linha com `registrar()` e dispara `enviar_pendentes()` em segundo plano; o coletor de 10 min repete o que falhou.
- Cadeias já resolvidas: A→B e depois B→C viram A→C e B→C (o site nunca recebe cadeia).
- O site recebe CAMINHOS (/acervo/projetos/<slug>/, /acervo/documentos/<slug>/): o painel usa o que o espelho do site conhece; para projeto sem página
  no espelho, `projeto.url_publica_confirmada`; sem URL, registra pendência (divergencia_site) e NÃO envia.
- Falha do site: tentativas/ultimo_erro na linha, nunca levanta, nunca desfaz o local."""
from __future__ import annotations

import logging
from urllib.parse import urlparse

LOTE = 400


def registrar(con, antigo: str, novo: str, entidade: str, motivo: str, ator: str) -> None:
    """Grava antigo→novo na fila (sem cadeia). Quem apontava para o antigo passa a apontar para o novo e volta para a fila."""
    if antigo == novo:
        return
    con.execute("UPDATE redirecionamento SET codigo_novo=?, aplicado_no_site=0, sem_site=0 WHERE codigo_novo=?", (novo, antigo))
    con.execute("""INSERT INTO redirecionamento (codigo_antigo, codigo_novo, entidade, motivo, criado_por) VALUES (?,?,?,?,?)
                   ON CONFLICT(codigo_antigo) DO UPDATE SET codigo_novo=excluded.codigo_novo, entidade=excluded.entidade, motivo=excluded.motivo,
                                                            criado_por=excluded.criado_por, criado_em=datetime('now'), aplicado_no_site=0, sem_site=0""", (antigo, novo, entidade, (motivo or "")[:300], ator))
    con.execute("DELETE FROM redirecionamento WHERE codigo_antigo=codigo_novo")


def _final(mapa: dict[str, str], cod: str) -> str:
    visto = {cod}
    while cod in mapa and mapa[cod] not in visto and len(visto) < 30:
        cod = mapa[cod]; visto.add(cod)
    return cod


def _caminho(url: str | None) -> str | None:
    if not url:
        return None
    p = urlparse(url)
    return (p.path or "/") if (p.path and p.path != "/") else None


def _url_conhecida(con, entidade: str, codigo: str) -> str | None:
    """Caminho público que o espelho do site conhece para este código (projeto ou folha), ou None."""
    cod = codigo.upper()
    if entidade == "projeto":
        r = con.execute("""SELECT url FROM wp_pagina WHERE (upper(codigo_detectado)=? OR lower(slug) LIKE ?) AND url LIKE '%/acervo/projetos/%'
                           ORDER BY (status='publish') DESC, id DESC LIMIT 1""", (cod, cod.lower() + "-%")).fetchone()
        if r and r[0]:
            return _caminho(r[0])
        r = con.execute("""SELECT url FROM wp_item WHERE upper(codigo_detectado)=? AND url LIKE '%/acervo/projetos/%' ORDER BY (status='publish') DESC, id DESC LIMIT 1""", (cod,)).fetchone()
        if r and r[0]:
            return _caminho(r[0])
        return None
    r = con.execute("""SELECT url FROM wp_item WHERE upper(codigo_detectado)=? AND url LIKE '%/acervo/documentos/%' ORDER BY (status='publish') DESC, id DESC LIMIT 1""", (cod,)).fetchone()
    return _caminho(r[0]) if r and r[0] else None


def resolver_urls(con, entidade: str, antigo: str, novo: str) -> tuple[str | None, str | None]:
    """(caminho antigo, caminho novo). Projeto: espelho do site; senão url_publica_confirmada (conforme tenha o código antigo ou o novo); o novo, na falta,
    é montado como a rota pública presumida (/acervo/projetos/<codigo>-<slug>/). Folha: só o que o espelho conhece."""
    ua, un = _url_conhecida(con, entidade, antigo), _url_conhecida(con, entidade, novo)
    if not ua:   # recodificado: o espelho já só tem o código novo; o endereço antigo foi guardado na hora da troca
        g = con.execute("SELECT url_antiga FROM redirecionamento WHERE codigo_antigo=?", (antigo,)).fetchone()
        ua = (g["url_antiga"] if g else None) or None
    if entidade == "projeto":
        p = con.execute("SELECT titulo, cidade, url_publica_confirmada FROM projeto WHERE codigo=?", (novo,)).fetchone()
        if p and p["url_publica_confirmada"]:
            cam = _caminho(p["url_publica_confirmada"])
            if cam and antigo.lower() in cam.lower() and not ua:
                ua = cam
            elif cam and novo.lower() in cam.lower() and not un:
                un = cam
        if p and not un:
            from .rotas_projetos import _url_publica_projeto
            un = _caminho(_url_publica_projeto(novo, p["titulo"], p["cidade"]))
    return ua, un


def pendentes(con) -> list[dict]:
    mapa = {r["codigo_antigo"]: r["codigo_novo"] for r in con.execute("SELECT codigo_antigo, codigo_novo FROM redirecionamento")}
    out = []
    for r in con.execute("SELECT codigo_antigo, codigo_novo, entidade FROM redirecionamento WHERE aplicado_no_site=0 AND sem_site=0 ORDER BY criado_em, rowid"):
        fim = _final(mapa, r["codigo_antigo"])
        if fim != r["codigo_antigo"]:
            out.append({"antigo": r["codigo_antigo"], "novo": fim, "entidade": r["entidade"]})
    return out


def _tem_presenca_no_site(con, entidade: str, antigo: str, novo: str) -> bool:
    """Havia algo deste código no site? (registro no espelho, ligação do painel com o site ou endereço confirmado). Sem isso não há o que redirecionar."""
    if _url_conhecida(con, entidade, antigo) or _url_conhecida(con, entidade, novo):
        return True
    if entidade == "projeto":
        r = con.execute("SELECT tainacan_item_id, wp_page_id, url_publica_confirmada FROM projeto WHERE codigo=?", (novo,)).fetchone()
        return bool(r and (r["tainacan_item_id"] or r["wp_page_id"] or r["url_publica_confirmada"]))
    if con.execute("SELECT 1 FROM wp_item WHERE upper(codigo_detectado)=? LIMIT 1", (antigo.upper(),)).fetchone():
        return True
    r = con.execute("SELECT tainacan_item_id FROM item WHERE codigo=?", (novo,)).fetchone()
    return bool(r and r[0])


def enviar_pendentes(con=None, wp=None) -> dict:
    """Manda ao site o que falta. Devolve {pendentes, enviados, sem_url, falhas, erro}. NUNCA levanta."""
    from .db import connect
    fechar = con is None
    con = con or connect()
    out = {"pendentes": 0, "enviados": 0, "sem_url": 0, "falhas": 0, "erro": None}
    try:
        itens = pendentes(con)
        out["pendentes"] = len(itens)
        if not itens:
            return out
        prontos = []
        for it in itens:
            if not _tem_presenca_no_site(con, it["entidade"], it["antigo"], it["novo"]):
                con.execute("UPDATE redirecionamento SET sem_site=1 WHERE codigo_antigo=?", (it["antigo"],))   # nunca esteve no site: nada a enviar (continua no mapa público do painel)
                out["pendentes"] -= 1
                continue
            ua, un = resolver_urls(con, it["entidade"], it["antigo"], it["novo"])
            if not ua or not un:
                out["sem_url"] += 1
                from .publicador import _pendencia
                _pendencia(con, it["entidade"], it["antigo"], "pendente_redirecionamento",
                           f"Redirecionamento {it['antigo']} → {it['novo']} não enviado ao site: não conheço o endereço público {'antigo' if not ua else 'novo'}. Sincronize com o site ou confirme a página pública do projeto.")
                continue
            if ua == un:   # o endereço não mudou (só o código): redirecionar para si mesmo faria laço no site; nada a enviar
                con.execute("UPDATE redirecionamento SET aplicado_no_site=1, aplicado_em=datetime('now'), ultimo_erro='endereço não mudou: nada a redirecionar' WHERE codigo_antigo=?", (it["antigo"],))
                out["pendentes"] -= 1
                continue
            prontos.append({**it, "url_antiga": ua, "url_nova": un})
        con.commit()
        if not prontos:
            return out
        try:
            wp = wp or __import__("app.wp", fromlist=["WP"]).WP()
            for k in range(0, len(prontos), LOTE):
                parte = prontos[k:k + LOTE]
                resp = wp.enviar_redirecionamentos([{"antigo": p["url_antiga"], "novo": p["url_nova"], "tipo": 301, "codigo_antigo": p["antigo"], "codigo_novo": p["novo"], "entidade": p["entidade"]} for p in parte])
                com_erro = {int(e.get("indice")): str(e.get("motivo") or "")[:200] for e in (resp.get("erros") or []) if isinstance(e, dict) and str(e.get("indice", "")).isdigit()}
                for i, p in enumerate(parte):
                    if i in com_erro:
                        out["falhas"] += 1
                        con.execute("UPDATE redirecionamento SET tentativas=tentativas+1, ultimo_erro=?, ultima_tentativa=datetime('now') WHERE codigo_antigo=?", (com_erro[i], p["antigo"]))
                    else:
                        out["enviados"] += 1
                        con.execute("UPDATE redirecionamento SET aplicado_no_site=1, aplicado_em=datetime('now'), tentativas=tentativas+1, ultimo_erro=NULL, ultima_tentativa=datetime('now') WHERE codigo_antigo=?", (p["antigo"],))
                con.commit()
        except Exception as e:  # noqa: BLE001
            out["erro"] = str(e)[:200]
            out["falhas"] += len(prontos) - out["enviados"] - out["falhas"]
            for p in prontos:
                con.execute("UPDATE redirecionamento SET tentativas=tentativas+1, ultimo_erro=?, ultima_tentativa=datetime('now') WHERE codigo_antigo=? AND aplicado_no_site=0", (out["erro"], p["antigo"]))
            con.commit()
            try:
                from .log_tecnico import registrar as _log
                _log(logging.WARNING, "redirecionamentos_site", "Não consegui enviar redirecionamentos ao site", erro=out["erro"][:160], pendentes=len(prontos))
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        out["erro"] = out["erro"] or str(e)[:200]
    finally:
        if fechar:
            con.close()
    return out


def status(con) -> dict:
    q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    return {"total": q("SELECT COUNT(*) FROM redirecionamento"), "aplicados_no_site": q("SELECT COUNT(*) FROM redirecionamento WHERE aplicado_no_site=1"),
            "pendentes": q("SELECT COUNT(*) FROM redirecionamento WHERE aplicado_no_site=0 AND sem_site=0"),
            "sem_registro_no_site": q("SELECT COUNT(*) FROM redirecionamento WHERE sem_site=1"),
            "com_erro": q("SELECT COUNT(*) FROM redirecionamento WHERE aplicado_no_site=0 AND sem_site=0 AND ultimo_erro IS NOT NULL")}
