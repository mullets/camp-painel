"""Projeto parecido? Compara um nome que chegou com os projetos já existentes no MESMO fundo.

Não decide nada: devolve uma nota, o nível (forte | provável) e os MOTIVOS em português, para a pessoa decidir. Quatro sinais:
- mesma identificação original (o nome da pasta no scanner): sinal mais forte;
- nome igual depois de ignorar acento, caixa, pontuação, artigos e palavras genéricas (residência, casa, edifício...): "Residência Banco Cidade" = "Banco Cidade";
- um nome contido no outro (2 palavras distintivas ou mais): "Banco Cidade" está em "Banco Cidade - Agência Matriz";
- nome muito parecido (erro de OCR/digitação): "Hoswaldo" x "Oswaldo".
Número ou letra de designação distingue projetos ("Casa 1" x "Casa 2", "Torre A" x "Torre B", "Banco Safra D27" x "D28"): se os nomes só diferem nisso, NÃO são parecidos.
Ano e cidade só ajustam a nota (mesmo ano e mesma cidade somam; anos distantes e cidades diferentes subtraem); sozinhos nunca criam um candidato.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

NIVEL_FORTE = 0.92
NIVEL_PROVAVEL = 0.75
STOP = {"de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "em", "no", "na", "nos", "nas", "para", "por", "com", "sem", "ao", "aos", "um", "uma"}
GENERICAS = {"residencia", "residencial", "casa", "edificio", "predio", "projeto", "obra", "sede", "conjunto", "apartamento", "sobrado", "chacara", "sitio"}
SINONIMOS = {"res": "residencia", "ed": "edificio", "edif": "edificio", "apto": "apartamento", "ap": "apartamento", "sta": "santa", "sto": "santo"}


def normalizar(txt: str | None) -> str:
    """Minúsculas, sem acento nem pontuação, espaços colapsados."""
    if not txt:
        return ""
    t = "".join(c for c in unicodedata.normalize("NFD", str(txt)) if unicodedata.category(c) != "Mn").lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def tokens(titulo: str | None) -> list[str]:
    """Palavras do nome, sem artigos e preposições. Uma letra solta no FIM é designação ("Torre A", "Bloco B") e fica."""
    pal = normalizar(titulo).split()
    return [SINONIMOS.get(w, w) for i, w in enumerate(pal) if w not in STOP or (len(w) == 1 and i == len(pal) - 1 and i > 0)]


def tokens_distintivos(titulo: str | None) -> list[str]:
    """Tira as palavras genéricas (residência, casa...), a não ser que sobre nada."""
    t = tokens(titulo)
    return [w for w in t if w not in GENERICAS] or t


def pontuar(novo: dict, existente: dict) -> tuple[float, list[str]]:
    """(nota 0..1, motivos). `novo` e `existente` têm titulo, ano, cidade, identificacao_original."""
    ni, ei = normalizar(novo.get("identificacao_original")), normalizar(existente.get("identificacao_original"))
    if ni and ni == ei:
        return 1.0, [f"mesma identificação original ({novo.get('identificacao_original').strip()})"]
    ta, tb = tokens_distintivos(novo.get("titulo")), tokens_distintivos(existente.get("titulo"))
    if not ta or not tb:
        return 0.0, []
    sa, sb = set(ta), set(tb)
    # Número ou letra de designação distingue projetos: "Casa 1" x "Casa 2", "Torre A" x "Torre B", "Banco Safra D27" x "D28" NÃO são parecidos.
    dif = sa ^ sb
    if dif and all(len(t) <= 1 or any(ch.isdigit() for ch in t) for t in dif):
        return 0.0, []
    motivos: list[str] = []
    if sa == sb:
        score = 1.0
        motivos.append("mesmo nome (igual sem acento, maiúscula e palavras genéricas)")
    else:
        inter = len(sa & sb)
        jac = inter / len(sa | sb)
        ratio = SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
        score = max(jac, ratio)
        if min(len(sa), len(sb)) >= 2 and inter == min(len(sa), len(sb)):
            score = max(score, 0.90)
            motivos.append("um nome está contido no outro")
        elif score >= NIVEL_PROVAVEL:
            motivos.append(f"nome muito parecido ({round(score * 100)}%)")
    if score < 0.6:
        return round(score, 3), []
    ya, yb = novo.get("ano") or 0, existente.get("ano") or 0
    if ya and yb:
        if ya == yb:
            score += 0.05
            motivos.append(f"mesmo ano ({ya})")
        elif abs(ya - yb) > 5:
            score -= 0.10
            motivos.append(f"anos diferentes ({ya} e {yb})")
    ca, cb = normalizar(novo.get("cidade")), normalizar(existente.get("cidade"))
    if ca and cb:
        if ca == cb:
            score += 0.05
            motivos.append(f"mesma cidade ({existente.get('cidade').strip()})")
        else:
            score -= 0.05
            motivos.append(f"cidades diferentes ({novo.get('cidade').strip()} e {existente.get('cidade').strip()})")
    return round(max(0.0, min(1.0, score)), 3), motivos


def nivel(score: float) -> str | None:
    return "forte" if score >= NIVEL_FORTE else "provavel" if score >= NIVEL_PROVAVEL else None


def buscar_parecidos(con, fundo_codigo: str, titulo: str, ano: int | None = 0, cidade: str | None = None,
                     identificacao_original: str | None = None, limite: int = 5) -> list[dict]:
    """Projetos do MESMO fundo parecidos com o que chegou, do mais para o menos parecido. Vazio = nada suspeito."""
    novo = {"titulo": titulo, "ano": ano or 0, "cidade": cidade, "identificacao_original": identificacao_original}
    achados = []
    for p in con.execute("""SELECT p.codigo, p.titulo, p.ano, p.cidade, p.identificacao_original,
                                   (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo) AS folhas_locais,
                                   (SELECT COUNT(*) FROM wp_item w WHERE w.projeto_detectado=p.codigo AND w.codigo_detectado LIKE p.codigo || '-%') AS folhas_site
                              FROM projeto p WHERE p.fundo_codigo=?""", (fundo_codigo,)):
        score, motivos = pontuar(novo, dict(p))
        n = nivel(score)
        if n:
            achados.append({"codigo": p["codigo"], "titulo": p["titulo"], "ano": p["ano"] or None, "cidade": p["cidade"],
                            "identificacao_original": p["identificacao_original"], "folhas": max(p["folhas_locais"], p["folhas_site"]),
                            "score": score, "nivel": n, "motivos": motivos})
    achados.sort(key=lambda x: (-x["score"], x["codigo"]))
    return achados[:limite]
