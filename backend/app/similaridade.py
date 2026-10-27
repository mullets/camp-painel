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


_SUBPASTA = re.compile(r"^\s*(\d{1,3}\s*[-–—._]\s*)?(arquivo\s+arquiv[ií]stico.*|arquivo\s+de\s+acesso.*|desenhos?(\s+e\s+pranchas)?|pranchas|fotografias?|fotos|documentos?|textos?"
                       r"|jpe?g|tiff?|png|pdf|originais|copias|cópias|digitaliza[cç][aã]o.*|scans?|em\s+identifica[cç][aã]o)\s*(\(.*\))?\s*$", re.I)


def nome_de_subpasta(titulo: str | None) -> bool:
    """'01 - Arquivo Arquivístico (TIFF)', '03 - Fotografias', 'JPG'…: nome de pasta de arquivos, não de obra (aviso de 14/10, F009-P0114)."""
    return bool(_SUBPASTA.match(titulo or ""))


# UX-15: título que é nome de pasta ou código do sistema, não o nome de uma obra. A mesma regra para criar, importar planilha,
# editar, publicar e para o aviso da tela Projetos. Ordem: o primeiro motivo que casar é o que a tela mostra.
_TECNICOS = (
    (re.compile(r"^\s*T\d{3}_", re.I), "começa com o prefixo de pasta T###_"),
    (re.compile(r"^\s*F\d{3}\s*[-–—_]", re.I), "começa com o código do fundo (F###-)"),
    (re.compile(r"^\s*P\d{4}\s*[-–—_]", re.I), "começa com o número do projeto (P####-)"),
    (re.compile(r"^\s*\d+\s*[-–—]\s", re.I), "começa com número de pasta (ex.: “01 - ”)"),
    (re.compile(r"\bTIFF?\b", re.I), "tem “TIFF” (formato de arquivo)"),
    (re.compile(r"\bP\d{4}\s*$", re.I), "termina com o número do projeto (P####)"),
    (re.compile(r"^\s*projeto\s+n[aã]o\s+identificado\b", re.I), "é “Projeto Não Identificado”, não o nome de uma obra"),
)
_PREFIXOS_LIMPOS = re.compile(r"^\s*(?:T\d{3}_+|F\d{3}(?:-P\d{4})?\s*[-–—_]+\s*|P\d{4}\s*[-–—_]+\s*|\d+\s*[-–—]\s+)", re.I)


def titulo_tecnico(titulo: str | None) -> str | None:
    """O motivo (frase curta) quando o título é nome de pasta ou código do sistema; None quando é um nome de obra."""
    t = (titulo or "").strip()
    if not t:
        return None
    if nome_de_subpasta(t):
        return "é nome de subpasta de arquivos (TIFF, JPG, fotografias…)"
    for rx, motivo in _TECNICOS:
        if rx.search(t):
            return motivo
    return None


def sugerir_titulo(titulo: str | None) -> str | None:
    """Como o título ficaria sem o prefixo de pasta ("T099_Casa_Azul" → "Casa Azul"). Só SUGERE: uma pessoa aceita caso a caso.
    None quando o que sobra ainda é técnico ou vazio (ex.: "01 - Arquivo Arquivístico (TIFF)", "Projeto Não Identificado 3")."""
    t = (titulo or "").strip()
    for _ in range(4):                                   # "F026 - T099_Casa" tem mais de um prefixo
        novo = _PREFIXOS_LIMPOS.sub("", t, count=1)
        if novo == t:
            break
        t = novo
    t = re.sub(r"\s*[-–—_]?\s*\(?\bP\d{4}\)?\s*$", "", t, flags=re.I)
    t = " ".join(t.replace("_", " ").split()).strip(" -–—")
    if not t or t == (titulo or "").strip() or titulo_tecnico(t) or len(t) < 3:
        return None
    return t


def buscar_em_outros_fundos(con, fundo_codigo: str | None, titulo: str, ano: int | None = 0, cidade: str | None = None, limite: int = 3) -> list[dict]:
    """Projeto com o MESMO nome em OUTRO fundo ("já existe 'Casa X' no fundo F012 — é o mesmo?"). Só o nível forte: nome
    praticamente igual. Não bloqueia nada: vira uma nota forte com link para a pessoa conferir."""
    # Decisão de 14/10 (Rafael): fundos não se misturam. Projeto parecido só se procura DENTRO do mesmo fundo (o mesmo arquiteto);
    # a nota/pergunta "mesmo nome em outro fundo" foi desligada. A função fica (chamadores antigos) e não acha nada.
    return []
    novo = {"titulo": titulo, "ano": ano or 0, "cidade": cidade}
    achados = []
    for p in con.execute("""SELECT p.codigo, p.titulo, p.ano, p.cidade, p.fundo_codigo, f.titulo AS fundo_titulo
                              FROM projeto p LEFT JOIN fundo f ON f.codigo=p.fundo_codigo
                             WHERE p.fundo_codigo<>? AND p.mesclado_em IS NULL AND p.descartado_em IS NULL""", (fundo_codigo or "",)):
        score, motivos = pontuar(novo, {"titulo": p["titulo"], "ano": p["ano"], "cidade": p["cidade"]})
        if score >= NIVEL_FORTE:
            achados.append({"codigo": p["codigo"], "titulo": p["titulo"], "ano": p["ano"] or None, "cidade": p["cidade"], "fundo_codigo": p["fundo_codigo"],
                            "fundo_titulo": p["fundo_titulo"], "score": score, "motivos": motivos})
    achados.sort(key=lambda x: (-x["score"], x["codigo"]))
    return achados[:limite]


# ---------------- UX-01 · a pasta que chegou combina com o projeto de destino? ----------------
# O nome da PASTA (o que a estação/CAMP Vision gravou) traz sujeira que não diz qual é a obra: o código do projeto, o número local
# ("P0001 - …"), o ano ("1970-1971"), a contagem ("(37 folhas)") e o "— complemento de 26/10 (3 folhas)" do lote de complemento.
LIMIAR_PASTA = 0.5
_GENERICAS_PASTA = {"lote", "pasta", "scan", "scans", "digitalizacao", "material", "folhas", "folha", "novo", "nova"}
_LIMPA_PASTA = (
    (re.compile(r"\s+[—–-]\s+complemento\s+de\s+.*$", re.I), ""),
    (re.compile(r"\bF\d{3}[-_ ]?P\d{4}\b", re.I), " "),
    (re.compile(r"\bP\d{4}\b", re.I), " "),
    (re.compile(r"\(\s*\d+\s*(folhas?|arquivos?|imagens?|documentos?|docs?)\s*\)", re.I), " "),
    (re.compile(r"\b(1[6-9]|20)\d{2}\b"), " "),
)


# Falso alarme em produção (27/10): "RESIDENCIA LUIZ SALES, RUA ALBERTO FARIA LOTES 27 E 28 QUADRA 70 - ALTO DOS PINHEIROS" × F009-P0092
# "Residência Sr. Luiz Marcelo Sales" dava 0,14: o endereço (rua, lotes, quadra, bairro) enchia a pasta de palavras que o título não tem.
# O endereço só é cortado quando vem DEPOIS de um separador (vírgula, ";", " - ") e o trecho começa por rua/avenida/lote/quadra/nº…:
# o primeiro trecho (o nome) nunca é cortado, e "Edifício Rua Augusta" (sem separador) continua inteiro.
_SEPARADOR_PASTA = re.compile(r"\s*[,;]\s*|\s+[-–—]\s+")
_INICIO_ENDERECO = {"rua", "r", "av", "avenida", "alameda", "al", "praca", "pca", "travessa", "tv", "estrada", "rodovia", "rod", "largo",
                    "lote", "lotes", "lt", "quadra", "qd", "n", "no", "numero", "km"}
# tratamento de pessoa: não diz qual é a obra ("Residência Sr. Luiz…" × pasta "Residência Luiz…")
_TRATAMENTOS = {"sr", "sra", "srs", "sras", "srta", "dr", "dra", "drs", "eng", "arq", "prof", "profa", "dona", "dom"}


def _sem_endereco(t: str) -> str:
    partes = _SEPARADOR_PASTA.split(t)
    for i, parte in enumerate(partes[1:], start=1):
        pal = normalizar(parte).split()
        if pal and pal[0] in _INICIO_ENDERECO:
            nome = " ".join(partes[:i])
            # só corta se sobrar um nome de verdade: "Residência, Rua Groenlândia 300" fica inteiro (o endereço é o nome)
            return nome if any(w not in GENERICAS and w not in _GENERICAS_PASTA and w not in _TRATAMENTOS for w in tokens(nome)) else t
    return t


def limpar_nome_de_pasta(nome: str | None) -> str:
    t = str(nome or "").replace("_", " ")
    for rx, novo in _LIMPA_PASTA:
        t = rx.sub(novo, t)
    t = " ".join(t.split()).strip(" -–—.,;")
    return " ".join(_sem_endereco(t).split()).strip(" -–—.,;")


def tokens_de_pasta(nome: str | None) -> list[str]:
    """Palavras que dizem qual é a obra. Vazio = a pasta só tem código/número/ano ("P0001", "F026-P0030")."""
    ts = [w for w in tokens_distintivos(limpar_nome_de_pasta(nome)) if not (w.isdigit() and len(w) > 3)]
    return [w for w in dict.fromkeys(ts) if w not in _GENERICAS_PASTA and w not in _TRATAMENTOS]


def _mesma_palavra(a: str, b: str) -> bool:
    """Igual, ou erro de OCR/digitação em palavra de 4+ letras ("Franics" x "Francis")."""
    return a == b or (min(len(a), len(b)) >= 4 and SequenceMatcher(None, a, b).ratio() >= 0.8)


def compatibilidade_pasta(pasta: str | None, titulo: str | None) -> float | None:
    """0..1: o nome da pasta combina com o título do projeto? None = um dos dois não tem palavra para comparar.
    1.0 quando todas as palavras do nome MENOR estão no outro ("Banco Cidade" em "Residência Banco Cidade - Agência Matriz";
    "Jockey Club" em "Edifício Jockey Club São Paulo") ou quando a maioria das palavras distintivas do título está na pasta
    (_titulo_na_pasta); o endereço depois de vírgula/" - " (rua, lote, quadra, bairro…) não entra na conta; senão a fração de palavras em comum (Jaccard): "Clube Sírio" x "Clube Ipê" = 0,33.
    Número de designação conta como palavra ("Casa 2" x "Casa 1" = 0)."""
    a, b = tokens_de_pasta(pasta), tokens_de_pasta(titulo)
    if not a or not b:
        return None
    comuns = sum(1 for x in a if any(_mesma_palavra(x, y) for y in b))
    if comuns >= min(len(a), len(b)) or _titulo_na_pasta(a, b):
        return 1.0
    return round(comuns / (len(a) + len(b) - comuns), 3)


# Palavras que muitos nomes têm e que, sozinhas, não dizem qual é a obra: não contam para "o título está na pasta"
# ("Clube Ipê" × "Clube Atlético" não combina por causa de "Clube").
_FRACAS_PASTA = {"clube", "sociedade", "associacao", "cia", "companhia", "banco", "agencia", "igreja", "escola", "colegio", "hotel", "loja",
                 "instituto", "hospital", "fabrica", "garagem", "apartamentos", "torre", "bloco", "sao", "santo", "santa", "brasil", "paulo"}


def _titulo_na_pasta(pasta: list[str], titulo: list[str]) -> bool:
    """A MAIORIA das palavras distintivas do título está na pasta: pelo menos 2 e pelo menos 2/3 delas ("Luiz Marcelo Sales" →
    "Luiz" e "Sales" na pasta). Palavras fracas (clube, banco, são…) não contam; número de designação do título que falta na pasta
    impede ("Casa Luiz Sales 2" × pasta "Luiz Sales 1")."""
    fortes = [w for w in titulo if w not in _FRACAS_PASTA]
    if any(any(ch.isdigit() for ch in w) and w not in pasta for w in fortes):
        return False
    achadas = sum(1 for w in fortes if any(_mesma_palavra(w, x) for x in pasta))
    return achadas >= 2 and 3 * achadas >= 2 * len(fortes)


# palavras que todo nome de fundo pode ter e que não distinguem um do outro
_GENERICAS_FUNDO = {"acervo", "fundo", "arquiteto", "arquitetos", "arquitetura", "associados", "escritorio", "ltda", "familia", "colecao"}


def _nome_fundo(t: str | None) -> str:
    pal = [w for w in normalizar(t).split() if w not in _GENERICAS_FUNDO]
    return " ".join(pal) or normalizar(t)


def buscar_fundos_parecidos(con, titulo: str, limite: int = 3) -> list[dict]:
    """Antes de cadastrar um fundo novo: fundos com nome parecido (a MESMA nota de projeto_parecido), do mais para o menos parecido."""
    if not _nome_fundo(titulo):
        return []
    achados = []
    for f in con.execute("SELECT codigo, sigla, titulo, (SELECT COUNT(*) FROM projeto p WHERE p.fundo_codigo=fundo.codigo) AS projetos FROM fundo"):
        score, motivos = pontuar({"titulo": _nome_fundo(titulo)}, {"titulo": _nome_fundo(f["titulo"])})
        n = nivel(score)
        if n:
            achados.append({"codigo": f["codigo"], "sigla": f["sigla"], "titulo": f["titulo"], "projetos": f["projetos"],
                            "score": score, "nivel": n, "motivos": motivos})
    achados.sort(key=lambda x: (-x["score"], x["codigo"]))
    return achados[:limite]


# UX-15 · cidade: a mesma cidade escrita de jeitos diferentes ("São Paulo, SP" × "São Paulo" × "SAO PAULO"). Só SUGERE a forma mais
# usada no acervo (autocomplete na tela); o campo enviado ao site continua o mesmo texto livre (contrato com o site não muda).
_UF_NO_FIM = re.compile(r"\s*[,/–—-]?\s*\b(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\s*$")
_MINUSCULAS = {"de", "da", "do", "das", "dos", "e"}


def chave_cidade(cidade: str | None) -> str:
    """'São Paulo, SP', 'São Paulo - SP', 'SAO PAULO' → 'sao paulo'."""
    t = (cidade or "").strip()
    return normalizar(_UF_NO_FIM.sub("", t) if _UF_NO_FIM.sub("", t).strip() else t)


def cidade_sem_caixa_alta(cidade: str | None) -> str | None:
    """'ALTO DE PINHEIROS' → 'Alto de Pinheiros' (mantém a sigla do estado). None quando o texto não está todo em maiúsculas."""
    t = " ".join((cidade or "").split())
    letras = [c for c in t if c.isalpha()]
    if len(letras) < 4 or not all(c.isupper() for c in letras):
        return None
    uf = _UF_NO_FIM.search(t)
    base, fim = (t[:uf.start()], t[uf.start():]) if uf and t[:uf.start()].strip() else (t, "")
    pal = [w.lower() if (i and w.lower() in _MINUSCULAS) else w.capitalize() for i, w in enumerate(base.split())]
    return " ".join(pal) + fim


def cidades_do_acervo(con) -> list[dict]:
    """As cidades dos projetos agrupadas pela chave, com a forma mais usada como sugestão (empate: a que traz o estado)."""
    grupos: dict[str, dict[str, int]] = {}
    for cid, n in con.execute("""SELECT TRIM(cidade), COUNT(*) FROM projeto WHERE TRIM(COALESCE(cidade,''))<>''
                                    AND mesclado_em IS NULL AND descartado_em IS NULL GROUP BY TRIM(cidade)"""):
        k = chave_cidade(cid)
        if k:
            grupos.setdefault(k, {})[cid] = n
    out = []
    for k, formas in grupos.items():
        boas = {f: n for f, n in formas.items() if not cidade_sem_caixa_alta(f)} or {cidade_sem_caixa_alta(f): n for f, n in formas.items()}
        canon = max(boas, key=lambda f: (boas[f], bool(_UF_NO_FIM.search(f)), f))
        out.append({"chave": k, "cidade": canon, "projetos": sum(formas.values()),
                    "variantes": [{"cidade": f, "projetos": n} for f, n in sorted(formas.items(), key=lambda x: -x[1]) if f != canon]})
    out.sort(key=lambda x: (-x["projetos"], x["cidade"]))
    return out


def sugerir_cidade(con, cidade: str | None) -> str | None:
    """A forma do acervo para a cidade digitada, quando é diferente dela (ou a versão sem caixa alta). None quando já está boa."""
    t = " ".join((cidade or "").split())
    if not t:
        return None
    k = chave_cidade(t)
    for g in cidades_do_acervo(con):
        if g["chave"] == k:
            return g["cidade"] if g["cidade"] != t else None
    return cidade_sem_caixa_alta(t)
