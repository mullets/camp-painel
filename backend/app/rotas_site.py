from fastapi import APIRouter, BackgroundTasks, Depends

from . import auth
from .db import connect

router = APIRouter(prefix="/api/site", tags=["site"])


@router.post("/sincronizar")
def sincronizar(bg: BackgroundTasks, tarefa: int = 0, u: dict = Depends(auth.exige("admin"))):
    from .sincronizador import executar
    if tarefa:                                   # H4: vira tarefa, com o chip do topo e o aviso de conclusão
        from . import tarefas

        def rodar(p) -> dict:
            p.passo("Lendo coleções, folhas e páginas do site")
            r = executar()
            if not r.get("ok"):
                return {**r, "mensagem": f"A sincronização falhou: {r.get('erro') or 'sem resposta do site'}"}
            return {**r, "mensagem": f"Sincronizado: {r['itens']} item(ns) do site, {r['divergencias']} divergência(s)."}
        return tarefas.iniciar("sincronizar", "site", u, rodar)
    bg.add_task(executar)
    return {"ok": True, "aviso": "Sincronização iniciada em segundo plano. Acompanhe em /api/site/status."}


@router.get("/status")
def status(u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    r = con.execute("SELECT * FROM sincronizacao ORDER BY id DESC LIMIT 1").fetchone()
    abertas = con.execute("SELECT COUNT(*) FROM divergencia_site WHERE resolvida=0").fetchone()[0]
    con.close()
    return {"ultima": dict(r) if r else None, "divergencias_abertas": abertas}


@router.get("/divergencias")
def divergencias(u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect()
    rows = con.execute("SELECT * FROM divergencia_site WHERE resolvida=0 ORDER BY campo, codigo LIMIT 500").fetchall()
    con.close()
    return [dict(r) for r in rows]


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
