"""UX-44 · Folhas sintéticas para o recorte automático (geradas na hora com Pillow; nenhuma imagem real no repositório).
- planta(): papel claro com linhas de desenho num fundo de scanner lilás com listras verticais (como a Contex), em JPEG.
- vegetal: papel translúcido quase da cor do fundo.
- sem_fundo: o papel vai até a borda (nada a recortar)."""
import io
import random

from PIL import Image, ImageDraw

LILAS = (168, 158, 208)
PAPEL = (226, 222, 210)
VEGETAL = (182, 172, 214)


def fundo_contex(W, H, seed=1):
    rnd = random.Random(seed)
    linha = Image.new("RGB", (W, 1))
    for x in range(W):
        f = ((x // 7) % 2) * 10 - 5 + rnd.randint(-3, 3)
        linha.putpixel((x, 0), tuple(c + f for c in LILAS))
    return linha.resize((W, H))


def planta(W=3000, H=2000, caixa=(600, 650, 2400, 1300), papel=PAPEL, linhas=(70, 70, 80), seed=1, jpeg=True):
    """caixa = (l, t, r, b) do papel, inclusive. Devolve a imagem PIL (passada por JPEG q85, como a prévia do CAMP Vision)."""
    im = fundo_contex(W, H, seed)
    d = ImageDraw.Draw(im)
    d.rectangle(caixa, fill=papel)
    l, t, r, b = caixa
    rnd = random.Random(seed)
    for _ in range(60):
        x0, y0 = rnd.randint(l + 20, max(l + 21, r - 40)), rnd.randint(t + 20, max(t + 21, b - 40))
        d.line((x0, y0, min(r - 10, x0 + rnd.randint(20, 400)), y0), fill=linhas, width=2)
        d.line((x0, y0, x0, min(b - 10, y0 + rnd.randint(20, 300))), fill=linhas, width=1)
    d.rectangle((l + 15, t + 15, r - 15, b - 15), outline=linhas, width=3)
    if jpeg:
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=85); buf.seek(0)
        im = Image.open(buf).convert("RGB")
    return im


def vegetal(W=3000, H=2000):
    return planta(W, H, papel=VEGETAL, linhas=(150, 140, 190))


def sem_fundo(W=3000, H=2000):
    return planta(W, H, caixa=(0, 0, W - 1, H - 1))


def iou(a, b):
    l, t, r, bb = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, r - l) * max(0, bb - t)
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def caixa_px(rec, W, H):
    return (rec["x"] * W, rec["y"] * H, (rec["x"] + rec["w"]) * W, (rec["y"] + rec["h"]) * H)
