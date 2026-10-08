"""Projetos (dossiês) e itens (folhas): leitura para todos; escrita admin/master."""
from __future__ import annotations

import json
import re
import unicodedata

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["projetos"])


def _colecao_config(con, chave: str, padrao: int) -> int:
    """Resolve coleção pelo conteúdo real do espelho, usando configuração só quando coerente."""
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    configurada = None
    try:
        configurada = int(r[0]) if r and str(r[0]).strip() else None
    except (TypeError, ValueError):
        configurada = None

    papel = "projetos" if "projetos" in chave else "itens"
    rows = con.execute("""
        SELECT colecao_id,
               COUNT(*) AS total,
               SUM(CASE WHEN projeto_detectado IS NOT NULL
                         AND codigo_detectado=projeto_detectado THEN 1 ELSE 0 END) AS projetos,
               SUM(CASE WHEN projeto_detectado IS NOT NULL
                         AND codigo_detectado<>projeto_detectado THEN 1 ELSE 0 END) AS documentos
          FROM wp_item
         WHERE codigo_detectado IS NOT NULL
         GROUP BY colecao_id
    """).fetchall()
    stats = {int(x["colecao_id"]): dict(x) for x in rows}

    def coerente(cid: int | None) -> bool:
        if not cid or cid not in stats:
            return False
        s = stats[cid]
        return (s["projetos"] or 0) >= (s["documentos"] or 0) if papel == "projetos" else (s["documentos"] or 0) > (s["projetos"] or 0)

    if coerente(configurada):
        return configurada
    if stats:
        campo = "projetos" if papel == "projetos" else "documentos"
        melhor = max(stats.values(), key=lambda x: (x.get(campo) or 0, x.get("total") or 0))
        if (melhor.get(campo) or 0) > 0:
            return int(melhor["colecao_id"])
    return configurada or padrao


def _serie_do_item(codigo: str | None, md: dict) -> str | None:
    m = re.search(r"-(S\d{2})-", codigo or "")
    if m:
        return m.group(1)
    texto = " ".join(str(md.get(k) or "") for k in ("Série", "Serie", "Tipo de acervo", "Categoria"))
    mapa = {
        "desenho": "S01", "prancha": "S01",
        "documento textual": "S02", "textual": "S02",
        "fotografia": "S03", "foto": "S03",
        "negativo": "S04",
        "slide": "S05", "diapositivo": "S05",
        "material": "S06", "especifica": "S06",
    }
    low = texto.lower()
    for termo, serie in mapa.items():
        if termo in low:
            return serie
    return None


def _slug_publico(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


_RE_CIDADE_UF = re.compile(r"\s*[,\-–(]\s*[^,\-–/()]+/[A-Za-z]{2}\s*\)?\s*$")


def _url_publica_projeto(codigo: str, titulo: str, cidade: str | None = None) -> str:
    """Monta a rota pública presumida da CAMP, SEM cidade/UF no slug (ex.: "..., São Paulo/SP" não entra).
    Só é usada quando o espelho do site não tem a página real (ver _pagina_publica_projeto)."""
    base = (titulo or "").strip()
    if cidade:
        base = re.sub(rf"\s*[,\-–(]\s*{re.escape(cidade)}(?:\s*[,/\-–]\s*[A-Za-z]{{2}})?\s*\)?\s*$", "", base, flags=re.I).strip(" ,-–")
    base = _RE_CIDADE_UF.sub("", base).strip(" ,-–")
    return f"https://camp.arq.br/acervo/projetos/{codigo.lower()}-{_slug_publico(base)}/"


def _pagina_publica_projeto(con, codigo: str, titulo: str, cidade: str | None) -> dict:
    """Endereço da página pública do projeto: o REAL (espelho das páginas do site) quando existe; senão o presumido.
    status é o status da página no WordPress (publish = qualquer visitante abre)."""
    r = con.execute("""SELECT url, status FROM wp_pagina
                        WHERE (codigo_detectado=? OR lower(slug) LIKE ?) AND url LIKE '%/acervo/projetos/%'
                        ORDER BY (status='publish') DESC, id DESC LIMIT 1""", (codigo, codigo.lower() + "-%")).fetchone()
    if r and r["url"]:
        return {"url": r["url"], "origem": "site", "status": r["status"]}
    return {"url": _url_publica_projeto(codigo, titulo, cidade), "origem": "presumido", "status": None}


@router.get("/projetos")
def listar(fundo: str | None = None, q: str | None = None, status: str | None = None, com_folhas: bool | None = None,
           pagina: int = 1, por_pagina: int = 100, u: dict = Depends(auth.exige("leitura"))) -> dict:
    sql = """SELECT p.codigo, p.titulo, p.fundo_codigo, f.titulo AS fundo, p.ano, p.cidade, p.status_site, p.autorizado_site,
                    p.tainacan_item_id, p.atualizado_em,
                    (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=p.codigo) AS folhas,
                    (SELECT GROUP_CONCAT(DISTINCT serie_codigo) FROM item i WHERE i.projeto_codigo=p.codigo) AS series
             FROM projeto p JOIN fundo f ON f.codigo=p.fundo_codigo WHERE 1=1"""
    par: list = []
    if fundo: sql += " AND p.fundo_codigo=?"; par.append(fundo)
    if status: sql += " AND p.status_site=?"; par.append(status)
    if q: sql += " AND (p.titulo LIKE ? OR p.codigo LIKE ? OR p.cidade LIKE ?)"; par += [f"%{q}%"] * 3
    if com_folhas is True: sql += " AND folhas > 0"
    if com_folhas is False: sql += " AND folhas = 0"
    con = connect()
    total = con.execute(f"SELECT COUNT(*) FROM ({sql})", par).fetchone()[0]
    por_pagina = max(1, min(por_pagina, 500))
    rows = con.execute(sql + " ORDER BY p.codigo LIMIT ? OFFSET ?", [*par, por_pagina, (pagina - 1) * por_pagina]).fetchall()
    con.close()
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "itens": [dict(r) for r in rows]}

@router.get("/projetos/codigos")
def codigos_projetos(fundo: str | None = None, q: str | None = None, status: str | None = None,
                     u: dict = Depends(auth.exige("leitura"))) -> dict:
    sql = "SELECT p.codigo FROM projeto p WHERE 1=1"
    par: list = []
    if fundo:
        sql += " AND p.fundo_codigo=?"; par.append(fundo)
    if status:
        sql += " AND p.status_site=?"; par.append(status)
    if q:
        sql += " AND (p.titulo LIKE ? OR p.codigo LIKE ? OR p.cidade LIKE ?)"; par += [f"%{q}%"] * 3
    con = connect()
    rows = [r[0] for r in con.execute(sql + " ORDER BY p.codigo", par).fetchall()]
    con.close()
    return {"total": len(rows), "codigos": rows}



@router.get("/diagnostico/codigos-entre-colecoes")
def diagnostico_codigos_entre_colecoes(codigo: str | None = None, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    sql = """
        SELECT w.codigo_detectado,
               GROUP_CONCAT(DISTINCT w.colecao_id) AS colecoes,
               COUNT(DISTINCT w.colecao_id) AS n_colecoes,
               COUNT(*) AS ocorrencias
          FROM wp_item w
         WHERE w.codigo_detectado IS NOT NULL AND w.codigo_detectado<>''
    """
    par: list = []
    if codigo:
        sql += " AND w.codigo_detectado=?"
        par.append(codigo)
    sql += " GROUP BY w.codigo_detectado HAVING COUNT(DISTINCT w.colecao_id)>1 ORDER BY ocorrencias DESC, w.codigo_detectado LIMIT 200"
    rows = [dict(r) for r in con.execute(sql, par).fetchall()]
    projetos_id = _colecao_config(con, "tainacan.projetos_collection_id", 8007)
    itens_id = _colecao_config(con, "tainacan.itens_collection_id", 8013)
    nomes = {r["id"]: r["nome"] for r in con.execute("SELECT id, nome FROM wp_colecao").fetchall()}
    con.close()
    return {"projetos_collection_id": projetos_id, "projetos_collection_nome": nomes.get(projetos_id),
            "itens_collection_id": itens_id, "itens_collection_nome": nomes.get(itens_id), "duplicidades": rows}


@router.get("/projetos/{codigo}/folhas-qnap")
def folhas_qnap(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Documentos que ESTÃO na pasta do(s) lote(s) do projeto no QNAP mas ainda não viraram folhas do painel (nem do site).

    A lista de folhas do projeto vem do banco (itens do site e itens locais); o CAMP Vision grava os arquivos no QNAP e o painel só
    registra o lote na Fila. Este painel mostra o que falta: a importação/revisão do lote é o passo seguinte."""
    from .qnap_folhas import documentos_da_pasta
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM projeto WHERE codigo=?", (codigo,)).fetchone():
            raise HTTPException(404, "Projeto não existe")
        conhecidos = {(r[0] or "").lower() for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo=?", (codigo,))}
        conhecidos |= {(r[0] or "").lower() for r in con.execute("SELECT codigo_detectado FROM wp_item WHERE projeto_detectado=?", (codigo,))}
        lotes = []
        for l in con.execute("SELECT id, nome, etapa, pasta_qnap FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC", (codigo,)):
            base = {"id": l["id"], "nome": l["nome"], "etapa": l["etapa"], "pasta": l["pasta_qnap"]}
            pasta = Path(l["pasta_qnap"]) if l["pasta_qnap"] else None
            if not pasta or not pasta.is_dir():
                lotes.append({**base, "existe": False, "total": 0, "fora_do_painel": 0, "parcial": False, "documentos": []})
                continue
            r = documentos_da_pasta(pasta)
            novos = [d for d in r["documentos"] if d["codigo"].lower() not in conhecidos]
            lotes.append({**base, "existe": True, "total": len(r["documentos"]), "fora_do_painel": len(novos), "parcial": r["parcial"], "documentos": novos[:600]})
        return {"lotes": lotes}
    finally:
        con.close()


@router.get("/projetos/{codigo}/folhas-qnap/arquivo")
def folha_qnap_arquivo(codigo: str, lote: int, caminho: str, u: dict = Depends(auth.exige("leitura"))) -> FileResponse:
    """Serve UMA prévia (JPG/PNG) de dentro da pasta de um lote DESTE projeto. Qualquer caminho que escape da pasta do lote = 404."""
    from .qnap_folhas import EXTS_PREVIA
    con = connect()
    try:
        l = con.execute("SELECT pasta_qnap FROM lista_processamento WHERE id=? AND projeto_codigo=?", (lote, codigo)).fetchone()
    finally:
        con.close()
    if not l or not l["pasta_qnap"]:
        raise HTTPException(404, "Arquivo não encontrado")
    base = Path(l["pasta_qnap"]).resolve()
    alvo = (base / caminho).resolve()
    if base not in alvo.parents or alvo.suffix.lower() not in EXTS_PREVIA or not alvo.is_file():
        raise HTTPException(404, "Arquivo não encontrado")
    if any(p.startswith((".", "@", "#")) for p in alvo.relative_to(base).parts):    # lixeira (@Recycle, #recycle) e ocultos do QNAP: nunca
        raise HTTPException(404, "Arquivo não encontrado")
    return FileResponse(alvo, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/projetos/{codigo}/detalhe")
def detalhe(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    p = con.execute("SELECT p.*, f.titulo AS fundo, f.sigla FROM projeto p JOIN fundo f ON f.codigo=p.fundo_codigo WHERE p.codigo=?", (codigo,)).fetchone()
    if not p:
        con.close(); raise HTTPException(404, "Projeto não existe")

    itens_local = [dict(r) for r in con.execute("""
        SELECT i.codigo, i.serie_codigo, i.sequencial, i.titulo, i.tipo_documento, i.folha, i.escala, i.ano_folha, i.status_site,
               i.autoria_divergente, i.duplicata_de, i.espelhado, i.rotacao_aplicada,
               i.tainacan_item_id AS tainacan_item_id_salvo
          FROM item i
         WHERE i.projeto_codigo=?
         ORDER BY i.serie_codigo, i.sequencial
    """, (codigo,))]
    itens_por_codigo = {x["codigo"]: x for x in itens_local}

    itens_cid = _colecao_config(con, "tainacan.itens_collection_id", 8013)
    itens_site = []
    for w in con.execute("""
        SELECT id, colecao_id, status, titulo, slug, url, documento_url, thumb_url,
               codigo_detectado, fundo_detectado, projeto_detectado, metadados, modificado_em
          FROM wp_item
         WHERE projeto_detectado=?
           AND fundo_detectado=?
           AND colecao_id=?
           AND codigo_detectado LIKE ?
         ORDER BY codigo_detectado, id
    """, (codigo, p["fundo_codigo"], itens_cid, codigo + "-%")).fetchall():
        d = dict(w)
        local = itens_por_codigo.get(d.get("codigo_detectado"))
        mdw = json.loads(d.get("metadados") or "{}")
        d["metadados_site"] = mdw
        if local:
            d.update({
                "serie_codigo": local.get("serie_codigo"),
                "sequencial": local.get("sequencial"),
                "tipo_documento": local.get("tipo_documento") or mdw.get("Tipo de documento"),
                "folha": local.get("folha") or mdw.get("Folha"),
                "escala": local.get("escala") or mdw.get("Escala"),
                "ano_folha": local.get("ano_folha"),
                "autoria_divergente": local.get("autoria_divergente"),
                "duplicata_de": local.get("duplicata_de"),
                "espelhado": local.get("espelhado"),
                "rotacao_aplicada": local.get("rotacao_aplicada"),
                "status_site_local": local.get("status_site"),
                "tainacan_item_id_salvo": local.get("tainacan_item_id_salvo"),
                "origem_catalogacao": "local+site",
            })
        else:
            d.update({
                "serie_codigo": _serie_do_item(d.get("codigo_detectado"), mdw),
                "sequencial": None,
                "tipo_documento": mdw.get("Tipo de documento") or mdw.get("Tipo") or mdw.get("Natureza do documento"),
                "folha": mdw.get("Folha"),
                "escala": mdw.get("Escala"),
                "ano_folha": None,
                "autoria_divergente": 0,
                "duplicata_de": None,
                "espelhado": 0,
                "rotacao_aplicada": 0,
                "status_site_local": None,
                "tainacan_item_id_salvo": None,
                "origem_catalogacao": "site",
            })
        d["tainacan_item_id"] = d["id"]
        d["codigo"] = d.get("codigo_detectado") or f"TAINACAN-{d['id']}"
        d["status_site"] = {"publish": "no_ar", "draft": "rascunho", "private": "fora_do_ar", "pending": "rascunho"}.get(d.get("status"), d.get("status") or "nao_publicado")
        itens_site.append(d)

    itens = itens_site if itens_site else itens_local
    for d in itens:
        d.setdefault("thumb_url", None)
        d.setdefault("url", None)
        d.setdefault("tainacan_item_id", None)
        d.setdefault("metadados_site", {})
        d.setdefault("origem_catalogacao", "local")

    projetos_cid = _colecao_config(con, "tainacan.projetos_collection_id", 8007)
    site = con.execute("""
        SELECT * FROM wp_item
         WHERE codigo_detectado=?
           AND colecao_id=?
         ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END, id DESC LIMIT 1
    """, (codigo, projetos_cid, p["tainacan_item_id"] or -1)).fetchone()
    md = json.loads(site["metadados"]) if site and site["metadados"] else {}
    erros = [dict(r) for r in con.execute("SELECT * FROM erro WHERE (codigo=? OR codigo LIKE ?) AND situacao IN ('aberto','em_correcao') ORDER BY gravidade", (codigo, codigo + "-%"))]
    pedidos = [dict(r) for r in con.execute("SELECT s.* FROM solicitacao s JOIN solicitacao_item si ON si.solicitacao_id=s.id WHERE si.codigo=? OR si.codigo LIKE ? GROUP BY s.id", (codigo, codigo + "-%"))]
    eventos = [dict(r) for r in con.execute("SELECT tipo, ator, quando, detalhe FROM evento WHERE entidade='projeto' AND codigo=? ORDER BY id DESC LIMIT 20", (codigo,))]
    filas = [dict(r) for r in con.execute("SELECT id, nome, etapa, folhas_esperadas, folhas_encontradas, atualizado_em FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC", (codigo,))]
    colecoes = {r["id"]: r["nome"] for r in con.execute("SELECT id, nome FROM wp_colecao").fetchall()}
    fonte_visual = {
        "colecao_projetos_id": projetos_cid,
        "colecao_projetos_nome": colecoes.get(projetos_cid),
        "colecao_itens_id": itens_cid,
        "colecao_itens_nome": colecoes.get(itens_cid),
        "documentos_site": len(itens_site),
        "documentos_locais": len(itens_local),
        "codigos_site": [x.get("codigo") for x in itens_site],
        "codigos_locais": [x.get("codigo") for x in itens_local],
    }
    pub = _pagina_publica_projeto(con, codigo, p["titulo"], p["cidade"])
    con.close()

    md_completos = {k: v for k, v in md.items() if v not in (None, "", [], {})}
    site_url = pub["url"]
    projeto = dict(p)
    projeto["tainacan_item_id_salvo"] = projeto.get("tainacan_item_id")
    projeto["tainacan_item_id"] = site["id"] if site else None

    series_nomes = {
        "S01": "Desenhos e pranchas",
        "S02": "Documentos textuais",
        "S03": "Fotografias",
        "S04": "Negativos",
        "S05": "Slides",
        "S06": "Materiais e especificações",
    }
    categorias = {}
    for x in itens:
        chave = x.get("serie_codigo") or "SEM_SERIE"
        categorias.setdefault(chave, {"codigo": chave, "nome": series_nomes.get(chave, "Sem série"), "itens": 0})
        categorias[chave]["itens"] += 1

    return {"projeto": projeto, "itens": itens, "categorias": list(categorias.values()),
            "fonte_visual": fonte_visual, "site_url": site_url, "site_url_origem": pub["origem"], "pagina_status": pub["status"],
            "tainacan_url": site["url"] if site else None, "metadados_site": md_completos,
            "erros": erros, "pedidos": pedidos, "eventos": eventos, "filas": filas}


@router.get("/itens/{codigo}")
def item(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    i = con.execute("""SELECT i.*, p.titulo AS projeto_titulo, p.fundo_codigo, f.titulo AS fundo, w.thumb_url, w.url AS site_url, w.status AS site_status, w.documento_url, w.imagem_origem, w.metadados,
                              w.id AS wp_id_exato, i.tainacan_item_id AS tainacan_item_id_salvo
                       FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo JOIN fundo f ON f.codigo=p.fundo_codigo
                       LEFT JOIN wp_item w ON w.id=(
                           SELECT w2.id FROM wp_item w2
                            WHERE w2.codigo_detectado=i.codigo
                              AND w2.colecao_id=?
                            ORDER BY w2.id DESC LIMIT 1
                       ) WHERE i.codigo=?""",
                       (_colecao_config(con, "tainacan.itens_collection_id", 8013), codigo)).fetchone()
    if not i:
        con.close(); raise HTTPException(404, "Folha não existe")
    vizinhos = [r[0] for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo=? ORDER BY serie_codigo, sequencial", (i["projeto_codigo"],))]
    k = vizinhos.index(codigo)
    agentes = [dict(r) for r in con.execute("SELECT a.forma_autorizada, ia.papel, ia.fonte FROM item_agente ia JOIN agente a ON a.id=ia.agente_id WHERE ia.item_codigo=?", (codigo,))]
    con.close()
    d = dict(i); md = json.loads(d.pop("metadados") or "{}")
    d["tainacan_item_id"] = d.pop("wp_id_exato", None)
    from .imagens import e_imagem
    d["imagem_grande"] = d.get("documento_url") if e_imagem(d.get("documento_url")) else None
    d["metadados_site"] = {k2: v for k2, v in md.items() if v and k2 in ("Tipo de desenho", "Técnica", "Suporte original", "Endereço", "Cliente",
                           "Fotógrafo", "Data do registro fotográfico", "Informação atribuída pela catalogação", "Descrição", "Arquiteto")}
    return {"item": d, "anterior": vizinhos[k - 1] if k > 0 else None, "proxima": vizinhos[k + 1] if k < len(vizinhos) - 1 else None,
            "posicao": k + 1, "total": len(vizinhos), "agentes": agentes}


class EdicaoProjeto(BaseModel):
    titulo: str | None = None
    ano: int | None = None
    ano_fim: int | None = None
    cidade: str | None = None
    endereco_obra: str | None = None
    identificacao_original: str | None = None
    cliente: str | None = None
    tipologia: str | None = None
    ambito_conteudo: str | None = None
    contagem_esperada: int | None = None
    lote_teste: bool | None = None
    autorizado_site: bool | None = None


@router.patch("/projetos/{codigo}")
def editar(codigo: str, d: EdicaoProjeto, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
    if not p:
        con.close(); raise HTTPException(404, "Projeto não existe")
    if d.autorizado_site:
        from .rotas_gestao import direitos_permitem_publicar
        msg = direitos_permitem_publicar(con, p["fundo_codigo"])
        if msg:
            con.close(); raise HTTPException(400, msg)
        bloq = con.execute("SELECT itens_autoria_divergente, erros_bloqueantes FROM v_bloqueios_publicacao WHERE codigo=?", (codigo,)).fetchone()
        if bloq and (bloq[0] or bloq[1]):
            con.close(); raise HTTPException(400, f"Não é possível autorizar: {bloq[0] or 0} folha(s) com autoria divergente, {bloq[1] or 0} erro(s) bloqueante(s)")
    if d.ano is not None and not (d.ano == 0 or 1800 <= d.ano <= 2100):
        con.close(); raise HTTPException(400, "Ano inválido (0000 para sem data)")
    campos, vals, mud = [], [], {}
    for k in ("titulo", "ano", "ano_fim", "cidade", "endereco_obra", "identificacao_original", "cliente", "tipologia", "ambito_conteudo", "contagem_esperada"):
        v = getattr(d, k)
        if v is not None and v != p[k]:
            campos.append(f"{k}=?"); vals.append(v); mud[k] = v
    for k in ("lote_teste", "autorizado_site"):
        v = getattr(d, k)
        if v is not None and int(v) != p[k]:
            campos.append(f"{k}=?"); vals.append(int(v)); mud[k] = v
    if campos:
        campos.append("atualizado_em=datetime('now')")
        con.execute(f"UPDATE projeto SET {', '.join(campos)} WHERE codigo=?", (*vals, codigo))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'editado',?,?)", (codigo, u["email"], json.dumps({"antes": {k: p[k] for k in mud}, "depois": mud}, ensure_ascii=False)))
        con.commit()
    con.close()
    site = None
    if mud and any(k in mud for k in ("titulo", "ano", "cidade", "cliente", "tipologia", "ambito_conteudo")):
        from .publicador import atualizar_dossie_no_site
        site = atualizar_dossie_no_site(codigo, mud, u["email"])
    return {"ok": True, "campos": list(mud), "site": site}


class NovoProjeto(BaseModel):
    fundo_codigo: str
    titulo: str
    ano: int = 0
    cidade: str | None = None
    endereco_obra: str | None = None
    identificacao_original: str | None = None


@router.post("/projetos")
def criar(d: NovoProjeto, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    if not con.execute("SELECT 1 FROM fundo WHERE codigo=?", (d.fundo_codigo,)).fetchone():
        con.close(); raise HTTPException(404, "Fundo não existe")
    if not d.titulo.strip():
        con.close(); raise HTTPException(400, "Nome do projeto é obrigatório")
    prox = con.execute("SELECT proximo FROM v_proximo_p WHERE fundo_codigo=?", (d.fundo_codigo,)).fetchone()[0]
    numero = int(prox[1:]); codigo = f"{d.fundo_codigo}-{prox}"
    con.execute("INSERT INTO numero_p (fundo_codigo, numero, reservado_por) VALUES (?,?,?)", (d.fundo_codigo, numero, u["id"]))
    con.execute("INSERT INTO projeto (codigo, fundo_codigo, numero, titulo, ano, cidade, endereco_obra, identificacao_original) VALUES (?,?,?,?,?,?,?,?)",
                (codigo, d.fundo_codigo, numero, d.titulo.strip(), d.ano or 0, d.cidade, d.endereco_obra, d.identificacao_original))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'criado',?,?)", (codigo, u["email"], json.dumps({"titulo": d.titulo})))
    con.commit(); con.close()
    from .publicador import criar_dossie_no_site
    site = criar_dossie_no_site(codigo, u["email"])
    return {"codigo": codigo, "site": site}


@router.post("/projetos/{codigo}/criar-no-site")
def criar_no_site(codigo: str, u: dict = Depends(auth.exige("admin"))) -> dict:
    from .publicador import criar_dossie_no_site
    return criar_dossie_no_site(codigo, u["email"])


class Publicacao(BaseModel):
    acao: str                 # publicar | rascunho | tirar_do_ar
    incluir_folhas: bool = True


RESULTADO = {"publish": "publicados", "draft": "voltaram para rascunho", "private": "despublicados"}


@router.get("/projetos/{codigo}/publicacao")
def condicoes_de_publicacao(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """O que falta para publicar este projeto (cada requisito com o botão que o resolve)."""
    from .publicacao import condicoes_projeto
    con = connect()
    try:
        p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
        if not p:
            raise HTTPException(404, "Projeto não existe")
        r = condicoes_projeto(con, p)
        r.update({"estado": p["status_site"], "pode_agir": u["papel"] in ("admin", "master"),
                  "pode_despublicar": u["papel"] == "master" or p["status_site"] != "no_ar"})
        return r
    finally:
        con.close()


@router.post("/projetos/{codigo}/publicar")
def publicar(codigo: str, d: Publicacao, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Escreve no Tainacan o status do dossiê e das folhas.

    Três fases, para nunca segurar transação do banco durante a rede: (1) ler e validar; (2) falar com o WordPress;
    (3) gravar o resultado local numa conexão nova e curta. Publicar exige todas as condições de publicacao.condicoes_projeto.
    """
    from .publicacao import condicoes_projeto, motivos_bloqueio, persistir_resultado
    from .wp import WP
    alvo = {"publicar": "publish", "rascunho": "draft", "tirar_do_ar": "private"}.get(d.acao)
    if not alvo:
        raise HTTPException(400, "Ação inválida")
    st_painel = {"publish": "no_ar", "draft": "rascunho", "private": "fora_do_ar"}[alvo]

    # fase 1: ler e validar (conexão fechada antes da rede)
    con = connect()
    try:
        p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
        if not p:
            raise HTTPException(404, "Projeto não existe")
        if alvo == "publish":
            falta = motivos_bloqueio(condicoes_projeto(con, p))
            if falta:
                raise HTTPException(400, "Não dá para publicar ainda: " + " | ".join(falta))
        if alvo != "publish" and u["papel"] != "master" and p["status_site"] == "no_ar":
            raise HTTPException(403, "Despublicar o que já está publicado exige o admin master")
        alvos = []
        if p["tainacan_item_id"]:
            col = con.execute("SELECT colecao_id FROM wp_item WHERE id=?", (p["tainacan_item_id"],)).fetchone()
            alvos.append(("projeto", codigo, col[0] if col else 8007, p["tainacan_item_id"]))
        if d.incluir_folhas:
            for i in con.execute("""SELECT i.codigo, i.tainacan_item_id, w.colecao_id FROM item i LEFT JOIN wp_item w ON w.id=i.tainacan_item_id
                                    WHERE i.projeto_codigo=? AND i.tainacan_item_id IS NOT NULL AND i.autoria_divergente=0 AND i.duplicata_de IS NULL""", (codigo,)):
                alvos.append(("item", i[0], i[2] or 8013, i[1]))
    finally:
        con.close()
    if not alvos:
        return {"ok": False, "alterados": 0, "total": 0, "falhas": [],
                "mensagem": "Este projeto ainda não tem registros no site: envie as folhas ao site (como rascunho) antes de mudar a publicação."}

    # fase 2: rede
    try:
        wp = WP()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"Não consegui acessar o WordPress ({str(e)[:160]}). Confira a senha de aplicação em Configurações.")
    sucessos, falhas = [], []
    for tipo, cod, cid, wid in alvos:
        try:
            wp.atualizar_status_item(cid, wid, alvo)
            sucessos.append((tipo, cod, wid))
        except Exception as e:  # noqa: BLE001
            falhas.append({"codigo": cod, "erro": str(e)[:240]})

    # fase 3: gravar o resultado local
    erro_db = persistir_resultado(sucessos, st_painel, alvo, "projeto", codigo, f"site_{d.acao}", u["email"],
                                  {"ok": len(sucessos), "falhas": len(falhas)})
    if erro_db:
        falhas.append({"codigo": codigo, "erro": f"O site foi atualizado, mas não consegui registrar aqui ({erro_db[:120]}). A próxima sincronização acerta."})
    if sucessos and not falhas:
        msg = f"{len(sucessos)} registro(s) {RESULTADO[alvo]}."
    elif sucessos:
        msg = f"{len(sucessos)} de {len(alvos)} registro(s) {RESULTADO[alvo]}; {len(falhas)} falharam (veja a lista)."
    else:
        msg = f"Nenhum registro foi alterado: {len(falhas)} falha(s) ao falar com o site."
    return {"ok": bool(sucessos) and not falhas, "alterados": len(sucessos), "total": len(alvos), "falhas": falhas, "mensagem": msg}


class AcaoProjetosLote(BaseModel):
    codigos: list[str]
    acao: str


@router.post("/projetos/lote")
def projetos_lote(d: AcaoProjetosLote, u: dict = Depends(auth.exige("admin"))) -> dict:
    if d.acao not in ("publicar", "rascunho", "tirar_do_ar"):
        raise HTTPException(400, "Ação em lote inválida")
    codigos = list(dict.fromkeys(c.strip().upper() for c in d.codigos if c.strip()))
    if not codigos:
        raise HTTPException(400, "Selecione ao menos um projeto")
    if len(codigos) > 500:
        raise HTTPException(400, "Ação em lote limitada a 500 projetos por vez")
    ok, falhas = [], []
    for codigo in codigos:
        try:
            r = publicar(codigo, Publicacao(acao=d.acao), u)
            if r.get("ok") and r.get("alterados", 0) > 0:
                ok.append({"codigo": codigo, "alterados": r.get("alterados", 0)})
            elif r.get("ok"):
                falhas.append({"codigo": codigo, "erro": r.get("mensagem") or "Nenhum registro vinculado a este projeto no site."})
            else:
                falhas.append({"codigo": codigo, "erro": ((r.get("falhas") or [{}])[0].get("erro")) or r.get("mensagem") or "Falha na publicação"})
        except HTTPException as e:
            falhas.append({"codigo": codigo, "erro": str(e.detail)})
        except Exception as e:  # noqa: BLE001
            falhas.append({"codigo": codigo, "erro": str(e)[:240]})
    con = connect()
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto','lote',?,?,?)",
                (f"lote_{d.acao}", u["email"], json.dumps({"selecionados": len(codigos), "ok": [x["codigo"] for x in ok], "falhas": falhas}, ensure_ascii=False)))
    con.commit(); con.close()
    return {"selecionados": len(codigos), "ok": ok, "falhas": falhas}

@router.post("/projetos/exportar-selecao")
def exportar_selecao(d: AcaoProjetosLote, u: dict = Depends(auth.exige("leitura"))) -> dict:
    codigos = list(dict.fromkeys(c.strip().upper() for c in d.codigos if c.strip()))
    if not codigos:
        return {"itens": []}
    if len(codigos) > 5000:
        raise HTTPException(400, "Exportação limitada a 5.000 projetos")
    con = connect()
    itens = []
    for i in range(0, len(codigos), 400):
        bloco = codigos[i:i + 400]
        ph = ",".join("?" for _ in bloco)
        rows = con.execute(f"""
            SELECT p.codigo, p.titulo, p.fundo_codigo, f.titulo AS fundo, p.ano, p.cidade,
                   p.status_site, p.autorizado_site, p.atualizado_em,
                   (SELECT COUNT(*) FROM item x WHERE x.projeto_codigo=p.codigo) AS folhas
              FROM projeto p JOIN fundo f ON f.codigo=p.fundo_codigo
             WHERE p.codigo IN ({ph})
             ORDER BY p.codigo
        """, bloco).fetchall()
        itens.extend(dict(r) for r in rows)
    con.close()
    return {"itens": itens}




@router.post("/projetos/{codigo}/subir-folhas")
def subir_folhas(codigo: str, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Cria no Tainacan (rascunho) todas as folhas do projeto que ainda não existem lá."""
    from .publicador import criar_folha_no_site
    con = connect()
    p = con.execute("SELECT tainacan_item_id FROM projeto WHERE codigo=?", (codigo,)).fetchone()
    if not p:
        con.close(); raise HTTPException(404, "Projeto não existe")
    if not p["tainacan_item_id"]:
        con.close(); raise HTTPException(400, "O projeto ainda não tem dossiê no site. Use 'Criar no site' primeiro.")
    pend = [r[0] for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NULL AND autoria_divergente=0 AND duplicata_de IS NULL ORDER BY serie_codigo, sequencial", (codigo,))]
    con.close()
    ok, falhas = 0, []
    for c in pend:
        r = criar_folha_no_site(c, u["email"])
        if r["erro"]: falhas.append({"codigo": c, "erro": r["erro"]})
        else: ok += 1
    return {"pendentes": len(pend), "criadas": ok, "falhas": falhas}
