"""Documentos (folhas) de uma pasta de lote no QNAP, agrupados por DOCUMENTO e não por arquivo.

Cada formato do mesmo documento pode ficar numa subpasta própria dentro da série (decisão de 08/10/2026):
    <projeto>/01 - Desenhos e pranchas/TIF/F026-P0006-1975-S01-D00001.tif
    <projeto>/01 - Desenhos e pranchas/JPG/F026-P0006-1975-S01-D00001.jpg
É UM documento (mesmo código, mesma série), com dois formatos. Contar arquivos contaria 2. A chave é (série, nome sem extensão), onde
a série é a primeira pasta abaixo da pasta do lote (vazia se o arquivo está direto nela). Funciona também sem subpasta de formato.
Lixeiras e pastas ocultas do QNAP (@Recycle, @eaDir, #recycle, .algo) são ignoradas. Leitura limitada por tempo (pasta no SMB).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

EXTS_IMAGEM = {".jpg", ".jpeg", ".tif", ".tiff", ".dng", ".png"}
EXTS_PREVIA = {".jpg", ".jpeg", ".png"}
IGNORAR_NA_RAIZ = {"catalogacao"}            # saídas do CAMP Vision (contatos.jpg, pacote, erros): não são documentos do projeto          # as que o navegador mostra e que o painel serve
_NOME_FORMATO = {"JPEG": "JPG", "TIFF": "TIF"}


def documentos_da_pasta(pasta: Path | str, prazo_s: float = 20.0, limite: int = 5000) -> dict:
    """{"documentos": [{codigo, serie, formatos[], previa|None}], "parcial": bool}, ordenado por série e código."""
    pasta = Path(pasta)
    fim = time.monotonic() + prazo_s
    docs: dict[tuple[str, str], dict] = {}
    parcial = False
    for raiz, dirs, arqs in os.walk(pasta):
        if time.monotonic() > fim:
            parcial = True
            break
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "@", "#")) and not (Path(raiz) == pasta and d.lower() in IGNORAR_NA_RAIZ))
        for nome in sorted(arqs):
            ext = Path(nome).suffix.lower()
            if ext not in EXTS_IMAGEM or nome.startswith("."):
                continue
            rel = (Path(raiz) / nome).relative_to(pasta)
            serie = rel.parts[0] if len(rel.parts) > 1 else ""
            stem = Path(nome).stem
            d = docs.setdefault((serie.lower(), stem.lower()), {"codigo": stem, "serie": serie, "formatos": [], "previa": None})
            fmt = ext.lstrip(".").upper()
            fmt = _NOME_FORMATO.get(fmt, fmt)
            if fmt not in d["formatos"]:
                d["formatos"].append(fmt)
            if ext in EXTS_PREVIA and (d["previa"] is None or ext in (".jpg", ".jpeg")):
                d["previa"] = rel.as_posix()
            if len(docs) >= limite:
                parcial = True
                break
        if parcial:
            break
    return {"documentos": sorted(docs.values(), key=lambda x: (x["serie"].lower(), x["codigo"].lower())), "parcial": parcial}


def contar_documentos(pasta: Path | str, prazo_s: float = 15.0) -> tuple[int, bool]:
    """(quantos documentos, leitura interrompida?)."""
    r = documentos_da_pasta(pasta, prazo_s)
    return len(r["documentos"]), r["parcial"]
