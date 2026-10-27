"""Pedir ao CAMP Vision que releia uma folha ou um projeto ("Ler dados agora").

O painel NÃO chama o CAMP Vision: ele não escuta, o fluxo é de mão única (o CV2 chama o painel). Então o botão registra um PEDIDO e o CV2 pergunta:
  GET  /api/estacoes/pedidos-releitura               -> o que está pedido
  POST /api/estacoes/pedidos-releitura/{id}/iniciado -> "comecei a reler"
  POST /api/estacoes/pedidos-releitura/{id}/concluido -> "terminei" (ok ou falha); o painel importa de novo o pacote (só atualiza folha ainda pendente:
  nunca sobrescreve revisão humana nem o que já está no site).
Pessoas: operador pede/cancela; qualquer logado vê. CV2: rede local + token (rede.exigir_estacao).
"""
import json
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import auth
from .db import connect
from .importador_lote import colisoes_decididas, importar_lote, ler_pacote
from .rede import exigir_estacao
from .rotas_operacao import _qnap_prontos_raiz

router = APIRouter(prefix="/api", tags=["releitura"])
ENCERRADOS = ("concluido", "falhou", "cancelado")
SEM_RESPOSTA_S, DEMORANDO_S = 24 * 3600, 2 * 3600


def _situacao(p: dict, idade: int) -> str:
    if p["estado"] == "pedido":
        return "sem_resposta" if idade > SEM_RESPOSTA_S else "aguardando"
    if p["estado"] == "em_andamento":
        return "demorando" if idade > DEMORANDO_S else "lendo"
    return p["estado"]


def _dict(con, r) -> dict:
    p = dict(r)
    try:
        p["resultado"] = json.loads(p["resultado"]) if p.get("resultado") else None
    except ValueError:
        p["resultado"] = None
    idade = con.execute("SELECT CAST(strftime('%s','now') AS INTEGER) - CAST(strftime('%s', ?) AS INTEGER)", (p["pedido_em"],)).fetchone()[0]
    p["idade_s"], p["situacao"], p["escopo"] = idade, _situacao(p, idade), ("folha" if p["item_codigo"] else "projeto")
    return p


def _cv2(con) -> dict:
    """O que o painel sabe do CAMP Vision: já consultou pedidos alguma vez? foi visto (heartbeat) há quanto tempo?"""
    c = con.execute("SELECT CAST(strftime('%s','now') AS INTEGER) - CAST(strftime('%s', consultado_em) AS INTEGER), estacao FROM releitura_consulta WHERE id=1").fetchone()
    h = con.execute("SELECT estacao_id, CAST(strftime('%s','now') AS INTEGER) - CAST(strftime('%s', atualizado_em) AS INTEGER) FROM estacao_heartbeat WHERE tipo_estacao='campvision' ORDER BY atualizado_em DESC LIMIT 1").fetchone()
    return {"atende": bool(c), "ultima_consulta_s": c[0] if c else None, "visto_ha_s": h[1] if h else None, "estacao": (c[1] if c and c[1] else (h[0] if h else None))}


def _aberto(con, projeto: str, item: str | None):
    """O pedido aberto que já cobre este alvo: o da própria folha, ou o do projeto inteiro."""
    if item:
        return con.execute("SELECT * FROM pedido_releitura WHERE projeto_codigo=? AND estado IN ('pedido','em_andamento') AND (item_codigo IS NULL OR item_codigo=?) ORDER BY item_codigo IS NULL, id DESC LIMIT 1", (projeto, item)).fetchone()
    return con.execute("SELECT * FROM pedido_releitura WHERE projeto_codigo=? AND item_codigo IS NULL AND estado IN ('pedido','em_andamento') ORDER BY id DESC LIMIT 1", (projeto,)).fetchone()


class NovoPedido(BaseModel):
    motivo: str | None = Field(default=None, max_length=300)
    itens: list[str] | None = None      # CAMP-131 (P10, opcional): reler SÓ estas folhas do projeto (ex.: as que têm aviso), em vez do lote inteiro


def _criar(projeto: str, item: str | None, motivo: str | None, u: dict) -> dict:
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM projeto WHERE codigo=?", (projeto,)).fetchone():
            raise HTTPException(404, "Projeto não existe")
        if item and not con.execute("SELECT 1 FROM item WHERE codigo=? AND projeto_codigo=?", (item, projeto)).fetchone():
            raise HTTPException(404, "Folha não existe")
        ja = _aberto(con, projeto, item)
        repetido = ja is not None
        if not ja:
            try:
                pid = con.execute("INSERT INTO pedido_releitura (projeto_codigo, item_codigo, motivo, pedido_por) VALUES (?,?,?,?)", (projeto, item, (motivo or "").strip() or None, u["email"])).lastrowid
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,'releitura_pedida',?,?)",
                            ("item" if item else "projeto", item or projeto, u["email"], json.dumps({"pedido": pid, "motivo": motivo}, ensure_ascii=False)))
                con.commit()
                ja = con.execute("SELECT * FROM pedido_releitura WHERE id=?", (pid,)).fetchone()
            except sqlite3.IntegrityError:                    # dois cliques ao mesmo tempo: vale o que o outro criou
                con.rollback()
                ja, repetido = _aberto(con, projeto, item), True
        return {**_dict(con, ja), "repetido": repetido, "cv2": _cv2(con)}
    finally:
        con.close()


@router.post("/itens/{codigo}/releitura")
def pedir_da_folha(codigo: str, d: NovoPedido, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        i = con.execute("SELECT projeto_codigo FROM item WHERE codigo=?", (codigo,)).fetchone()
    finally:
        con.close()
    if not i:
        raise HTTPException(404, "Folha não existe")
    return _criar(i["projeto_codigo"], codigo, d.motivo, u)


@router.post("/projetos/{codigo}/releitura")
def pedir_do_projeto(codigo: str, d: NovoPedido, u: dict = Depends(auth.exige("operador"))) -> dict:
    if d.itens:                                   # CAMP-131: um pedido por folha (o CV2 já atende pedido de folha), nunca o projeto inteiro
        itens = list(dict.fromkeys(str(x).strip() for x in d.itens if str(x).strip()))[:200]
        r = [_criar(codigo, it, d.motivo, u) for it in itens]
        return {"pedidos": r, "folhas": len(r), "repetido": all(x.get("repetido") for x in r), "cv2": r[0]["cv2"] if r else None}
    return _criar(codigo, None, d.motivo, u)


@router.get("/projetos/{codigo}/releitura/previa")
def previa_do_projeto(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """CAMP-131 (P10): o que a releitura vai fazer, com os números REAIS do projeto, ANTES de pedir (o texto da confirmação).
    A regra é a do importador e da releitura: folha revisada por gente (conferida, corrigida, retida) nunca é sobrescrita; o site só muda quando alguém
    publica de novo; lote já aprovado não recebe nada sozinho (o que mudou aparece em "Releituras: o que mudou" para aceitar ou ignorar)."""
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM projeto WHERE codigo=?", (codigo,)).fetchone():
            raise HTTPException(404, "Projeto não existe")
        q = lambda w: con.execute(f"SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND {w}", (codigo,)).fetchone()[0]  # noqa: E731
        com_aviso = [r[0] for r in con.execute("""SELECT DISTINCT e.codigo FROM erro e JOIN item i ON i.codigo=e.codigo
                                                   WHERE i.projeto_codigo=? AND e.origem='campvision' AND e.situacao IN ('aberto','em_correcao') ORDER BY e.codigo""", (codigo,))]
        aprovado = bool(con.execute("SELECT 1 FROM lista_processamento WHERE projeto_codigo=? AND descartado_em IS NULL AND aprovado_em IS NOT NULL LIMIT 1", (codigo,)).fetchone())
        folhas = q("1=1")
        return {"folhas": folhas, "corrigidas": q("revisao='corrigida'"), "conferidas": q("revisao='conferida' AND COALESCE(retida,0)=0"),
                "retidas": q("COALESCE(retida,0)=1"), "pendentes": q("revisao='pendente'"), "no_site": q("status_site IN ('no_ar','rascunho')"),
                "com_aviso": com_aviso, "lote_aprovado": aprovado, "segundos_por_folha": 15,
                "minutos": max(1, -(-folhas * 15 // 60)), "minutos_com_aviso": max(1, -(-len(com_aviso) * 15 // 60))}
    finally:
        con.close()


def _estado(con, projeto: str, item: str | None) -> dict:
    ab = _aberto(con, projeto, item)
    ultimo = con.execute("SELECT * FROM pedido_releitura WHERE projeto_codigo=? AND (item_codigo IS ? OR item_codigo IS NULL) AND estado IN ('concluido','falhou') ORDER BY id DESC LIMIT 1", (projeto, item)).fetchone()
    return {"aberto": _dict(con, ab) if ab else None, "ultimo": _dict(con, ultimo) if ultimo else None, "cv2": _cv2(con)}


@router.get("/itens/{codigo}/releitura")
def estado_da_folha(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        i = con.execute("SELECT projeto_codigo FROM item WHERE codigo=?", (codigo,)).fetchone()
        if not i:
            raise HTTPException(404, "Folha não existe")
        return _estado(con, i["projeto_codigo"], codigo)
    finally:
        con.close()


@router.get("/projetos/{codigo}/releitura")
def estado_do_projeto(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM projeto WHERE codigo=?", (codigo,)).fetchone():
            raise HTTPException(404, "Projeto não existe")
        return _estado(con, codigo, None)
    finally:
        con.close()


@router.post("/releituras/{pid}/cancelar")
def cancelar(pid: int, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        p = con.execute("SELECT * FROM pedido_releitura WHERE id=?", (pid,)).fetchone()
        if not p:
            raise HTTPException(404, "Pedido não existe")
        if p["estado"] in ENCERRADOS:
            raise HTTPException(409, "Este pedido já foi encerrado")
        con.execute("UPDATE pedido_releitura SET estado='cancelado', concluido_em=datetime('now') WHERE id=? AND estado IN ('pedido','em_andamento')", (pid,))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,'releitura_cancelada',?,?)",
                    ("item" if p["item_codigo"] else "projeto", p["item_codigo"] or p["projeto_codigo"], u["email"], json.dumps({"pedido": pid})))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


# ---------------- o lado do CAMP Vision (rede local + token) ----------------
def _codigo_de_origem(con, item_codigo: str) -> str | None:
    """Código que a folha tem no PACOTE/acervo quando o painel a renumerou numa decisão 'lote_colide'
    (adicionar_ao_fim). None se ela não foi renumerada."""
    it = con.execute("SELECT lote_id FROM item WHERE codigo=?", (item_codigo,)).fetchone()
    if not it or not it["lote_id"]:
        return None
    for origem, info in colisoes_decididas(con, it["lote_id"]).items():
        if (info.get("renumeradas") or {}).get(origem) == item_codigo:
            return origem
    return None


# UX-12 (26/10, logs: esta rota levou 10,9 s, o normal é ~25 ms): cada consulta do CAMP Vision GRAVAVA "consultou agora" e esperava
# a vez de escrever no banco (até 30 s) quando outra escrita longa estava em curso. A tela só usa esse registro para dizer
# "consultou há mais de 10 min", então: grava no máximo 1 vez por minuto (ou quando muda a estação/IP) e, com o banco ocupado,
# desiste em 0,5 s e tenta na próxima consulta. A resposta ao CAMP Vision é a mesma (contrato inalterado).
_CONSULTA_GRAVADA: dict = {"t": -1e9, "quem": None}
CONSULTA_GRAVAR_S = 60.0


def _registrar_consulta(con, estacao: str | None, ip: str) -> None:
    import sqlite3
    import time
    if time.monotonic() - _CONSULTA_GRAVADA["t"] < CONSULTA_GRAVAR_S and _CONSULTA_GRAVADA["quem"] == (estacao, ip):
        return
    try:
        con.execute("PRAGMA busy_timeout = 500")
        con.execute("INSERT INTO releitura_consulta (id, consultado_em, estacao, ip) VALUES (1, datetime('now'), ?, ?) ON CONFLICT(id) DO UPDATE SET consultado_em=excluded.consultado_em, estacao=excluded.estacao, ip=excluded.ip",
                    (estacao, ip))
        con.commit()
        _CONSULTA_GRAVADA.update(t=time.monotonic(), quem=(estacao, ip))
    except sqlite3.OperationalError:          # banco ocupado: fica para a próxima consulta (o CAMP Vision não espera por isso)
        con.rollback()
    finally:
        con.execute("PRAGMA busy_timeout = 30000")


def _relativa(pasta: str, raiz: Path) -> str | None:
    """Caminho da pasta do lote relativo à raiz do acervo. Primeiro só com texto (sem tocar no SMB); resolve() só se precisar (link simbólico)."""
    import os
    try:
        return str(Path(os.path.normpath(os.path.abspath(pasta))).relative_to(os.path.normpath(os.path.abspath(str(raiz)))))
    except ValueError:
        pass
    try:
        return str(Path(pasta).resolve().relative_to(raiz.resolve()))
    except (ValueError, OSError):
        return None


@router.get("/estacoes/pedidos-releitura")
def pedidos_para_o_cv2(request: Request, estacao: str = "") -> dict:
    ip = exigir_estacao(request)
    con = connect()
    try:
        _registrar_consulta(con, estacao.strip().lower()[:64] or None, ip)
        raiz = _qnap_prontos_raiz()
        saida = []
        for p in con.execute("SELECT * FROM pedido_releitura WHERE estado='pedido' OR (estado='em_andamento' AND (estacao IS ? OR ? = '')) ORDER BY id LIMIT 50", (estacao.strip().lower() or None, estacao.strip())).fetchall():
            l = con.execute("SELECT pasta_qnap FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC LIMIT 1", (p["projeto_codigo"],)).fetchone()
            rel = None
            if l and l["pasta_qnap"]:
                rel = _relativa(l["pasta_qnap"], raiz)
            pedido = {"id": p["id"], "escopo": "folha" if p["item_codigo"] else "projeto", "projeto_codigo": p["projeto_codigo"], "item_codigo": p["item_codigo"],
                      "motivo": p["motivo"], "pedido_em": p["pedido_em"], "estado": p["estado"], "pasta_relativa": rel}
            origem = _codigo_de_origem(con, p["item_codigo"]) if p["item_codigo"] else None
            if origem:   # contrato 2.5, opcional: a folha foi renumerada pelo painel (lote_colide); o acervo ainda a chama pelo código do pacote
                pedido["item_codigo_origem"] = origem
            saida.append(pedido)
        return {"pedidos": saida}
    finally:
        con.close()


class Iniciado(BaseModel):
    estacao: str = Field(default="campvision2", max_length=64)


@router.post("/estacoes/pedidos-releitura/{pid}/iniciado")
def iniciado(pid: int, d: Iniciado, request: Request) -> dict:
    exigir_estacao(request)
    con = connect()
    try:
        p = con.execute("SELECT estado FROM pedido_releitura WHERE id=?", (pid,)).fetchone()
        if not p:
            raise HTTPException(404, "Pedido não existe")
        if p["estado"] in ENCERRADOS:
            raise HTTPException(409, "Pedido já encerrado: não leia")
        con.execute("UPDATE pedido_releitura SET estado='em_andamento', estacao=?, iniciado_em=COALESCE(iniciado_em, datetime('now')) WHERE id=?", (d.estacao.strip().lower(), pid))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


class Concluido(BaseModel):
    ok: bool = True
    mensagem: str | None = Field(default=None, max_length=500)
    # contrato 2.2 (todos opcionais): o que a releitura fez e custou
    relidos: int | None = None
    com_mudanca: int | None = None
    campos_preenchidos: int | None = None
    regravados: int | None = None
    custo_usd: float | None = None
    escopo: str | None = Field(default=None, max_length=20)
    falhas: list | None = None


@router.post("/estacoes/pedidos-releitura/{pid}/concluido")
def concluido(pid: int, d: Concluido, request: Request) -> dict:
    exigir_estacao(request)
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        p = con.execute("SELECT * FROM pedido_releitura WHERE id=?", (pid,)).fetchone()
        if not p:
            raise HTTPException(404, "Pedido não existe")
        if p["estado"] in ENCERRADOS:
            raise HTTPException(409, "Pedido já encerrado")
        resultado: dict = {}
        if d.ok:
            resultado = _importar_de_novo(con, p["projeto_codigo"])
        cv = {k: v for k, v in (("relidos", d.relidos), ("com_mudanca", d.com_mudanca), ("campos_preenchidos", d.campos_preenchidos), ("regravados", d.regravados),
                                ("custo_usd", d.custo_usd), ("escopo", d.escopo), ("falhas", (d.falhas or [])[:20] or None)) if v is not None}
        if cv:
            resultado["campvision"] = cv                # custo e quantas folhas foram relidas ficam com o pedido
        con.execute("UPDATE pedido_releitura SET estado=?, concluido_em=datetime('now'), mensagem=?, resultado=? WHERE id=?",
                    ("concluido" if d.ok else "falhou", (d.mensagem or "").strip() or None, json.dumps(resultado, ensure_ascii=False) if resultado else None, pid))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)",
                    ("item" if p["item_codigo"] else "projeto", p["item_codigo"] or p["projeto_codigo"], "releitura_concluida" if d.ok else "releitura_falhou", p["estacao"] or "campvision",
                     json.dumps({"pedido": pid, "mensagem": d.mensagem, **({"importacao": resultado.get("importacao")} if resultado.get("importacao") else {})}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "estado": "concluido" if d.ok else "falhou", "resultado": resultado or None}
    except HTTPException:
        con.rollback()
        raise
    finally:
        con.close()


def _importar_de_novo(con, projeto: str) -> dict:
    """A releitura reescreveu o pacote: importa de novo o lote mais recente do projeto (só atualiza folha ainda pendente; nunca sobrescreve revisão humana)."""
    for l in con.execute("SELECT id, pasta_qnap, aprovado_em FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC", (projeto,)).fetchall():
        try:
            if not l["pasta_qnap"] or ler_pacote(Path(l["pasta_qnap"])) is None:
                continue
        except HTTPException:
            continue
        if l["aprovado_em"]:
            return {"importacao": None, "aviso": "O lote já está aprovado: reabra a revisão para aplicar a nova leitura."}
        try:
            return {"importacao": importar_lote(con, l["id"], "campvision (releitura)"), "lote_id": l["id"]}
        except HTTPException as e:
            return {"importacao": None, "aviso": f"Não consegui importar a nova leitura: {e.detail}"}
    return {"importacao": None, "aviso": "O painel não achou o pacote do CAMP Vision para importar."}
