"""Girar e reduzir imagens (as prévias das folhas), com cache em disco. Precisa do Pillow; sem ele só se serve o original.

Cache por (arquivo, data, tamanho, giro, lado máximo): girar de novo ou trocar o arquivo gera outra entrada. Escrita atômica (arquivo temporário + rename).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .config import settings


def disponivel() -> bool:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def pasta_cache() -> Path:
    p = Path(os.environ.get("CAMP_CACHE_DIR") or Path(settings.CAMP_DB_PATH).parent / "cache_previas")
    p.mkdir(parents=True, exist_ok=True)
    return p


def jpeg_girado(origem: Path | str, giro: int = 0, lado_max: int | None = None) -> Path:
    """O JPEG girado `giro` graus no sentido horário (0, 90, 180, 270) e, se pedido, reduzido ao lado maior `lado_max`. Sem giro nem redução devolve o próprio arquivo."""
    origem = Path(origem)
    giro %= 360
    if giro == 0 and not lado_max:
        return origem
    st = origem.stat()
    alvo = pasta_cache() / (hashlib.sha1(f"{origem}|{st.st_mtime_ns}|{st.st_size}|{giro}|{lado_max or 0}".encode()).hexdigest() + ".jpg")
    if alvo.is_file():
        return alvo
    from PIL import Image
    with Image.open(origem) as im:
        if lado_max:
            im.draft("RGB", (lado_max, lado_max))          # JPEG: decodifica já reduzido (rápido e leve)
        im = im.convert("RGB")
        if giro:
            im = im.transpose({90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}[giro])
        if lado_max:
            im.thumbnail((lado_max, lado_max))
        tmp = alvo.with_name(f"{alvo.name}.{os.getpid()}.tmp")
        im.save(tmp, "JPEG", quality=82 if lado_max else 88, optimize=True)
        os.replace(tmp, alvo)
    return alvo
