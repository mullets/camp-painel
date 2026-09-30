"""CAMP Acervos — API do painel."""
import json
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from . import auth
from .db import connect, init_db, aplicar_migracoes
from .rotas_admin import router as rotas_admin
from .rotas_auth import router as rotas_auth

FRONT = Path(__file__).resolve().parents[2] / "frontend" / "index.html"

app = FastAPI(title="CAMP Acervos", version="0.2.0", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(rotas_auth)
app.include_router(rotas_admin)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    aplicar_migracoes()


@app.middleware("http")
async def cabecalhos_seguranca(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Permissions-Policy"] = "camera=(self), geolocation=()"
    resp.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return resp


@app.exception_handler(HTTPException)
async def _http_exc(request: Request, exc: HTTPException):
    return JSONResponse({"erro": exc.detail}, status_code=exc.status_code)


@app.get("/", include_in_schema=False)
def painel() -> FileResponse:
    # a página em si é pública (só HTML); todo dado vem da API, que exige sessão
    return FileResponse(FRONT)


@app.get("/api/fundos")
def listar_fundos(u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect()
    rows = con.execute("SELECT * FROM fundo WHERE ativo = 1 ORDER BY codigo").fetchall()
    con.close()
    return [dict(r) for r in rows]


@app.get("/api/fundos/proximo")
def proximo_fundo(u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    codigo = con.execute("SELECT codigo FROM v_proximo_fundo").fetchone()[0]
    con.close()
    return {"codigo": codigo}


@app.get("/api/fundos/{codigo}")
def obter_fundo(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    row = con.execute("SELECT * FROM fundo WHERE codigo = ?", (codigo,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, f"Fundo {codigo} não existe")
    return dict(row)


@app.get("/api/fundos.json")
def fundos_json(request: Request) -> dict:
    """Lido pela estação Contex, que não tem login. Só responde para a rede local."""
    ip = request.client.host if request.client else ""
    if not (ip.startswith("192.168.") or ip.startswith("10.") or ip == "127.0.0.1"):
        raise HTTPException(403, "Somente rede local")
    con = connect()
    dados = con.execute("SELECT fundos FROM v_fundos_json").fetchone()[0]
    con.close()
    return {"fundos": json.loads(dados or "[]")}
