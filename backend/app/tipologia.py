"""B3 · Classificação do projeto com o vocabulário do site (programa/uso, natureza, modalidade, situação da obra).

No site são 4 taxonomias do Tainacan ligadas à coleção Projetos ("Tipologia — …", criadas pelo plugin
camp-acervo-auto-pages, class-tipologia.php) com termos FECHADOS (allow_new_terms = no). O painel usa os termos do
espelho (wp_termo, com os ids do site); sem espelho, usa a cópia abaixo (a mesma lista do plugin, 13/10/2026).
No projeto, cada faceta fica numa coluna de texto com os nomes separados por "; ".
"""
from __future__ import annotations

import unicodedata

# chave: (coluna do projeto, rótulo, taxonomia no site, metadado na coleção Projetos, aceita mais de um)
FACETAS = {
    "programa": ("tipologia", "Programa / uso", "Tipologia — Programa / uso", "Programa / uso", True),
    "natureza": ("natureza", "Natureza do trabalho", "Tipologia — Natureza do trabalho", "Natureza do trabalho", True),
    "modalidade": ("modalidade", "Modalidade", "Tipologia — Modalidade", "Modalidade", True),
    "situacao": ("situacao_obra", "Situação da obra", "Tipologia — Situação da obra", "Situação da obra", False),
}
COLUNAS = {v[0]: k for k, v in FACETAS.items()}

PADRAO = {
    "programa": [
        ('Habitação', ['Residência unifamiliar', 'Casa de praia', 'Casa de campo', 'Casa de veraneio', 'Sobrado / casas geminadas', 'Edícula', 'Vila / condomínio horizontal', 'Edifício residencial', 'Conjunto habitacional', 'Habitação social']),
        ('Hospedagem', ['Hotel', 'Apart-hotel / flat', 'Pousada', 'Albergue / abrigo', 'Alojamento', 'Colônia de férias', 'Camping']),
        ('Comércio', ['Loja', 'Galeria comercial', 'Centro comercial', 'Shopping', 'Supermercado', 'Mercado municipal', 'Concessionária', 'Showroom', 'Restaurante', 'Restaurante popular', 'Bar / café', 'Posto de combustível']),
        ('Escritórios e serviços', ['Escritórios', 'Edifício corporativo', 'Agência bancária', 'Cartório', 'Correios', 'Gráfica', 'Oficina', 'Ateliê', 'Estúdio de gravação', 'Estúdio de TV / rádio', 'Clínica veterinária']),
        ('Saúde', ['Hospital', 'Hospital psiquiátrico', 'Maternidade', 'Pronto-socorro', 'Clínica', 'Consultório', 'Ambulatório', 'Unidade básica de saúde', 'Centro de reabilitação', 'Sanatório', 'Laboratório']),
        ('Assistência social', ['Asilo / casa de repouso', 'Orfanato', 'Centro comunitário', 'Centro de convivência']),
        ('Educação', ['Creche', 'Jardim de infância', 'Pré-escola', 'Escola', 'Escola técnica', 'Escola de artes', 'Escola de música', 'Internato', 'CEU', 'Faculdade', 'Universidade', 'Campus universitário']),
        ('Pesquisa e ciência', ['Centro de pesquisa', 'Instituto', 'Observatório', 'Planetário']),
        ('Cultura', ['Museu', 'Centro cultural', 'Galeria de arte', 'Biblioteca', 'Arquivo', 'Teatro', 'Cinema', 'Auditório', 'Sala de concertos', 'Centro de convenções', 'Pavilhão de exposições', 'SESC']),
        ('Esporte e lazer', ['Clube social', 'Clube esportivo', 'Clube de campo', 'Iate clube', 'Ginásio', 'Estádio', 'Quadra / campo esportivo', 'Piscina / centro aquático', 'Autódromo', 'Hipódromo', 'Playground', 'Parque de diversões', 'Zoológico', 'Pesqueiro']),
        ('Religioso e funerário', ['Igreja', 'Capela', 'Templo', 'Sinagoga', 'Mesquita', 'Centro espírita', 'Terreiro', 'Convento', 'Mosteiro', 'Seminário', 'Cemitério', 'Crematório', 'Mausoléu', 'Memorial']),
        ('Institucional e governo', ['Sede administrativa', 'Repartição pública', 'Posto de atendimento público', 'Paço municipal', 'Câmara municipal', 'Assembleia legislativa', 'Palácio de governo', 'Fórum', 'Tribunal', 'Embaixada', 'Consulado', 'Sede de associação', 'Sede de sindicato']),
        ('Segurança', ['Delegacia', 'Quartel', 'Corpo de bombeiros', 'Penitenciária', 'Presídio']),
        ('Indústria e logística', ['Fábrica', 'Galpão', 'Armazém', 'Depósito', 'Centro de distribuição', 'Frigorífico', 'Silo', 'Usina']),
        ('Transporte', ['Aeroporto', 'Rodoviária', 'Terminal de ônibus', 'Estação de metrô', 'Estação ferroviária', 'Terminal marítimo', 'Porto', 'Marina', 'Estacionamento', 'Edifício-garagem', 'Praça de pedágio']),
        ('Infraestrutura', ['Ponte', 'Viaduto', 'Passarela', 'Túnel', 'Barragem', "Caixa-d'água / reservatório", 'Estação de tratamento de água', 'Estação de tratamento de esgoto', 'Subestação', 'Usina de lixo', 'Torre de telecomunicações']),
        ('Rural', ['Sede de fazenda', 'Casa de colono', 'Tulha', 'Paiol', 'Curral', 'Estábulo', 'Haras', 'Aviário / granja']),
        ('Espaço público e paisagem', ['Praça', 'Parque', 'Jardim', 'Jardim botânico', 'Boulevard / calçadão', 'Mirante', 'Monumento', 'Arte pública']),
        ('Urbanismo', ['Loteamento', 'Requalificação urbana', 'Plano diretor', 'Cidade nova']),
        ('Uso misto', ['Edifício multiuso', 'Conjunto multifuncional']),
        ('Design, mobiliário e exposições', ['Mobiliário', 'Luminária', 'Expografia', 'Stand / cenografia']),
    ],
    "natureza": [
        ('Edificação (obra nova)', []),
        ('Reforma / ampliação', []),
        ('Restauro / intervenção em patrimônio', []),
        ('Interiores', []),
        ('Mobiliário e design', []),
        ('Paisagismo', []),
        ('Desenho urbano', []),
        ('Planejamento urbano e regional', []),
        ('Comunicação visual / sinalização', []),
    ],
    "modalidade": [
        ('Concurso', ['Concurso premiado', 'Concurso com menção', 'Concurso não premiado']),
        ('Encomenda privada', []),
        ('Encomenda pública', []),
        ('Estudo / iniciativa própria', []),
        ('Projeto acadêmico / pesquisa', []),
    ],
    "situacao": [
        ('Construída', []),
        ('Construída com alterações', []),
        ('Demolida', []),
        ('Não construída', []),
        ('Não identificada', []),
    ],
}


def _norm(t: str) -> str:
    return " ".join(unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower().split())


def separar(valor: str | None) -> list[str]:
    vistos, out = set(), []
    for x in str(valor or "").replace(",", ";").split(";"):
        x = x.strip()
        if x and _norm(x) not in vistos:
            vistos.add(_norm(x)); out.append(x)
    return out


def vocabulario(con) -> dict:
    """{chave: {rotulo, multiplo, origem, grupos: [{nome, id, filhos: [{nome, id}]}]}}: do espelho do site quando há termos."""
    out = {}
    for chave, (_col, rotulo, tax, _meta, multiplo) in FACETAS.items():
        grupos = []
        t = con.execute("SELECT id FROM wp_taxonomia WHERE nome=?", (tax,)).fetchone()
        termos = con.execute("SELECT id, nome, pai_id FROM wp_termo WHERE taxonomia_id=? ORDER BY nome", (t[0],)).fetchall() if t else []
        if termos:
            pais = [x for x in termos if not x["pai_id"]]
            for p in pais:
                grupos.append({"nome": p["nome"], "id": p["id"], "filhos": [{"nome": f["nome"], "id": f["id"]} for f in termos if f["pai_id"] == p["id"]]})
            ordem = {_norm(g): i for i, (g, _f) in enumerate(PADRAO[chave])}
            grupos.sort(key=lambda g: (ordem.get(_norm(g["nome"]), 999), g["nome"]))
            origem = "site"
        else:
            grupos = [{"nome": g, "id": None, "filhos": [{"nome": f, "id": None} for f in fs]} for g, fs in PADRAO[chave]]
            origem = "copia"
        out[chave] = {"rotulo": rotulo, "multiplo": multiplo, "origem": origem, "grupos": grupos}
    return out


def _termos(voc: dict, chave: str) -> dict:
    d = {}
    for g in voc[chave]["grupos"]:
        d[_norm(g["nome"])] = (g["nome"], g["id"])
        for f in g["filhos"]:
            d.setdefault(_norm(f["nome"]), (f["nome"], f["id"]))
    return d


def validar(con, chave: str, valor: str | None, voc: dict | None = None) -> str:
    """Devolve o valor com os nomes exatos do vocabulário ("; " entre eles) ou ValueError com o que não existe."""
    voc = voc or vocabulario(con)
    termos, nomes, fora = _termos(voc, chave), [], []
    for x in separar(valor):
        t = termos.get(_norm(x))
        (nomes if t else fora).append(t[0] if t else x)
    if fora:
        raise ValueError(f"{FACETAS[chave][1]}: “{'”, “'.join(fora)}” não está na lista do site")
    if nomes and not FACETAS[chave][4] and len(nomes) > 1:
        raise ValueError(f"{FACETAS[chave][1]}: escolha só um")
    return "; ".join(nomes)


def ids_do_site(con, chave: str, valor: str | None) -> list[int] | None:
    """Ids dos termos no site para gravar no metadado de taxonomia; None se algum nome não está no espelho."""
    termos = _termos(vocabulario(con), chave)
    ids = []
    for x in separar(valor):
        t = termos.get(_norm(x))
        if not t or not t[1]:
            return None
        ids.append(t[1])
    return ids
