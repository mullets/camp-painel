"""CAMP-DUP-FORMATOS (04/11/2026): a MESMA prancha que entrou 2–3 vezes como folhas diferentes, uma por formato
(subpastas TIFF / DNG / JPG / JPG LIMPO, "fotos em alta" / "fotos para internet" no QNAP; F001 Arnaldo Martino, ~648 folhas em 29/10).

Aqui só fica a REGRA (sem gravar nada): como reconhecer que duas folhas do MESMO projeto são a mesma prancha e qual delas fica.
Quem grava é a ferramenta de duplicatas (duplicatas._marcar), chamada por scripts/limpar_duplicatas_formato.py, e o importador
(importador_lote.py) ao trazer um código novo.

Casa "a mesma prancha" (dentro do mesmo projeto):
  forte  — mesmo md5 (o CAMP Vision grava o md5 do arquivo mestre em catalogacao/preparo.json);
         — dHash (64 bits, o mesmo do CAMP Vision) a ≤ 6 bits, olhando as 4 rotações da prévia (a cópia JPG pode ter sido girada);
         — mesmo radical do nome em subpastas diferentes, quando as duas subpastas são de FORMATO (TIFF, JPG LIMPO, "fotos em alta"…)
           ou quando o dHash confirma a ≤ 12 bits ("Planta/001.tif" e "Corte/001.tif" NÃO são a mesma prancha);
         — mesma posição em duas subpastas com o mesmo número de arquivos, se o dHash confirmar a ≤ 12 bits.
  incerto (só listado, nunca entra no plano) — a posição casa e não há imagem para confirmar, ou a imagem não confirma.
REGRA DURA (04/11/2026, depois da simulação real do F001, que juntava D3–D7 DNG do P0030 e fotos em sequência do P0001): duas folhas só
são a mesma prancha se vierem de pastas de FORMATO/VERSÃO diferentes (`conflito`). Da mesma pasta, nunca (vira incerto); o mesmo formato
em pastas diferentes (TIFF × TIFF), só pelo md5; sem arquivo de origem, só pelo md5. Um grupo tem no máximo uma folha por pasta/formato:
junta-se pelo par mais forte primeiro (md5 > mesmo nome > menor dHash) e o par que violaria a regra vai para os incertos. As marcas
antigas `duplicata_de` (CAMP Vision ou pessoa) não juntam nada: só informam; a de MÁQUINA que liga duas folhas da mesma pasta é listada
como "marca antiga suspeita" (`marcas_suspeitas`) para uma pessoa revisar.
A que fica ("principal"): não é cópia de outra > já está no site > já conferida > TIFF > DNG > JPG LIMPO > JPG > outra;
"fotos em alta" > sem indicação > "fotos para internet"; empate: o menor D.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path, PurePosixPath, PureWindowsPath

LIMIAR_FORTE = 6          # o mesmo do CAMP Vision para "quase igual"
LIMIAR_CONFIRMA = 12      # basta para CONFIRMAR um par que o nome ou a posição já indicam
LIMIAR_DUVIDA = 20        # acima disto a imagem diz que são pranchas diferentes: o par nem aparece como incerto

ROTULO_FORMATO = {0: "TIFF", 1: "DNG", 2: "JPG LIMPO", 3: "JPG", 4: "outro"}
_PALAVRAS_FORMATO = {"tif", "tiff", "dng", "jpg", "jpeg", "png", "raw", "limpo", "limpa", "alta", "baixa", "internet", "web", "master", "matriz",
                     "fotos", "foto", "em", "para", "resolucao", "res", "hi", "low", "high", "original", "originais"}
_SUFIXOS_NOME = {"limpo", "limpa", "alta", "baixa", "internet", "web", "final", "copia", "copy", "edit", "editado"}


# ----------------------------------------------------------------- utilidades
def norm(t) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def distancia(a: str, b: str) -> int:
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except (TypeError, ValueError):
        return 64


def menor_distancia(xs, ys) -> int:
    return min((distancia(x, y) for x in xs or () for y in ys or ()), default=64)


def _caminho(p: str):
    return PureWindowsPath(p) if "\\" in p else PurePosixPath(p)


def origens(arquivo_origem) -> list[str]:
    return [o.strip() for o in str(arquivo_origem or "").split(" | ") if o.strip()]


def subpasta(arquivo_origem) -> str:
    os_ = origens(arquivo_origem)
    if not os_:
        return "(sem origem)"
    return _caminho(os_[0]).parent.name or "(raiz do lote)"


def _pastas(arquivo_origem, n: int = 3) -> list[str]:
    os_ = origens(arquivo_origem)
    return [norm(p) for p in _caminho(os_[0]).parent.parts[-n:]] if os_ else []


def e_pasta_de_formato(nome: str) -> bool:
    """'TIFF', 'JPG LIMPO', 'fotos em alta', 'Fotos para internet' são pastas de FORMATO; 'Plantas', 'Cortes' não."""
    p = norm(nome).split()
    return bool(p) and all(x in _PALAVRAS_FORMATO for x in p)


def radical(arquivo_origem) -> str:
    os_ = origens(arquivo_origem)
    if not os_:
        return ""
    return " ".join(x for x in norm(_caminho(os_[0]).stem).split() if x not in _SUFIXOS_NOME)


def rank_formato(arquivo_origem) -> tuple[int, int]:
    """(formato, resolução): menor é melhor. TIFF 0, DNG 1, JPG LIMPO 2, JPG 3, outro 4; "alta" 0, nada 1, "internet" 2."""
    pastas = _pastas(arquivo_origem)
    sp = pastas[-1] if pastas else ""
    os_ = origens(arquivo_origem)
    ext = _caminho(os_[0]).suffix.lower() if os_ else ""
    if "tif" in sp.split() or "tiff" in sp.split() or ext in (".tif", ".tiff"):
        f = 0
    elif "dng" in sp.split() or ext == ".dng":
        f = 1
    elif "limpo" in sp.split() or "limpa" in sp.split():
        f = 2
    elif ext in (".jpg", ".jpeg") or "jpg" in sp.split() or "jpeg" in sp.split():
        f = 3
    else:
        f = 4
    tudo = " ".join(pastas).split()
    r = 0 if any(x in tudo for x in ("alta", "master", "matriz")) else (2 if any(x in tudo for x in ("internet", "baixa", "web")) else 1)
    return f, r


def rotulo_formato(arquivo_origem) -> str:
    f, r = rank_formato(arquivo_origem)
    return ROTULO_FORMATO[f] + {0: " em alta", 1: "", 2: " para internet"}[r]


def no_site(i) -> bool:
    return i["status_site"] in ("no_ar", "rascunho")


def conferida(i) -> bool:
    return (i["revisao"] or "pendente") != "pendente"


def chave_principal(i) -> tuple:
    return (1 if i["duplicata_de"] else 0, 0 if no_site(i) else 1, 0 if conferida(i) else 1, *rank_formato(i["arquivo_origem"]), i["sequencial"] or 0)


# ----------------------------------------------------------------- imagens e hashes (só leitura)
def dhash_rotacoes(arq: Path) -> list[str]:
    """dHash (o MESMO cálculo do CAMP Vision: 9x8 em cinza, LANCZOS) nas 4 rotações da imagem."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(arq) as img:
        img.draft("L", (512, 512))
        base = img.convert("L")
        base.thumbnail((512, 512))
        out = []
        for giro in (0, 90, 180, 270):
            g = base.rotate(giro, expand=True) if giro else base
            px = list(g.resize((9, 8), Image.LANCZOS).tobytes())
            bits = 0
            for lin in range(8):
                for col in range(8):
                    bits = (bits << 1) | (1 if px[lin * 9 + col] > px[lin * 9 + col + 1] else 0)
            out.append(f"{bits:016x}")
        return out


def imagem_da_folha(raiz: Path | None, item) -> Path | None:
    """A prévia que o painel já mostra (pendencias.previa, dentro de _campvision/preview) ou o JPG da folha, sempre DENTRO da raiz dos prontos."""
    if not raiz:
        return None
    try:
        prev = (json.loads(item["pendencias"] or "{}") or {}).get("previa")
    except (ValueError, AttributeError, TypeError):
        prev = None
    try:
        raiz_r = raiz.resolve()
    except OSError:
        return None
    for rel in (prev if prev and prev != "@jpg" else None, item["arquivo_jpg"]):
        if not rel or str(rel).startswith("http"):
            continue
        try:
            c = Path(str(rel))
            alvo = (c if c.is_absolute() else raiz / c).resolve()
            if raiz_r in alvo.parents and alvo.suffix.lower() in (".jpg", ".jpeg") and alvo.is_file():
                return alvo
        except OSError:
            continue
    return None


def ler_preparo(pasta) -> dict[str, dict]:
    """catalogacao/preparo.json do CAMP Vision numa pasta de lote: {código: {md5, phash}}. Ausente/ilegível: {}."""
    try:
        dados = json.loads((Path(pasta) / "catalogacao" / "preparo.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    out = {}
    for cod, p in (dados or {}).items() if isinstance(dados, dict) else ():
        if isinstance(p, dict):
            out[str(cod)] = {"md5": str(p.get("md5") or "").strip().lower(), "phash": str(p.get("hash_perceptual") or "").strip().lower()}
    return out


class _UF:
    def __init__(self):
        self.p = {}

    def achar(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def unir(self, a, b):
        self.p[self.achar(a)] = self.achar(b)


# ----------------------------------------------------------------- regra dura (CAMP-DUP-FORMATOS, 2ª rodada)
def pasta_chave(arquivo_origem) -> str | None:
    """A pasta do arquivo de origem (caminho inteiro, normalizado); None quando a folha não tem arquivo de origem."""
    os_ = origens(arquivo_origem)
    if not os_:
        return None
    return norm(str(_caminho(os_[0]).parent)) or "(raiz do lote)"


def conflito(origem_a, origem_b, md5_igual: bool = False) -> str | None:
    """REGRA DURA: duas folhas só podem ser a mesma prancha se vierem de pastas de FORMATO/VERSÃO diferentes (TIFF × DNG × JPG ×
    JPG LIMPO; "em alta" × "para internet"). Devolve o motivo do NÃO (ou None quando podem ser a mesma prancha):
      - a mesma pasta (fotos parecidas em sequência, pranchas de um mesmo jogo): NUNCA, nem pelo md5;
      - o mesmo formato em pastas diferentes (TIFF × TIFF): só se o arquivo for o mesmo (md5);
      - sem arquivo de origem conhecido: só o mesmo arquivo (md5)."""
    pa, pb = pasta_chave(origem_a), pasta_chave(origem_b)
    if pa is None or pb is None:
        return None if md5_igual else "sem a pasta de origem, só o mesmo arquivo (md5) junta"
    if pa == pb:
        return f"as duas estão na mesma pasta ('{subpasta(origem_a)}'): folhas da mesma pasta nunca são a mesma prancha"
    if not md5_igual and rank_formato(origem_a) == rank_formato(origem_b):
        sa, sb = subpasta(origem_a), subpasta(origem_b)
        if sa == sb:                               # 'TIFF' e 'TIFF': mostra a pasta de cima para a pessoa achar as duas
            sa, sb = ("/".join(_caminho(origens(o)[0]).parent.parts[-2:]) for o in (origem_a, origem_b))
        return f"as duas são {rotulo_formato(origem_a)} ('{sa}' e '{sb}'): só junto formatos diferentes"
    return None


def _campo(i, k):
    try:
        return i[k]
    except (KeyError, IndexError):
        return None


def marca_de_pessoa(i) -> bool:
    """A marca 'duplicata de' foi conferida por uma PESSOA (tela Duplicatas/revisão) e continua a mesma: nunca é alterada aqui."""
    return bool(_campo(i, "duplicata_de") and _campo(i, "duplicata_conferida_em") and _campo(i, "duplicata_conferida_de") == _campo(i, "duplicata_de")
                and (_campo(i, "duplicata_conferida_por") or "") != "limpeza de formatos")


def marcas_suspeitas(itens: list) -> list[dict]:
    """Marcas antigas de MÁQUINA (CAMP Vision pelo dHash, importação) que ligam duas folhas da MESMA pasta: provavelmente pranchas
    diferentes e parecidas. Só listadas para uma pessoa revisar (marca de pessoa nunca entra)."""
    por_cod = {i["codigo"]: i for i in itens}
    out = []
    for i in itens:
        de = i["duplicata_de"]
        if not de or de not in por_cod or marca_de_pessoa(i):
            continue
        pa = pasta_chave(i["arquivo_origem"])
        if pa is not None and pa == pasta_chave(por_cod[de]["arquivo_origem"]):
            tipo = _campo(i, "tipo_duplicata") or ""
            out.append({"codigo": i["codigo"], "de": de, "tipo": tipo, "pasta": subpasta(i["arquivo_origem"]),
                        "quem": "CAMP Vision" if tipo in ("exata", "perceptual") else "automática"})
    return out


# ----------------------------------------------------------------- agrupar
def agrupar(itens: list, md5: dict[str, str], hashes: dict[str, list[str]]) -> dict:
    """itens: linhas de `item` de UM projeto (codigo, sequencial, arquivo_origem, duplicata_de, revisao, status_site…).
    md5 {codigo: md5}, hashes {codigo: [dHash…]} (vazio quando não há imagem). Devolve
    {grupos: [[principal, cópia…]], motivos: {frozenset(par): {…}}, incertos: [(a, b, motivo)], sem_imagem: n}.

    Junta pelo par MAIS FORTE primeiro (md5 > mesmo nome > menor dHash) e só se a união respeitar a regra dura (`conflito`) entre
    TODAS as folhas dos dois grupos: um grupo tem no máximo uma folha por pasta e por formato. O par que a regra recusa vai para os
    incertos (nunca para o plano). As marcas antigas `duplicata_de` NÃO juntam nada aqui (só informam)."""
    por_cod = {i["codigo"]: i for i in itens}
    cods = list(por_cod)
    ori = {c: por_cod[c]["arquivo_origem"] for c in cods}
    sub = {c: subpasta(ori[c]) for c in cods}
    m5 = {c: (md5.get(c) or "").strip().lower() for c in cods}
    pares, incertos = [], []                       # pares: (força, dHash, a, b, motivo)

    por_md5 = defaultdict(list)
    for c in cods:
        if m5[c]:
            por_md5[m5[c]].append(c)
    for g in por_md5.values():
        for x, a in enumerate(g):
            for b in g[x + 1:]:
                pares.append((0, 0, a, b, "mesmo arquivo (md5)"))
    com = [c for c in cods if hashes.get(c)]
    for k, a in enumerate(com):
        for b in com[k + 1:]:
            d = menor_distancia(hashes[a], hashes[b])
            if d <= LIMIAR_FORTE:
                pares.append((2, d, a, b, f"imagem igual (dHash {d})"))
    por_rad = defaultdict(list)
    for c in cods:
        r = radical(ori[c])
        if r:
            por_rad[r].append(c)
    for g in por_rad.values():
        for x, a in enumerate(g):
            for b in g[x + 1:]:
                if sub[a] == sub[b]:
                    continue
                d = menor_distancia(hashes.get(a), hashes.get(b))
                if d <= LIMIAR_CONFIRMA:
                    pares.append((1, d, a, b, f"mesmo nome em outra subpasta (dHash {d})"))
                elif d == 64 and e_pasta_de_formato(sub[a]) and e_pasta_de_formato(sub[b]):
                    pares.append((1, 64, a, b, "mesmo nome em outra pasta de formato"))
                else:
                    incertos.append((a, b, "mesmo nome em outra subpasta" + (f", mas a imagem é diferente (dHash {d})" if d < 64 else ", sem imagem para confirmar")))
    por_sub = defaultdict(list)
    for c in cods:
        os_ = origens(ori[c])
        por_sub[sub[c]].append((_caminho(os_[0]).name.lower() if os_ else "", por_cod[c]["sequencial"] or 0, c))
    for s in por_sub:
        por_sub[s].sort()
    subs = sorted(por_sub)
    for x, s1 in enumerate(subs):
        for s2 in subs[x + 1:]:
            if len(por_sub[s1]) != len(por_sub[s2]) or len(por_sub[s1]) < 2:
                continue
            for (_, _, a), (_, _, b) in zip(por_sub[s1], por_sub[s2]):
                d = menor_distancia(hashes.get(a), hashes.get(b))
                if d <= LIMIAR_CONFIRMA:
                    pares.append((2, d, a, b, f"mesma posição na subpasta (dHash {d})"))
                else:
                    incertos.append((a, b, "mesma posição na subpasta" + (f", mas a imagem é diferente (dHash {d})" if d < 64 else ", sem imagem para confirmar")))

    seq = {c: por_cod[c]["sequencial"] or 0 for c in cods}
    pares.sort(key=lambda p: (p[0], p[1], min(seq[p[2]], seq[p[3]]), max(seq[p[2]], seq[p[3]])))
    uf, membros, motivos = _UF(), {c: [c] for c in cods}, defaultdict(set)
    recusados = []                                 # (a, b, motivo do par, por que não, direto?)
    for _, _, a, b, m in pares:
        ra, rb = uf.achar(a), uf.achar(b)
        if ra == rb:
            motivos[frozenset((a, b))].add(m)
            continue
        porque = conflito(ori[a], ori[b], bool(m5[a]) and m5[a] == m5[b])
        if porque:
            recusados.append((a, b, m, porque, True))
            continue
        barra = next(((x, y, q) for x in membros[ra] for y in membros[rb]
                      for q in [conflito(ori[x], ori[y], bool(m5[x]) and m5[x] == m5[y])] if q), None)
        if barra:                                  # a união poria duas folhas da mesma pasta/formato no mesmo grupo: fica o par mais forte
            x, y, q = barra
            recusados.append((a, b, m, f"juntaria {_d(x)} e {_d(y)} ({q.split(':')[0]})", False))
            continue
        uf.unir(a, b)                              # _UF.unir: a raiz de `a` passa a apontar para a raiz de `b`
        membros[rb] = membros[rb] + membros.pop(ra)
        motivos[frozenset((a, b))].add(m)
    grupos = defaultdict(list)
    for c in cods:
        grupos[uf.achar(c)].append(c)
    grupos = [sorted(g, key=lambda c: chave_principal(por_cod[c])) for g in grupos.values() if len(g) > 1]
    grupos.sort(key=lambda g: por_cod[g[0]]["sequencial"] or 0)
    juntos = {c for g in grupos for c in g}
    vistos, inc = set(), []
    for a, b, m, porque, direto in recusados:     # a regra dura recusou: vira INCERTO (nunca entra no plano)
        par = frozenset((a, b))
        if par in vistos or uf.achar(a) == uf.achar(b) or (not direto and a in juntos and b in juntos):
            continue                               # (recusado só pelo grupo e as duas já têm o seu grupo: nada sobrou)
        vistos.add(par)
        inc.append((a, b, f"{m}, mas {porque}"))
    for a, b, m in incertos:                       # o par incerto que outro critério já juntou não é mais incerto
        if uf.achar(a) == uf.achar(b) or frozenset((a, b)) in vistos or (a in juntos and b in juntos):
            continue                               # (as duas já estão em grupos diferentes: a imagem já separou)
        d = menor_distancia(hashes.get(a), hashes.get(b))
        if LIMIAR_DUVIDA < d < 64:
            continue
        vistos.add(frozenset((a, b)))
        inc.append((a, b, m))
    return {"grupos": grupos, "motivos": motivos, "incertos": inc, "juntos": juntos,
            "sem_imagem": sum(1 for c in cods if not hashes.get(c)),
            "incertos_sem_imagem": sum(1 for _, _, m in inc if "sem imagem" in m),
            "marcas_suspeitas": marcas_suspeitas(itens)}


def _d(cod: str) -> str:
    try:
        return "D" + str(int(str(cod).rsplit("-D", 1)[1]))
    except (IndexError, ValueError):
        return str(cod)


# ----------------------------------------------------------------- importação (defesa)
def ligado(con) -> bool:
    """importacao.repetida_por_imagem: sem a chave ou '1' = ligado; '0' desliga (volta ao de antes: só o que o CAMP Vision marcar)."""
    try:
        r = con.execute("SELECT valor FROM configuracao WHERE chave='importacao.repetida_por_imagem'").fetchone()
    except Exception:  # noqa: BLE001
        return True
    return not (r and str(r[0]).strip() == "0")


def raiz_da_cadeia(con, cod: str) -> str:
    vistos = {cod}
    while True:
        r = con.execute("SELECT duplicata_de FROM item WHERE codigo=?", (cod,)).fetchone()
        if not r or not r[0] or r[0] in vistos:
            return cod
        cod = r[0]
        vistos.add(cod)
