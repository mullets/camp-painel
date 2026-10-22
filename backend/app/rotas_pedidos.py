"""Sobras #12: pedidos de material (tela "Pedidos de material").

(a) Entrada automática: o formulário do site chama POST /api/pedidos/site com o cabeçalho X-Camp-Token = configuração
    `pedidos.token` (sensível). Sem login. Campos validados e tamanho limitado. Contrato em docs/pedidos-do-site.md.
(b) Pacote de entrega: GET /api/solicitacoes/{id}/pacote lista o que entregar (código, resolução pedida, caminho no QNAP);
    POST /api/solicitacoes/{id}/entregar marca como entregue, com data, e guarda o resumo do pacote.
(c) Métricas: GET /api/solicitacoes/metricas, pedidos por fundo e tempo médio entre o pedido e a entrega.
(d) Aviso por e-mail ao admin quando chega um pedido pelo site (alertas.avisar_pedido_novo, assunto opcional).
"""
from __future__ import annotations

import hmac
import json
import logging
import re
import threading
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from . import auth
from .db import connect
from .email_envio import ENDERECO
from .log_tecnico import registrar

router = APIRouter(prefix="/api", tags=["pedidos"])

FINALIDADES = ("publicacao", "pesquisa", "editorial", "familia", "exposicao", "outro")
FORMATOS = {"tif": "TIFF em resolução total", "jpg_3000": "JPG com 3000 px no lado maior",
            "jpg_original": "JPG na resolução original", "pdf": "PDF"}
CODIGO = re.compile(r"^F\d{3}-P\d{4}(?:-\d{4}-S\d{2}-D\d{5})?$")
LIMITE_CORPO = 16 * 1024            # bytes: um pedido honesto cabe com folga
LIMITE_ITENS = 50
LIMITE_POR_HORA = 60                # pedidos aceitos pela rota pública por hora (todas as origens somadas)
_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_janela: list[float] = []
_trava = threading.Lock()


def _token() -> str:
    con = connect()
    try:
        r = con.execute("SELECT valor FROM configuracao WHERE chave='pedidos.token'").fetchone()
    finally:
        con.close()
    return ((r[0] if r else "") or "").strip()


def _texto(d: dict, campo: str, rotulo: str, maximo: int, obrigatorio: bool = False, linhas: bool = False) -> str | None:
    v = d.get(campo)
    if v is None or (isinstance(v, str) and not v.strip()):
        if obrigatorio:
            raise HTTPException(400, f"Falta o campo '{campo}' ({rotulo}).")
        return None
    if not isinstance(v, str):
        raise HTTPException(400, f"O campo '{campo}' ({rotulo}) tem que ser texto.")
    v = _CONTROLE.sub("", v).strip()
    if not linhas:
        v = " ".join(v.split())
    if len(v) > maximo:
        raise HTTPException(400, f"O campo '{campo}' ({rotulo}) passa de {maximo} letras.")
    return v


def validar_pedido(d) -> dict:
    """Confere o pedido vindo do site e devolve os campos limpos, ou levanta 400 com o motivo (em português, para o site mostrar)."""
    if not isinstance(d, dict):
        raise HTTPException(400, "O corpo tem que ser um objeto JSON.")
    nome = _texto(d, "nome", "quem pede", 120, obrigatorio=True)
    if len(nome) < 2:
        raise HTTPException(400, "O campo 'nome' (quem pede) é curto demais.")
    email = _texto(d, "email", "e-mail para resposta", 200, obrigatorio=True)
    if not ENDERECO.match(email):
        raise HTTPException(400, "O campo 'email' não parece um endereço de e-mail.")
    instituicao = _texto(d, "instituicao", "instituição", 200)
    finalidade = _texto(d, "finalidade", "para quê", 20, obrigatorio=True)
    if finalidade not in FINALIDADES:
        raise HTTPException(400, f"O campo 'finalidade' tem que ser um destes: {', '.join(FINALIDADES)}.")
    detalhe = _texto(d, "mensagem", "mensagem", 2000, linhas=True)
    itens_brutos = d.get("itens") or []
    if not isinstance(itens_brutos, list):
        raise HTTPException(400, "O campo 'itens' tem que ser uma lista.")
    if len(itens_brutos) > LIMITE_ITENS:
        raise HTTPException(400, f"No máximo {LIMITE_ITENS} itens por pedido.")
    itens = []
    for k, it in enumerate(itens_brutos, 1):
        if isinstance(it, str):
            it = {"codigo": it}
        if not isinstance(it, dict):
            raise HTTPException(400, f"O item {k} da lista não é válido.")
        cod = str(it.get("codigo") or "").strip().upper()
        fmt = str(it.get("formato") or "jpg_3000").strip().lower()
        if not CODIGO.match(cod):
            raise HTTPException(400, f"O item {k} tem um código inválido: use o código do projeto (F026-P0001) ou da folha (F026-P0001-1968-S01-D00003).")
        if fmt not in FORMATOS:
            raise HTTPException(400, f"O item {k} tem um formato inválido: use {', '.join(FORMATOS)}.")
        if (cod, fmt) not in {(x["codigo"], x["formato"]) for x in itens}:
            itens.append({"codigo": cod, "formato": fmt})
    if not itens and not detalhe:
        raise HTTPException(400, "Diga o que você quer: mande a lista 'itens' ou escreva na 'mensagem'.")
    return {"solicitante": nome, "email": email, "instituicao": instituicao, "finalidade": finalidade, "detalhe": detalhe, "itens": itens}


def _avisar(sid: int) -> None:
    from . import alertas
    con = connect()
    try:
        alertas.avisar_pedido_novo(con, sid)
    except Exception as e:  # noqa: BLE001  (o pedido já está salvo; a falha do aviso só vai para o log)
        registrar(logging.WARNING, "pedido_aviso_falhou", "Não consegui avisar o pedido novo por e-mail", pedido=sid, erro_tipo=type(e).__name__)
    finally:
        con.close()


@router.post("/pedidos/site")
async def pedido_do_site(request: Request, tarefas: BackgroundTasks) -> dict:
    """Rota PÚBLICA (sem login) para o formulário do site. Exige o cabeçalho X-Camp-Token igual a `pedidos.token`."""
    token = _token()
    if not token:
        raise HTTPException(503, "O painel ainda não aceita pedidos do site (pedidos.token vazio).")
    enviado = request.headers.get("x-camp-token", "")
    if not enviado or not hmac.compare_digest(enviado.encode(), token.encode()):
        raise HTTPException(401, "Token ausente ou inválido.")
    tam = request.headers.get("content-length")
    if tam and tam.isdigit() and int(tam) > LIMITE_CORPO:
        raise HTTPException(413, f"Pedido grande demais (máximo {LIMITE_CORPO // 1024} KB).")
    corpo = await request.body()
    if len(corpo) > LIMITE_CORPO:
        raise HTTPException(413, f"Pedido grande demais (máximo {LIMITE_CORPO // 1024} KB).")
    try:
        dados = json.loads(corpo.decode("utf-8") or "null")
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "O corpo não é um JSON válido.")
    p = validar_pedido(dados)
    agora = time.time()
    with _trava:
        while _janela and agora - _janela[0] > 3600:
            _janela.pop(0)
        if len(_janela) >= LIMITE_POR_HORA:
            raise HTTPException(429, "Muitos pedidos na última hora. Tente de novo mais tarde.")
        _janela.append(agora)
    con = connect()
    try:
        sid = con.execute("INSERT INTO solicitacao (solicitante, email, instituicao, finalidade, detalhe, origem) VALUES (?,?,?,?,?,'site')",
                          (p["solicitante"], p["email"], p["instituicao"], p["finalidade"], p["detalhe"])).lastrowid
        for it in p["itens"]:
            con.execute("INSERT OR IGNORE INTO solicitacao_item (solicitacao_id, codigo, formato) VALUES (?,?,?)", (sid, it["codigo"], it["formato"]))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('solicitacao',?,'criada','site',?)",
                    (str(sid), json.dumps({"solicitante": p["solicitante"], "origem": "site", "itens": len(p["itens"])}, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    tarefas.add_task(_avisar, sid)
    return {"ok": True, "id": sid, "mensagem": "Pedido recebido. A equipe da CAMP responde pelo e-mail informado."}


# ---------------- (e) coleta no site (CAMP-013) ----------------
@router.get("/pedidos/coleta")
def coleta_status(u: dict = Depends(auth.exige("operador"))) -> dict:
    """Quando o painel buscou pedidos no site pela última vez e o que ficou pendente."""
    from . import coletor_pedidos_site as cp
    con = connect()
    try:
        return cp.status(con)
    finally:
        con.close()


@router.post("/pedidos/coletar")
def coletar_agora(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Busca agora os pedidos e correções do site (o mesmo que o coletor automático faz a cada 10 min)."""
    from . import coletor_pedidos_site as cp
    return cp.coletar()


# ---------------- (b) pacote de entrega ----------------
def pacote(con, sid: int) -> dict:
    s = con.execute("SELECT * FROM solicitacao WHERE id=?", (sid,)).fetchone()
    if not s:
        raise HTTPException(404, "Pedido não existe")
    linhas, faltam = [], []
    for si in con.execute("SELECT codigo, formato, entregue FROM solicitacao_item WHERE solicitacao_id=? ORDER BY codigo, formato", (sid,)).fetchall():
        cod, fmt = si["codigo"], si["formato"]
        if con.execute("SELECT 1 FROM item WHERE codigo=?", (cod,)).fetchone():
            folhas = con.execute("SELECT i.*, p.pasta_qnap FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo WHERE i.codigo=?", (cod,)).fetchall()
        else:
            folhas = con.execute("""SELECT i.*, p.pasta_qnap FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo
                                     WHERE i.projeto_codigo=? AND i.duplicata_de IS NULL ORDER BY i.serie_codigo, i.sequencial""", (cod,)).fetchall()
            if not folhas:
                faltam.append({"codigo": cod, "formato": fmt, "motivo": "projeto sem folhas cadastradas" if con.execute("SELECT 1 FROM projeto WHERE codigo=?", (cod,)).fetchone() else "código não encontrado no painel"})
                continue
        for f in folhas:
            arq = f["arquivo_tif"] if fmt == "tif" else f["arquivo_jpg"] if fmt.startswith("jpg") else None
            linhas.append({"pedido": cod, "codigo": f["codigo"], "titulo": f["titulo"], "formato": fmt, "resolucao": FORMATOS[fmt],
                           "caminho_qnap": arq or None, "pasta_projeto": f["pasta_qnap"], "entregue": bool(si["entregue"]),
                           # 19/10: folha recortada/alinhada na revisão: o JPG a entregar é o corrigido do painel (o do QNAP é o do CAMP Vision)
                           "jpg_corrigido": f"/api/itens/{f['codigo']}/imagem-corrigida" if fmt.startswith("jpg") and "imagem_corrigida" in f.keys() and f["imagem_corrigida"] else None})
    por_fmt: dict[str, int] = {}
    for l in linhas:
        por_fmt[l["formato"]] = por_fmt.get(l["formato"], 0) + 1
    resumo = " + ".join(f"{n} {FORMATOS[k]}" for k, n in sorted(por_fmt.items())) or "nada"
    return {"id": sid, "solicitante": s["solicitante"], "situacao": s["situacao"], "entregue_em": s["entregue_em"], "entrega": s["entrega"],
            "linhas": linhas, "faltam": faltam, "total": len(linhas), "resumo": resumo,
            "sem_caminho": sum(1 for l in linhas if not l["caminho_qnap"])}


def _csv(p: dict) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["codigo", "titulo", "resolucao_pedida", "caminho_qnap", "pasta_do_projeto", "pedido_como"])
    for l in p["linhas"]:
        w.writerow([l["codigo"], l["titulo"] or "", l["resolucao"], l["caminho_qnap"] or "", l["pasta_projeto"] or "", l["pedido"]])
    for f in p["faltam"]:
        w.writerow([f["codigo"], "", FORMATOS.get(f["formato"], f["formato"]), "", "", f"não entra: {f['motivo']}"])
    return buf.getvalue()


@router.get("/solicitacoes/metricas")
def metricas(u: dict = Depends(auth.exige("leitura"))) -> dict:
    """(c) Pedidos por fundo (um pedido conta uma vez em cada fundo que pede) e o tempo médio entre o pedido e a entrega."""
    con = connect()
    try:
        fundos = [dict(r) for r in con.execute("""
            SELECT x.fundo, f.titulo AS fundo_titulo, COUNT(*) AS pedidos, SUM(s.situacao='entregue') AS entregues,
                   ROUND(AVG(CASE WHEN s.entregue_em IS NOT NULL THEN julianday(s.entregue_em)-julianday(s.recebida_em) END), 1) AS dias_medio
              FROM (SELECT DISTINCT substr(codigo,1,4) AS fundo, solicitacao_id FROM solicitacao_item) x
              JOIN solicitacao s ON s.id=x.solicitacao_id LEFT JOIN fundo f ON f.codigo=x.fundo
             GROUP BY x.fundo ORDER BY pedidos DESC, x.fundo""")]
        g = con.execute("""SELECT COUNT(*) AS pedidos, SUM(situacao='entregue') AS entregues,
                                  ROUND(AVG(CASE WHEN entregue_em IS NOT NULL THEN julianday(entregue_em)-julianday(recebida_em) END), 1) AS dias_medio,
                                  SUM(origem='site') AS do_site
                             FROM solicitacao""").fetchone()
        return {"fundos": fundos, "pedidos": g["pedidos"] or 0, "entregues": g["entregues"] or 0, "do_site": g["do_site"] or 0, "dias_medio": g["dias_medio"]}
    finally:
        con.close()


@router.get("/solicitacoes/{sid}/pacote")
def ver_pacote(sid: int, formato: str | None = None, u: dict = Depends(auth.exige("operador"))):
    con = connect()
    try:
        p = pacote(con, sid)
    finally:
        con.close()
    if formato == "csv":
        return Response(content=_csv(p), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="pedido-{sid}-entrega.csv"'})
    return p


class Entrega(BaseModel):
    observacao: str | None = None        # ex.: "por WeTransfer, 410 MB"


@router.post("/solicitacoes/{sid}/entregar")
def entregar(sid: int, d: Entrega, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Marca o pedido como entregue, com a data de agora, e guarda o resumo do pacote (o que foi entregue)."""
    con = connect()
    try:
        p = pacote(con, sid)
        if p["situacao"] == "entregue":
            raise HTTPException(409, "Este pedido já foi marcado como entregue.")
        if p["situacao"] == "recusada":
            raise HTTPException(409, "Este pedido foi recusado.")
        if not p["linhas"]:
            raise HTTPException(409, "Este pedido não tem folhas escolhidas para entregar. Inclua o material antes.")
        obs = " ".join((d.observacao or "").split())[:300]
        entrega = f"{p['total']} arquivo(s): {p['resumo']}" + (f" · {obs}" if obs else "")
        con.execute("UPDATE solicitacao SET situacao='entregue', entregue_em=datetime('now'), entrega=? WHERE id=?", (entrega, sid))
        con.execute("UPDATE solicitacao_item SET entregue=1 WHERE solicitacao_id=?", (sid,))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('solicitacao',?,'editada',?,?)",
                    (str(sid), u["email"], json.dumps({"situacao": "entregue", "entrega": entrega, "folhas": [l["codigo"] for l in p["linhas"]][:200]}, ensure_ascii=False)))
        con.commit()
        em = con.execute("SELECT entregue_em FROM solicitacao WHERE id=?", (sid,)).fetchone()[0]
        return {"ok": True, "entregue_em": em, "entrega": entrega, "total": p["total"]}
    finally:
        con.close()
