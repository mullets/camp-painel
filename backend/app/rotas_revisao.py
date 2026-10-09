"""Revisão pós-CAMP Vision: importar as folhas do lote, conferir/corrigir, e o admin aprovar. Ler: leitura; revisar: operador; aprovar: admin."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import auth, giro_imagem as imagens
from .db import connect
from .importador_lote import importar_lote, ler_pacote
from .rotas_operacao import _qnap_prontos_raiz

router = APIRouter(prefix="/api", tags=["revisao"])


def _evento(con, entidade: str, codigo: str, tipo: str, ator: str, detalhe: dict | None = None) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)", (entidade, codigo, tipo, ator, json.dumps(detalhe, ensure_ascii=False) if detalhe else None))


def _lote(con, lote_id: int):
    l = con.execute("SELECT * FROM lista_processamento WHERE id=?", (lote_id,)).fetchone()
    if not l:
        raise HTTPException(404, "Lote não existe")
    return l


@router.post("/lotes/{lote_id}/importar")
def importar(lote_id: int, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        l = _lote(con, lote_id)
        if l["aprovado_em"]:
            raise HTTPException(409, "O lote já foi aprovado: reabra a revisão para importar de novo")
        r = importar_lote(con, lote_id, u["email"])
        con.commit()
        return r
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


def _contagem(con, lote_id: int) -> dict:
    c = {"total": 0, "pendente": 0, "conferida": 0, "corrigida": 0, "bloqueadas": 0}
    for r in con.execute("SELECT revisao, status_site, COUNT(*) FROM item WHERE lote_id=? GROUP BY revisao, status_site", (lote_id,)):
        c["total"] += r[2]
        c[r[0]] += r[2]
        if r[1] == "bloqueado":
            c["bloqueadas"] += r[2]
    return c


@router.get("/projetos/{codigo}/revisao")
def resumo(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM projeto WHERE codigo=?", (codigo,)).fetchone():
            raise HTTPException(404, "Projeto não existe")
        lotes = []
        for l in con.execute("SELECT * FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC", (codigo,)):
            pasta = Path(l["pasta_qnap"] or "")
            acessivel = pasta.is_dir()
            pacote = {"acessivel": acessivel, "existe": False, "documentos": 0, "retirados": 0, "teste": False}
            if acessivel:
                try:
                    p = ler_pacote(pasta)
                except HTTPException:
                    p = None
                if p is not None:
                    docs = p.get("documentos") if isinstance(p.get("documentos"), list) else (p.get("itens") or [])
                    pacote.update({"existe": True, "documentos": len(docs), "retirados": len(p.get("retirados") or []), "teste": bool(p.get("teste"))})
            c = _contagem(con, l["id"])
            motivo = None
            if l["aprovado_em"]:
                motivo = "Já aprovado"
            elif c["total"] == 0:
                motivo = "Importe as folhas do lote antes"
            elif c["pendente"]:
                motivo = f"Faltam conferir {c['pendente']} folha(s)"
            try:
                importacao = json.loads(l["resultado"] or "{}").get("importacao")
            except ValueError:
                importacao = None
            lotes.append({"id": l["id"], "nome": l["nome"], "etapa": l["etapa"], "aprovado_por": l["aprovado_por"], "aprovado_em": l["aprovado_em"], "pacote": pacote,
                          "itens": c, "importacao": importacao, "pode_aprovar": motivo is None, "motivo": motivo})
        return {"lotes": lotes}
    finally:
        con.close()


class RevisaoItem(BaseModel):
    estado: str     # conferida (está certo) | corrigida (a pessoa editou) | pendente (volta para conferir)


@router.post("/itens/{codigo}/revisao")
def revisar(codigo: str, d: RevisaoItem, u: dict = Depends(auth.exige("operador"))) -> dict:
    if d.estado not in ("pendente", "conferida", "corrigida"):
        raise HTTPException(400, "estado deve ser pendente, conferida ou corrigida")
    con = connect()
    try:
        i = con.execute("SELECT i.revisao, i.status_site, i.lote_id, l.aprovado_em FROM item i LEFT JOIN lista_processamento l ON l.id=i.lote_id WHERE i.codigo=?", (codigo,)).fetchone()
        if not i:
            raise HTTPException(404, "Folha não existe")
        if i["aprovado_em"]:
            raise HTTPException(409, "O lote desta folha já foi aprovado: reabra a revisão para mudar")
        if i["status_site"] in ("rascunho", "no_ar"):
            raise HTTPException(409, "Esta folha já está no site: a revisão do lote não se aplica")
        con.execute("UPDATE item SET revisao=?, revisado_por=?, revisado_em=CASE WHEN ?='pendente' THEN NULL ELSE datetime('now') END, atualizado_em=datetime('now') WHERE codigo=?",
                    (d.estado, None if d.estado == "pendente" else u["email"], d.estado, codigo))
        _evento(con, "item", codigo, "revisao", u["email"], {"de": i["revisao"], "para": d.estado})
        con.commit()
        return {"ok": True, "revisao": d.estado}
    finally:
        con.close()


@router.post("/lotes/{lote_id}/conferir-sem-pendencia")
def conferir_sem_pendencia(lote_id: int, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Marca como conferida só a folha SEM nada que o CAMP Vision tenha apontado (bloqueio, ressalva, sinal) e com título preenchido. O resto fica para um olho humano."""
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        l = _lote(con, lote_id)
        if l["aprovado_em"]:
            raise HTTPException(409, "O lote já foi aprovado: reabra a revisão para mudar")
        marcadas = 0
        for i in con.execute("SELECT codigo, titulo, status_site, pendencias FROM item WHERE lote_id=? AND revisao='pendente'", (lote_id,)).fetchall():
            try:
                p = json.loads(i["pendencias"] or "{}")
            except ValueError:
                p = {"bloqueios": ["pendências ilegíveis"]}
            if i["status_site"] == "bloqueado" or not (i["titulo"] or "").strip() or p.get("bloqueios") or p.get("ressalvas") or p.get("sinais"):
                continue
            con.execute("UPDATE item SET revisao='conferida', revisado_por=?, revisado_em=datetime('now'), atualizado_em=datetime('now') WHERE codigo=?", (u["email"], i["codigo"]))
            marcadas += 1
        restam = con.execute("SELECT COUNT(*) FROM item WHERE lote_id=? AND revisao='pendente'", (lote_id,)).fetchone()[0]
        _evento(con, "projeto", l["projeto_codigo"], "revisao_em_lote", u["email"], {"lote_id": lote_id, "conferidas": marcadas, "restam": restam})
        con.commit()
        return {"conferidas": marcadas, "restam": restam}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


@router.post("/lotes/{lote_id}/conferir-todas")
def conferir_todas(lote_id: int, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Marca TODAS as folhas ainda pendentes do lote como conferidas (inclusive as que o CAMP Vision apontou: o botão existe para quando a pessoa já olhou).
    Devolve quantas tinham algo apontado, para a tela dizer. Não aprova o lote: isso continua sendo do admin."""
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        l = _lote(con, lote_id)
        if l["aprovado_em"]:
            raise HTTPException(409, "O lote já foi aprovado: reabra a revisão para mudar")
        marcadas = apontadas = 0
        for i in con.execute("SELECT codigo, status_site, pendencias FROM item WHERE lote_id=? AND revisao='pendente' AND status_site NOT IN ('rascunho','no_ar')", (lote_id,)).fetchall():
            try:
                p = json.loads(i["pendencias"] or "{}")
            except ValueError:
                p = {}
            if i["status_site"] == "bloqueado" or p.get("bloqueios") or p.get("ressalvas") or p.get("sinais"):
                apontadas += 1
            con.execute("UPDATE item SET revisao='conferida', revisado_por=?, revisado_em=datetime('now'), atualizado_em=datetime('now') WHERE codigo=?", (u["email"], i["codigo"]))
            marcadas += 1
        _evento(con, "projeto", l["projeto_codigo"], "revisao_em_lote", u["email"], {"lote_id": lote_id, "todas": True, "conferidas": marcadas, "com_algo_apontado": apontadas})
        con.commit()
        return {"conferidas": marcadas, "com_pendencia": apontadas, "restam": 0}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


class Giro(BaseModel):
    graus: int      # 90 (horário), -90 (anti-horário) ou 180


@router.post("/itens/{codigo}/girar")
def girar(codigo: str, d: Giro, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Vira a prévia da folha (e a imagem que vai ao site). A tela e o site mostram a folha já virada; o arquivo original no QNAP não é tocado."""
    if d.graus not in (90, -90, 180):
        raise HTTPException(400, "graus deve ser 90, -90 ou 180")
    if not imagens.disponivel():
        raise HTTPException(503, "O servidor ainda não tem o Pillow instalado: rode ./atualizar.sh e tente de novo")
    con = connect()
    try:
        i = con.execute("SELECT i.giro_manual, i.status_site, l.aprovado_em FROM item i LEFT JOIN lista_processamento l ON l.id=i.lote_id WHERE i.codigo=?", (codigo,)).fetchone()
        if not i:
            raise HTTPException(404, "Folha não existe")
        if i["aprovado_em"]:
            raise HTTPException(409, "O lote desta folha já foi aprovado: reabra a revisão para mudar")
        if i["status_site"] in ("rascunho", "no_ar"):
            raise HTTPException(409, "Esta folha já está no site: a imagem lá não muda por aqui")
        novo = (i["giro_manual"] + d.graus) % 360
        con.execute("UPDATE item SET giro_manual=?, atualizado_em=datetime('now') WHERE codigo=?", (novo, codigo))
        _evento(con, "item", codigo, "giro", u["email"], {"de": i["giro_manual"], "para": novo})
        con.commit()
        return {"giro_manual": novo}
    finally:
        con.close()


@router.post("/lotes/{lote_id}/aprovar")
def aprovar(lote_id: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        l = _lote(con, lote_id)
        if l["aprovado_em"]:
            raise HTTPException(409, "Este lote já foi aprovado")
        c = _contagem(con, lote_id)
        if c["total"] == 0:
            raise HTTPException(400, "Importe as folhas do lote antes de aprovar")
        if c["pendente"]:
            raise HTTPException(400, f"Faltam conferir {c['pendente']} folha(s)")
        con.execute("UPDATE lista_processamento SET aprovado_por=?, aprovado_em=datetime('now'), atualizado_em=datetime('now') WHERE id=?", (u["email"], lote_id))
        _evento(con, "projeto", l["projeto_codigo"], "revisao_aprovada", u["email"], {"lote_id": lote_id, "folhas": c["total"], "bloqueadas": c["bloqueadas"]})
        con.commit()
        return {"ok": True, **c}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


@router.post("/lotes/{lote_id}/reabrir")
def reabrir(lote_id: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        l = _lote(con, lote_id)
        if not l["aprovado_em"]:
            raise HTTPException(409, "Este lote não está aprovado")
        if l["etapa"] in ("rascunho", "publicado"):
            raise HTTPException(409, "O lote já foi para o site: não dá para reabrir a revisão")
        con.execute("UPDATE lista_processamento SET aprovado_por=NULL, aprovado_em=NULL, atualizado_em=datetime('now') WHERE id=?", (lote_id,))
        _evento(con, "projeto", l["projeto_codigo"], "revisao_reaberta", u["email"], {"lote_id": lote_id})
        con.commit()
        return {"ok": True}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


@router.get("/itens/{codigo}/previa")
def previa(codigo: str, t: int = 0, u: dict = Depends(auth.exige("leitura"))) -> FileResponse:
    """Prévia (~3000 px, já girada) que o CAMP Vision grava em ACERVOS_CAMP/_campvision/preview/. O caminho vem do pacote (de fora): só serve de dentro dessa pasta."""
    con = connect()
    try:
        i = con.execute("SELECT pendencias, giro_manual FROM item WHERE codigo=?", (codigo,)).fetchone()
    finally:
        con.close()
    try:
        rel = (json.loads(i["pendencias"] or "{}") if i else {}).get("previa") or ""
    except ValueError:
        rel = ""
    if not rel:
        raise HTTPException(404, "Sem prévia")
    raiz = _qnap_prontos_raiz()
    base = (raiz / "_campvision" / "preview").resolve()
    alvo = (raiz / rel).resolve()
    if base not in alvo.parents or alvo.suffix.lower() not in (".jpg", ".jpeg") or alvo.stem != codigo or not alvo.is_file():
        raise HTTPException(404, "Sem prévia")
    giro, lado = (i["giro_manual"] if i else 0), (t if 120 <= t <= 1600 else 0)     # t = miniatura (lado maior em px); 0 = tamanho da prévia
    if giro and not imagens.disponivel():
        raise HTTPException(503, "O servidor ainda não tem o Pillow instalado: rode ./atualizar.sh")
    if (giro or lado) and imagens.disponivel():
        try:
            alvo = imagens.jpeg_girado(alvo, giro, lado or None)
        except Exception as e:  # noqa: BLE001  (arquivo corrompido, disco cheio...)
            raise HTTPException(500, f"Não consegui preparar a imagem: {str(e)[:120]}")
    return FileResponse(alvo, headers={"Cache-Control": "private, max-age=3600"})
