"""Uso do acervo: quem pediu para baixar qual material, quando e para quê. SÓ admin e master (há dados pessoais)."""
import csv
import hashlib
import io
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from . import auth, email_envio, uso_formularios
from .db import connect

router = APIRouter(prefix="/api", tags=["uso"])
JUNCAO = "LEFT JOIN item i ON i.codigo=u.material_codigo LEFT JOIN projeto p ON p.codigo=u.projeto_codigo"
FILTROS = ("q", "de", "ate", "uso", "fundo", "material")
LIMITE_EMAILS_POR_HORA = 30


def _wp_http():
    from .wp import WP
    try:
        return WP().h
    except RuntimeError as e:
        raise HTTPException(503, str(e))


def _evento(con, tipo: str, ator: str, detalhe: dict) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('uso','uso',?,?,?)", (tipo, ator, json.dumps(detalhe, ensure_ascii=False)))


def _hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:12]


def _ids(texto: str | None) -> list[int]:
    if not texto:
        return []
    try:
        ids = [int(x) for x in texto.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, "ids inválidos")
    if len(ids) > 1000:
        raise HTTPException(400, "No máximo 1000 pedidos por vez")
    return ids


def _filtro(q, de, ate, uso, fundo, material, ids: list[int] | None = None) -> tuple[str, list]:
    w, p = ["u.apagada=0"], []          # entradas APAGADAS nunca aparecem em nada
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
    if ids:
        w.append("u.id IN (" + ",".join("?" * len(ids)) + ")"); p += ids
    return " AND ".join(w), p


def _sql_pedidos(w: str) -> str:
    return f"""SELECT u.id, u.recebida_em, u.nome, u.email, u.instituicao, u.uso, u.material_codigo, u.pagina, u.anonimizada,
                      COALESCE(i.titulo, p.titulo) AS material_titulo FROM uso_download u {JUNCAO} WHERE {w}"""


def _sql_pessoas(w: str) -> str:
    return f"""SELECT COALESCE(u.email,'') AS email, MAX(u.nome) AS nome, MAX(u.instituicao) AS instituicao, COUNT(*) AS downloads,
                      COUNT(DISTINCT u.material_codigo) AS materiais, MIN(u.recebida_em) AS primeira, MAX(u.recebida_em) AS ultima,
                      GROUP_CONCAT(DISTINCT u.uso) AS usos
                 FROM uso_download u {JUNCAO} WHERE {w} GROUP BY COALESCE(u.email, 'removido-' || u.id)"""


def _sql_materiais(w: str) -> str:
    return f"""SELECT u.material_codigo AS codigo, COALESCE(i.titulo, p.titulo) AS titulo, COUNT(*) AS downloads,
                      COUNT(DISTINCT COALESCE(u.email, 'removido-' || u.id)) AS pessoas, MAX(u.recebida_em) AS ultima
                 FROM uso_download u {JUNCAO} WHERE {w} AND u.material_codigo IS NOT NULL GROUP BY u.material_codigo"""


def _pagina(con, sql_base: str, params: list, pagina: int, por: int, ordem: str) -> tuple[list, int, int, int]:
    por = max(1, min(por, 200)); pagina = max(1, pagina)
    total = con.execute(f"SELECT COUNT(*) FROM ({sql_base})", params).fetchone()[0]
    linhas = [dict(r) for r in con.execute(f"{sql_base} {ordem} LIMIT ? OFFSET ?", [*params, por, (pagina - 1) * por])]
    return linhas, total, pagina, por


def _lista(sql, ordem, pagina, por_pagina, q, de, ate, uso, fundo, material) -> dict:
    con = connect()
    try:
        w, p = _filtro(q, de, ate, uso, fundo, material)
        itens, total, pagina, por = _pagina(con, sql(w), p, pagina, por_pagina, ordem)
        return {"itens": itens, "total": total, "pagina": pagina, "por_pagina": por}
    finally:
        con.close()


@router.get("/uso")
def listar(pagina: int = 1, por_pagina: int = 50, q: str | None = Query(None), de: str | None = Query(None), ate: str | None = Query(None),
           uso: str | None = Query(None), fundo: str | None = Query(None), material: str | None = Query(None), u: dict = Depends(auth.exige("admin"))) -> dict:
    return _lista(_sql_pedidos, "ORDER BY u.recebida_em DESC, u.id DESC", pagina, por_pagina, q, de, ate, uso, fundo, material)


@router.get("/uso/pessoas")
def pessoas(pagina: int = 1, por_pagina: int = 50, q: str | None = Query(None), de: str | None = Query(None), ate: str | None = Query(None),
            uso: str | None = Query(None), fundo: str | None = Query(None), material: str | None = Query(None), u: dict = Depends(auth.exige("admin"))) -> dict:
    return _lista(_sql_pessoas, "ORDER BY ultima DESC, downloads DESC", pagina, por_pagina, q, de, ate, uso, fundo, material)


@router.get("/uso/materiais")
def materiais(pagina: int = 1, por_pagina: int = 50, q: str | None = Query(None), de: str | None = Query(None), ate: str | None = Query(None),
              uso: str | None = Query(None), fundo: str | None = Query(None), material: str | None = Query(None), u: dict = Depends(auth.exige("admin"))) -> dict:
    return _lista(_sql_materiais, "ORDER BY downloads DESC, ultima DESC", pagina, por_pagina, q, de, ate, uso, fundo, material)


@router.get("/uso/resumo")
def resumo(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        um = lambda sql: con.execute(sql).fetchone()[0]
        coleta = con.execute("SELECT quando, form_id, endpoint, lidas, novas, completo, erro FROM uso_coleta ORDER BY id DESC LIMIT 1").fetchone()
        return {
            "total": um("SELECT COUNT(*) FROM uso_download WHERE apagada=0"),
            "ultimos_30_dias": um("SELECT COUNT(*) FROM uso_download WHERE apagada=0 AND date(recebida_em) >= date('now','-30 days')"),
            "pessoas": um("SELECT COUNT(DISTINCT email) FROM uso_download WHERE apagada=0 AND email IS NOT NULL"),
            "materiais": um("SELECT COUNT(DISTINCT material_codigo) FROM uso_download WHERE apagada=0 AND material_codigo IS NOT NULL"),
            "sem_material": um("SELECT COUNT(*) FROM uso_download WHERE apagada=0 AND material_codigo IS NULL"),
            "anonimizadas": um("SELECT COUNT(*) FROM uso_download WHERE apagada=0 AND anonimizada=1"),
            "apagadas": um("SELECT COUNT(*) FROM uso_download WHERE apagada=1"),
            "usos": [dict(r) for r in con.execute("SELECT uso, COUNT(*) AS n FROM uso_download WHERE apagada=0 AND uso IS NOT NULL GROUP BY uso ORDER BY n DESC LIMIT 20")],
            "ultima_coleta": dict(coleta) if coleta else None,
        }
    finally:
        con.close()


@router.get("/uso/exportar.csv")
def exportar(visao: str = Query("pedidos"), ids: str | None = Query(None), q: str | None = Query(None), de: str | None = Query(None), ate: str | None = Query(None),
             uso: str | None = Query(None), fundo: str | None = Query(None), material: str | None = Query(None), u: dict = Depends(auth.exige("admin"))) -> Response:
    """Todas as linhas do filtro (não só a página), na visão da aba (pedidos | pessoas | materiais). `ids` exporta só os pedidos escolhidos.
    Inclui telefone nos pedidos. Fica na auditoria (sem os dados das pessoas)."""
    if visao not in ("pedidos", "pessoas", "materiais"):
        raise HTTPException(400, "visao deve ser pedidos, pessoas ou materiais")
    idl = _ids(ids)
    if idl and visao != "pedidos":
        raise HTTPException(400, "Escolher pedidos só vale na visão 'pedidos'")
    con = connect()
    try:
        w, p = _filtro(q, de, ate, uso, fundo, material, idl)
        buf = io.StringIO()
        cw = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL)
        if visao == "pedidos":
            cw.writerow(["quando", "nome", "email", "telefone", "instituicao", "uso_declarado", "material_codigo", "material_titulo", "pagina_da_ficha"])
            linhas = con.execute(f"""SELECT u.recebida_em, u.nome, u.email, u.telefone, u.instituicao, u.uso, u.material_codigo,
                                            COALESCE(i.titulo, p.titulo) AS material_titulo, u.pagina
                                       FROM uso_download u {JUNCAO} WHERE {w} ORDER BY u.recebida_em DESC, u.id DESC""", p).fetchall()
        elif visao == "pessoas":
            cw.writerow(["email", "nome", "instituicao", "pedidos", "materiais_diferentes", "primeiro_pedido", "ultimo_pedido", "usos_declarados"])
            linhas = con.execute(f"{_sql_pessoas(w)} ORDER BY ultima DESC", p).fetchall()
        else:
            cw.writerow(["material_codigo", "material_titulo", "pedidos", "pessoas", "ultimo_pedido"])
            linhas = con.execute(f"{_sql_materiais(w)} ORDER BY downloads DESC, ultima DESC", p).fetchall()
        for r in linhas:
            cw.writerow([("" if v is None else v) for v in tuple(r)])
        _evento(con, "uso_exportado", u["email"], {"visao": visao, "linhas": len(linhas), "escolhidos": len(idl),
                                                   "filtro": {k: v for k, v in dict(q=q, de=de, ate=ate, uso=uso, fundo=fundo, material=material).items() if v}})
        con.commit()
        return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="camp-uso-{visao}-{date.today().isoformat()}.csv"'})
    finally:
        con.close()


@router.get("/uso/email/config")
def email_config(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Se o envio de e-mail está configurado, e os textos padrão. NUNCA devolve a senha."""
    con = connect()
    try:
        c = email_envio.configuracao(con)
        g = lambda k: (con.execute("SELECT valor FROM configuracao WHERE chave=?", (k,)).fetchone() or [""])[0] or ""
        return {"configurado": email_envio.configurado(c), "remetente": c["remetente"] or None, "assunto": g("uso.email_assunto"), "corpo": g("uso.email_corpo")}
    finally:
        con.close()


@router.get("/uso/{uid}")
def detalhe(uid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute(f"""SELECT u.*, COALESCE(i.titulo, p.titulo) AS material_titulo FROM uso_download u {JUNCAO} WHERE u.id=? AND u.apagada=0""", (uid,)).fetchone()
        if not r:
            raise HTTPException(404, "Registro não encontrado")
        d = dict(r)
        d["resposta"] = json.loads(d.pop("resposta_json")) if d.get("resposta_json") else None
        d["emails"] = [dict(x) for x in con.execute("SELECT enviado_em, enviado_por, assunto, ok FROM uso_email WHERE uso_id=? ORDER BY id DESC LIMIT 20", (uid,))]
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
    """Apaga só os DADOS PESSOAIS de uma pessoa (a pedido dela); o uso e o material continuam nas contagens."""
    if not d.email.strip():
        raise HTTPException(400, "Informe o e-mail da pessoa")
    con = connect()
    try:
        n = uso_formularios.anonimizar_pessoa(con, d.email)
        if not n:
            raise HTTPException(404, "Nenhum registro com esse e-mail")
        _evento(con, "uso_pessoa_anonimizada", u["email"], {"registros": n, "email_hash": _hash(d.email)})
        con.commit()
        return {"anonimizadas": n}
    finally:
        con.close()


class Apagar(BaseModel):
    ids: list[int] = []
    email: str | None = None
    filtro: dict | None = None      # {q, de, ate, uso, fundo, material}: pelo menos UM campo preenchido


@router.post("/uso/apagar")
def apagar(d: Apagar, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Apaga entradas DE VERDADE: somem de listas, contagens e exportações, e todos os dados pessoais são removidos.
    Só resta uma marca invisível (formulário + id da entrada) para uma coleta futura não trazer a entrada de volta.
    Três modos, exatamente um: `ids`, `email` (todas da pessoa) ou `filtro` (todas as do filtro; exige ao menos um campo)."""
    modos = [bool(d.ids), bool((d.email or "").strip()), bool(d.filtro)]
    if sum(modos) != 1:
        raise HTTPException(400, "Informe exatamente um: ids, email ou filtro")
    con = connect()
    try:
        detalhe: dict = {}
        if d.ids:
            if len(d.ids) > 1000:
                raise HTTPException(400, "No máximo 1000 pedidos por vez")
            ids, detalhe = d.ids, {"modo": "ids"}
        elif (d.email or "").strip():
            ids = [r[0] for r in con.execute("SELECT id FROM uso_download WHERE apagada=0 AND lower(email)=lower(?)", (d.email.strip(),))]
            detalhe = {"modo": "email", "email_hash": _hash(d.email)}
        else:
            f = {k: (str(v).strip() if v is not None else "") for k, v in d.filtro.items() if k in FILTROS}
            if not any(f.values()):
                raise HTTPException(400, "Para apagar por filtro, preencha ao menos um filtro (não dá para apagar tudo de uma vez)")
            w, p = _filtro(*(f.get(k) or None for k in FILTROS))
            ids = [r[0] for r in con.execute(f"SELECT u.id FROM uso_download u {JUNCAO} WHERE {w}", p)]
            detalhe = {"modo": "filtro", "filtro": {k: v for k, v in f.items() if v}}
        n = uso_formularios.apagar_ids(con, ids)
        if not n:
            raise HTTPException(404, "Nenhuma entrada encontrada para apagar")
        _evento(con, "uso_apagado", u["email"], {**detalhe, "apagadas": n})
        con.commit()
        return {"apagadas": n}
    finally:
        con.close()


@router.delete("/uso/{uid}")
def apagar_um(uid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        n = uso_formularios.apagar_ids(con, [uid])
        if not n:
            raise HTTPException(404, "Registro não encontrado")
        _evento(con, "uso_apagado", u["email"], {"modo": "um", "apagadas": 1})
        con.commit()
        return {"apagadas": 1}
    finally:
        con.close()


class EmailPedido(BaseModel):
    assunto: str
    corpo: str


@router.post("/uso/{uid}/email")
def enviar_email(uid: int, d: EmailPedido, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Manda UM e-mail para a pessoa deste pedido. O destinatário vem do banco, nunca do corpo da requisição."""
    assunto, corpo = d.assunto.strip(), d.corpo.strip()
    if not assunto or len(assunto) > 200 or "\n" in assunto or "\r" in assunto:
        raise HTTPException(400, "Assunto obrigatório, com até 200 caracteres e sem quebra de linha")
    if not corpo or len(corpo) > 10000:
        raise HTTPException(400, "Mensagem obrigatória, com até 10.000 caracteres")
    con = connect()
    try:
        r = con.execute("SELECT id, email FROM uso_download WHERE id=? AND apagada=0", (uid,)).fetchone()
        if not r or not r["email"]:
            raise HTTPException(404, "Este pedido não tem e-mail (apagado ou sem dados pessoais)")
        c = email_envio.configuracao(con)
        if not email_envio.configurado(c):
            raise HTTPException(409, "O envio de e-mail não está configurado: preencha smtp.host, smtp.usuario, smtp.senha e smtp.remetente em Configurações")
        if con.execute("SELECT COUNT(*) FROM uso_email WHERE ok=1 AND enviado_em >= datetime('now','-1 hour')").fetchone()[0] >= LIMITE_EMAILS_POR_HORA:
            raise HTTPException(429, f"Limite de {LIMITE_EMAILS_POR_HORA} e-mails por hora atingido")
        try:
            email_envio.enviar(c, r["email"], assunto, corpo, responder_para=u["email"])
            ok, erro = 1, None
        except email_envio.EnvioErro as e:
            ok, erro = 0, str(e)
        con.execute("INSERT INTO uso_email (uso_id, enviado_por, assunto, ok, erro) VALUES (?,?,?,?,?)", (uid, u["email"], assunto, ok, erro))
        _evento(con, "uso_email_enviado" if ok else "uso_email_falhou", u["email"], {"uso_id": uid, "email_hash": _hash(r["email"]), "erro": erro})
        con.commit()
        if not ok:
            raise HTTPException(502, f"Não consegui enviar: {erro}")
        return {"enviado": True, "para": r["email"]}
    finally:
        con.close()
