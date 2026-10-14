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


def espelho_efetivo(item) -> bool:
    """Espelhar a folha? A decisão de uma pessoa (item.espelho_manual 0/1) vale sobre o que o CAMP Vision apontou (item.espelhado)."""
    k = item.keys() if hasattr(item, "keys") else ()
    manual = item["espelho_manual"] if "espelho_manual" in k else None
    if manual is not None:
        return bool(manual)
    return bool(item["espelhado"]) if "espelhado" in k else False


def jpeg_girado(origem: Path | str, giro: int = 0, lado_max: int | None = None, espelhar: bool = False) -> Path:
    """O JPEG espelhado (esquerda-direita, se `espelhar`), depois girado `giro` graus no sentido horário (0, 90, 180, 270) e, se pedido,
    reduzido ao lado maior `lado_max`. Sem espelho, giro nem redução devolve o próprio arquivo."""
    origem = Path(origem)
    giro %= 360
    if giro == 0 and not lado_max and not espelhar:
        return origem
    st = origem.stat()
    chave = f"{origem}|{st.st_mtime_ns}|{st.st_size}|{giro}|{lado_max or 0}" + ("|espelho" if espelhar else "")
    alvo = pasta_cache() / (hashlib.sha1(chave.encode()).hexdigest() + ".jpg")
    if alvo.is_file():
        return alvo
    from PIL import Image
    with Image.open(origem) as im:
        if lado_max:
            im.draft("RGB", (lado_max, lado_max))          # JPEG: decodifica já reduzido (rápido e leve)
        im = im.convert("RGB")
        if espelhar:
            im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if giro:
            im = im.transpose({90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}[giro])
        if lado_max:
            im.thumbnail((lado_max, lado_max))
        tmp = alvo.with_name(f"{alvo.name}.{os.getpid()}.tmp")
        im.save(tmp, "JPEG", quality=82 if lado_max else 88, optimize=True)
        os.replace(tmp, alvo)
    return alvo
