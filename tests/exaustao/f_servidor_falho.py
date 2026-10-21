#!/usr/bin/env python3
"""O site FALSO (tests/servidor_wp_falso.py) com falhas armáveis, para o grupo F (CAMP-109 a 114, site e publicação).

Igual ao falso, mais:
- CAMP-111: se o arquivo F_FALHA_ARQ existir, a 4ª folha enviada ao site DEPOIS de armar volta com erro (o site respondendo 502 no meio)
  e a falha se desarma sozinha (apaga o arquivo). Sem o arquivo, nunca falha.
- CAMP-112: trocar a imagem de uma folha no site funciona (o anexo continua o mesmo), a não ser que exista F_FALHA_ARQ + "_imagem".
- CAMP-113: a capa vai ao site (só anota no histórico, como o real).
Uso (de dentro de backend/): F_FALHA_ARQ=/tmp/x/falhar ... python3 ../tests/exaustao/f_servidor_falho.py PORTA
"""
import os
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
falso = runpy.run_path(str(Path(__file__).resolve().parent.parent / "servidor_wp_falso.py"), run_name="wp_falso")   # aplica os substitutos (sem subir o servidor)

from app import publicador  # noqa: E402

ARQ = os.environ.get("F_FALHA_ARQ", "")
_conta = {"n": 0}
_folha_ok = publicador.criar_folha_no_site


_trava_conta = __import__("threading").Lock()   # 21/10: as folhas chegam em paralelo; a 4ª continua sendo UMA só


def folha_que_cai(codigo, ator, *a, **k):
    with _trava_conta:
        cair = False
        if ARQ and os.path.exists(ARQ):
            _conta["n"] += 1
            if _conta["n"] == 4:
                os.remove(ARQ)
                _conta["n"] = 0
                cair = True
    if cair:
        return {"item_id": None, "metadados": [], "imagem": None, "erro": "o site respondeu 502 (Bad Gateway)"}
    return _folha_ok(codigo, ator, *a, **k)


publicador.criar_folha_no_site = folha_que_cai


def girar_falso(codigo, giro, ajuste=None):
    if ARQ and os.path.exists(ARQ + "_imagem"):
        raise RuntimeError("o site respondeu 503 (Service Unavailable)")
    return {"media_id": 4242, "giro": giro}


def capa_falsa(codigo_projeto, ator, limpar=False):
    import json
    from app.db import connect
    con = connect()
    try:
        cap = con.execute("SELECT capa_item FROM projeto WHERE codigo=?", (codigo_projeto,)).fetchone()[0]
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'site_capa',?,?)", (codigo_projeto, ator, json.dumps({"folha": cap})))
        con.commit()
    finally:
        con.close()
    return {"enviado": True, "erro": None, "aguardando": False}


publicador.girar_imagem_no_site, publicador.capa_no_site = girar_falso, capa_falsa


# CAMP-124 (P3): "Enviar N alterações ao site" reenvia título e metadados de folhas já publicadas (publicador.atualizar_folha_no_site,
# que chama WP().patch_item e WP().definir_metadado). O site falso aceita e anota; com o arquivo F_FALHA_ARQ + "_texto", recusa.
from app import wp as _wp  # noqa: E402

_WPBase = _wp.WP


class WPComTextos(_WPBase):
    def _talvez_cair(self):
        if ARQ and os.path.exists(ARQ + "_texto"):
            raise RuntimeError("o site respondeu 503 (Service Unavailable)")

    def patch_item(self, cid, wid, **corpo):
        self._talvez_cair()
        return {"id": wid, **corpo}

    def definir_metadado(self, wid, mid, valor):
        self._talvez_cair()
        return {"item_id": wid, "metadado": mid, "valor": valor}


_wp.WP = publicador.WP = WPComTextos   # o publicador importou WP pelo nome

if __name__ == "__main__":
    import uvicorn
    from app.main import app
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8967
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")
