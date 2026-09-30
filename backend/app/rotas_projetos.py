"""Projetos (dossiês) e itens (folhas): leitura para todos; escrita admin/master."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["projetos"])


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


@router.get("/projetos/{codigo}/detalhe")
def detalhe(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    p = con.execute("SELECT p.*, f.titulo AS fundo, f.sigla FROM projeto p JOIN fundo f ON f.codigo=p.fundo_codigo WHERE p.codigo=?", (codigo,)).fetchone()
    if not p:
        con.close(); raise HTTPException(404, "Projeto não existe")
    itens = [dict(r) for r in con.execute("""
        SELECT i.codigo, i.serie_codigo, i.sequencial, i.titulo, i.tipo_documento, i.folha, i.escala, i.ano_folha, i.status_site,
               i.autoria_divergente, i.duplicata_de, i.espelhado, i.rotacao_aplicada, i.tainacan_item_id, w.thumb_url, w.url
        FROM item i LEFT JOIN wp_item w ON w.id=i.tainacan_item_id WHERE i.projeto_codigo=? ORDER BY i.serie_codigo, i.sequencial""", (codigo,))]
    site = con.execute("SELECT url, metadados FROM wp_item WHERE id=?", (p["tainacan_item_id"],)).fetchone() if p["tainacan_item_id"] else None
    md = json.loads(site["metadados"]) if site and site["metadados"] else {}
    erros = [dict(r) for r in con.execute("SELECT * FROM erro WHERE (codigo=? OR codigo LIKE ?) AND situacao IN ('aberto','em_correcao') ORDER BY gravidade", (codigo, codigo + "-%"))]
    pedidos = [dict(r) for r in con.execute("SELECT s.* FROM solicitacao s JOIN solicitacao_item si ON si.solicitacao_id=s.id WHERE si.codigo=? OR si.codigo LIKE ? GROUP BY s.id", (codigo, codigo + "-%"))]
    eventos = [dict(r) for r in con.execute("SELECT tipo, ator, quando, detalhe FROM evento WHERE entidade='projeto' AND codigo=? ORDER BY id DESC LIMIT 20", (codigo,))]
    filas = [dict(r) for r in con.execute("SELECT id, nome, etapa, folhas_esperadas, folhas_encontradas, atualizado_em FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC", (codigo,))]
    con.close()
    md_uteis = {k: v for k, v in md.items() if v and k in ("Programa / uso", "Natureza do trabalho", "Situação da obra", "Cliente (divulgável)",
                "Colaboradores", "Cálculo estrutural", "Construtora", "UF", "Lacunas conhecidas", "Fases documentadas", "Versões e relações",
                "Nomes alternativos", "Publicações e bibliografia", "Autoria do projeto", "Papel no projeto")}
    return {"projeto": dict(p), "itens": itens, "site_url": site["url"] if site else None, "metadados_site": md_uteis,
            "erros": erros, "pedidos": pedidos, "eventos": eventos, "filas": filas}


@router.get("/itens/{codigo}")
def item(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    i = con.execute("""SELECT i.*, p.titulo AS projeto_titulo, p.fundo_codigo, f.titulo AS fundo, w.thumb_url, w.url AS site_url, w.documento_url, w.metadados
                       FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo JOIN fundo f ON f.codigo=p.fundo_codigo
                       LEFT JOIN wp_item w ON w.id=i.tainacan_item_id WHERE i.codigo=?""", (codigo,)).fetchone()
    if not i:
        con.close(); raise HTTPException(404, "Folha não existe")
    vizinhos = [r[0] for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo=? ORDER BY serie_codigo, sequencial", (i["projeto_codigo"],))]
    k = vizinhos.index(codigo)
    agentes = [dict(r) for r in con.execute("SELECT a.forma_autorizada, ia.papel, ia.fonte FROM item_agente ia JOIN agente a ON a.id=ia.agente_id WHERE ia.item_codigo=?", (codigo,))]
    con.close()
    d = dict(i); md = json.loads(d.pop("metadados") or "{}")
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
        bloq = con.execute("SELECT itens_autoria_divergente, erros_bloqueantes FROM v_bloqueios_publicacao WHERE codigo=?", (codigo,)).fetchone()
        if bloq and (bloq[0] or bloq[1]):
            con.close(); raise HTTPException(400, f"Não é possível autorizar: {bloq[0] or 0} folha(s) com autoria divergente, {bloq[1] or 0} erro(s) bloqueante(s)")
    if d.ano is not None and not (d.ano == 0 or 1800 <= d.ano <= 2100):
        con.close(); raise HTTPException(400, "Ano inválido (0000 para sem data)")
    campos, vals, mud = [], [], {}
    for k in ("titulo", "ano", "ano_fim", "cidade", "endereco_obra", "cliente", "tipologia", "ambito_conteudo", "contagem_esperada"):
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
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'editado',?,?)", (codigo, u["email"], json.dumps(mud, ensure_ascii=False)))
        con.commit()
    con.close()
    return {"ok": True, "campos": list(mud)}


class NovoProjeto(BaseModel):
    fundo_codigo: str
    titulo: str
    ano: int = 0
    cidade: str | None = None
    endereco_obra: str | None = None


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
    con.execute("INSERT INTO projeto (codigo, fundo_codigo, numero, titulo, ano, cidade, endereco_obra) VALUES (?,?,?,?,?,?,?)",
                (codigo, d.fundo_codigo, numero, d.titulo.strip(), d.ano or 0, d.cidade, d.endereco_obra))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'criado',?,?)", (codigo, u["email"], json.dumps({"titulo": d.titulo})))
    con.commit(); con.close()
    return {"codigo": codigo}
