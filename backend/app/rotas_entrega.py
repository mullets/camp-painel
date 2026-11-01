"""Página PÚBLICA de download de um pedido entregue por e-mail (01/11/2026; ver entrega.py).

GET /entrega/<token>          lista os arquivos do pedido, com o tamanho e um botão para baixar cada um
GET /entrega/<token>/<n>      o arquivo n (TIFF/JPG), servido do QNAP ou da pasta do painel

Sem login: quem tem o link (que só existe no e-mail da pessoa) baixa até a data de validade. Link vencido ou cancelado mostra a
página dizendo isso, sem listar nada. Nunca entra no cache nem em buscador.
"""
from __future__ import annotations

import json
from html import escape

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

from . import entrega
from .db import connect

router = APIRouter(tags=["entrega"])

_SEM_CACHE = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"}

_CSS = """body{margin:0;font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f6f5f2;color:#1d1d1b}
main{max-width:760px;margin:0 auto;padding:32px 16px 48px}h1{font-size:22px;margin:0 0 4px}p{margin:8px 0}.sub{color:#5c5c58}
ul{list-style:none;padding:0;margin:20px 0;display:grid;gap:8px}li{background:#fff;border:1px solid #e3e1db;border-radius:8px;padding:12px 14px;
display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}.cod{font-family:ui-monospace,Menlo,monospace;font-size:14px}
small{color:#5c5c58}a.btn{background:#1d1d1b;color:#fff;text-decoration:none;padding:8px 14px;border-radius:6px;white-space:nowrap}
footer{margin-top:28px;font-size:14px;color:#5c5c58}"""


def _pagina(titulo: str, corpo: str, status: int = 200) -> HTMLResponse:
    html = (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{escape(titulo)} · CAMP</title><style>{_CSS}</style></head>'
            f'<body><main>{corpo}<footer>CAMP · Casa da Arquitetura Moderna Paulista · camp.arq.br</footer></main></body></html>')
    return HTMLResponse(html, status_code=status, headers=_SEM_CACHE)


@router.get("/entrega/{token}", include_in_schema=False)
def pagina(token: str) -> HTMLResponse:
    con = connect()
    try:
        r, motivo = entrega.achar(con, token)
        if motivo == "inexistente":
            return _pagina("Link não encontrado", "<h1>Link não encontrado</h1><p>Confira se o endereço foi copiado inteiro do e-mail.</p>", 404)
        if motivo:
            quando = "venceu" if motivo == "vencido" else "foi cancelado"
            return _pagina("Link encerrado", f"<h1>Este link {quando}</h1><p>Responda o e-mail da CAMP que a equipe manda um link novo.</p>", 410)
        arquivos = json.loads(r["arquivos"] or "[]")
        itens = "".join(
            f'<li><span><span class="cod">{escape(a["codigo"])}</span>{"<br>" + escape(a["titulo"]) if a.get("titulo") else ""}'
            f'<br><small>{escape(a["resolucao"])} · {escape(entrega._fmt_tamanho(a.get("tamanho")))}</small></span>'
            f'<a class="btn" href="/entrega/{escape(token)}/{int(a["n"])}" download>Baixar</a></li>' for a in arquivos)
        validade = entrega._data_br(r["expira_em"])
        corpo = (f'<h1>Material do pedido #{int(r["solicitacao_id"])}</h1>'
                 f'<p class="sub">{len(arquivos)} arquivo(s) do acervo da CAMP. O link vale até {escape(validade)}.</p>'
                 f'<ul>{itens}</ul><p>Ao publicar ou expor este material, cite a fonte: <b>Acervo CAMP (camp.arq.br)</b>.</p>')
        return _pagina(f"Pedido #{int(r['solicitacao_id'])}", corpo)
    finally:
        con.close()


@router.get("/entrega/{token}/{n}", include_in_schema=False)
def baixar(token: str, n: int) -> FileResponse:
    con = connect()
    try:
        alvo, nome = entrega.arquivo(con, token, n)
    finally:
        con.close()
    tipo = "image/tiff" if alvo.suffix.lower() in (".tif", ".tiff") else "image/jpeg"
    return FileResponse(alvo, media_type=tipo, filename=nome, headers=_SEM_CACHE)
