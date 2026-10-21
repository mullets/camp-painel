#!/usr/bin/env python3
"""Sobe o painel com um WordPress FALSO, para testar a publicação no navegador sem falar com o site de verdade.

Os substitutos são os mesmos dos testes de backend (tests/teste_backend.py): criar o dossiê e as folhas só grava no
espelho local (wp_item) e mudar o status só anota. A página pública do projeto entra no espelho de páginas (wp_pagina)
com um endereço em site-falso.invalid, como a sincronização faria com o endereço real, e a conferência do endereço no
site (pagina_publica.confirmar) nunca sai da máquina.

Uso (de dentro de backend/, com banco PRÓPRIO e porta própria, nunca a 8765 compartilhada):
  CAMP_DB_PATH=/tmp/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 ../tests/servidor_wp_falso.py 8782
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import uvicorn  # noqa: E402

from app import pagina_publica, publicador, wp as _wp  # noqa: E402
from app.db import connect  # noqa: E402
from app.main import app  # noqa: E402
from app.rotas_projetos import _url_publica_projeto  # noqa: E402

SITE_FALSO = "http://site-falso.invalid"
_seq = {"n": 0}
import threading as _th  # noqa: E402
_TRAVA = _th.RLock()   # 21/10: o painel manda várias folhas ao mesmo tempo; o site de verdade dá ids únicos, este falso também tem de dar


def _novo_id(con) -> int:
    _seq["n"] += 1
    return max(900000, con.execute("SELECT COALESCE(MAX(id),0) FROM wp_item").fetchone()[0]) + _seq["n"]


def dossie_falso(codigo, ator, *a, **k):
    with _TRAVA:
        con = connect()
        try:
            p = con.execute("SELECT titulo, cidade, fundo_codigo FROM projeto WHERE codigo=?", (codigo,)).fetchone()
            wid = _novo_id(con)
            con.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,codigo_detectado,projeto_detectado,fundo_detectado) VALUES (?,8007,'draft',?,?,?,?)",
                        (wid, p["titulo"], codigo, codigo, p["fundo_codigo"]))
            con.execute("UPDATE projeto SET tainacan_item_id=? WHERE codigo=?", (wid, codigo))
            url = _url_publica_projeto(codigo, p["titulo"], p["cidade"]).replace("https://camp.arq.br", SITE_FALSO)
            con.execute("INSERT OR REPLACE INTO wp_pagina (id,titulo,slug,url,status,codigo_detectado,json) VALUES (?,?,?,?, 'draft', ?, ?)",
                        (wid, p["titulo"], url.rstrip("/").rsplit("/", 1)[-1], url, codigo, json.dumps({"item": wid})))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'site_dossie_criado',?,?)",
                        (codigo, ator, json.dumps({"item_id": wid, "metadados": ["Título", "Ano"], "erro": None})))
            con.commit()
            return {"item_id": wid, "metadados": [], "erro": None}
        finally:
            con.close()


def folha_falsa(codigo, ator, enviar_imagem=True, *a, **k):
    with _TRAVA:
        con = connect()
        try:
            wid = _novo_id(con)
            con.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,codigo_detectado,projeto_detectado) VALUES (?,8013,'draft','folha',?,?)", (wid, codigo, codigo[:10]))
            con.execute("UPDATE item SET tainacan_item_id=?, status_site='rascunho' WHERE codigo=?", (wid, codigo))
            con.commit()
            return {"item_id": wid, "metadados": [], "imagem": None, "erro": None}
        finally:
            con.close()


class WPFalso:
    def __init__(self, *a, **k):
        pass

    def atualizar_status_item(self, cid, wid, alvo):
        con = connect()
        try:
            con.execute("UPDATE wp_pagina SET status=? WHERE id=?", (alvo, wid))   # a página do projeto passa a abrir para todos
            con.commit()
        finally:
            con.close()


publicador.criar_dossie_no_site, publicador.criar_folha_no_site, _wp.WP = dossie_falso, folha_falsa, WPFalso
pagina_publica.confirmar = lambda codigo, palpite: {"url": None, "como": None}

if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8782
    if porta == 8765:
        sys.exit("a porta 8765 é compartilhada: use outra (8780-8789)")
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")
