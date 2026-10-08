"""Uso do acervo: quem pediu para baixar qual material, quando e para quê. SÓ admin e master (há dados pessoais)."""
import csv
import hashlib
import io
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from . import auth, uso_formularios
from .db import connect

router = APIRouter(prefix="/api", tags=["uso"])
JUNCAO = "LEFT JOIN item i ON i.codigo=u.material_codigo LEFT JOIN projeto p ON p.codigo=u.projeto_codigo"


def _wp_http():
    from .wp import WP
    try:
        return WP().h
    except RuntimeError as e:
        raise HTTPException(503, str(e))


def _evento(con, tipo: str, ator: str, detalhe: dict) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('uso','uso',?,?,?)", (tipo, ator, json.dumps(detalhe, ensure_ascii=False)))


def _filtro(q, de, ate, uso, fundo, material) -> tuple[str, list]:
    w, p = ["1=1"], []
    if q:
        like = f"%{q.strip()}%"
        w.append("(u.nome LIKE ? OR u.email LIKE ? OR u.instituicao LIKE ? OR u.material_codigo LIKE ? OR u.uso LIKE ? OR COALESCE(i.titulo,p.titulo) LIKE ?)")
        p += [like] * 6
    if de:
        w.append("date(u.recebida_em) >= date(?)"); p.append(de)
    if ate:
        w.append("date(u.recebida_em) <= date(?)"); p.append(ate)
    if uso:
        w.append("u.uso = ?"); p.append(uso)
    if fundo:
        w.append("u.fundo_codigo = ?"); p.append(fundo)
    if material:
        w.append("u.material_codigo = ?"); p.append(material)
    return " AND ".join(w), p


def _pagina(con, sql_base: str, params: list, pagina: int, por: int, ordem: str, total_sql: str | None = None) -> tuple[list, int, int, int]:
    por = max(1, min(por, 200)); pagina = max(1, pagina)
    total = con.execute(total_sql or f"SELECT COUNT(*) FROM ({sql_base})", params).fetchone()[0]
    linhas = [dict(r) for r in con.execute(f"{sql_base} {ordem} LIMIT ? OFFSET ?", [*params, por, (pagina - 1) * por])]
    return linhas, total, pagina, por


@router.get("/uso")
def listar(pagina: int = 1, por_pagina: int = 50, q: str | None = Query(None), de: str | None = Query(None), ate: str | None = Query(None),
           uso: str | None = Query(None), fundo: str | None = Query(None), material: str | None = Query(None), u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        w, p = _filtro(q, de, ate, uso, fundo, material)
        base = f"""SELECT u.id, u.recebida_em, u.nome, u.email, u.instituicao, u.uso, u.material_codigo, u.pagina, u.anonimizada,
                          COALESCE(i.titulo, p.titulo) AS material_titulo FROM uso_download u {JUNCAO} WHERE {w}"""
        itens, total, pagina, por = _pagina(con, base, p, pagina, por_pagina, "ORDER BY u.recebida_em DESC, u.id DESC")
        return {"itens": itens, "total": total, "pagina": pagina, "por_pagina": por}
    finally:
        con.close()


@router.get("/uso/pessoas")
def pessoas(pagina: int = 1, por_pagina: int = 50, q: str | None = Query(None), de: str | None = Query(None), ate: str | None = Query(None),
            uso: str | None = Query(None), fundo: str | None = Query(None), material: str | None = Query(None), u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        w, p = _filtro(q, de, ate, uso, fundo, material)
        base = f"""SELECT COALESCE(u.email,'') AS email, MAX(u.nome) AS nome, MAX(u.instituicao) AS instituicao, COUNT(*) AS downloads,
                          COUNT(DISTINCT u.material_codigo) AS materiais, MIN(u.recebida_em) AS primeira, MAX(u.recebida_em) AS ultima,
                          GROUP_CONCAT(DISTINCT u.uso) AS usos
                     FROM uso_download u {JUNCAO} WHERE {w} GROUP BY COALESCE(u.email, 'removido-' || u.id)"""
        itens, total, pagina, por = _pagina(con, base, p, pagina, por_pagina, "ORDER BY ultima DESC, downloads DESC")
        return {"itens": itens, "total": total, "pagina": pagina, "por_pagina": por}
    finally:
        con.close()


@router.get("/uso/materiais")
def materiais(pagina: int = 1, por_pagina: int = 50, q: str | None = Query(None), de: str | None = Query(None), ate: str | None = Query(None),
              uso: str | None = Query(None), fundo: str | None = Query(None), material: str | None = Query(None), u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        w, p = _filtro(q, de, ate, uso, fundo, material)
        base = f"""SELECT u.material_codigo AS codigo, COALESCE(i.titulo, p.titulo) AS titulo, COUNT(*) AS downloads,
                          COUNT(DISTINCT COALESCE(u.email, 'removido-' || u.id)) AS pessoas, MAX(u.recebida_em) AS ultima
                     FROM uso_download u {JUNCAO} WHERE {w} AND u.material_codigo IS NOT NULL GROUP BY u.material_codigo"""
        itens, total, pagina, por = _pagina(con, base, p, pagina, por_pagina, "ORDER BY downloads DESC, ultima DESC")
        return {"itens": itens, "total": total, "pagina": pagina, "por_pagina": por}
    finally:
        con.close()


@router.get("/uso/resumo")
def resumo(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        um = lambda sql: con.execute(sql).fetchone()[0]
        coleta = con.execute("SELECT quando, form_id, endpoint, lidas, novas, completo, erro FROM uso_coleta ORDER BY id DESC LIMIT 1").fetchone()
        return {
            "total": um("SELECT COUNT(*) FROM uso_download"),
            "ultimos_30_dias": um("SELECT COUNT(*) FROM uso_download WHERE date(recebida_em) >= date('now','-30 days')"),
            "pessoas": um("SELECT COUNT(DISTINCT email) FROM uso_download WHERE email IS NOT NULL"),
            "materiais": um("SELECT COUNT(DISTINCT material_codigo) FROM uso_download WHERE material_codigo IS NOT NULL"),
            "sem_material": um("SELECT COUNT(*) FROM uso_download WHERE material_codigo IS NULL"),
            "anonimizadas": um("SELECT COUNT(*) FROM uso_download WHERE anonimizada=1"),
            "usos": [dict(r) for r in con.execute("SELECT uso, COUNT(*) AS n FROM uso_download WHERE uso IS NOT NULL GROUP BY uso ORDER BY n DESC LIMIT 20")],
            "ultima_coleta": dict(coleta) if coleta else None,
        }
    finally:
        con.close()


@router.get("/uso/exportar.csv")
def exportar(q: str | None = Query(None), de: str | None = Query(None), ate: str | None = Query(None), uso: str | None = Query(None),
             fundo: str | None = Query(None), material: str | None = Query(None), u: dict = Depends(auth.exige("admin"))) -> Response:
    """Todas as linhas do filtro (não só a página). Inclui telefone. Fica na auditoria (sem os dados das pessoas)."""
    con = connect()
    try:
        w, p = _filtro(q, de, ate, uso, fundo, material)
        linhas = con.execute(f"""SELECT u.recebida_em, u.nome, u.email, u.telefone, u.instituicao, u.uso, u.material_codigo,
                                        COALESCE(i.titulo, p.titulo) AS material_titulo, u.pagina
                                   FROM uso_download u {JUNCAO} WHERE {w} ORDER BY u.recebida_em DESC, u.id DESC""", p).fetchall()
        buf = io.StringIO()
        cw = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL)
        cw.writerow(["quando", "nome", "email", "telefone", "instituicao", "uso_declarado", "material_codigo", "material_titulo", "pagina_da_ficha"])
        for r in linhas:
            cw.writerow([("" if v is None else v) for v in tuple(r)])
        _evento(con, "uso_exportado", u["email"], {"linhas": len(linhas), "filtro": {k: v for k, v in dict(q=q, de=de, ate=ate, uso=uso, fundo=fundo, material=material).items() if v}})
        con.commit()
        return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="camp-uso-{date.today().isoformat()}.csv"'})
    finally:
        con.close()


@router.get("/uso/{uid}")
def detalhe(uid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute(f"""SELECT u.*, COALESCE(i.titulo, p.titulo) AS material_titulo FROM uso_download u {JUNCAO} WHERE u.id=?""", (uid,)).fetchone()
        if not r:
            raise HTTPException(404, "Registro não encontrado")
        d = dict(r)
        d["resposta"] = json.loads(d.pop("resposta_json")) if d.get("resposta_json") else None
        return d
    finally:
        con.close()


class Puxar(BaseModel):
    completo: bool = False


@router.post("/uso/puxar")
def puxar(d: Puxar, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Traz as entradas do formulário do site agora. completo=true lê todo o histórico."""
    h = _wp_http()
    con = connect()
    try:
        r = uso_formularios.puxar(h, con, completo=d.completo)
        _evento(con, "uso_coletado", u["email"], {k: r[k] for k in ("form_id", "lidas", "novas", "completo", "erro")})
        con.commit()
        return r
    finally:
        con.close()


@router.post("/uso/reprocessar")
def reprocessar(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return {"reprocessadas": uso_formularios.reprocessar(con)}
    finally:
        con.close()


class Pessoa(BaseModel):
    email: str


@router.post("/uso/anonimizar")
def anonimizar(d: Pessoa, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Apaga os dados pessoais de uma pessoa (a pedido dela). Na auditoria fica só uma impressão curta do e-mail, nunca o e-mail."""
    if not d.email.strip():
        raise HTTPException(400, "Informe o e-mail da pessoa")
    con = connect()
    try:
        n = uso_formularios.anonimizar_pessoa(con, d.email)
        if not n:
            raise HTTPException(404, "Nenhum registro com esse e-mail")
        _evento(con, "uso_pessoa_anonimizada", u["email"], {"registros": n, "email_hash": hashlib.sha256(d.email.strip().lower().encode()).hexdigest()[:12]})
        con.commit()
        return {"anonimizadas": n}
    finally:
        con.close()
