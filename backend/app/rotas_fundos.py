"""Fundos e agentes: leitura para todos, escrita para admin/master. Códigos imutáveis."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["fundos"])
RE_SIGLA = re.compile(r"^[A-Z]{3}$")


def _evento(con, entidade, codigo, tipo, ator, detalhe=None):
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)",
                (entidade, codigo, tipo, ator, json.dumps(detalhe, ensure_ascii=False) if detalhe else None))


class NovoFundo(BaseModel):
    titulo: str
    sigla: str
    data_inicio: int | None = None
    data_fim: int | None = None
    tipo_agente: str = "pessoa"          # pessoa | entidade_coletiva | familia


class EdicaoFundo(BaseModel):
    titulo: str | None = None
    sigla: str | None = None             # só aceita se ainda estiver vazia
    data_inicio: int | None = None
    data_fim: int | None = None
    dimensao_suporte: str | None = None
    historia_arquivistica: str | None = None
    fonte_historia: str | None = None
    procedencia: str | None = None
    condicoes_acesso: str | None = None
    condicoes_reproducao: str | None = None
    status_site: str | None = None
    motivo_fora_do_ar: str | None = None
    mostrar_doador: bool | None = None   # B1: o site pode mostrar o nome de quem entregou o acervo


def _validar_sigla(con, sigla: str, ignorar: str | None = None):
    sigla = sigla.upper().strip()
    if not RE_SIGLA.match(sigla):
        raise HTTPException(400, "Sigla precisa ter exatamente 3 letras (A–Z)")
    dup = con.execute("SELECT codigo FROM fundo WHERE sigla=? AND codigo<>?", (sigla, ignorar or "")).fetchone()
    if dup:
        raise HTTPException(409, f"Sigla {sigla} já é do fundo {dup[0]}")
    return sigla


def _validar_anos(ini, fim):
    for a in (ini, fim):
        if a is not None and not (1800 <= a <= 2100):
            raise HTTPException(400, "Ano fora do intervalo 1800–2100")
    if ini and fim and fim < ini:
        raise HTTPException(400, "Ano final anterior ao inicial")


@router.get("/fundos/resumo")
def resumo(u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect()
    rows = con.execute("""
        SELECT f.codigo, f.sigla, f.titulo, f.data_inicio, f.data_fim, f.status_site, f.motivo_fora_do_ar, f.ativo,
               (SELECT COUNT(*) FROM projeto p WHERE p.fundo_codigo=f.codigo AND p.mesclado_em IS NULL) AS projetos,
               (SELECT COUNT(*) FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo WHERE p.fundo_codigo=f.codigo) AS itens,
               (SELECT COUNT(*) FROM wp_item w WHERE w.fundo_detectado=f.codigo AND w.status='publish') AS no_site,
               (SELECT COUNT(*) FROM wp_item w WHERE w.fundo_detectado=f.codigo AND w.status='draft') AS rascunhos_site,
               (SELECT GROUP_CONCAT(a.forma_autorizada, ' · ') FROM fundo_agente fa JOIN agente a ON a.id=fa.agente_id
                 WHERE fa.fundo_codigo=f.codigo AND fa.papel='produtor') AS produtores,
               COALESCE((SELECT situacao FROM direitos_fundo d WHERE d.fundo_codigo=f.codigo),'nao_definida') AS direitos
        FROM fundo f ORDER BY f.codigo""").fetchall()
    out = [dict(r) for r in rows]
    from .pendencias import fundos_travados       # a mesma regra do número "travados por direitos" do painel inicial
    travados = {f["codigo"]: f for f in fundos_travados(con)}
    for f in out:
        t = travados.get(f["codigo"])
        f["travado"], f["travado_projetos"] = bool(t), (t["projetos"] if t else 0)
    # termos que existem no site mas não têm código na tabela
    for r in con.execute("""SELECT x.id, x.nome, e.observacao FROM wp_termo x JOIN wp_taxonomia t ON t.id=x.taxonomia_id
                            LEFT JOIN fundo_termo_site e ON e.nome_site=x.nome WHERE t.nome='Fundos' AND (e.fundo_codigo IS NULL)"""):
        nome = r[1]
        pub = con.execute("SELECT COUNT(*) FROM wp_item WHERE status='publish' AND json_extract(metadados,'$.Fundo')=?", (nome,)).fetchone()[0]
        rasc = con.execute("SELECT COUNT(*) FROM wp_item WHERE status='draft' AND json_extract(metadados,'$.Fundo')=?", (nome,)).fetchone()[0]
        out.append({"codigo": None, "sigla": None, "titulo": nome, "data_inicio": None, "data_fim": None, "status_site": "no_ar" if pub else ("rascunho" if rasc else "nao_publicado"),
                    "motivo_fora_do_ar": None, "ativo": 1, "projetos": 0, "itens": 0, "no_site": pub, "rascunhos_site": rasc, "produtores": None,
                    "so_no_site": True, "termo_id": r[0], "observacao": r[2] or "existe no site, sem código na tabela de autoridade"})
    con.close()
    return out


@router.get("/fundos/{codigo}/detalhe")
def detalhe(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    f = con.execute("SELECT * FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    if not f:
        con.close(); raise HTTPException(404, "Fundo não existe")
    agentes = [dict(r) for r in con.execute("""
        SELECT a.id, a.tipo, a.forma_autorizada, a.existencia_inicio, a.existencia_fim, fa.papel, fa.inicio, fa.fim,
               (SELECT GROUP_CONCAT(forma, ' | ') FROM agente_forma_variante v WHERE v.agente_id=a.id) AS formas
        FROM fundo_agente fa JOIN agente a ON a.id=fa.agente_id WHERE fa.fundo_codigo=? ORDER BY fa.papel, a.forma_autorizada""", (codigo,))]
    projetos = [dict(r) for r in con.execute(
        "SELECT codigo, titulo, ano, cidade, status_site, autorizado_site FROM projeto WHERE fundo_codigo=? AND mesclado_em IS NULL ORDER BY codigo", (codigo,))]
    site = [dict(r) for r in con.execute(
        "SELECT status, COUNT(*) AS n FROM wp_item WHERE fundo_detectado=? GROUP BY status", (codigo,))]
    eventos = [dict(r) for r in con.execute(
        "SELECT tipo, ator, quando, detalhe FROM evento WHERE entidade='fundo' AND codigo=? ORDER BY id DESC LIMIT 20", (codigo,))]
    con.close()
    return {"fundo": dict(f), "agentes": agentes, "projetos": projetos, "site": site, "eventos": eventos}


@router.post("/fundos")
def reservar(d: NovoFundo, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    sigla = _validar_sigla(con, d.sigla)
    _validar_anos(d.data_inicio, d.data_fim)
    if not d.titulo.strip():
        con.close(); raise HTTPException(400, "Nome do fundo é obrigatório")
    if con.execute("SELECT 1 FROM fundo WHERE lower(titulo)=lower(?)", (d.titulo.strip(),)).fetchone():
        con.close(); raise HTTPException(409, "Já existe fundo com esse nome")
    codigo = con.execute("SELECT codigo FROM v_proximo_fundo").fetchone()[0]
    con.execute("INSERT INTO fundo (codigo, sigla, titulo, data_inicio, data_fim, credito_padrao) VALUES (?,?,?,?,?,?)",
                (codigo, sigla, d.titulo.strip(), d.data_inicio, d.data_fim,
                 f"Acervo {d.titulo.strip()}/CAMP - Casa da Arquitetura Moderna Paulista"))
    ag = con.execute("SELECT id FROM agente WHERE forma_autorizada=?", (d.titulo.strip(),)).fetchone()
    aid = ag[0] if ag else con.execute("INSERT INTO agente (tipo, forma_autorizada, existencia_inicio, existencia_fim) VALUES (?,?,?,?)",
                                       (d.tipo_agente, d.titulo.strip(), d.data_inicio, d.data_fim)).lastrowid
    con.execute("INSERT OR IGNORE INTO fundo_agente (fundo_codigo, agente_id, papel, inicio, fim) VALUES (?,?,'produtor',?,?)",
                (codigo, aid, d.data_inicio, d.data_fim))
    _evento(con, "fundo", codigo, "criado", u["email"], {"sigla": sigla, "titulo": d.titulo})
    con.commit(); con.close()
    from .publicador import criar_fundo_no_site
    site = criar_fundo_no_site(codigo, u["email"])
    return {"codigo": codigo, "sigla": sigla, "site": site}


@router.patch("/fundos/{codigo}")
def editar(codigo: str, d: EdicaoFundo, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    f = con.execute("SELECT * FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    if not f:
        con.close(); raise HTTPException(404, "Fundo não existe")
    campos, vals, mud = [], [], {}
    if d.sigla is not None:
        if f["sigla"]:
            con.close(); raise HTTPException(400, f"Sigla já definida ({f['sigla']}). Sigla é imutável: entra no nome dos arquivos.")
        campos.append("sigla=?"); vals.append(_validar_sigla(con, d.sigla, codigo)); mud["sigla"] = vals[-1]
    ini = d.data_inicio if d.data_inicio is not None else f["data_inicio"]
    fim = d.data_fim if d.data_fim is not None else f["data_fim"]
    _validar_anos(ini, fim)
    if d.status_site is not None:
        if d.status_site not in ("nao_publicado", "rascunho", "no_ar", "fora_do_ar"):
            con.close(); raise HTTPException(400, "Situação inválida")
        if d.status_site == "fora_do_ar" and not (d.motivo_fora_do_ar or f["motivo_fora_do_ar"]):
            con.close(); raise HTTPException(400, "Informe o motivo para despublicar")
        if u["papel"] != "master" and d.status_site != f["status_site"] and d.status_site in ("no_ar", "fora_do_ar"):
            con.close(); raise HTTPException(403, "Colocar ou tirar um fundo inteiro do ar exige o admin master")
    if d.historia_arquivistica and not (d.fonte_historia or f["fonte_historia"]):
        con.close(); raise HTTPException(400, "História arquivística exige fonte citada")
    for k in ("titulo", "data_inicio", "data_fim", "dimensao_suporte", "historia_arquivistica", "fonte_historia",
              "procedencia", "condicoes_acesso", "condicoes_reproducao", "status_site", "motivo_fora_do_ar"):
        v = getattr(d, k)
        if v is not None and v != f[k]:
            campos.append(f"{k}=?"); vals.append(v); mud[k] = v
    if d.mostrar_doador is not None and int(d.mostrar_doador) != (f["mostrar_doador"] or 0):
        campos.append("mostrar_doador=?"); vals.append(int(d.mostrar_doador)); mud["mostrar_doador"] = int(d.mostrar_doador)
    if not campos:
        con.close(); return {"ok": True, "mudou": False}
    campos.append("atualizado_em=datetime('now')")
    con.execute(f"UPDATE fundo SET {', '.join(campos)} WHERE codigo=?", (*vals, codigo))
    _evento(con, "fundo", codigo, "editado", u["email"], {"antes": {k: f[k] for k in mud}, "depois": mud})
    con.commit(); con.close()
    site = None
    if "titulo" in mud:
        from .publicador import renomear_fundo_no_site
        site = renomear_fundo_no_site(codigo, mud["titulo"], u["email"])
    desc = None
    if set(mud) & CAMPOS_DESCRICAO_SITE:   # B1: o texto do fundo no site acompanha a edição
        desc = _descricao_no_site(codigo, u["email"])
    return {"ok": True, "mudou": True, "campos": list(mud), "site": site, "descricao_site": desc}


CAMPOS_DESCRICAO_SITE = {"data_inicio", "data_fim", "dimensao_suporte", "historia_arquivistica", "procedencia", "condicoes_acesso",
                         "condicoes_reproducao", "mostrar_doador", "sigla"}


def _descricao_no_site(codigo: str, ator: str) -> dict | None:
    from .publicador import atualizar_descricao_fundo_no_site
    try:
        return atualizar_descricao_fundo_no_site(codigo, ator)
    except HTTPException:   # F000 · Convidado não vai ao site
        return None


@router.get("/fundos/{codigo}/descricao-site")
def ver_descricao_site(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """B1: o texto que o site mostra sobre o fundo, e o que ainda está "em organização"."""
    from .publicador import campos_hub_fundo, descricao_publica_fundo
    con = connect()
    f = con.execute("SELECT codigo, tainacan_term_id, mostrar_doador FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    if not f:
        con.close(); raise HTTPException(404, "Fundo não existe")
    texto = descricao_publica_fundo(con, codigo)
    _meta, faltam = campos_hub_fundo(con, codigo)
    con.close()
    return {"texto": texto, "faltam": faltam, "no_site": bool(f["tainacan_term_id"]), "mostrar_doador": bool(f["mostrar_doador"])}


@router.post("/fundos/{codigo}/descricao-site")
def enviar_descricao_site(codigo: str, u: dict = Depends(auth.exige("admin"))) -> dict:
    from .publicador import atualizar_descricao_fundo_no_site
    r = atualizar_descricao_fundo_no_site(codigo, u["email"])
    if r.get("erro"):
        raise HTTPException(502, f"O site não aceitou o texto: {r['erro']}")
    if not r.get("enviado"):
        raise HTTPException(409, "O fundo ainda não existe no site. Use \"Criar no site\" primeiro.")
    return {"ok": True, "mensagem": f"Texto do fundo {codigo} atualizado no site"}


@router.post("/fundos/{codigo}/criar-no-site")
def criar_no_site(codigo: str, u: dict = Depends(auth.exige("admin"))) -> dict:
    from .publicador import criar_fundo_no_site
    return criar_fundo_no_site(codigo, u["email"])


# ---- agentes ----
class NovoAgente(BaseModel):
    tipo: str
    forma_autorizada: str
    existencia_inicio: int | None = None
    existencia_fim: int | None = None
    formas_variantes: list[str] = []
    historia: str | None = None
    fonte_historia: str | None = None
    lugares: str | None = None
    fundos: list[str] = []               # códigos em que é produtor


@router.get("/agentes")
def listar_agentes(q: str | None = None, u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect()
    sql = """SELECT a.*, (SELECT GROUP_CONCAT(forma,' | ') FROM agente_forma_variante v WHERE v.agente_id=a.id) AS formas,
             (SELECT GROUP_CONCAT(fundo_codigo,' ') FROM fundo_agente fa WHERE fa.agente_id=a.id) AS fundos,
             EXISTS(SELECT 1 FROM agente_retrato r WHERE r.agente_id=a.id) AS tem_retrato FROM agente a"""
    p = []
    if q:
        sql += " WHERE a.forma_autorizada LIKE ? OR a.id IN (SELECT agente_id FROM agente_forma_variante WHERE forma LIKE ?)"; p = [f"%{q}%", f"%{q}%"]
    rows = con.execute(sql + " ORDER BY a.forma_autorizada", p).fetchall(); con.close()
    return [dict(r) for r in rows]


@router.post("/agentes")
def criar_agente(d: NovoAgente, u: dict = Depends(auth.exige("admin"))) -> dict:
    if d.tipo not in ("pessoa", "entidade_coletiva", "familia"):
        raise HTTPException(400, "Tipo inválido")
    if d.historia and not d.fonte_historia:
        raise HTTPException(400, "História exige fonte citada — nada de biografia sem referência")
    _validar_anos(d.existencia_inicio, d.existencia_fim)
    con = connect()
    if con.execute("SELECT 1 FROM agente WHERE lower(forma_autorizada)=lower(?)", (d.forma_autorizada.strip(),)).fetchone():
        con.close(); raise HTTPException(409, "Já existe agente com esse nome")
    aid = con.execute("INSERT INTO agente (tipo, forma_autorizada, existencia_inicio, existencia_fim, historia, fonte_historia, lugares) VALUES (?,?,?,?,?,?,?)",
                      (d.tipo, d.forma_autorizada.strip(), d.existencia_inicio, d.existencia_fim, d.historia, d.fonte_historia, d.lugares)).lastrowid
    for f in d.formas_variantes:
        if f.strip():
            con.execute("INSERT OR IGNORE INTO agente_forma_variante (agente_id, forma, contexto) VALUES (?,?,'carimbo')", (aid, f.strip().upper()))
    for c in d.fundos:
        if con.execute("SELECT 1 FROM fundo WHERE codigo=?", (c,)).fetchone():
            con.execute("INSERT OR IGNORE INTO fundo_agente (fundo_codigo, agente_id, papel) VALUES (?,?,'produtor')", (c, aid))
    _evento(con, "agente", str(aid), "criado", u["email"], {"nome": d.forma_autorizada, "fundos": d.fundos})
    con.commit(); con.close()
    return {"id": aid}


class EdicaoAgente(BaseModel):
    forma_autorizada: str | None = None
    existencia_inicio: int | None = None
    existencia_fim: int | None = None
    historia: str | None = None
    fonte_historia: str | None = None
    lugares: str | None = None
    formas_variantes: list[str] | None = None
    status_site: str | None = None


@router.patch("/agentes/{aid}")
def editar_agente(aid: int, d: EdicaoAgente, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    a = con.execute("SELECT * FROM agente WHERE id=?", (aid,)).fetchone()
    if not a:
        con.close(); raise HTTPException(404, "Agente não existe")
    if (d.historia or a["historia"]) and not (d.fonte_historia or a["fonte_historia"]):
        con.close(); raise HTTPException(400, "História exige fonte citada")
    campos, vals, mud = [], [], {}
    for k in ("forma_autorizada", "existencia_inicio", "existencia_fim", "historia", "fonte_historia", "lugares", "status_site"):
        v = getattr(d, k)
        if v is not None and v != a[k]:
            campos.append(f"{k}=?"); vals.append(v); mud[k] = v
    if campos:
        campos.append("atualizado_em=datetime('now')")
        con.execute(f"UPDATE agente SET {', '.join(campos)} WHERE id=?", (*vals, aid))
    if d.formas_variantes is not None:
        con.execute("DELETE FROM agente_forma_variante WHERE agente_id=?", (aid,))
        for f in d.formas_variantes:
            if f.strip():
                con.execute("INSERT OR IGNORE INTO agente_forma_variante (agente_id, forma, contexto) VALUES (?,?,'carimbo')", (aid, f.strip().upper()))
        mud["formas_variantes"] = d.formas_variantes
    if mud:
        _evento(con, "agente", str(aid), "editado", u["email"], {"antes": {k: a[k] if k in a.keys() else None for k in mud}, "depois": mud})
    con.commit(); con.close()
    site = None
    if "forma_autorizada" in mud:
        from .publicador import renomear_agente_no_site
        site = renomear_agente_no_site(aid, mud["forma_autorizada"], u["email"])
    hub = None
    if "historia" in mud or "fonte_historia" in mud:   # B9: a biografia do painel é a do site (página do arquiteto)
        from .publicador import enviar_agente_ao_hub
        c2 = connect(); a2 = c2.execute("SELECT historia, fonte_historia FROM agente WHERE id=?", (aid,)).fetchone(); c2.close()
        hub = enviar_agente_ao_hub(aid, {"_camp_bio": a2["historia"] or "", "_camp_bio_fontes": a2["fonte_historia"] or ""}, u["email"])
    return {"ok": True, "campos": list(mud), "site": site, "hub": hub}


# ---- B9: retrato e biografia do arquiteto pelo painel ----
LIMITE_RETRATO = 3 * 1024 * 1024


def _tipo_retrato(b: bytes) -> str | None:
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return None


@router.get("/agentes/{aid}/retrato")
def ver_retrato(aid: int, u: dict = Depends(auth.exige("leitura"))) -> Response:
    con = connect()
    r = con.execute("SELECT imagem, tipo FROM agente_retrato WHERE agente_id=?", (aid,)).fetchone(); con.close()
    if not r:
        raise HTTPException(404, "Sem retrato")
    return Response(bytes(r["imagem"]), media_type=r["tipo"], headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=60"})


@router.put("/agentes/{aid}/retrato")
async def definir_retrato(aid: int, request: Request, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Guarda o retrato no painel e o envia à página do arquiteto no site (biblioteca de mídia + _camp_foto_id)."""
    dados = await request.body()
    if len(dados) > LIMITE_RETRATO:
        raise HTTPException(413, "Retrato grande demais (máximo 3 MB).")
    tipo = _tipo_retrato(dados)
    if not tipo:
        raise HTTPException(400, "Envie o retrato em JPEG ou PNG.")
    con = connect()
    a = con.execute("SELECT forma_autorizada FROM agente WHERE id=?", (aid,)).fetchone()
    if not a:
        con.close(); raise HTTPException(404, "Arquiteto não existe")
    con.execute("""INSERT INTO agente_retrato (agente_id, imagem, tipo, media_id, atualizado_por) VALUES (?,?,?,NULL,?)
                   ON CONFLICT(agente_id) DO UPDATE SET imagem=excluded.imagem, tipo=excluded.tipo, media_id=NULL,
                   atualizado_por=excluded.atualizado_por, atualizado_em=datetime('now')""", (aid, dados, tipo, u["email"]))
    _evento(con, "agente", str(aid), "retrato_atualizado", u["email"], {"bytes": len(dados), "tipo": tipo})
    con.commit(); con.close()
    from .publicador import enviar_agente_ao_hub
    hub = enviar_agente_ao_hub(aid, {"_camp_foto_id": "subir"}, u["email"])
    return {"ok": True, "hub": hub, "mensagem": _msg_hub(f"Retrato de {a['forma_autorizada']} salvo", hub)}


@router.delete("/agentes/{aid}/retrato")
def remover_retrato(aid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    n = con.execute("DELETE FROM agente_retrato WHERE agente_id=?", (aid,)).rowcount
    if n:
        _evento(con, "agente", str(aid), "retrato_removido", u["email"], None)
    con.commit(); con.close()
    from .publicador import enviar_agente_ao_hub
    hub = enviar_agente_ao_hub(aid, {"_camp_foto_id": 0}, u["email"])
    return {"ok": True, "hub": hub, "mensagem": _msg_hub("Retrato removido", hub)}


@router.delete("/agentes/{aid}/biografia")
def apagar_biografia(aid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Remoção rápida (ex.: "Chu Ming: retirar biografia"): apaga no painel e tira o texto do site."""
    con = connect()
    a = con.execute("SELECT forma_autorizada, historia, fonte_historia FROM agente WHERE id=?", (aid,)).fetchone()
    if not a:
        con.close(); raise HTTPException(404, "Arquiteto não existe")
    con.execute("UPDATE agente SET historia=NULL, fonte_historia=NULL, atualizado_em=datetime('now') WHERE id=?", (aid,))
    _evento(con, "agente", str(aid), "biografia_apagada", u["email"], {"antes": {"historia": a["historia"], "fonte_historia": a["fonte_historia"]}})
    con.commit(); con.close()
    from .publicador import enviar_agente_ao_hub
    hub = enviar_agente_ao_hub(aid, {"_camp_bio": "", "_camp_bio_fontes": ""}, u["email"])
    return {"ok": True, "hub": hub, "mensagem": _msg_hub(f"Biografia de {a['forma_autorizada']} apagada", hub)}


@router.post("/agentes/{aid}/enviar-ao-site")
def reenviar_agente(aid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Reenvia biografia e retrato (ex.: depois que o fundo ganhou página no site, ou depois de uma falha)."""
    con = connect()
    a = con.execute("SELECT forma_autorizada, historia, fonte_historia FROM agente WHERE id=?", (aid,)).fetchone()
    tem = con.execute("SELECT 1 FROM agente_retrato WHERE agente_id=?", (aid,)).fetchone(); con.close()
    if not a:
        raise HTTPException(404, "Arquiteto não existe")
    from .publicador import enviar_agente_ao_hub
    meta = {"_camp_bio": a["historia"] or "", "_camp_bio_fontes": a["fonte_historia"] or ""}
    if tem:
        meta["_camp_foto_id"] = "subir"
    hub = enviar_agente_ao_hub(aid, meta, u["email"])
    if hub.get("erro"):
        raise HTTPException(502, f"O site não recebeu: {hub['erro']}")
    return {"ok": True, "hub": hub, "mensagem": _msg_hub(f"{a['forma_autorizada']}: biografia{' e retrato' if tem else ''}", hub)}


def _msg_hub(base: str, hub: dict) -> str:
    if hub.get("erro"):
        return f"{base} no painel; o site não recebeu ({hub['erro'][:120]}) e fica na lista do que falta enviar"
    if hub.get("fundos"):
        return f"{base} e enviado ao site ({', '.join(hub['fundos'])})"
    return f"{base}. O arquiteto ainda não tem fundo no site; vai junto quando tiver"


class StatusFundo(BaseModel):
    acao: str            # no_ar | rascunho | fora_do_ar
    motivo: str | None = None


@router.post("/fundos/{codigo}/status-site")
def status_site(codigo: str, d: StatusFundo, u: dict = Depends(auth.exige("master"))) -> dict:
    """Propaga para TODOS os dossiês e folhas do fundo no Tainacan. Exige master."""
    if d.acao not in ("no_ar", "rascunho", "fora_do_ar"):
        raise HTTPException(400, "Ação inválida")
    if d.acao == "fora_do_ar" and not d.motivo:
        raise HTTPException(400, "Informe o motivo para despublicar o fundo")
    from .publicador import propagar_status_fundo
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM fundo WHERE codigo=?", (codigo,)).fetchone():
            raise HTTPException(404, "Fundo não existe")
        if d.acao == "no_ar":
            from .rotas_gestao import direitos_permitem_publicar
            msg = direitos_permitem_publicar(con, codigo)
            if msg:
                raise HTTPException(400, f"Não dá para publicar o fundo {codigo}: {msg}")
        if d.motivo:
            con.execute("UPDATE fundo SET motivo_fora_do_ar=? WHERE codigo=?", (d.motivo, codigo))
            con.commit()
    finally:
        con.close()
    try:
        return propagar_status_fundo(codigo, d.acao, u["email"])
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "alterados": 0,
            "tentados": 0,
            "falhas": [{"codigo": codigo, "erro": str(e)[:300], "etapa": "publicacao_fundo"}],
            "erro": str(e)[:300],
        }
