"""CAMP-017 · Eventos das estações (capturado / enviado) e lotes enviados que o CAMP Vision ainda não processou.

POST /api/estacoes/eventos (rede local + token das estações) é idempotente pela `chave` (uuid) e NUNCA deve falhar por causa de campo faltando:
a estação não pode ser bloqueada por isso. `sha256_manifesto` pode vir nulo (no "capturado" não há manifesto).
Lote "enviado" sem lote no painel depois de 1 h = `sem_processar`. Quando o lote chega, compara total enviado × folhas entregues:
só abre aviso se chegaram MENOS folhas do que arquivos enviados (a Windows pode mandar total menor que o manifesto mesclado com lote anterior
ainda não consumido, então folhas a mais NÃO é divergência)."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request

from . import auth
from .db import connect
from .rede import exigir_estacao

router = APIRouter(prefix="/api", tags=["estacoes-eventos"])

EVENTOS = ("capturado", "enviado")
TIPOS = ("foto", "contex", "universal", "campvision")
COD_PROJETO = re.compile(r"^F\d{3}-P\d{4}$")
HORAS_SEM_PROCESSAR = 1


def _txt(v, n: int) -> str | None:
    t = " ".join(str(v if v is not None else "").split())[:n]
    return t or None


def _int(v) -> int | None:
    try:
        return int(v) if v is not None and str(v).strip() != "" and int(v) >= 0 else None
    except (TypeError, ValueError):
        return None


@router.post("/estacoes/eventos")
async def registrar_evento(request: Request) -> dict:
    exigir_estacao(request)
    try:
        d = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "O corpo não é um JSON válido.")
    if not isinstance(d, dict):
        raise HTTPException(400, "O corpo tem que ser um objeto JSON.")
    chave = _txt(d.get("chave"), 80)
    evento = (_txt(d.get("evento"), 20) or "").lower()
    if not chave or not re.fullmatch(r"[0-9A-Za-z._:-]{8,80}", chave):
        raise HTTPException(400, "Falta a `chave` (uuid do evento).")
    if evento not in EVENTOS:
        raise HTTPException(400, "`evento` tem que ser 'capturado' ou 'enviado'.")
    projeto = (_txt(d.get("projeto_codigo"), 20) or "").upper()
    projeto = projeto if COD_PROJETO.match(projeto) else None
    tipo = (_txt(d.get("tipo_estacao"), 20) or "").lower()
    tipo = tipo if tipo in TIPOS else None
    estacao = (_txt(d.get("estacao_id"), 64) or "").lower() or None
    con = connect()
    try:
        ja = con.execute("SELECT id FROM estacao_evento WHERE chave=?", (chave,)).fetchone()
        if ja:
            return {"ok": True, "id": ja[0], "duplicado": True}
        eid = con.execute("""INSERT INTO estacao_evento (chave, estacao_id, tipo_estacao, operador, projeto_codigo, evento, total_arquivos, pasta_entrada, sha256_manifesto)
                             VALUES (?,?,?,?,?,?,?,?,?)""",
                          (chave, estacao, tipo, _txt(d.get("operador"), 80), projeto, evento, _int(d.get("total_arquivos")), _txt(d.get("pasta_entrada"), 300),
                           _txt(d.get("sha256_manifesto"), 80))).lastrowid
        existe = bool(projeto and con.execute("SELECT 1 FROM projeto WHERE codigo=?", (projeto,)).fetchone())
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)",
                    ("projeto" if existe else "estacao", projeto if existe else (estacao or "estacao"), f"estacao_{evento}", estacao or "estacao",
                     json.dumps({"operador": _txt(d.get("operador"), 80), "total_arquivos": _int(d.get("total_arquivos")), "pasta_entrada": _txt(d.get("pasta_entrada"), 300),
                                 "projeto": projeto}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "id": eid, "duplicado": False}
    finally:
        con.close()


def sem_processar(con) -> list[dict]:
    """Lotes que a estação ENVIOU há mais de 1 h e para os quais o painel ainda não tem lote (o CAMP Vision não processou)."""
    out = []
    for e in con.execute("""SELECT e.*, p.titulo AS projeto_titulo, (julianday('now')-julianday(e.recebido_em))*24 AS horas
                              FROM estacao_evento e LEFT JOIN projeto p ON p.codigo=e.projeto_codigo
                             WHERE e.evento='enviado' AND e.conferido_em IS NULL AND e.projeto_codigo IS NOT NULL
                               AND e.recebido_em <= datetime('now', ?) ORDER BY e.recebido_em""", (f"-{HORAS_SEM_PROCESSAR} hours",)):
        lote = con.execute("""SELECT id FROM lista_processamento WHERE projeto_codigo=? AND descartado_em IS NULL AND criado_em >= datetime(?, '-10 minutes') LIMIT 1""",
                           (e["projeto_codigo"], e["recebido_em"])).fetchone()
        if lote:
            continue
        out.append({"id": e["id"], "projeto_codigo": e["projeto_codigo"], "projeto_titulo": e["projeto_titulo"], "estacao_id": e["estacao_id"], "operador": e["operador"],
                    "total_arquivos": e["total_arquivos"], "enviado_em": e["recebido_em"], "horas": round(e["horas"], 1)})
    return out


def conferir_contagem(con, projeto: str, lote_id: int, folhas_entregues: int) -> dict | None:
    """Chamado quando um lote do projeto chega ao painel: compara com o último "enviado" ainda não conferido. Aviso só se chegaram MENOS folhas
    do que arquivos enviados. Nunca levanta."""
    try:
        e = con.execute("""SELECT id, chave, total_arquivos, estacao_id FROM estacao_evento WHERE evento='enviado' AND projeto_codigo=? AND conferido_em IS NULL
                           ORDER BY recebido_em DESC, id DESC LIMIT 1""", (projeto,)).fetchone()
        if not e:
            return None
        total = e["total_arquivos"]
        div = bool(total is not None and folhas_entregues < total)
        con.execute("UPDATE estacao_evento SET conferido_em=datetime('now'), lote_id=?, folhas_entregues=?, divergente=? WHERE id=?", (lote_id, folhas_entregues, int(div), e["id"]))
        if div:
            con.execute("""INSERT OR IGNORE INTO erro (gravidade, categoria, origem, codigo, descricao, relatado_por, chave) VALUES ('aviso','outro','revisao',?,?,?,?)""",
                        (projeto, f"A estação {e['estacao_id'] or ''} enviou {total} arquivo(s), mas chegaram {folhas_entregues} folha(s) ao painel: confira se algum arquivo ficou de fora.".replace("  ", " "),
                         "Estação", f"estacao_evento:{e['chave']}"))
        return {"enviados": total, "entregues": folhas_entregues, "divergente": div}
    except Exception:  # noqa: BLE001
        return None


@router.get("/estacoes/eventos/pendentes")
def pendentes(u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        return {"limite_horas": HORAS_SEM_PROCESSAR, "itens": sem_processar(con)}
    finally:
        con.close()


def _pasta_do_projeto(con, projeto: str) -> str | None:
    """Pasta do projeto no QNAP: a do lote mais recente (não descartado) ou a do próprio projeto."""
    l = con.execute("SELECT pasta_qnap FROM lista_processamento WHERE projeto_codigo=? AND descartado_em IS NULL AND pasta_qnap IS NOT NULL AND pasta_qnap<>'' ORDER BY id DESC LIMIT 1", (projeto,)).fetchone()
    if l:
        return l["pasta_qnap"]
    p = con.execute("SELECT pasta_qnap FROM projeto WHERE codigo=?", (projeto,)).fetchone()
    return (p["pasta_qnap"] if p else None) or None


@router.post("/estacoes/eventos/{evento_id}/ler-agora")
def ler_agora(evento_id: int, u: dict = Depends(auth.exige("operador"))) -> dict:
    """"Ler agora" (quadro "Enviados pela estação e ainda sem processar"): o painel lê SOZINHO a pasta do projeto, como se o CAMP Vision tivesse
    avisado, sem esperar ele reenviar. Cria o lote (ou o lote de complemento) e importa as folhas novas. Idempotente."""
    from .rotas_operacao import ler_pasta_do_aviso
    con = connect()
    try:
        e = con.execute("SELECT id, projeto_codigo, conferido_em FROM estacao_evento WHERE id=?", (evento_id,)).fetchone()
        if not e:
            raise HTTPException(404, "Esse aviso não existe mais.")
        proj = e["projeto_codigo"]
        if not proj:
            raise HTTPException(400, "Esse aviso não diz de que projeto é.")
        pasta = _pasta_do_projeto(con, proj)
        if not pasta:
            raise HTTPException(400, f"O painel não sabe a pasta do projeto {proj} no QNAP. Use \"Varrer QNAP\" na Fila.")
        r = ler_pasta_do_aviso(con, pasta, proj)
        acao = r.get("acao")
        if acao == "complemento":
            msg = f"Li a pasta: {r.get('novos') or 0} folha(s) novas viraram um lote para revisar ({r.get('nome_lote') or 'complemento'})."
        elif acao in ("nova", "atualizada"):
            msg = "Li a pasta e o lote está na Fila para revisar."
        elif acao == "igual":
            msg = "Li a pasta: o painel já tem todas as folhas desse envio. Se o aviso é engano, use \"Dispensar\"."
        else:
            msg = r.get("motivo") or "O painel não conseguiu ler a pasta."
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'ler_pasta_agora',?,?)",
                    (proj, u.get("email") or "operador", json.dumps({"evento_id": evento_id, "acao": acao, "pasta": pasta}, ensure_ascii=False)))
        con.commit()
        return {"ok": bool(r.get("ok")), "acao": acao, "mensagem": msg, "lote_id": r.get("lote_id")}
    finally:
        con.close()


@router.post("/estacoes/eventos/{evento_id}/dispensar")
def dispensar(evento_id: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Tira o aviso do quadro (engano ou já resolvido por outro caminho). Fica no histórico do projeto."""
    con = connect()
    try:
        e = con.execute("SELECT id, projeto_codigo, conferido_em FROM estacao_evento WHERE id=?", (evento_id,)).fetchone()
        if not e:
            raise HTTPException(404, "Esse aviso não existe mais.")
        if e["conferido_em"]:
            return {"ok": True, "ja_estava": True}
        con.execute("UPDATE estacao_evento SET conferido_em=datetime('now'), divergente=0 WHERE id=?", (evento_id,))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'estacao_evento_dispensado',?,?)",
                    (e["projeto_codigo"] or "estacao", u.get("email") or "admin", json.dumps({"evento_id": evento_id}, ensure_ascii=False)))
        con.commit()
        return {"ok": True}
    finally:
        con.close()
