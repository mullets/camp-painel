"""Visitas ao site: evolução das visitas e projetos mais visitados (especificação do Rafael, 04/11/2026).

Só LÊ o banco do painel (o que o coletor diário de visitas.py guardou do Google Analytics): nenhuma chamada ao Google por tela aberta.

Métricas (não são sinônimos — a tela diz qual é qual):
- Evolução: "Visitas" = SESSÕES do site público (visita_dia.sessoes; GA4 `sessions`, filtrado pelo domínio ga4.dominio quando a coleta
  é pela conta de serviço — o painel não tem a tag do Google, então visita ao painel nunca entra).
- Ranking de projetos: "visualizações da página do projeto" (visita_dimensao tipo 'pagina', GA4 `screenPageViews` por pagePath).

Período: o dia vem da dimensão `date` do GA4 (fuso da propriedade; a da CAMP é America/Sao_Paulo). "Hoje" é calculado em São Paulo e os
períodos prontos terminam ONTEM (o dia de hoje ainda não terminou). Comparação: o período imediatamente anterior, de mesma duração.
Dia fora do que foi sincronizado = SEM DADO (None), nunca zero; dia sincronizado sem linha = 0 (o GA4 não devolve dia sem visita).

Identificação de projeto (só o vínculo REAL, nunca pelo título):
- item do projeto no espelho do site: projeto.tainacan_item_id → wp_item.id (ID do Tainacan) → wp_item.url em /acervo/projetos/;
- página do projeto no espelho do site (wp_pagina, ID da página do site) em /acervo/projetos/<slug>/ cujo slug começa pelo código
  do projeto (o site monta esse slug a partir do código do item, que é imutável no painel) e o código existe no painel;
- projeto.url_publica_confirmada (o painel perguntou ao site e o endereço abriu);
- redirecionamentos de projeto (recodificar/mesclar: o site responde 301 do endereço antigo para o novo) e projeto mesclado → destino.
Endereço ligado a dois projetos diferentes não é atribuído a nenhum. Página em /acervo/projetos/<algo>/ sem vínculo (ou com código de
projeto no endereço) = "não identificada" (para investigar); o resto (home, arquitetos, fundos, listagens, busca, documentos, notícias…)
fica fora do ranking.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import date, datetime, timedelta
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")
PERIODOS = {"7d": 7, "30d": 30, "90d": 90}
MAX_DIAS = 1100
DIAS_DIARIO = 92          # até ~3 meses: um ponto por dia; até 2 anos: por semana (7 dias a partir do início); acima: por mês
DIAS_SEMANAL = 731
METRICA_EVOLUCAO = {"chave": "sessoes", "nome": "Visitas",
                    "definicao": "Visitas = sessões no site público (camp.arq.br) segundo o Google Analytics: cada vez que alguém entra "
                                 "no site conta uma visita, mesmo que veja várias páginas. Acessos ao painel não entram."}
METRICA_RANKING = {"chave": "visualizacoes", "nome": "Visualizações da página do projeto",
                   "definicao": "Cada vez que a página pública de um projeto foi aberta (visualizações de página no Google Analytics). "
                                "É uma medida diferente das visitas do gráfico: uma visita pode abrir várias páginas."}
RE_PROJ = re.compile(r"^F\d{3}-P\d{4}$")
RE_COD_NO_CAMINHO = re.compile(r"(?<![a-z0-9])f\d{3}-p\d{4}(?![0-9])", re.I)
BASE_PROJETOS = "/acervo/projetos/"
LISTAGEM = {"page", "feed", "amp"}


def hoje_sp() -> date:
    return datetime.now(FUSO).date()


# ---------------------------------------------------------------- período
def intervalo(periodo: str | None, de: str | None, ate: str | None, hoje: date | None = None) -> dict:
    """{de, ate, dias, periodo, ontem, ajustado}. Levanta ValueError com a mensagem para a tela."""
    hoje = hoje or hoje_sp()
    ontem = hoje - timedelta(days=1)
    periodo = periodo or ("livre" if de and ate else "30d")
    ajustado = False
    if periodo in PERIODOS:
        a = ontem
        d = a - timedelta(days=PERIODOS[periodo] - 1)
    elif periodo == "livre":
        try:
            d, a = date.fromisoformat(str(de)), date.fromisoformat(str(ate))
        except ValueError:
            raise ValueError("Datas no formato AAAA-MM-DD")
        if a > ontem:                      # o dia de hoje ainda não terminou: o intervalo para em ontem
            a, ajustado = ontem, True
        if d > a:
            raise ValueError("A data inicial é depois da final (o período termina, no máximo, ontem)")
        if (a - d).days + 1 > MAX_DIAS:
            raise ValueError(f"Escolha um intervalo de até {MAX_DIAS} dias")
    else:
        raise ValueError("Escolha um período: 7d, 30d, 90d ou livre (de/ate)")
    return {"periodo": periodo, "de": d.isoformat(), "ate": a.isoformat(), "dias": (a - d).days + 1, "ontem": ontem.isoformat(),
            "hoje": hoje.isoformat(), "ajustado": ajustado, "fuso": "America/Sao_Paulo"}


def anterior(de: str, ate: str) -> tuple[str, str]:
    d, a = date.fromisoformat(de), date.fromisoformat(ate)
    n = (a - d).days + 1
    return (d - timedelta(days=n)).isoformat(), (d - timedelta(days=1)).isoformat()


def _dias(de: str, ate: str) -> list[str]:
    d, a = date.fromisoformat(de), date.fromisoformat(ate)
    return [(d + timedelta(days=i)).isoformat() for i in range((a - d).days + 1)]


# ---------------------------------------------------------------- sincronização (o "cache" é o próprio banco)
def sincronizacao(con) -> dict:
    """A última sincronização do Google Analytics (ok ou com erro) e a última que deu certo."""
    ult = con.execute("SELECT id, inicio, fim, de, ate, linhas, erro FROM visita_coleta WHERE fonte='ga4' ORDER BY id DESC LIMIT 1").fetchone()
    ok = con.execute("SELECT id, inicio, fim, de, ate FROM visita_coleta WHERE fonte='ga4' AND erro IS NULL AND fim IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    tem_dado = con.execute("SELECT 1 FROM visita_dia LIMIT 1").fetchone() is not None
    return {"ultima": dict(ult) if ult else None, "ultima_ok": dict(ok) if ok else None,
            "falhou": bool(ult and ult["erro"]), "nunca": not ok and not tem_dado}


def _cobertos(con, de: str, ate: str) -> set[str]:
    """Dias deste intervalo que o painel já sincronizou (coleta do GA4 que deu certo) ou que têm linha guardada."""
    faixas = [(r[0], r[1]) for r in con.execute(
        "SELECT de, ate FROM visita_coleta WHERE fonte='ga4' AND erro IS NULL AND fim IS NOT NULL AND ate>=? AND de<=?", (de, ate))]
    out = {r[0] for r in con.execute("SELECT dia FROM visita_dia WHERE dia BETWEEN ? AND ?", (de, ate))}
    for d in _dias(de, ate):
        if d not in out and any(a <= d <= b for a, b in faixas):
            out.add(d)
    return out


def _estado(sinc: dict, dias_cobertos: int, total: int) -> str:
    if sinc["nunca"]:
        return "indisponivel"
    if not dias_cobertos:
        return "indisponivel" if sinc["falhou"] else "sem_dados"
    return "ok" if total else "sem_dados"


# ---------------------------------------------------------------- evolução
def _agrupar(serie: list[tuple[str, int | None]], modo: str) -> list[dict]:
    if modo == "dia":
        return [{"inicio": d, "fim": d, "visitas": v} for d, v in serie]
    grupos: list[list] = []
    for i, (d, v) in enumerate(serie):
        novo = (i % 7 == 0) if modo == "semana" else (not grupos or grupos[-1][0][0][:7] != d[:7])
        if novo:
            grupos.append([])
        grupos[-1].append((d, v))
    out = []
    for g in grupos:
        vals = [v for _, v in g if v is not None]
        out.append({"inicio": g[0][0], "fim": g[-1][0], "visitas": sum(vals) if vals else None,
                    "parcial": len(vals) < len(g) or (modo == "semana" and len(g) < 7)})
    return out


def _serie(con, de: str, ate: str) -> tuple[list[tuple[str, int | None]], set[str]]:
    cob = _cobertos(con, de, ate)
    val = {r[0]: int(r[1] or 0) for r in con.execute("SELECT dia, sessoes FROM visita_dia WHERE dia BETWEEN ? AND ?", (de, ate))}
    return [(d, (val.get(d, 0) if d in cob else None)) for d in _dias(de, ate)], cob


def _variacao(atual: int, antes: int | None, comparavel: bool) -> dict:
    if not comparavel or antes is None:
        return {"disponivel": False, "motivo": "sem_dados_anterior", "absoluta": None, "percentual": None, "base_zero": False}
    if antes == 0:
        return {"disponivel": True, "motivo": "base_zero", "absoluta": atual, "percentual": None, "base_zero": True}
    return {"disponivel": True, "motivo": None, "absoluta": atual - antes, "percentual": round((atual - antes) / antes * 100, 1), "base_zero": False}


def evolucao(con, per: dict, comparar: bool = False) -> dict:
    de, ate, n = per["de"], per["ate"], per["dias"]
    modo = "dia" if n <= DIAS_DIARIO else "semana" if n <= DIAS_SEMANAL else "mes"
    serie, cob = _serie(con, de, ate)
    total = sum(v for _, v in serie if v is not None)
    dias_cob = len(cob)
    ade, aate = anterior(de, ate)
    serie_a, cob_a = _serie(con, ade, aate)
    total_a = sum(v for _, v in serie_a if v is not None)
    comparavel = dias_cob == n and len(cob_a) == n          # só compara período inteiro com período inteiro
    sinc = sincronizacao(con)
    pontos = _agrupar(serie, modo)
    com_valor = [p for p in pontos if p["visitas"]]
    pico = max(com_valor, key=lambda p: p["visitas"]) if com_valor else None
    out = {**per, "metrica": METRICA_EVOLUCAO, "agregacao": modo, "pontos": pontos, "total": total if dias_cob else None,
           "dias_com_dados": dias_cob, "media_dia": round(total / dias_cob, 1) if dias_cob else None,
           "completo": dias_cob == n, "variacao": _variacao(total, total_a if len(cob_a) else None, comparavel),
           "anterior": {"de": ade, "ate": aate, "total": total_a if len(cob_a) == n else None, "dias_com_dados": len(cob_a)},
           "pico": {"inicio": pico["inicio"], "fim": pico["fim"], "visitas": pico["visitas"]} if pico else None,
           "sincronizacao": sinc, "estado": _estado(sinc, dias_cob, total)}
    if comparar:
        out["anterior"]["pontos"] = _agrupar(serie_a, modo)
    return out


# ---------------------------------------------------------------- identificação das páginas
def normalizar(url: str | None) -> str:
    """Caminho comparável de um endereço do site: sem domínio, sem query (parâmetros de rastreamento como utm_*, fbclid, gclid) e sem
    fragmento; %xx decodificado; barras repetidas juntas; minúsculas (o WordPress resolve o caminho de página sem diferenciar maiúsculas);
    sempre com barra no fim (o site responde as duas formas com a mesma página). Não junta caminhos diferentes."""
    s = str(url or "").strip()
    if not s or s.lower() in ("(not set)", "(não informado)"):
        return ""
    if "://" in s:
        s = urlsplit(s).path or "/"
    s = s.split("#", 1)[0].split("?", 1)[0]
    s = unquote(s)
    s = re.sub(r"/{2,}", "/", "/" + s.lstrip("/")).lower()
    if not s.endswith("/") and not re.search(r"\.[a-z0-9]{2,5}$", s):
        s += "/"
    return s


def _final(cod: str, mesclado: dict, redir: dict) -> str:
    visto = {cod}
    for _ in range(30):
        nxt = mesclado.get(cod) or redir.get(cod)
        if not nxt or nxt in visto:
            break
        cod = nxt
        visto.add(cod)
    return cod


def mapa_projetos(con) -> dict:
    """{"mapa": caminho → código, "conflitos": caminhos ligados a mais de um projeto, "url": código → endereço público real}."""
    projetos = {r["codigo"]: r for r in con.execute("SELECT codigo, mesclado_em, tainacan_item_id, url_publica_confirmada FROM projeto")}
    mesclado = {c: r["mesclado_em"] for c, r in projetos.items() if r["mesclado_em"]}
    redir = {r[0]: r[1] for r in con.execute("SELECT codigo_antigo, codigo_novo FROM redirecionamento WHERE entidade='projeto'")}
    mapa: dict[str, str] = {}
    conflitos: set[str] = set()
    url: dict[str, tuple[int, str]] = {}

    def add(endereco: str, cod: str, peso: int) -> None:
        p = normalizar(endereco)
        if not p.startswith(BASE_PROJETOS) or p == BASE_PROJETOS:
            return
        cod = _final(cod, mesclado, redir)
        if cod not in projetos:
            return
        if mapa.get(p, cod) != cod:
            conflitos.add(p)
        mapa.setdefault(p, cod)
        if "://" in endereco and (cod not in url or peso < url[cod][0]):
            url[cod] = (peso, endereco)

    for r in con.execute("""SELECT p.codigo, w.url, w.status FROM projeto p JOIN wp_item w ON w.id=p.tainacan_item_id
                             WHERE w.url LIKE '%/acervo/projetos/%'"""):
        add(r["url"], r["codigo"], 1 if r["status"] == "publish" else 3)
    for r in con.execute("SELECT id, slug, url, status, codigo_detectado FROM wp_pagina WHERE url LIKE '%/acervo/projetos/%' AND codigo_detectado IS NOT NULL"):
        cod, slug = str(r["codigo_detectado"]).upper(), str(r["slug"] or "").lower()
        if not RE_PROJ.match(cod) or not (slug == cod.lower() or slug.startswith(cod.lower() + "-")):
            continue
        p = normalizar(r["url"])
        if p.count("/") != 4:            # /acervo/projetos/<slug>/ — a página do projeto, não uma subpágina
            continue
        if cod in projetos or cod in redir:
            add(r["url"], cod, 0 if r["status"] == "publish" else 2)
    for c, r in projetos.items():
        if r["url_publica_confirmada"]:
            add(r["url_publica_confirmada"], c, 4)
    for r in con.execute("SELECT codigo_antigo, codigo_novo, url_antiga FROM redirecionamento WHERE entidade='projeto' AND url_antiga IS NOT NULL"):
        add(r["url_antiga"], r["codigo_novo"], 9)
    for p in conflitos:
        mapa.pop(p, None)
    return {"mapa": mapa, "conflitos": conflitos, "url": {c: u for c, (_, u) in url.items()}}


def classificar(caminho: str, m: dict) -> tuple[str, str | None]:
    """('projeto', código) · ('nao_identificada', motivo) · ('outra', None)."""
    if caminho in m["conflitos"]:
        return "nao_identificada", "Este endereço está ligado a mais de um projeto no espelho do site: nenhum recebe estas visualizações."
    if caminho in m["mapa"]:
        return "projeto", m["mapa"][caminho]
    resto = caminho[len(BASE_PROJETOS):].strip("/").split("/") if caminho.startswith(BASE_PROJETOS) else []
    cod = RE_COD_NO_CAMINHO.search(caminho)
    if resto and resto[0] and resto[0] not in LISTAGEM:
        if cod:
            return "nao_identificada", f"O endereço tem o código {cod.group(0).upper()}, mas o espelho do site não liga esta página a esse projeto (sincronize o site ou confira o endereço)."
        return "nao_identificada", "Página de projeto sem vínculo com um projeto do painel."
    if cod and not caminho.startswith("/acervo/documentos/"):
        return "nao_identificada", f"O endereço tem o código {cod.group(0).upper()}, mas não é a página pública do projeto."
    return "outra", None


def _paginas(con, de: str, ate: str) -> list:
    return con.execute("""SELECT valor, MAX(extra) AS extra, SUM(visualizacoes) AS v FROM visita_dimensao
                           WHERE tipo='pagina' AND dia BETWEEN ? AND ? GROUP BY valor""", (de, ate)).fetchall()


def _sem_acento(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", str(s or "").lower()) if unicodedata.category(ch) != "Mn")


def _foto(con, codigo: str) -> str | None:
    """A capa do projeto (folha escolhida, se for mesmo deste projeto); senão a primeira folha publicada do projeto com imagem; senão nada."""
    r = con.execute("""SELECT i.codigo FROM projeto p JOIN item i ON i.codigo=p.capa_item AND i.projeto_codigo=p.codigo WHERE p.codigo=?""", (codigo,)).fetchone()
    if r:
        return r[0]
    r = con.execute("""SELECT codigo FROM item WHERE projeto_codigo=? AND status_site='no_ar' AND duplicata_de IS NULL
                         AND (arquivo_jpg IS NOT NULL OR pendencias LIKE '%previa%') ORDER BY serie_codigo, sequencial LIMIT 1""", (codigo,)).fetchone()
    return r[0] if r else None


def _autoria(r) -> dict | None:
    """Autoria do projeto quando cadastrada; senão só o acervo (fundo) a que pertence — nunca o titular como autor não confirmado."""
    a = "; ".join(x.strip() for x in re.split(r"[;\n]+", r["autoria"] or "") if x.strip())
    if a:
        return {"texto": a.replace("; ", ", "), "tipo": "autoria"}
    if r["fundo"]:
        return {"texto": f"Acervo {r['fundo']}", "tipo": "acervo"}
    return None


def projetos(con, per: dict, ordem: str = "mais", busca: str = "", limite: int = 10, site: str = "https://camp.arq.br",
             fundo: str = "", autor: str = "") -> dict:
    if ordem not in ("mais", "menos", "crescimento"):
        raise ValueError("Ordem: mais, menos ou crescimento")
    de, ate = per["de"], per["ate"]
    ade, aate = anterior(de, ate)
    m = mapa_projetos(con)
    cob, cob_a = _cobertos(con, de, ate), _cobertos(con, ade, aate)
    comparavel = len(cob) == per["dias"] and len(cob_a) == per["dias"]
    por: dict[str, dict] = {}
    ni: dict[str, dict] = {}
    outras = {"visualizacoes": 0, "paginas": 0}
    for r in _paginas(con, de, ate):
        cam = normalizar(r["valor"])
        tipo, x = classificar(cam, m)
        v = int(r["v"] or 0)
        if tipo == "projeto":
            d = por.setdefault(x, {"v": 0, "caminhos": {}})
            d["v"] += v
            d["caminhos"][r["valor"]] = d["caminhos"].get(r["valor"], 0) + v
        elif tipo == "nao_identificada":
            d = ni.setdefault(cam, {"caminho": cam, "titulo": None, "visualizacoes": 0, "motivo": x, "enderecos": []})
            d["visualizacoes"] += v
            d["titulo"] = d["titulo"] or (r["extra"] if r["extra"] and r["extra"] != "(not set)" else None)
            if r["valor"] not in d["enderecos"]:
                d["enderecos"].append(r["valor"])
        else:
            outras["visualizacoes"] += v
            outras["paginas"] += 1
    antes: dict[str, int] = {}
    for r in _paginas(con, ade, aate):
        tipo, x = classificar(normalizar(r["valor"]), m)
        if tipo == "projeto":
            antes[x] = antes.get(x, 0) + int(r["v"] or 0)
    itens = []
    if por:
        marc = ",".join("?" * len(por))
        info = {r["codigo"]: r for r in con.execute(f"""SELECT p.codigo, p.titulo, p.ano, p.ano_fim, p.autoria, p.fundo_codigo, f.titulo AS fundo
                                                          FROM projeto p LEFT JOIN fundo f ON f.codigo=p.fundo_codigo WHERE p.codigo IN ({marc})""", list(por))}
        for cod, d in por.items():
            r = info.get(cod)
            if not r:
                continue
            a = antes.get(cod, 0) if comparavel else None
            var = _variacao(d["v"], a, comparavel)
            mais_visto = max(d["caminhos"].items(), key=lambda kv: kv[1])[0]
            itens.append({"codigo": cod, "titulo": r["titulo"], "ano": r["ano"] or None, "ano_fim": r["ano_fim"] or None,
                          "autoria": _autoria(r), "fundo_codigo": r["fundo_codigo"], "visualizacoes": d["v"], "anterior": a,
                          "diferenca": var["absoluta"], "variacao_pct": var["percentual"], "base_zero": var["base_zero"],
                          "url_publica": m["url"].get(cod) or (site.rstrip("/") + normalizar(mais_visto)),
                          "caminhos": sorted(d["caminhos"]), "foto": _foto(con, cod),
                          "autores": [x.strip() for x in re.split(r"[;\n]+", r["autoria"] or "") if x.strip()]})
    itens.sort(key=lambda i: (-i["visualizacoes"], _sem_acento(i["titulo"])))
    for k, i in enumerate(itens, 1):
        i["posicao"] = k
    maximo = itens[0]["visualizacoes"] if itens else 0
    total_proj = sum(i["visualizacoes"] for i in itens)
    # Redesenho §14 (campos opcionais): filtro por fundo e por arquiteto (autoria cadastrada) no ranking completo, com as opções
    # tiradas do próprio ranking do período (só fundos/autores que têm projeto visitado). A posição continua a do ranking inteiro.
    fundos: dict[str, dict] = {}
    autores: dict[str, int] = {}
    for i in itens:
        if i["fundo_codigo"]:
            f = fundos.setdefault(i["fundo_codigo"], {"codigo": i["fundo_codigo"], "titulo": None, "projetos": 0})
            f["projetos"] += 1
        for a in i["autores"]:
            autores[a] = autores.get(a, 0) + 1
    if fundos:
        marc = ",".join("?" * len(fundos))
        for r in con.execute(f"SELECT codigo, titulo, sigla FROM fundo WHERE codigo IN ({marc})", list(fundos)):
            fundos[r["codigo"]]["titulo"] = r["titulo"]
            fundos[r["codigo"]]["sigla"] = r["sigla"]
    sel = itens
    if fundo:
        sel = [i for i in sel if i["fundo_codigo"] == fundo]
    if autor:
        sel = [i for i in sel if autor in i["autores"]]
    if busca.strip():
        q = _sem_acento(busca.strip())
        sel = [i for i in itens if q in _sem_acento(" ".join([i["titulo"], i["codigo"], (i["autoria"] or {}).get("texto", "")]))]
    if ordem == "menos":
        sel = sorted(sel, key=lambda i: (i["visualizacoes"], i["posicao"]))
    elif ordem == "crescimento":
        sel = sorted(sel, key=lambda i: (i["diferenca"] is None, -(i["diferenca"] or 0), i["posicao"]))
    sinc = sincronizacao(con)
    nao_ident = sorted(ni.values(), key=lambda d: -d["visualizacoes"])
    return {**per, "metrica": METRICA_RANKING, "site": site.rstrip("/"), "ordem": ordem, "busca": busca, "comparavel": comparavel,
            "fundo": fundo, "autor": autor, "fundos": sorted(fundos.values(), key=lambda f: f["codigo"]),
            "autores": [{"nome": a, "projetos": n} for a, n in sorted(autores.items(), key=lambda kv: _sem_acento(kv[0]))],
            "anterior": {"de": ade, "ate": aate}, "maximo": maximo, "total_projetos": len(itens), "encontrados": len(sel),
            "visualizacoes_projetos": total_proj, "itens": sel[:limite] if limite else sel,
            "nao_identificadas": {"paginas": len(nao_ident), "visualizacoes": sum(d["visualizacoes"] for d in nao_ident), "itens": nao_ident[:100]},
            "outras": outras, "sincronizacao": sinc, "estado": _estado(sinc, len(cob), total_proj + outras["visualizacoes"] + sum(d["visualizacoes"] for d in nao_ident))}


def csv_projetos(r: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["posição", "código", "projeto", "autoria ou acervo", "ano", "visualizações da página do projeto",
                f"período anterior ({r['anterior']['de']} a {r['anterior']['ate']})", "variação (%)", "página pública"])
    for i in r["itens"]:
        ano = f"{i['ano']}–{i['ano_fim']}" if i["ano"] and i["ano_fim"] else (i["ano"] or "")
        var = "" if i["variacao_pct"] is None else str(i["variacao_pct"]).replace(".", ",")
        w.writerow([i["posicao"], i["codigo"], i["titulo"], (i["autoria"] or {}).get("texto", ""), ano, i["visualizacoes"],
                    "" if i["anterior"] is None else i["anterior"], var, i["url_publica"]])
    return "﻿" + buf.getvalue()
