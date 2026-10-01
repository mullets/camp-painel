"""CAMP Acervos — API do painel."""
import json
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from . import auth
from .db import connect, init_db, aplicar_migracoes
from .rotas_admin import router as rotas_admin
from .rotas_auth import router as rotas_auth
from .rotas_fundos import router as rotas_fundos
from .rotas_gestao import router as rotas_gestao
from .rotas_operacao import router as rotas_operacao
from .rotas_projetos import router as rotas_projetos
from .rotas_site import router as rotas_site

FRONT = Path(__file__).resolve().parents[2] / "frontend" / "index.html"

app = FastAPI(title="CAMP Acervos", version="0.2.0", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(rotas_auth)
app.include_router(rotas_admin)
app.include_router(rotas_site)
app.include_router(rotas_fundos)
app.include_router(rotas_projetos)
app.include_router(rotas_operacao)
app.include_router(rotas_gestao)


@app.on_event("startup")
async def _startup() -> None:
    init_db()
    aplicar_migracoes()
    import asyncio
    asyncio.create_task(_sincronizacao_periodica())


async def _sincronizacao_periodica() -> None:
    """Site -> painel a cada N minutos (configuracao 'sync.intervalo_min'; 0 desliga)."""
    import asyncio
    from .sincronizador import executar
    await asyncio.sleep(60)
    while True:
        try:
            con = connect()
            r = con.execute("SELECT valor FROM configuracao WHERE chave='sync.intervalo_min'").fetchone()
            con.close()
            minutos = int(r[0]) if r and r[0] and str(r[0]).isdigit() else 15
        except Exception:  # noqa: BLE001
            minutos = 15
        if minutos > 0:
            try:
                await asyncio.to_thread(executar, True, lambda *_: None)
            except Exception:  # noqa: BLE001
                pass
        await asyncio.sleep(max(1, minutos or 15) * 60)


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


@app.get("/api/versao")
def versao() -> dict:
    v = Path(__file__).resolve().parents[1] / "VERSION"
    return {"versao": v.read_text().strip() if v.exists() else "dev"}


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
def proximo_fundo(u: dict = Depends(auth.exige("admin"))) -> dict:
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
