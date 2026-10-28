import json

from fastapi import APIRouter, BackgroundTasks, Depends

from . import auth
from .db import connect

router = APIRouter(prefix="/api/site", tags=["site"])


@router.post("/sincronizar")
def sincronizar(bg: BackgroundTasks, tarefa: int = 0, u: dict = Depends(auth.exige("admin"))):
    from .sincronizador import executar, iniciar
    if tarefa:                                   # H4: vira tarefa, com o chip do topo e o aviso de conclusão
        return iniciar(u)                        # 27/10: uma por vez; com uma rodando (a automática inclusive), devolve a mesma
    bg.add_task(executar)
    return {"ok": True, "aviso": "Sincronização iniciada em segundo plano. Acompanhe em /api/site/status."}


@router.get("/status")
def status(u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    r = con.execute("SELECT * FROM sincronizacao ORDER BY id DESC LIMIT 1").fetchone()
    abertas = con.execute("SELECT COUNT(*) FROM divergencia_site WHERE resolvida=0").fetchone()[0]
    fila_existe = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fila_correcao_site'").fetchone()
    fila = con.execute("SELECT COUNT(*) AS total, SUM(CASE WHEN tentativas>0 THEN 1 ELSE 0 END) AS erros FROM fila_correcao_site").fetchone() if fila_existe else None
    con.close()
    return {"ultima": dict(r) if r else None, "divergencias_abertas": abertas,
            "correcoes_pendentes": fila["total"] if fila else 0,
            "correcoes_com_falha": (fila["erros"] or 0) if fila else 0}


@router.get("/divergencias")
def divergencias(u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect()
    rows = con.execute("SELECT * FROM divergencia_site WHERE resolvida=0 ORDER BY campo, codigo LIMIT 500").fetchall()
    con.close()
    return [dict(r) for r in rows]


@router.get("/correcoes-pendentes")
def correcoes_pendentes(u: dict = Depends(auth.exige("admin"))) -> dict:
    """REF-006: diagnóstico somente leitura da fila de alterações para o site."""
    con = connect()
    try:
        existe = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fila_correcao_site'").fetchone()
        if not existe:
            return {"total": 0, "correcoes": [], "fila_disponivel": False}
        total = con.execute("SELECT COUNT(*) FROM fila_correcao_site").fetchone()[0]
        registros = con.execute("""SELECT item_codigo, versao, estado, tentativas, proxima_em,
                                          reservado_ate, ultimo_erro, atualizado_em
                                     FROM fila_correcao_site
                                 ORDER BY tentativas DESC, atualizado_em LIMIT 200""").fetchall()
        return {"total": total, "correcoes": [dict(x) for x in registros], "fila_disponivel": True}
    finally:
        con.close()


_INICIO_RODADA = __import__("threading").Lock()


@router.post("/correcoes-pendentes/enviar")
def enviar_correcoes_pendentes(tarefa: int = 1, u: dict = Depends(auth.exige("admin"))):
    """UX-40 (Rafael, 27/10: "Sim" para um botão que manda UMA rodada, com o resultado de cada envio na tela, deixando o
    reenvio automático desligado). Sempre vira tarefa em segundo plano: a resposta volta na hora (202) e o site lento não prende
    o servidor. Uma rodada por vez: um segundo clique devolve a tarefa que já está rodando. Usa a mesma rotina do trabalhador
    (fila_correcao_site.executar_pendentes), com forcar_manual=True; `site.reenvio_persistente` não muda."""
    from . import fila_correcao_site as fila, tarefas

    def rodar(p) -> dict:
        con = connect()
        try:
            antes = fila.contar(con)
        finally:
            con.close()
        p.total(min(antes["prontas"], fila.LOTE_MAX))
        p.passo("Enviando ao site as correções que estão esperando")

        def andou(codigo, ok, erro, na_fila=False):
            p.passo("Enviando ao site as correções que estão esperando", codigo)
            # UX-47: erro passageiro (site lento) não é falha: a escrita continua na fila e sai na próxima tentativa
            p.feita(1, f"{codigo}: {'enviada' if ok else ('o site não respondeu a tempo, continua na fila: ' if na_fila else 'falhou: ') + limpar(erro)}")

        r = fila.executar_pendentes(limite=fila.LOTE_MAX, orcamento_s=900.0, forcar_manual=True, ator=u["email"],
                                    ao_terminar_item=andou)
        if r.get("desligado"):
            return {"ok": False, "mensagem": "O envio de correções ao site está desligado em Configurações "
                                             "(site.enviar_correcoes_sozinho = 0). Nada foi enviado."}
        if r.get("ocupado"):
            return {"ok": False, "mensagem": "Já há uma rodada de envio ao site em andamento. Nada foi enviado de novo."}
        con = connect()
        try:
            depois = fila.contar(con)
            falhas = [{"codigo": f["codigo"], "erro": limpar(f["erro"])} for f in r["falhas"]]
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('site','correcoes','site_correcoes_enviadas',?,?)",
                        (u["email"], json.dumps({"enviadas": len(r["enviadas"]), "falharam": len(falhas),
                                                 "ainda_na_fila": depois["total"], "manual": True,
                                                 "falhas": falhas[:50]}, ensure_ascii=False)))
            con.commit()
        finally:
            con.close()
        n_env, n_fal = len(r["enviadas"]), len(falhas)
        msg = (f"Envio ao site: {n_env} {'enviada' if n_env == 1 else 'enviadas'}, {n_fal} {'falhou' if n_fal == 1 else 'falharam'}, "
               f"{depois['total']} ainda na fila")
        if not n_env and not n_fal:
            msg = f"Nada saiu nesta rodada: nenhuma correção pronta para enviar ({depois['total']} ainda na fila)"
        return {"ok": not falhas, "mensagem": msg, "enviadas": r["enviadas"], "falhas": falhas,
                "na_fila": [{"codigo": x["codigo"], "erro": limpar(x["erro"])} for x in r.get("na_fila") or []],
                "ainda_na_fila": depois["total"], "esperando_proxima_tentativa": depois["total"] - depois["prontas"],
                "proxima_em": depois["proxima_em"]}

    with _INICIO_RODADA:                        # dois cliques ao mesmo tempo: uma tarefa só
        return tarefas.iniciar("enviar_correcoes", "site", u, rodar)


def limpar(erro) -> str:
    """"RuntimeError: o site respondeu 502" → "o site respondeu 502" (o tipo do erro fica só no banco)."""
    t = str(erro or "")
    for pre in ("RuntimeError: ", "Exception: "):
        if t.startswith(pre):
            return t[len(pre):]
    return t


@router.get("/itens")
def itens(fundo: str | None = None, status: str | None = None, q: str | None = None, limite: int = 200,
          u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    sql = "SELECT id, colecao_id, status, titulo, url, thumb_url, codigo_detectado, fundo_detectado, projeto_detectado, modificado_em FROM wp_item WHERE 1=1"
    p: list = []
    if fundo: sql += " AND fundo_detectado=?"; p.append(fundo)
    if status: sql += " AND status=?"; p.append(status)
    if q: sql += " AND (titulo LIKE ? OR codigo_detectado LIKE ?)"; p += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY codigo_detectado LIMIT ?"; p.append(min(limite, 1000))
    con = connect(); rows = con.execute(sql, p).fetchall(); con.close()
    return [dict(r) for r in rows]


@router.get("/rascunhos-orfaos")
def rascunhos_orfaos(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Rascunhos do site (coleção das folhas) com o código de uma folha que já está LIGADA a outro item do site:
    sobras de envios repetidos. Só lista, a partir do espelho do site; nada é apagado aqui (apagar é decisão de quem cuida do site, depois de conferir)."""
    from .publicador import COL_ACERVO
    con = connect()
    try:
        rows = con.execute("""
            SELECT w.id, w.titulo, w.status, w.url, w.codigo_detectado AS codigo, w.modificado_em,
                   i.codigo AS folha, i.tainacan_item_id AS ligado_a, i.status_site AS folha_status,
                   l.status AS ligado_status, l.url AS ligado_url
              FROM wp_item w
              JOIN item i ON upper(i.codigo) = upper(w.codigo_detectado)
              LEFT JOIN wp_item l ON l.id = i.tainacan_item_id
             WHERE w.colecao_id = ? AND w.status IN ('draft', 'pending', 'auto-draft')
               AND i.tainacan_item_id IS NOT NULL AND i.tainacan_item_id <> w.id
             ORDER BY w.codigo_detectado, w.id""", (COL_ACERVO,)).fetchall()
        sinc = con.execute("SELECT terminada_em FROM sincronizacao WHERE ok=1 ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        con.close()
    return {"total": len(rows), "rascunhos": [dict(r) for r in rows], "espelho_de": sinc[0] if sinc else None,
            "aviso": "Só a lista: nada foi apagado. Confira cada rascunho no site antes de apagar lá."}
