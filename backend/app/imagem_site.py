"""Qual arquivo sobe ao site para uma folha.

O CAMP Vision grava uma PRÉVIA para o site (~3000 px, JPEG sRGB, já girada/desespelhada) em ACERVOS_CAMP/_campvision/preview/<projeto>/<código>.jpg
e os caminhos que ele informa são RELATIVOS a ACERVOS_CAMP. Antes, o envio tratava arquivo_jpg como caminho local e uma folha vinda da revisão subia sem imagem.
Ordem: (1) a prévia do CAMP Vision; (2) o arquivo da folha, absoluto ou relativo à raiz dos prontos; (3) o valor como estava (legado).
Nunca sai de _campvision/preview (a prévia) nem da raiz dos prontos (o resto): o caminho vem de um pacote de fora.
"""
from __future__ import annotations

import json
from pathlib import Path


def raiz_prontos(con) -> Path | None:
    for chave in ("qnap.prontos_raiz", "qnap.raiz"):
        r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
        if r and r[0]:
            return Path(r[0])
    return None


def imagem_para_o_site(con, item) -> str | None:
    """`item` é uma linha com arquivo_jpg e pendencias. Devolve o caminho a subir, ou None se não há imagem."""
    raiz = raiz_prontos(con)
    try:
        previa = (json.loads(item["pendencias"] or "{}") or {}).get("previa") if item["pendencias"] else None
    except (ValueError, TypeError):
        previa = None
    if previa and raiz:
        base = (raiz / "_campvision" / "preview").resolve()
        alvo = (raiz / previa).resolve()
        if base in alvo.parents and alvo.suffix.lower() in (".jpg", ".jpeg") and alvo.is_file():
            return str(alvo)
    jpg = item["arquivo_jpg"]
    if not jpg or str(jpg).startswith("http"):
        return None
    c = Path(jpg)
    if c.is_absolute():
        return str(c)
    if raiz:
        base = raiz.resolve()
        alvo = (raiz / jpg).resolve()
        if base in alvo.parents and alvo.is_file():
            return str(alvo)
    return str(jpg)
