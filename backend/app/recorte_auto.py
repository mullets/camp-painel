"""UX-44 · Recorte automático na borda do papel e ajuste de branco/contraste, SÓ nas imagens derivadas (pública e "como vai ao site").

Pedido do Rafael (print do site, F009-P0015, "Corte"): "a qualidade das digitalizações de plantas está péssima". A planta ocupava só uma faixa
do meio da imagem; o resto era o FUNDO DO SCANNER (lilás com listras verticais da Contex). Como a imagem pública tem no máximo 1.920 px
(regra fixa do contrato com o site, não muda), o desenho chegava com ~1.100 px úteis, e com o papel acinzentado/lavado.

O que este módulo faz (só Pillow; o painel não depende de numpy/OpenCV):
1) `detectar(im)`: numa cópia reduzida (lado maior 1.500 px), estima a cor do fundo do scanner pelas bordas externas, marca o que difere
   do fundo (papel, vegetal, cópia heliográfica), acha o maior bloco por projeções (colunas → linhas → colunas) e devolve o retângulo
   envolvente com 1% de margem, em FRAÇÕES (0–1) — o MESMO formato do recorte manual (item.recorte), no mesmo referencial (imagem já
   espelhada/girada e endireitada). Confiança baixa (área < 10%, retângulo que muda com o limiar, pouco contraste fundo × papel, bloco
   ralo — típico do papel vegetal) = "incerto": NÃO recorta e a conferência mostra o selo "recorte automático incerto".
   Papel até a borda (as bordas já são papel) ou retângulo > 97% da imagem = "sem_fundo": nada a recortar.
2) `ajustar_cor(im)`: níveis pelo papel (o papel vira quase branco, 248, balanço de branco por canal) e ponto preto suave (metade do
   traço mais escuro; o ganho é limitado a 2,2×), para não "estourar" as linhas finas. Papel escuro (cópia azul/blueprint) não mexe.

Regras: o TIF e a prévia do CAMP Vision NUNCA mudam (isto só roda ao gerar o derivado). Recorte manual sempre vence. A pessoa pode recusar
o automático na conferência ("Usar recorte inteiro (sem recorte)", item.sem_recorte_auto = 1).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

VERSAO = "v2"            # v2 (28/10): sem ajuste de cor por padrão; as que subiram em v1 voltam à cor original no reprocessar
VERSAO_COM_COR = "v1"            # muda quando o algoritmo muda: entra na chave dos caches e marca a imagem que subiu (item.site_imagem_recorte)
LADO_ANALISE = 1500
MARGEM = 0.01
AREA_MIN, AREA_MAX = 0.10, 0.97
BRANCO_PAPEL = 248
GANHO_MAX = 2.2


# ---------------------------------------------------------------- configuração
def _cfg(con, chave: str, padrao: str = "1") -> str:
    try:
        r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    except Exception:  # noqa: BLE001  (banco antigo sem a tabela)
        return padrao
    return str(r[0]) if r and r[0] is not None else padrao


def recorte_ligado(con) -> bool:
    return _cfg(con, "imagem.recorte_automatico") not in ("0", "false", "nao", "")


def cor_ligada(con) -> bool:
    """28/10 (Rafael: "quero sempre igual o original"): DESLIGADO por padrão (migração 200). A imagem pública vai com a cor do original;
    o recorte da borda do scanner continua (não mexe na cor)."""
    return _cfg(con, "imagem.ajuste_cor", "0") not in ("0", "false", "nao", "")


def recusado(item) -> bool:
    """A pessoa escolheu "Usar recorte inteiro (sem recorte)" na conferência."""
    k = item.keys() if hasattr(item, "keys") else ()
    return bool(item["sem_recorte_auto"]) if "sem_recorte_auto" in k else False


# ---------------------------------------------------------------- utilidades (histogramas, sem numpy)
def _percentil(hist: list[int], p: float) -> int:
    total = sum(hist)
    if not total:
        return 0
    alvo, acc = total * p, 0
    for v, n in enumerate(hist):
        acc += n
        if acc >= alvo:
            return v
    return len(hist) - 1


def _maior_trecho(perfil: list[float], limiar: float, folga: int) -> tuple[int, int] | None:
    """O maior trecho contínuo com perfil >= limiar, juntando buracos de até `folga` posições (uma linha do desenho, uma listra)."""
    trechos, ini, ult = [], None, None
    for i, v in enumerate(perfil):
        if v >= limiar:
            if ini is None:
                ini = i
            elif i - ult - 1 > folga:
                trechos.append((ini, ult)); ini = i
            ult = i
    if ini is not None:
        trechos.append((ini, ult))
    if not trechos:
        return None
    return max(trechos, key=lambda t: (sum(perfil[t[0]:t[1] + 1]), t[1] - t[0]))


def _perfil(mask, eixo: str) -> list[float]:
    """Fração (0–1) de pixels marcados por coluna (eixo 'x') ou por linha (eixo 'y')."""
    from PIL import Image
    W, H = mask.size
    r = mask.resize((W, 1) if eixo == "x" else (1, H), Image.Resampling.BOX)
    return [v / 255 for v in r.getdata()]


def _caixa(mask, folga_x: int, folga_y: int) -> tuple[int, int, int, int] | None:
    """Colunas → linhas (só nas colunas achadas) → colunas de novo (só nas linhas achadas). Limiar relativo: 40% do percentil 95 do perfil."""
    W, H = mask.size

    def corte(perfil, folga):
        if not perfil:
            return None
        ordenado = sorted(perfil)
        ref = ordenado[min(len(ordenado) - 1, int(len(ordenado) * 0.95))]
        if ref < 0.05:
            return None
        return _maior_trecho(perfil, max(0.04, 0.4 * ref), folga)

    cx = corte(_perfil(mask, "x"), folga_x)
    if not cx:
        return None
    cy = corte(_perfil(mask.crop((cx[0], 0, cx[1] + 1, H)), "y"), folga_y)
    if not cy:
        return None
    cx2 = corte(_perfil(mask.crop((0, cy[0], W, cy[1] + 1)), "x"), folga_x)
    if cx2:
        cx = cx2
    return cx[0], cy[0], cx[1] + 1, cy[1] + 1


def _iou(a, b) -> float:
    l, t, r, bb = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, r - l) * max(0, bb - t)
    uni = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / uni if uni else 0.0


def _papel_claro(cor) -> bool:
    return min(cor) >= 200 and max(cor) - min(cor) <= 25


# ---------------------------------------------------------------- 1) detecção da borda do papel
def detectar(im) -> dict:
    """Recebe uma imagem PIL (já espelhada/girada/endireitada). Devolve {situacao, recorte, motivo, confianca}:
    situacao "ok" (recorte = {x,y,w,h} em frações, com 1% de margem), "incerto" (não recorta; para revisão) ou "sem_fundo" (nada a recortar)."""
    from PIL import Image, ImageChops, ImageFilter
    p = im.convert("RGB")
    if max(p.size) > LADO_ANALISE:
        p = p.copy(); p.thumbnail((LADO_ANALISE, LADO_ANALISE), Image.Resampling.BILINEAR)
    W, H = p.size
    if W < 40 or H < 40:
        return {"situacao": "sem_fundo", "recorte": None, "motivo": "imagem pequena demais para analisar", "confianca": 0.0}
    b = max(2, round(min(W, H) * 0.015))

    def mediana(img):
        h = img.histogram()
        return tuple(_percentil(h[i * 256:(i + 1) * 256], 0.5) for i in range(3))
    # cada borda em 10 trechos; o fundo do scanner é a cor com mais trechos parecidos (o papel pode encostar em uma ou duas bordas)
    trechos = []
    for j in range(10):
        trechos += [(W * j // 10, 0, W * (j + 1) // 10, b), (W * j // 10, H - b, W * (j + 1) // 10, H),
                    (0, H * j // 10, b, H * (j + 1) // 10), (W - b, H * j // 10, W, H * (j + 1) // 10)]
    trechos = [(cx, mediana(p.crop(cx))) for cx in trechos]
    dist = lambda a, c: max(abs(a[i] - c[i]) for i in range(3))
    apoio = lambda c: sum(1 for _, o in trechos if dist(o, c) < 20)
    melhor = max((c for _, c in trechos), key=lambda c: (apoio(c), max(c) - min(c)))
    iguais = [c for _, c in trechos if dist(c, melhor) < 20]
    fundo = tuple(sorted(c[i] for c in iguais)[len(iguais) // 2] for i in range(3))
    if _papel_claro(fundo):
        return {"situacao": "sem_fundo", "recorte": None, "motivo": "as bordas já são papel (sem fundo do scanner à vista)", "confianca": 1.0}

    dif = ImageChops.difference(p, Image.new("RGB", p.size, fundo))
    r_, g_, b_ = dif.split()
    d = ImageChops.lighter(ImageChops.lighter(r_, g_), b_)          # maior diferença entre os canais, 0–255
    hist_borda = [0] * 256
    for cx, c in trechos:
        if dist(c, fundo) < 20:                                       # só os trechos de fundo (não o papel que encosta na borda)
            for i, n in enumerate(d.crop(cx).histogram()):
                hist_borda[i] += n
    ruido = _percentil(hist_borda, 0.9)                              # as listras da Contex e o grão do scanner
    limiar = max(18, ruido * 1.5 + 6)
    fx, fy = max(2, W // 100), max(2, H // 100)

    def caixa_com(lim):
        m = d.point(lambda v: 255 if v >= lim else 0).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
        return m, _caixa(m, fx, fy)
    mask, cx = caixa_com(limiar)
    if not cx:
        return {"situacao": "incerto", "recorte": None, "motivo": "não achei o papel (pouca diferença entre o papel e o fundo do scanner)", "confianca": 0.0}
    area = (cx[2] - cx[0]) * (cx[3] - cx[1]) / (W * H)
    if area > AREA_MAX:
        return {"situacao": "sem_fundo", "recorte": None, "motivo": "o papel ocupa a imagem quase toda", "confianca": 1.0}
    dentro = mask.crop(cx).resize((1, 1), Image.Resampling.BOX).getpixel((0, 0)) / 255      # quanto do retângulo é "papel"
    contraste = _percentil(d.crop(cx).histogram(), 0.5)                                     # diferença típica papel × fundo
    _, cx_alto = caixa_com(limiar * 1.4)
    _, cx_baixo = caixa_com(max(12, limiar * 0.75))
    estab = min(_iou(cx, cx_alto) if cx_alto else 0.0, _iou(cx, cx_baixo) if cx_baixo else 0.0)
    motivos = []
    if area < AREA_MIN:
        motivos.append("o papel achado é pequeno demais")
    if contraste < max(30, ruido * 2.5):
        motivos.append("pouco contraste entre o papel e o fundo do scanner (papel vegetal?)")
    if dentro < 0.75:
        motivos.append("o papel achado está ralo/transparente")
    if estab < 0.9:
        motivos.append("o retângulo muda com o limiar")
    conf = round(max(0.0, min(1.0, min(estab, dentro, contraste / max(1.0, 2 * max(30, ruido * 2.5))))), 2)
    if motivos:
        return {"situacao": "incerto", "recorte": None, "motivo": "; ".join(motivos), "confianca": conf}
    x0 = max(0.0, cx[0] / W - MARGEM); y0 = max(0.0, cx[1] / H - MARGEM)
    x1 = min(1.0, cx[2] / W + MARGEM); y1 = min(1.0, cx[3] / H + MARGEM)
    rec = {"x": round(x0, 4), "y": round(y0, 4), "w": round(x1 - x0, 4), "h": round(y1 - y0, 4)}
    if rec["w"] * rec["h"] > AREA_MAX:
        return {"situacao": "sem_fundo", "recorte": None, "motivo": "o papel ocupa a imagem quase toda", "confianca": 1.0}
    return {"situacao": "ok", "recorte": rec, "motivo": "", "confianca": conf}


# ---------------------------------------------------------------- 2) branco e contraste pelo papel
def ajustar_cor(im):
    """Níveis pelo papel, por canal (balanço de branco): o papel vai a 248 e o ponto preto fica na METADE do 0,5% mais escuro (e no máximo
    a um quarto do papel), então nenhum traço encosta no preto;
    ganho limitado a 2,2× (suave: não estoura linha fina). Papel escuro (luminância < 120, cópia azul) volta como está. Só RGB."""
    from PIL import Image
    im = im.convert("RGB")
    W, H = im.size
    a = im.crop((round(W * 0.03), round(H * 0.03), round(W * 0.97), round(H * 0.97))) if W > 60 and H > 60 else im
    a = a.copy(); a.thumbnail((800, 800), Image.Resampling.BILINEAR)
    L = a.convert("L")
    hl = L.histogram()
    corte_papel = _percentil(hl, 0.5)
    mascara = L.point(lambda v: 255 if v >= corte_papel else 0)
    from PIL import ImageStat
    papel = ImageStat.Stat(a, mascara).median
    papel_l = 0.299 * papel[0] + 0.587 * papel[1] + 0.114 * papel[2]
    if papel_l < 120:
        return im
    preto = 0.5 * min(_percentil(hl, 0.005), papel_l * 0.5)       # metade do traço mais escuro: o traço escurece, mas não vira preto chapado
    luts = []
    for c in range(3):
        topo = max(papel[c], preto + 1)
        ganho = BRANCO_PAPEL / (topo - preto)
        p0 = preto
        if ganho > GANHO_MAX:
            ganho = GANHO_MAX; p0 = topo - BRANCO_PAPEL / ganho
        if ganho < 1:              # papel já mais claro que 248 neste canal: não escurece
            ganho, p0 = 1.0, 0.0
        luts += [max(0, min(255, round((v - p0) * ganho))) for v in range(256)]
    return im.point(luts)


# ---------------------------------------------------------------- proposta da folha (com cache em disco)
def _abrir_orientado(origem: Path, giro: int, espelhar: bool, ang: float):
    from PIL import Image
    from .ajuste_imagem import _orientar, aplicar
    with Image.open(origem) as im0:
        im0.draft("RGB", (LADO_ANALISE, LADO_ANALISE))
        im = im0.convert("RGB")
    im.thumbnail((LADO_ANALISE, LADO_ANALISE), Image.Resampling.BILINEAR)
    return aplicar(_orientar(im, giro, espelhar), ang, None)


def proposta(origem: Path | str, giro: int = 0, espelhar: bool = False, ang: float = 0.0) -> dict:
    """O recorte automático da folha (não grava nada na folha). Cache em disco por arquivo+data+tamanho+giro+espelho+ângulo+versão."""
    from .giro_imagem import pasta_cache
    origem = Path(origem)
    st = origem.stat()
    chave = f"auto|{VERSAO}|{origem}|{st.st_mtime_ns}|{st.st_size}|{giro % 360}|{int(bool(espelhar))}|{ang or 0}"
    alvo = pasta_cache() / ("recorte-" + hashlib.sha1(chave.encode()).hexdigest() + ".json")
    try:
        return json.loads(alvo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    r = detectar(_abrir_orientado(origem, giro % 360, espelhar, ang or 0.0))
    r["versao"] = VERSAO
    tmp = alvo.with_name(f"{alvo.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8"); os.replace(tmp, alvo)
    except OSError:
        pass
    return r


def plano(con, i, origem, giro: int, espelhar: bool, rec, ang) -> dict:
    """O que o derivado público desta folha leva: {recorte_auto (frações|None), cor (bool), situacao, motivo}.
    Recorte manual vence (só o ajuste de cor, se ligado). Recusado na conferência: sem recorte; cor só se o papel enche a imagem."""
    liga_rec, liga_cor = recorte_ligado(con), cor_ligada(con)
    if rec:
        return {"recorte_auto": None, "cor": liga_cor, "situacao": "manual", "motivo": ""}
    if not (liga_rec or liga_cor) or origem is None:
        return {"recorte_auto": None, "cor": False, "situacao": "desligado", "motivo": ""}
    p = proposta(origem, giro, espelhar, ang)
    if p["situacao"] == "ok":
        if liga_rec and not recusado(i):
            return {"recorte_auto": p["recorte"], "cor": liga_cor, "situacao": "ok", "motivo": ""}
        return {"recorte_auto": None, "cor": False, "situacao": "recusado" if recusado(i) else "desligado", "motivo": ""}
    return {"recorte_auto": None, "cor": liga_cor and p["situacao"] == "sem_fundo", "situacao": p["situacao"], "motivo": p.get("motivo", "")}
