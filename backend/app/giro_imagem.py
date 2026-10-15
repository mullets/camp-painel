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


LADO_PUBLICO = 1920       # CAMP-048: nada acima disso vai ao site (nem o TIF, nem a prévia de ~3000 px)
QUALIDADE_PUBLICA = 85


def lado_real(caminho: Path | str) -> int | None:
    """Lado maior da imagem em px (só lê o cabeçalho); None se não der para ler."""
    try:
        from PIL import Image
        with Image.open(caminho) as im:
            return max(im.size)
    except Exception:  # noqa: BLE001
        return None


def derivado_publico(origem: Path | str, giro: int = 0, lado_max: int = LADO_PUBLICO, espelhar: bool = False) -> Path:
    """CAMP-048 · O derivado que vai ao SITE: JPEG q85, sRGB, lado maior <= lado_max (padrão 1920), a partir da prévia do CAMP Vision (já girada/desespelhada),
    com o giro/espelho que a pessoa pediu por cima. Cache em disco por arquivo+data+tamanho+giro+espelho+lado; escrita atômica. Sempre reprocessa
    (mesmo a prévia pequena), para o que sobe ter sempre o mesmo formato. Precisa do Pillow."""
    origem = Path(origem)
    lado_max = min(int(lado_max or LADO_PUBLICO), LADO_PUBLICO)
    giro %= 360
    st = origem.stat()
    chave = f"pub|{origem}|{st.st_mtime_ns}|{st.st_size}|{giro}|{lado_max}|q{QUALIDADE_PUBLICA}" + ("|espelho" if espelhar else "")
    alvo = pasta_cache() / ("pub-" + hashlib.sha1(chave.encode()).hexdigest() + ".jpg")
    if alvo.is_file():
        return alvo
    from PIL import Image
    with Image.open(origem) as im:
        im.draft("RGB", (lado_max, lado_max))
        perfil = im.info.get("icc_profile")
        im = im.convert("RGB") if not perfil else im
        if perfil:                                     # perfil de cor embutido (AdobeRGB, ProPhoto...): converte para sRGB de verdade
            try:
                import io
                from PIL import ImageCms
                im = ImageCms.profileToProfile(im.convert("RGB") if im.mode not in ("RGB", "CMYK") else im, ImageCms.ImageCmsProfile(io.BytesIO(perfil)),
                                               ImageCms.createProfile("sRGB"), outputMode="RGB")
            except Exception:  # noqa: BLE001  (perfil quebrado: segue como RGB; sai sem perfil, ou seja, lido como sRGB)
                im = im.convert("RGB")
        if espelhar:
            im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if giro:
            im = im.transpose({90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}[giro])
        im.thumbnail((lado_max, lado_max), Image.Resampling.LANCZOS)
        tmp = alvo.with_name(f"{alvo.name}.{os.getpid()}.tmp")
        im.save(tmp, "JPEG", quality=QUALIDADE_PUBLICA, optimize=True)          # sem EXIF e sem perfil: a imagem já está em sRGB
        os.replace(tmp, alvo)
    return alvo


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
