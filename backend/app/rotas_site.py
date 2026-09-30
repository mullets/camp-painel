from fastapi import APIRouter, BackgroundTasks, Depends

from . import auth
from .db import connect

router = APIRouter(prefix="/api/site", tags=["site"])


@router.post("/sincronizar")
def sincronizar(bg: BackgroundTasks, u: dict = Depends(auth.exige("admin"))) -> dict:
    from .sincronizador import executar
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
