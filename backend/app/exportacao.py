"""Exportação do acervo para fora do painel: EAD 2002 (importa no AtoM), CSV de folhas (abre no Excel) e pacote BagIt 1.0 por projeto.

- EAD: fundo -> <archdesc level="fonds">, projeto -> <c level="file">, folha -> <c level="item">. Montado com os campos ISAD(G)
  que já existem no fundo (datas, dimensão, história arquivística, procedência, acesso, reprodução), os direitos do fundo
  e a autoridade (titulares e coautores, a mesma regra de main.autoridade_fundos). O XML sai pelo ElementTree: o escape é dele.
- CSV: uma linha por folha, UTF-8 com BOM (o Excel reconhece os acentos).
- BagIt: data/ com os TIFF do QNAP + metadados (EAD e CSV), bagit.txt, bag-info.txt, manifest-sha256.txt e tagmanifest-sha256.txt.
  Grava numa pasta '.parcial' e só renomeia no fim: pasta sem '.parcial' é pacote completo e conferido.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from . import auth
from .config import settings
from .db import connect

router = APIRouter(prefix="/api", tags=["exportacao"])

REPOSITORIO = "CAMP - Casa da Arquitetura Moderna Paulista"
DOCTYPE = ('<!DOCTYPE ead PUBLIC "+//ISBN 1-931666-00-8//DTD ead.dtd (Encoded Archival Description (EAD) Version 2002)//EN" '
           '"http://lcweb2.loc.gov/xmlcommon/dtds/ead2002/ead.dtd">')
STATUS_TXT = {"nao_publicado": "não publicado", "bloqueado": "bloqueado", "em_revisao": "em revisão", "rascunho": "rascunho",
              "no_ar": "publicado", "fora_do_ar": "despublicado"}
DIREITOS_TXT = {"nao_definida": "não definidos", "autorizado": "autorizado", "restrito": "restrito", "nao_autorizado": "não autorizado"}
COLUNAS_CSV = ["codigo", "projeto", "titulo", "ano", "serie", "folha", "status", "direitos", "localizacao"]
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")     # proibidos em XML 1.0 (o ElementTree não tira)


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return r[0] if r and r[0] else padrao


def _txt(v) -> str:
    return _CTRL.sub("", str(v)).strip() if v is not None else ""


# ---------------------------------------------------------------- dados
def _fundo(con, codigo: str) -> dict:
    f = con.execute("SELECT * FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    if not f:
        raise HTTPException(404, "Fundo não existe")
    d = dict(f)
    dr = con.execute("SELECT * FROM direitos_fundo WHERE fundo_codigo=?", (codigo,)).fetchone()
    d["direitos"] = dict(dr) if dr else {}
    from .main import autoridade_fundos                       # import tardio: main importa este módulo
    d["autoridade"] = autoridade_fundos(con, [codigo])[codigo]
    ids = [p["id"] for p in d["autoridade"]["titulares"] + d["autoridade"]["coautores"]]
    d["agentes"] = {r["id"]: dict(r) for r in con.execute(
        f"SELECT id, tipo, historia, fonte_historia FROM agente WHERE id IN ({','.join('?' * len(ids))})", ids)} if ids else {}
    return d


def _projetos(con, fundo: str, projeto: str | None = None) -> list[dict]:
    if projeto:
        rows = con.execute("SELECT * FROM projeto WHERE codigo=?", (projeto,)).fetchall()
    else:
        rows = con.execute("SELECT * FROM projeto WHERE fundo_codigo=? AND mesclado_em IS NULL AND descartado_em IS NULL AND lote_teste=0 ORDER BY numero", (fundo,)).fetchall()
    return [dict(r) for r in rows]


def _itens(con, projeto: str) -> list[dict]:
    return [dict(r) for r in con.execute("""
        SELECT i.*, s.nome AS serie_nome,
               (SELECT lf.tipo || ' ' || lf.identificador FROM item_localizacao il JOIN localizacao_fisica lf ON lf.id=il.localizacao_id
                 WHERE il.item_codigo=i.codigo) AS localizacao
          FROM item i LEFT JOIN serie s ON s.codigo=i.serie_codigo
         WHERE i.projeto_codigo=? ORDER BY i.serie_codigo, i.sequencial""", (projeto,))]


def _projeto_ou_404(con, codigo: str) -> dict:
    p = con.execute("SELECT codigo, fundo_codigo, titulo FROM projeto WHERE codigo=?", (codigo,)).fetchone()
    if not p:
        raise HTTPException(404, "Projeto não existe")
    return dict(p)


# ---------------------------------------------------------------- EAD 2002
def _sub(pai, tag: str, texto=None, **attrs):
    e = ET.SubElement(pai, tag, {k.rstrip("_"): _txt(v) for k, v in attrs.items() if v not in (None, "")})
    if texto not in (None, ""):
        e.text = _txt(texto)
    return e


def _paragrafos(pai, tag: str, *textos, cabecalho: str | None = None):
    partes = [t for t in (_txt(x) for x in textos) if t]
    if not partes:
        return None
    e = _sub(pai, tag)
    if cabecalho:
        _sub(e, "head", cabecalho)
    for t in partes:
        for bloco in [b.strip() for b in t.split("\n\n") if b.strip()] or [t]:
            _sub(e, "p", bloco)
    return e


def _data(pai, inicio, fim=None):
    ini = int(inicio) if inicio else 0
    fi = int(fim) if fim else 0
    if not ini and not fi:
        return _sub(pai, "unitdate", "sem data")
    if ini and fi and fi != ini:
        return _sub(pai, "unitdate", f"{ini}-{fi}", normal=f"{ini}/{fi}", type="inclusive")
    a = ini or fi
    return _sub(pai, "unitdate", str(a), normal=str(a))


def _nome(pai, nome: str, tipo: str | None, papel: str | None = None):
    tag = {"entidade_coletiva": "corpname", "familia": "famname"}.get(tipo or "", "persname")
    return _sub(pai, tag, nome, role=papel)


def _c_item(pai, i: dict, ano_projeto) -> None:
    c = _sub(pai, "c", level="item")
    did = _sub(c, "did")
    _sub(did, "unitid", i["codigo"])
    titulo = i.get("titulo") or i.get("tipo_documento") or "Sem título"
    _sub(did, "unittitle", titulo)
    _data(did, i.get("ano_folha") or ano_projeto)
    pd = _sub(did, "physdesc")
    _sub(pd, "extent", "1 documento")
    from .tipos_documento import separar
    for t in separar(i.get("tipos_documento") or i.get("tipo_documento")):          # um <genreform> por tipo (planta, corte…)
        _sub(pd, "genreform", t)
    if i.get("dimensoes"):
        _sub(pd, "dimensions", i["dimensoes"])
    if i.get("suporte"):
        _sub(pd, "physfacet", i["suporte"])
    if i.get("escala"):
        _sub(did, "materialspec", f"Escala {i['escala']}")
    if i.get("localizacao"):
        _sub(did, "physloc", i["localizacao"])
    notas = []
    if i.get("folha"):
        notas.append(f"Folha {i['folha']}")
    if i.get("serie_codigo"):
        notas.append(f"Série {i['serie_codigo']} - {i.get('serie_nome') or ''}".strip(" -"))
    _paragrafos(c, "odd", *notas)
    if i.get("credito"):
        _paragrafos(c, "prefercite", i["credito"])
    # 19/10: escritórios parceiros / projetos complementares. Não são <origination> (ISAD(G) 3.2.1 = o produtor que acumulou o
    # material, o titular do fundo): são entidades ligadas ao documento, ou seja, PONTOS DE ACESSO. Um <corpname> por escritório,
    # com a disciplina em role (o EAD 2002 permite role em corpname dentro de controlaccess).
    from .parceiros import ler as _ler_parceiros
    lista = _ler_parceiros(i.get("parceiros"))
    if lista:
        ca = _sub(c, "controlaccess")
        _sub(ca, "head", "Escritórios parceiros / projetos complementares")
        for p in lista:
            _sub(ca, "corpname", p["escritorio"], role=p.get("disciplina"))


def _c_projeto(pai, p: dict, itens: list[dict]) -> None:
    c = _sub(pai, "c", level="file")
    did = _sub(c, "did")
    _sub(did, "unitid", p["codigo"])
    _sub(did, "unittitle", p.get("titulo") or "Sem título")
    _data(did, p.get("ano"), p.get("ano_fim"))
    autores = [a.strip() for a in (p.get("autoria") or "").split(";") if a.strip()]
    if autores:
        org = _sub(did, "origination", label="Autoria")
        for a in autores:
            _sub(org, "persname", a, role="autor")
    pd = _sub(did, "physdesc")
    _sub(pd, "extent", f"{len(itens)} folha(s)")
    if p.get("identificacao_original"):
        _sub(did, "physloc", p["identificacao_original"])
    lugar = ", ".join(x for x in (p.get("endereco_obra"), p.get("cidade")) if x)
    _paragrafos(c, "scopecontent", p.get("ambito_conteudo"), f"Local da obra: {lugar}" if lugar else None,
                f"Cliente: {p['cliente']}" if p.get("cliente") else None)
    termos = [x for x in (p.get("tipologia"), p.get("natureza"), p.get("modalidade")) if x]
    if termos or p.get("cidade"):
        ca = _sub(c, "controlaccess")
        for t in termos:
            _sub(ca, "subject", t)
        if p.get("cidade"):
            _sub(ca, "geogname", p["cidade"])
    for i in itens:
        _c_item(c, i, p.get("ano"))


def montar_ead(con, fundo: str, projeto: str | None = None) -> bytes:
    """EAD 2002 do fundo inteiro, ou do fundo com um só projeto dentro (o AtoM importa o contexto junto)."""
    f = _fundo(con, fundo)
    projs = _projetos(con, fundo, projeto)
    itens = {p["codigo"]: _itens(con, p["codigo"]) for p in projs}
    aut, dr = f["autoridade"], f["direitos"]
    alvo = projeto or fundo

    ead = ET.Element("ead")
    hdr = _sub(ead, "eadheader", langencoding="iso639-2b", countryencoding="iso3166-1", dateencoding="iso8601",
               repositoryencoding="iso15511", scriptencoding="iso15924", relatedencoding="DC")
    _sub(hdr, "eadid", f"CAMP-{alvo}", countrycode="BR", identifier=alvo)
    fd = _sub(hdr, "filedesc")
    ts = _sub(fd, "titlestmt")
    _sub(ts, "titleproper", f["titulo"] if not projeto else f"{projs[0]['titulo']} ({f['titulo']})", encodinganalog="Title")
    ps = _sub(fd, "publicationstmt")
    _sub(ps, "publisher", REPOSITORIO)
    _sub(ps, "date", datetime.now().strftime("%Y-%m-%d"), normal=datetime.now().strftime("%Y%m%d"))
    pf = _sub(hdr, "profiledesc")
    cr = _sub(pf, "creation", "Gerado pelo painel CAMP Acervos em ")
    _sub(cr, "date", datetime.now().strftime("%Y-%m-%d %H:%M"), normal=datetime.now().strftime("%Y%m%d"))
    lu = _sub(pf, "langusage")
    _sub(lu, "language", "português", langcode="por", scriptcode="Latn")

    ad = _sub(ead, "archdesc", level="fonds" if (f.get("nivel_descricao") or "fundo") == "fundo" else "collection", relatedencoding="ISAD(G)v2")
    did = _sub(ad, "did")
    _sub(did, "unitid", fundo, countrycode="BR", repositorycode="CAMP")
    _sub(did, "unittitle", f["titulo"], encodinganalog="3.1.2")
    _data(did, f.get("data_inicio"), f.get("data_fim")).set("encodinganalog", "3.1.3")
    if aut["titulares"]:
        org = _sub(did, "origination", encodinganalog="3.2.1")
        for t in aut["titulares"]:
            _nome(org, t["nome"], (f["agentes"].get(t["id"]) or {}).get("tipo"), "produtor")
    pd = _sub(did, "physdesc", encodinganalog="3.1.5")
    _sub(pd, "extent", f.get("dimensao_suporte") or f"{len(projs)} projeto(s), {sum(len(x) for x in itens.values())} folha(s)")
    rp = _sub(did, "repository")
    _sub(rp, "corpname", REPOSITORIO)
    lm = _sub(did, "langmaterial")
    _sub(lm, "language", "português", langcode="por")

    for t in aut["titulares"]:
        a = f["agentes"].get(t["id"]) or {}
        if a.get("historia"):
            b = _paragrafos(ad, "bioghist", a["historia"], f"Fonte: {a['fonte_historia']}" if a.get("fonte_historia") else None, cabecalho=t["nome"])
            b.set("encodinganalog", "3.2.2")
    if f.get("historia_arquivistica"):
        _paragrafos(ad, "custodhist", f["historia_arquivistica"], f"Fonte: {f['fonte_historia']}" if f.get("fonte_historia") else None).set("encodinganalog", "3.2.3")
    if f.get("procedencia"):
        _paragrafos(ad, "acqinfo", f["procedencia"]).set("encodinganalog", "3.2.4")
    acesso = [f.get("condicoes_acesso")]
    if dr.get("situacao") and dr["situacao"] != "autorizado":
        acesso.append(f"Direitos de publicação: {DIREITOS_TXT.get(dr['situacao'], dr['situacao'])}.")
    if dr.get("restricoes"):
        acesso.append(f"Restrições: {dr['restricoes']}")
    e = _paragrafos(ad, "accessrestrict", *acesso)
    if e is not None:
        e.set("encodinganalog", "3.4.1")
    uso = [f.get("condicoes_reproducao"), f"Licença: {dr['licenca']}" if dr.get("licenca") else None,
           f"Titular dos direitos: {dr['titular']}" if dr.get("titular") else None]
    e = _paragrafos(ad, "userestrict", *uso)
    if e is not None:
        e.set("encodinganalog", "3.4.2")
    _paragrafos(ad, "prefercite", (dr.get("credito_exigido") or f.get("credito_padrao") or "").replace("{agente}", ", ".join(t["nome"] for t in aut["titulares"]) or "CAMP"))
    if aut["titulares"] or aut["coautores"]:
        ca = _sub(ad, "controlaccess")
        for t in aut["titulares"]:
            _nome(ca, t["nome"], (f["agentes"].get(t["id"]) or {}).get("tipo"), "titular")
        for t in aut["coautores"]:
            _nome(ca, t["nome"], (f["agentes"].get(t["id"]) or {}).get("tipo"), "coautor")
    dsc = _sub(ad, "dsc")
    for p in projs:
        _c_projeto(dsc, p, itens[p["codigo"]])
    ET.indent(ead, space=" ")
    corpo = ET.tostring(ead, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + DOCTYPE + "\n" + corpo + "\n").encode("utf-8")


# ---------------------------------------------------------------- CSV
def _seguro(v) -> str:
    """Célula que começa com = + - @ vira texto no Excel (não executa fórmula)."""
    s = _txt(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def montar_csv(con, fundo: str, projeto: str | None = None) -> bytes:
    f = _fundo(con, fundo)
    dr = f["direitos"]
    direitos = " · ".join(x for x in (DIREITOS_TXT.get(dr.get("situacao") or "nao_definida", ""), dr.get("licenca")) if x)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(COLUNAS_CSV)
    for p in _projetos(con, fundo, projeto):
        for i in _itens(con, p["codigo"]):
            ano = i.get("ano_folha") or p.get("ano") or ""
            w.writerow([_seguro(x) for x in (i["codigo"], p["codigo"], i.get("titulo") or "", ano or "",
                                             f"{i['serie_codigo']} {i.get('serie_nome') or ''}".strip(), i.get("folha") or "",
                                             STATUS_TXT.get(i.get("status_site"), i.get("status_site") or ""), direitos,
                                             i.get("localizacao") or p.get("identificacao_original") or "")])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _baixar(conteudo: bytes, nome: str, tipo: str) -> Response:
    return Response(content=conteudo, media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{nome}"', "Cache-Control": "no-store"})


@router.get("/fundos/{codigo}/ead.xml")
def ead_fundo(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> Response:
    con = connect()
    try:
        return _baixar(montar_ead(con, codigo), f"{codigo}-ead.xml", "application/xml; charset=utf-8")
    finally:
        con.close()


@router.get("/projetos/{codigo}/ead.xml")
def ead_projeto(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> Response:
    con = connect()
    try:
        p = _projeto_ou_404(con, codigo)
        return _baixar(montar_ead(con, p["fundo_codigo"], codigo), f"{codigo}-ead.xml", "application/xml; charset=utf-8")
    finally:
        con.close()


@router.get("/fundos/{codigo}/folhas.csv")
def csv_fundo(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> Response:
    con = connect()
    try:
        return _baixar(montar_csv(con, codigo), f"{codigo}-folhas.csv", "text/csv; charset=utf-8")
    finally:
        con.close()


@router.get("/projetos/{codigo}/folhas.csv")
def csv_projeto(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> Response:
    con = connect()
    try:
        p = _projeto_ou_404(con, codigo)
        return _baixar(montar_csv(con, p["fundo_codigo"], codigo), f"{codigo}-folhas.csv", "text/csv; charset=utf-8")
    finally:
        con.close()


# ---------------------------------------------------------------- BagIt 1.0
def pasta_exportacao(con) -> Path:
    """configuracao 'exportacao.pasta'; vazia = <pasta do banco>/exportacoes (o diretório de dados do painel)."""
    return Path(_cfg(con, "exportacao.pasta", str(Path(settings.CAMP_DB_PATH).resolve().parent / "exportacoes")))


def raiz_qnap(con) -> Path:
    """Onde estão os TIFF: a raiz dos prontos do CAMP Vision (item.arquivo_tif é relativo a ela), ou a raiz do QNAP."""
    return Path(_cfg(con, "qnap.prontos_raiz", _cfg(con, "qnap.raiz", settings.CAMP_QNAP_ROOT)))


def _tif_no_qnap(raiz: Path, rel) -> Path | None:
    """O TIFF da folha, só se existir e estiver DENTRO da raiz (o caminho vem do pacote do CAMP Vision)."""
    if not rel:
        return None
    try:
        c = Path(str(rel))
        alvo = c.resolve() if c.is_absolute() else (raiz / c).resolve()
        if raiz.resolve() in alvo.parents and alvo.suffix.lower() in (".tif", ".tiff") and alvo.is_file():
            return alvo
    except OSError:
        return None
    return None


def _caminho_bag(rel: str) -> str:
    """BagIt §2.1.3: no manifesto, CR, LF e % do nome vão codificados."""
    return rel.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _copiar_com_hash(origem: Path, destino: Path) -> tuple[str, int]:
    h, n = hashlib.sha256(), 0
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(origem, "rb") as fi, open(destino, "wb") as fo:
        for bloco in iter(lambda: fi.read(1 << 20), b""):
            h.update(bloco); fo.write(bloco); n += len(bloco)
    shutil.copystat(origem, destino, follow_symlinks=True)
    return h.hexdigest(), n


def _gravar_com_hash(destino: Path, conteudo: bytes) -> tuple[str, int]:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)
    return hashlib.sha256(conteudo).hexdigest(), len(conteudo)


def _tamanho(n: int) -> str:
    for unidade, fator in (("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if n >= fator:
            from .formato import tamanho_br
            return tamanho_br(n / fator, unidade)        # UX-33: "1,5 GB", nunca "1.5 GB"
    return f"{n} bytes"


def checar_qnap(con) -> Path:
    from .rotas_gestao import _estado_qnap
    raiz = raiz_qnap(con)
    montado, motivo = _estado_qnap(raiz)
    if not montado:
        raise HTTPException(503, f"QNAP não conectado: a pasta {raiz} {'está vazia' if motivo == 'vazia' else 'não existe'} neste servidor.")
    return raiz


def gerar_bag(codigo: str, ator: str, p=None) -> dict:
    """Gera o pacote do projeto. p = Progresso da tarefa (ou None quando roda direto)."""
    passo = (lambda t, a=None: p.passo(t, a)) if p else (lambda t, a=None: None)
    con = connect()
    try:
        proj = _projeto_ou_404(con, codigo)
        raiz = checar_qnap(con)
        destino_base = pasta_exportacao(con)
        passo("Montando os metadados (EAD e CSV)")
        ead = montar_ead(con, proj["fundo_codigo"], codigo)
        csv_b = montar_csv(con, proj["fundo_codigo"], codigo)
        itens = _itens(con, codigo)
    finally:
        con.close()
    if p:
        p.total(len(itens))
    achados, faltando = [], []
    for i in itens:
        alvo = _tif_no_qnap(raiz, i.get("arquivo_tif"))
        if alvo is None:
            faltando.append({"codigo": i["codigo"], "erro": f"TIFF não encontrado no QNAP: {i['arquivo_tif']}" if i.get("arquivo_tif") else "folha sem TIFF registrado"})
        else:
            achados.append((i, alvo))
    total_bytes = sum(a.stat().st_size for _, a in achados)
    try:
        destino_base.mkdir(parents=True, exist_ok=True)
        livre = shutil.disk_usage(destino_base).free
    except OSError as e:
        raise HTTPException(500, f"Não consegui usar a pasta de exportação {destino_base}: {e.strerror or e}")
    if total_bytes + len(ead) + len(csv_b) + (1 << 20) > livre:
        from .formato import num_br
        raise HTTPException(507, f"Falta espaço em {destino_base}: o pacote precisa de {num_br(total_bytes / 1e9)} GB e há {num_br(livre / 1e9)} GB livres.")

    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    nome = f"{codigo}-{carimbo}"
    final, tmp = destino_base / nome, destino_base / (nome + ".parcial")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        manifesto: list[tuple[str, str]] = []
        oxum_b = oxum_n = 0
        for rel, conteudo in ((f"data/metadados/{codigo}-ead.xml", ead), (f"data/metadados/{codigo}-folhas.csv", csv_b)):
            h, n = _gravar_com_hash(tmp / rel, conteudo)
            manifesto.append((h, rel)); oxum_b += n; oxum_n += 1
        for i, alvo in achados:
            passo("Copiando os TIFF do QNAP", i["codigo"])
            rel = f"data/tiff/{i['serie_codigo']}/{alvo.name}"
            h, n = _copiar_com_hash(alvo, tmp / rel)
            manifesto.append((h, rel)); oxum_b += n; oxum_n += 1
            if p:
                p.feita(1)
        if p and faltando:
            p.feita(len(faltando))
        passo("Gravando os manifestos")
        (tmp / "manifest-sha256.txt").write_text("".join(f"{h}  {_caminho_bag(r)}\n" for h, r in sorted(manifesto, key=lambda x: x[1])), encoding="utf-8")
        (tmp / "bagit.txt").write_text("BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n", encoding="utf-8")
        info = [("Source-Organization", REPOSITORIO), ("External-Identifier", codigo), ("External-Description", _txt(proj["titulo"]).replace("\n", " ")),
                ("Bagging-Date", datetime.now().strftime("%Y-%m-%d")), ("Bag-Software-Agent", "CAMP Acervos (painel)"),
                ("Payload-Oxum", f"{oxum_b}.{oxum_n}"), ("Bag-Size", _tamanho(oxum_b)), ("Contact-Name", ator)]
        if faltando:
            info.append(("Internal-Sender-Description", f"Pacote incompleto: faltam {len(faltando)} TIFF no QNAP"))
        (tmp / "bag-info.txt").write_text("".join(f"{k}: {v}\n" for k, v in info), encoding="utf-8")
        tags = []
        for t in ("bagit.txt", "bag-info.txt", "manifest-sha256.txt"):
            tags.append(f"{hashlib.sha256((tmp / t).read_bytes()).hexdigest()}  {t}\n")
        (tmp / "tagmanifest-sha256.txt").write_text("".join(tags), encoding="utf-8")
        os.replace(tmp, final)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    con = connect()
    try:
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto', ?, 'exportado_bagit', ?, ?)",
                    (codigo, ator, json.dumps({"pasta": str(final), "tiff": len(achados), "faltando": [x["codigo"] for x in faltando], "bytes": oxum_b}, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    msg = f"Pacote BagIt de {codigo} gerado em {final} com {len(achados)} TIFF"
    if faltando:
        msg += f", mas faltam {len(faltando)} arquivo(s) no QNAP (listados abaixo)"
    return {"ok": not faltando, "mensagem": msg + ".", "pasta": str(final), "tiff": len(achados), "bytes": oxum_b,
            "faltando": [x["codigo"] for x in faltando], "falhas": faltando}


@router.post("/projetos/{codigo}/bagit")
def bagit_projeto(codigo: str, tarefa: int = 0, u: dict = Depends(auth.exige("admin"))):
    """?tarefa=1 (H4): roda em segundo plano e devolve {tarefa_id}. QNAP desconectado e projeto inexistente respondem na hora."""
    con = connect()
    try:
        _projeto_ou_404(con, codigo)
        checar_qnap(con)
    finally:
        con.close()
    if not tarefa:
        return gerar_bag(codigo, u["email"])
    from . import tarefas
    return tarefas.iniciar("bagit", codigo, u, lambda p: gerar_bag(codigo, u["email"], p), titulo=f"Pacote BagIt de {codigo}")
