"""11/11 · "Completar a ficha" em etapas (Rafael: "precisamos gamificar isso, porque não estão preenchendo tudo que precisa corretamente;
faz em etapas: quando começa, depois das folhas já irmos para tipo de habitação etc., com as respostas mais frequentes primeiro").

Uma pergunta por vez, na ordem dos objetivos do projeto (publicacao.METAS_DADOS): tipo da obra (programa / uso), natureza, modalidade,
situação da obra, ano e cidade. Cada pergunta traz as respostas MAIS USADAS primeiro: as do mesmo fundo (o arquiteto costuma repetir o
tipo de obra) e, depois, as do acervo todo. Os termos das 4 facetas são só os da lista do site (tipologia.vocabulario); nada é inventado.
Só lê: a resposta é gravada pela rota de sempre (PATCH /api/projetos/{codigo}), com a validação de sempre.
"""
from __future__ import annotations

import re
from collections import Counter

from . import tipologia as tp

# (id, coluna, chave da faceta ou None, pergunta, ajuda, tipo)
PERGUNTAS = (
    ("programa", "tipologia", "programa", "Qual é o tipo da obra?", "Programa / uso: residência, edifício residencial, escola, igreja…", "lista"),
    ("natureza", "natureza", "natureza", "O que foi feito?", "Natureza do trabalho: obra nova, reforma, restauro, interiores…", "lista"),
    ("modalidade", "modalidade", "modalidade", "Como o projeto nasceu?", "Modalidade: encomenda privada ou pública, concurso, estudo próprio…", "lista"),
    ("situacao_obra", "situacao_obra", "situacao", "A obra foi construída?", "Situação da obra hoje.", "lista"),
    ("ano", "ano", None, "De que ano é o projeto?", "O ano do projeto (não o da digitalização). Sem data: pule.", "ano"),
    ("cidade", "cidade", None, "Em que cidade fica a obra?", "Só a cidade (o endereço fica na edição do projeto).", "texto"),
)
MAX_FREQ = 8
VIVO = "mesclado_em IS NULL AND descartado_em IS NULL AND fundo_codigo<>'F000'"
_ANO_CODIGO = re.compile(r"^F\d{3}-P\d{4}-(\d{4})-S\d{2}-D\d+$")


def _vazio(v) -> bool:
    return v in (None, "", 0, "0")


def _frequentes(con, coluna: str, fundo: str, termos: dict | None) -> list[dict]:
    """[{nome, n, n_fundo}] da coluna nos projetos vivos: primeiro o que o fundo mais usa, depois o acervo todo."""
    tot, fun = Counter(), Counter()
    for valor, f in con.execute(f"SELECT {coluna}, fundo_codigo FROM projeto WHERE {VIVO} AND COALESCE({coluna},'')<>''"):
        nomes = tp.separar(valor) if termos is not None else [str(valor).strip()]
        for x in nomes:
            if termos is not None:
                t = termos.get(tp._norm(x))
                if not t:
                    continue                      # fora da lista do site: não vira sugestão
                x = t[0]
            if not x:
                continue
            tot[x] += 1
            if f == fundo:
                fun[x] += 1
    ordem = sorted(tot, key=lambda x: (-fun[x], -tot[x], x))
    return [{"nome": x, "n": tot[x], "n_fundo": fun[x]} for x in ordem[:MAX_FREQ]]


def _primeiros_da_lista(voc: dict, chave: str) -> list[dict]:
    """Acervo sem uso ainda: os primeiros termos da lista do site (o grupo e os filhos dele)."""
    out = []
    for g in voc[chave]["grupos"]:
        filhos = [f["nome"] for f in g["filhos"]] if chave == "programa" else []    # tipo da obra: os termos finos; as outras: o grupo
        for nome in (filhos or [g["nome"]]):
            out.append({"nome": nome, "n": 0, "n_fundo": 0})
            if len(out) >= MAX_FREQ:
                return out
    return out


def _ano_das_folhas(con, codigo: str) -> list[dict]:
    """O ano que vem no código das folhas (F0xx-P0yyy-AAAA-…), o mais frequente primeiro (0 = sem data não conta)."""
    anos = Counter()
    for (c,) in con.execute("SELECT codigo FROM item WHERE projeto_codigo=?", (codigo,)):
        m = _ANO_CODIGO.match(c or "")
        if m and m.group(1) != "0000":
            anos[m.group(1)] += 1
    return [{"nome": a, "n": n, "n_fundo": 0, "das_folhas": True} for a, n in anos.most_common(3)]


def etapas(con, codigo: str) -> dict | None:
    p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
    if not p:
        return None
    voc = tp.vocabulario(con)
    out = []
    for id_, col, chave, pergunta, ajuda, tipo in PERGUNTAS:
        e = {"id": id_, "coluna": col, "pergunta": pergunta, "ajuda": ajuda, "tipo": tipo, "feito": not _vazio(p[col]),
             "atual": tp.separar(p[col]) if chave else ([] if _vazio(p[col]) else [str(p[col])])}
        if chave:
            termos = tp._termos(voc, chave)
            e["faceta"], e["multiplo"] = chave, bool(voc[chave]["multiplo"])
            e["frequentes"] = _frequentes(con, col, p["fundo_codigo"], termos) or _primeiros_da_lista(voc, chave)
        elif tipo == "ano":
            e["frequentes"] = _ano_das_folhas(con, codigo)
        else:
            e["frequentes"] = _frequentes(con, col, p["fundo_codigo"], None)
        out.append(e)
    faltam = sum(1 for e in out if not e["feito"])
    return {"codigo": codigo, "titulo": p["titulo"], "etapas": out, "faltam": faltam, "total": len(out)}
