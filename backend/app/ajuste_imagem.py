"""Recorte e alinhamento manual da folha (pedido de 19/10: "às vezes está vindo bem ruim").

O que se guarda na folha (a FONTE, permite desfazer):
- item.recorte: JSON {"x","y","w","h"} em frações (0–1) da imagem JÁ espelhada/girada (giro de 90°) e endireitada;
- item.alinhamento: ângulo fino em graus, de -10 a +10 (passo 0,1), positivo = sentido horário (o mesmo do CSS rotate);
- item.imagem_corrigida: o JPG corrigido que o painel gerou ao aplicar (caminho relativo à pasta de imagens corrigidas).

Ordem de aplicação (a mesma da tela): espelho → giro de 90° → ângulo fino (em torno do centro, sem aumentar a tela; o que sobra
nos cantos fica branco) → recorte.

Decisão de 19/10 (Rafa): ao aplicar, o painel gera DE VERDADE um JPG corrigido (alta qualidade) e ele passa a ser A imagem da folha
(prévia, miniatura, pedidos em JPG e o envio ao site). O TIF e os arquivos do CAMP Vision NUNCA mudam: o painel não grava na pasta
final do QNAP (docs/campvision.md, "mão única"); o JPG corrigido fica no diretório de dados do painel (ao lado do banco), em
`imagens_corrigidas/<projeto>/<código>-<marca>.jpg`. A marca muda com os parâmetros e com o arquivo de origem, então se o CAMP Vision
regravar a prévia, a versão corrigida é refeita. Arquivo sumido (disco novo, restauração do banco): é refeito a partir dos parâmetros.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .config import settings

ANGULO_MAX = 10.0
LADO_MIN = 0.05          # o recorte não pode ficar menor que 5% da largura/altura
QUALIDADE = 92


def pasta() -> Path:
    p = Path(os.environ.get("CAMP_IMAGENS_CORRIGIDAS_DIR") or Path(settings.CAMP_DB_PATH).parent / "imagens_corrigidas")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _num(v, nome):
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{nome} precisa ser um número")
    if f != f or f in (float("inf"), float("-inf")):
        raise ValueError(f"{nome} precisa ser um número")
    return f


def normalizar(recorte, angulo) -> tuple[dict | None, float]:
    """Valida e arredonda. Recorte inteiro (0,0,1,1) vira None. Levanta ValueError com frase em português."""
    a = round(_num(angulo or 0, "O ângulo"), 1)
    if abs(a) > ANGULO_MAX + 1e-9:
        raise ValueError(f"O ângulo de alinhamento vai de -{ANGULO_MAX:g}° a +{ANGULO_MAX:g}°")
    if a == 0:
        a = 0.0
    if not recorte:
        return None, a
    if not isinstance(recorte, dict):
        raise ValueError("Recorte inválido")
    x, y, w, h = (round(_num(recorte.get(k), f"O recorte ({k})"), 4) for k in ("x", "y", "w", "h"))
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 1.0001 or y + h > 1.0001:
        raise ValueError("O recorte tem de ficar dentro da imagem")
    if w < LADO_MIN or h < LADO_MIN:
        raise ValueError("O recorte ficou pequeno demais (mínimo 5% da largura e da altura)")
    w, h = min(w, 1 - x), min(h, 1 - y)
    if x <= 0.0005 and y <= 0.0005 and w >= 0.9995 and h >= 0.9995:
        return None, a
    return {"x": x, "y": y, "w": round(w, 4), "h": round(h, 4)}, a


def ler(item) -> tuple[dict | None, float]:
    """(recorte, ângulo) gravados na folha; tolera linha sem as colunas (banco antigo / SELECT sem elas)."""
    k = item.keys() if hasattr(item, "keys") else ()
    rec = None
    if "recorte" in k and item["recorte"]:
        try:
            rec = json.loads(item["recorte"])
        except (ValueError, TypeError):
            rec = None
    ang = float(item["alinhamento"] or 0) if "alinhamento" in k else 0.0
    try:
        return normalizar(rec, ang)
    except ValueError:
        return None, 0.0


def tem_ajuste(rec, ang) -> bool:
    return bool(rec) or bool(ang)


def para_gravar(rec) -> str | None:
    return json.dumps(rec, sort_keys=True) if rec else None


def depois_do_giro(rec, ang, graus: int):
    """A folha girou `graus` (horário) DEPOIS do recorte: a caixa gira junto (o ângulo fino não muda: rotações em torno do centro comutam)."""
    graus %= 360
    if not rec or not graus:
        return rec, ang
    x, y, w, h = rec["x"], rec["y"], rec["w"], rec["h"]
    if graus == 90:
        n = {"x": 1 - y - h, "y": x, "w": h, "h": w}
    elif graus == 180:
        n = {"x": 1 - x - w, "y": 1 - y - h, "w": w, "h": h}
    else:
        n = {"x": y, "y": 1 - x - w, "w": h, "h": w}
    return {k: round(max(0.0, v), 4) for k, v in n.items()}, ang


def depois_do_espelho(rec, ang):
    """A folha foi espelhada (esquerda-direita, o que a pessoa vê): a caixa espelha e o ângulo troca de sinal."""
    if rec:
        rec = {**rec, "x": round(max(0.0, 1 - rec["x"] - rec["w"]), 4)}
    return rec, (-ang if ang else 0.0)


def aplicar(im, ang: float, rec):
    """Ângulo fino (horário, em torno do centro, mesma tela, cantos brancos) e recorte, numa imagem PIL já espelhada/girada."""
    from PIL import Image
    if ang:
        fundo = 255 if im.mode == "L" else (255, 255, 255)
        im = im.rotate(-ang, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=fundo)
    if rec:
        W, H = im.size
        l, t = round(rec["x"] * W), round(rec["y"] * H)
        r, b = min(W, round((rec["x"] + rec["w"]) * W)), min(H, round((rec["y"] + rec["h"]) * H))
        im = im.crop((l, t, max(r, l + 1), max(b, t + 1)))
    return im


def _orientar(im, giro: int, espelhar: bool):
    from PIL import Image
    if espelhar:
        im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if giro % 360:
        im = im.transpose({90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}[giro % 360])
    return im


def _rel(codigo: str, origem: Path, giro: int, espelhar: bool, ang: float, rec) -> str:
    st = origem.stat()
    chave = f"{origem}|{st.st_mtime_ns}|{st.st_size}|{giro % 360}|{int(bool(espelhar))}|{ang}|{para_gravar(rec)}|q{QUALIDADE}"
    proj = codigo[:10] if len(codigo) >= 10 else "outros"
    return f"{proj}/{codigo}-{hashlib.sha1(chave.encode()).hexdigest()[:12]}.jpg"


def garantir(codigo: str, origem: Path | str, giro: int, espelhar: bool, ang: float, rec) -> tuple[Path, str]:
    """O JPG corrigido (gera se ainda não existe para estes parâmetros e esta origem). Devolve (caminho, caminho relativo à pasta).
    Alta qualidade: tamanho da origem (a prévia do CAMP Vision, ~3000 px), JPEG q92, sRGB. Escrita atômica."""
    origem = Path(origem)
    rel = _rel(codigo, origem, giro, espelhar, ang, rec)
    alvo = pasta() / rel
    if alvo.is_file():
        return alvo, rel
    alvo.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    with Image.open(origem) as im0:
        perfil = im0.info.get("icc_profile")
        im = im0
        if perfil:
            try:
                import io
                from PIL import ImageCms
                im = ImageCms.profileToProfile(im0.convert("RGB") if im0.mode not in ("RGB", "CMYK") else im0, ImageCms.ImageCmsProfile(io.BytesIO(perfil)),
                                               ImageCms.createProfile("sRGB"), outputMode="RGB")
            except Exception:  # noqa: BLE001  (perfil quebrado: segue como RGB)
                im = im0.convert("RGB")
        else:
            im = im0.convert("RGB")
        im = aplicar(_orientar(im, giro, espelhar), ang, rec)
        tmp = alvo.with_name(f"{alvo.name}.{os.getpid()}.tmp")
        im.save(tmp, "JPEG", quality=QUALIDADE, optimize=True, subsampling=0)
        os.replace(tmp, alvo)
    return alvo, rel


def caminho_gravado(rel: str | None) -> Path | None:
    """O arquivo registrado na folha (item.imagem_corrigida), só se estiver DENTRO da pasta de imagens corrigidas."""
    if not rel:
        return None
    base = pasta().resolve()
    alvo = (base / str(rel)).resolve()
    return alvo if base in alvo.parents and alvo.is_file() else None


def origem_da_folha(raiz: Path, item) -> Path | None:
    """A imagem que a pessoa vê na revisão (antes do ajuste): a prévia do CAMP Vision (só de dentro de _campvision/preview);
    senão o JPG da folha no QNAP (só de dentro da raiz dos prontos). A mesma regra da rota da prévia."""
    k = item.keys() if hasattr(item, "keys") else ()
    codigo = item["codigo"] if "codigo" in k else None
    try:
        rel = (json.loads(item["pendencias"] or "{}") or {}).get("previa") or ""
    except (ValueError, TypeError):
        rel = ""
    if rel and rel != "@jpg":
        try:
            base = (raiz / "_campvision" / "preview").resolve()
            cand = (raiz / rel).resolve()
            if base in cand.parents and cand.suffix.lower() in (".jpg", ".jpeg") and (codigo is None or cand.stem == codigo) and cand.is_file():
                return cand
        except OSError:
            pass
    jpg = item["arquivo_jpg"] if "arquivo_jpg" in k else None
    if not jpg or str(jpg).startswith("http"):
        return None
    try:
        c = Path(str(jpg))
        alvo = c.resolve() if c.is_absolute() else (raiz / str(jpg)).resolve()
        if raiz.resolve() in alvo.parents and alvo.suffix.lower() in (".jpg", ".jpeg") and alvo.is_file():
            return alvo
    except OSError:
        return None
    return None


def sugerir_angulo(origem: Path | str, giro: int = 0, espelhar: bool = False) -> float:
    """"Endireitar automaticamente": o ângulo (−10 a +10, passo 0,1) que deixa as linhas da folha mais retas.
    Perfil de projeção das bordas (só Pillow): girando a imagem das bordas, as linhas horizontais/verticais alinhadas concentram
    o traço em poucas linhas/colunas, e a variância dos perfis sobe. Busca grossa (0,5°) e depois fina (0,1°)."""
    from PIL import Image, ImageFilter, ImageOps, ImageStat
    with Image.open(origem) as im0:
        im0.draft("L", (700, 700))
        im = _orientar(im0.convert("L"), giro, espelhar)
    im.thumbnail((600, 600))
    bordas = ImageOps.invert(im).filter(ImageFilter.FIND_EDGES) if ImageStat.Stat(im).mean[0] > 127 else im.filter(ImageFilter.FIND_EDGES)
    bordas = bordas.point(lambda v: 255 if v > 40 else 0)
    W, H = bordas.size
    m = int(min(W, H) * 0.02)               # descarta a moldura de 2% (a borda do papel/scanner engana)
    bordas = bordas.crop((m, m, W - m, H - m))
    W, H = bordas.size

    def nota(a: float) -> float:
        r = bordas.rotate(-a, resample=Image.Resampling.BILINEAR, expand=False, fillcolor=0)
        return ImageStat.Stat(r.resize((1, H), Image.Resampling.BOX)).var[0] + ImageStat.Stat(r.resize((W, 1), Image.Resampling.BOX)).var[0]

    melhor = max((x / 2 for x in range(-20, 21)), key=lambda a: (nota(a), -abs(a)))
    fino = [round(melhor + d / 10, 1) for d in range(-5, 6) if abs(melhor + d / 10) <= ANGULO_MAX + 1e-9]
    a = max(fino, key=lambda x: (nota(x), -abs(x)))
    return 0.0 if a == 0 else round(a, 1)
