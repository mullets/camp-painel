"""B6 · Importar inventário de projetos por planilha (CSV ou XLSX), com prévia.

1) POST /api/planilha/ler      — o arquivo (corpo cru, nome em X-Arquivo-Nome) vira colunas + linhas e o mapa sugerido;
2) POST /api/planilha/analisar — com o fundo e o mapa (campo do projeto -> coluna), cada linha volta com o que vai ser
   gravado, os problemas (sem nome, ano inválido) e os parecidos (no fundo e dentro da própria planilha);
3) POST /api/planilha/criar    — cria os projetos das linhas escolhidas, com os P em sequência, e registra na auditoria.
Nada fica guardado entre os passos: a tela manda as linhas de novo (no máximo 2.000).
"""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["planilha"])
LIMITE_LINHAS = 2000
LIMITE_BYTES = 8 * 1024 * 1024

# campo do projeto: (rótulo, cabeçalhos que costumam aparecer nos inventários)
CAMPOS = {
    "titulo": ("Nome do projeto", ["nome do projeto", "titulo", "título", "projeto", "nome", "obra", "denominacao", "denominação"]),
    "ano": ("Ano", ["ano", "ano do projeto", "data", "data do projeto", "ano inicial"]),
    "ano_fim": ("Ano final", ["ano final", "ate", "até", "ano fim"]),
    "cidade": ("Cidade", ["cidade", "municipio", "município", "cidade/uf", "local", "localidade"]),
    "endereco_obra": ("Endereço da obra", ["endereco", "endereço", "endereco da obra", "endereço da obra", "logradouro"]),
    "cliente": ("Cliente", ["cliente", "proprietario", "proprietário", "contratante"]),
    "tipologia": ("Programa / uso", ["programa", "programa / uso", "uso", "tipologia"]),
    "identificacao_original": ("Identificação original", ["codigo original", "código original", "identificacao original", "identificação original",
                                                          "numero", "número", "nº", "n°", "no", "ref", "referencia", "referência", "codigo do escritorio", "código do escritório"]),
    "contagem_esperada": ("Folhas (contagem)", ["folhas", "pranchas", "quantidade", "qtd", "qtde", "n de folhas", "nº de folhas"]),
    "ambito_conteudo": ("Âmbito e conteúdo / observações", ["observacoes", "observações", "obs", "descricao", "descrição", "conteudo", "conteúdo", "ambito", "âmbito"]),
}


def _norm(t) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9/ ]+", " ", t).split())


def ler(nome: str, dados: bytes) -> tuple[list[str], list[dict]]:
    nome = (nome or "").lower()
    if nome.endswith((".xlsx", ".xlsm")) or dados[:2] == b"PK":
        try:
            import openpyxl
        except ImportError as e:
            raise HTTPException(400, "Este servidor ainda não lê .xlsx: salve a planilha como CSV e envie de novo.") from e
        try:
            wb = openpyxl.load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"Não consegui abrir a planilha: {str(e)[:120]}") from e
        brutas = [["" if v is None else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)).strip() for v in r]
                  for r in wb.worksheets[0].iter_rows(values_only=True)]
    elif nome.endswith((".csv", ".txt")) or not nome:
        for cod in ("utf-8-sig", "cp1252"):
            try:
                texto = dados.decode(cod); break
            except UnicodeDecodeError:
                continue
        try:
            dialeto = csv.Sniffer().sniff(texto[:5000], delimiters=";,\t")
        except csv.Error:
            dialeto = csv.excel; dialeto.delimiter = ";" if texto[:2000].count(";") > texto[:2000].count(",") else ","
        brutas = [[c.strip() for c in r] for r in csv.reader(io.StringIO(texto), dialeto)]
    else:
        raise HTTPException(400, "Envie a planilha em .csv ou .xlsx.")
    brutas = [r for r in brutas if any(c for c in r)]
    if not brutas:
        raise HTTPException(400, "A planilha está vazia.")
    cab, vistos = [], {}
    for i, c in enumerate(brutas[0]):
        c = c or f"Coluna {i + 1}"
        vistos[c] = vistos.get(c, 0) + 1
        cab.append(c if vistos[c] == 1 else f"{c} ({vistos[c]})")
    linhas = [{cab[i]: (r[i] if i < len(r) else "") for i in range(len(cab))} for r in brutas[1:]]
    if len(linhas) > LIMITE_LINHAS:
        raise HTTPException(400, f"A planilha tem {len(linhas)} linhas; o limite por vez é {LIMITE_LINHAS}. Divida em partes.")
    return cab, linhas


def sugerir_mapa(colunas: list[str]) -> dict:
    mapa, usadas = {}, set()
    for campo, (_rot, sinon) in CAMPOS.items():
        alvos = [_norm(s) for s in sinon]
        for c in colunas:
            if c not in usadas and _norm(c) in alvos:
                mapa[campo] = c; usadas.add(c); break
    return mapa


def _ano(v) -> tuple[int, str | None]:
    t = str(v or "").strip()
    if not t:
        return 0, None
    m = re.search(r"(1[89]\d\d|20\d\d)", t)
    if not m:
        return 0, f"ano “{t}” não reconhecido (fica sem data)"
    return int(m.group(1)), None


def _int(v) -> int | None:
    m = re.search(r"\d+", str(v or ""))
    return int(m.group(0)) if m else None


class Analise(BaseModel):
    fundo: str
    mapa: dict
    linhas: list[dict]
    nome_arquivo: str | None = None


class Criacao(Analise):
    criar: list[int]          # números das linhas (1 = primeira linha de dados) que viram projeto


def _analisar(con, fundo: str, mapa: dict, linhas: list[dict]) -> list[dict]:
    from .similaridade import buscar_parecidos, sugerir_titulo, titulo_tecnico
    if not con.execute("SELECT 1 FROM fundo WHERE codigo=?", (fundo,)).fetchone():
        raise HTTPException(404, "Fundo não existe")
    if not mapa.get("titulo"):
        raise HTTPException(400, "Escolha a coluna do nome do projeto")
    if len(linhas) > LIMITE_LINHAS:
        raise HTTPException(400, f"No máximo {LIMITE_LINHAS} linhas por vez")
    from . import tipologia as tp
    voc = tp.vocabulario(con)
    out, chaves = [], {}
    for n, ln in enumerate(linhas, start=1):
        g = lambda campo: str(ln.get(mapa.get(campo) or "", "") or "").strip()  # noqa: E731
        dados = {c: g(c) or None for c in CAMPOS}
        problemas, avisos = [], []
        if not dados["titulo"]:
            problemas.append("sem nome do projeto")
        elif titulo_tecnico(dados["titulo"]):           # UX-15: nome de pasta/código não vira projeto; a sugestão limpa vai junto
            sug = sugerir_titulo(dados["titulo"])
            problemas.append(f"nome do projeto é nome de pasta ou código ({titulo_tecnico(dados['titulo'])})" + (f": sugestão “{sug}”" if sug else ""))
        ano, av = _ano(dados["ano"]); dados["ano"] = ano
        if av:
            avisos.append(av)
        if dados["ano_fim"]:
            dados["ano_fim"] = _ano(dados["ano_fim"])[0] or None
        if dados["contagem_esperada"]:
            dados["contagem_esperada"] = _int(dados["contagem_esperada"])
        if dados["tipologia"]:   # B3: o programa do site é lista fechada; o que não está nela fica de fora (escolhe-se depois no projeto)
            try:
                dados["tipologia"] = tp.validar(con, "programa", dados["tipologia"], voc) or None
            except ValueError:
                avisos.append(f"programa “{dados['tipologia']}” não está na lista do site (fica vazio; escolha no projeto)")
                dados["tipologia"] = None
        parecidos = buscar_parecidos(con, fundo, dados["titulo"], ano, dados["cidade"], dados["identificacao_original"], limite=3) if dados["titulo"] else []
        chave = (_norm(dados["titulo"]), ano)
        repetida = chaves.get(chave) if dados["titulo"] else None
        if repetida:
            avisos.append(f"igual à linha {repetida} desta planilha")
        else:
            chaves[chave] = n
        out.append({"n": n, "dados": dados, "problemas": problemas, "avisos": avisos, "repetida_de": repetida,
                    "parecidos": [{"codigo": p["codigo"], "titulo": p["titulo"], "ano": p["ano"], "nivel": p.get("nivel")} for p in parecidos]})
    return out


@router.post("/planilha/ler")
async def ler_planilha(request: Request, u: dict = Depends(auth.exige("admin"))) -> dict:
    dados = await request.body()
    if len(dados) > LIMITE_BYTES:
        raise HTTPException(413, "Planilha grande demais (máximo 8 MB).")
    from urllib.parse import unquote
    nome = unquote(request.headers.get("x-arquivo-nome", ""))
    colunas, linhas = ler(nome, dados)
    return {"colunas": colunas, "linhas": linhas, "total": len(linhas), "mapa": sugerir_mapa(colunas),
            "campos": {k: v[0] for k, v in CAMPOS.items()}}


@router.post("/planilha/analisar")
def analisar(d: Analise, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = _analisar(con, d.fundo, d.mapa, d.linhas)
    finally:
        con.close()
    return {"linhas": r, "resumo": {"total": len(r), "prontas": sum(1 for x in r if not x["problemas"] and not x["parecidos"] and not x["repetida_de"]),
                                    "com_parecido": sum(1 for x in r if x["parecidos"] or x["repetida_de"]), "com_problema": sum(1 for x in r if x["problemas"])}}


@router.post("/planilha/criar")
def criar(d: Criacao, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Cria os projetos das linhas escolhidas (as com problema nunca), com P em sequência, numa transação só."""
    con = connect()
    try:
        analise = {x["n"]: x for x in _analisar(con, d.fundo, d.mapa, d.linhas)}
        escolhidas = [analise[n] for n in sorted(set(d.criar)) if n in analise and not analise[n]["problemas"]]
        if not escolhidas:
            raise HTTPException(400, "Nenhuma linha escolhida pode virar projeto")
        criados = []
        con.execute("BEGIN IMMEDIATE")
        for x in escolhidas:
            dd = x["dados"]
            prox = con.execute("SELECT proximo FROM v_proximo_p WHERE fundo_codigo=?", (d.fundo,)).fetchone()[0]
            numero = int(prox[1:]); codigo = f"{d.fundo}-{prox}"
            con.execute("INSERT INTO numero_p (fundo_codigo, numero, reservado_por) VALUES (?,?,?)", (d.fundo, numero, u["id"]))
            con.execute("""INSERT INTO projeto (codigo, fundo_codigo, numero, titulo, ano, ano_fim, cidade, endereco_obra, cliente, tipologia,
                           identificacao_original, contagem_esperada, ambito_conteudo) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (codigo, d.fundo, numero, dd["titulo"], dd["ano"] or 0, dd["ano_fim"], dd["cidade"], dd["endereco_obra"], dd["cliente"],
                         dd["tipologia"], dd["identificacao_original"], dd["contagem_esperada"], dd["ambito_conteudo"]))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'criado',?,?)",
                        (codigo, u["email"], json.dumps({"titulo": dd["titulo"], "origem": "planilha", "arquivo": d.nome_arquivo, "linha": x["n"],
                                                         "parecidos": [p["codigo"] for p in x["parecidos"]]}, ensure_ascii=False)))
            criados.append({"n": x["n"], "codigo": codigo, "titulo": dd["titulo"]})
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('fundo',?,'inventario_importado',?,?)",
                    (d.fundo, u["email"], json.dumps({"arquivo": d.nome_arquivo, "criados": len(criados), "de": criados[0]["codigo"], "ate": criados[-1]["codigo"],
                                                      "linhas_na_planilha": len(d.linhas)}, ensure_ascii=False)))
        con.commit()
    except HTTPException:
        con.rollback(); raise
    except Exception:
        con.rollback(); raise
    finally:
        con.close()
    return {"ok": True, "criados": criados, "mensagem": f"{len(criados)} projeto{'s' if len(criados) != 1 else ''} criado{'s' if len(criados) != 1 else ''} no {d.fundo}: "
                                                         f"{criados[0]['codigo']}" + (f" a {criados[-1]['codigo']}" if len(criados) > 1 else "")}
