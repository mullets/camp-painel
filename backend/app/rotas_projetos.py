"""Projetos (dossiês) e itens (folhas): leitura para todos; escrita admin/master."""
from __future__ import annotations

import json
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["projetos"])


def _slug_publico(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def _url_publica_projeto(codigo: str, titulo: str, cidade: str | None = None) -> str:
    """Monta a rota pública da CAMP sem repetir cidade/UF no slug."""
    base = (titulo or "").strip()
    if cidade:
        base = re.sub(
            rf"\s*[,\-–]\s*{re.escape(cidade)}(?:\s*[,\-–]\s*[A-Z]{{2}})?\s*$",
            "",
            base,
            flags=re.I,
        ).strip(" ,-–")
    return f"https://camp.arq.br/acervo/projetos/{codigo.lower()}-{_slug_publico(base)}/"


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
               i.autoria_divergente, i.duplicata_de, i.espelhado, i.rotacao_aplicada,
               w.id AS tainacan_item_id, i.tainacan_item_id AS tainacan_item_id_salvo,
               w.thumb_url, w.url,
               CASE WHEN w.id IS NOT NULL AND i.tainacan_item_id IS NOT NULL AND w.id != i.tainacan_item_id THEN 1 ELSE 0 END AS vinculo_corrigido
        FROM item i
        LEFT JOIN wp_item w ON w.id=(
            SELECT w2.id FROM wp_item w2
            WHERE w2.codigo_detectado=i.codigo
            ORDER BY w2.id DESC LIMIT 1
        )
        WHERE i.projeto_codigo=? ORDER BY i.serie_codigo, i.sequencial""", (codigo,))]
    site = con.execute("""
        SELECT * FROM wp_item
        WHERE codigo_detectado=?
        ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END, id DESC LIMIT 1
    """, (codigo, p["tainacan_item_id"] or -1)).fetchone()
    md = json.loads(site["metadados"]) if site and site["metadados"] else {}
    erros = [dict(r) for r in con.execute("SELECT * FROM erro WHERE (codigo=? OR codigo LIKE ?) AND situacao IN ('aberto','em_correcao') ORDER BY gravidade", (codigo, codigo + "-%"))]
    pedidos = [dict(r) for r in con.execute("SELECT s.* FROM solicitacao s JOIN solicitacao_item si ON si.solicitacao_id=s.id WHERE si.codigo=? OR si.codigo LIKE ? GROUP BY s.id", (codigo, codigo + "-%"))]
    eventos = [dict(r) for r in con.execute("SELECT tipo, ator, quando, detalhe FROM evento WHERE entidade='projeto' AND codigo=? ORDER BY id DESC LIMIT 20", (codigo,))]
    filas = [dict(r) for r in con.execute("SELECT id, nome, etapa, folhas_esperadas, folhas_encontradas, atualizado_em FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC", (codigo,))]
    con.close()
    md_completos = {k: v for k, v in md.items() if v not in (None, "", [], {})}
    site_url = _url_publica_projeto(codigo, p["titulo"], p["cidade"])
    projeto = dict(p)
    projeto["tainacan_item_id_salvo"] = projeto.get("tainacan_item_id")
    projeto["tainacan_item_id"] = site["id"] if site else None
    return {"projeto": projeto, "itens": itens, "site_url": site_url,
            "tainacan_url": site["url"] if site else None, "metadados_site": md_completos,
            "erros": erros, "pedidos": pedidos, "eventos": eventos, "filas": filas}


@router.get("/itens/{codigo}")
def item(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    i = con.execute("""SELECT i.*, p.titulo AS projeto_titulo, p.fundo_codigo, f.titulo AS fundo, w.thumb_url, w.url AS site_url, w.documento_url, w.metadados,
                              w.id AS wp_id_exato, i.tainacan_item_id AS tainacan_item_id_salvo
                       FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo JOIN fundo f ON f.codigo=p.fundo_codigo
                       LEFT JOIN wp_item w ON w.id=(
                           SELECT w2.id FROM wp_item w2 WHERE w2.codigo_detectado=i.codigo ORDER BY w2.id DESC LIMIT 1
                       ) WHERE i.codigo=?""", (codigo,)).fetchone()
    if not i:
        con.close(); raise HTTPException(404, "Folha não existe")
    vizinhos = [r[0] for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo=? ORDER BY serie_codigo, sequencial", (i["projeto_codigo"],))]
    k = vizinhos.index(codigo)
    agentes = [dict(r) for r in con.execute("SELECT a.forma_autorizada, ia.papel, ia.fonte FROM item_agente ia JOIN agente a ON a.id=ia.agente_id WHERE ia.item_codigo=?", (codigo,))]
    con.close()
    d = dict(i); md = json.loads(d.pop("metadados") or "{}")
    d["tainacan_item_id"] = d.pop("wp_id_exato", None)
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


@router.post("/projetos/{codigo}/publicar")
def publicar(codigo: str, d: Publicacao, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Escreve no Tainacan: muda status do dossiê e das folhas. publicar exige projeto autorizado e sem bloqueios."""
    from .wp import WP
    alvo = {"publicar": "publish", "rascunho": "draft", "tirar_do_ar": "private"}.get(d.acao)
    if not alvo:
        raise HTTPException(400, "Ação inválida")
    con = connect()
    p = con.execute("SELECT * FROM projeto WHERE codigo=?", (codigo,)).fetchone()
    if not p:
        con.close(); raise HTTPException(404, "Projeto não existe")
    if alvo == "publish":
        from .rotas_gestao import direitos_permitem_publicar
        msg = direitos_permitem_publicar(con, p["fundo_codigo"])
        if msg:
            con.close(); raise HTTPException(400, msg)
        if not p["autorizado_site"]:
            con.close(); raise HTTPException(400, "Projeto não autorizado para o site. Autorize antes de publicar.")
        bloq = con.execute("SELECT itens_autoria_divergente, erros_bloqueantes FROM v_bloqueios_publicacao WHERE codigo=?", (codigo,)).fetchone()
        if bloq and (bloq[0] or bloq[1]):
            con.close(); raise HTTPException(400, f"Bloqueado: {bloq[0] or 0} autoria divergente, {bloq[1] or 0} erro(s) bloqueante(s)")
        if p["lote_teste"]:
            con.close(); raise HTTPException(400, "Lote de teste não vai ao ar")
    if alvo != "publish" and u["papel"] != "master" and p["status_site"] == "no_ar":
        con.close(); raise HTTPException(403, "Tirar do ar o que já está publicado exige o admin master")
    wp = WP()
    feitos, falhas = [], []
    alvos = []
    if p["tainacan_item_id"]:
        col = con.execute("SELECT colecao_id FROM wp_item WHERE id=?", (p["tainacan_item_id"],)).fetchone()
        alvos.append(("projeto", codigo, col[0] if col else 8007, p["tainacan_item_id"]))
    if d.incluir_folhas:
        for i in con.execute("""SELECT i.codigo, i.tainacan_item_id, w.colecao_id FROM item i LEFT JOIN wp_item w ON w.id=i.tainacan_item_id
                                WHERE i.projeto_codigo=? AND i.tainacan_item_id IS NOT NULL AND i.autoria_divergente=0 AND i.duplicata_de IS NULL""", (codigo,)):
            alvos.append(("item", i[0], i[2] or 8013, i[1]))
    st_painel = {"publish": "no_ar", "draft": "rascunho", "private": "fora_do_ar"}[alvo]
    for tipo, cod, cid, wid in alvos:
        try:
            wp.atualizar_status_item(cid, wid, alvo)
            con.execute(f"UPDATE {tipo} SET status_site=?, atualizado_em=datetime('now') WHERE codigo=?", (st_painel, cod))
            con.execute("UPDATE wp_item SET status=? WHERE id=?", (alvo, wid))
            feitos.append(cod)
        except Exception as e:  # noqa: BLE001
            falhas.append({"codigo": cod, "erro": str(e)[:200]})
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,?,?,?)",
                (codigo, f"site_{d.acao}", u["email"], json.dumps({"ok": len(feitos), "falhas": len(falhas)})))
    con.commit(); con.close()
    return {"ok": not falhas, "alterados": len(feitos), "falhas": falhas}


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
