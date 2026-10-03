"""CAMP Acervos — API do painel."""
import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import auth
from .rede import exigir_estacao
from .db import connect, init_db, aplicar_migracoes
from .log_tecnico import configurar as configurar_logs, registrar as log_registrar
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
    configurar_logs()
    log_registrar(logging.INFO, "app_start", "Inicializando CAMP Painel")
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
                log_registrar(logging.INFO, "sync_start", "Sincronização automática iniciada", intervalo_min=minutos)
                r_sync = await asyncio.to_thread(executar, True, lambda msg: log_registrar(logging.INFO, "sync_msg", str(msg)[:1000]))
                log_registrar(logging.INFO if r_sync.get("ok") else logging.ERROR, "sync_end",
                              "Sincronização automática concluída", resultado=r_sync)
            except Exception as e:  # noqa: BLE001
                log_registrar(logging.ERROR, "sync_exception", "Falha inesperada na sincronização automática",
                              erro_tipo=type(e).__name__, exc_info=True)
        await asyncio.sleep(max(1, minutos or 15) * 60)


@app.middleware("http")
async def cabecalhos_seguranca(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    inicio = time.perf_counter()
    ip = request.client.host if request.client else "?"
    try:
        resp = await call_next(request)
    except Exception as e:
        duracao = round((time.perf_counter() - inicio) * 1000)
        log_registrar(logging.ERROR, "http_exception", f"{request.method} {request.url.path} falhou",
                      request_id=request_id, metodo=request.method, rota=request.url.path, ip=ip,
                      duracao_ms=duracao, erro_tipo=type(e).__name__, exc_info=True)
        raise
    duracao = round((time.perf_counter() - inicio) * 1000)
    nivel = logging.WARNING if resp.status_code >= 400 else logging.INFO
    log_registrar(nivel, "http_request", f"{request.method} {request.url.path} {resp.status_code}",
                  request_id=request_id, metodo=request.method, rota=request.url.path, ip=ip,
                  status=resp.status_code, duracao_ms=duracao)
    resp.headers["X-Request-ID"] = request_id
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
    exigir_estacao(request)
    con = connect()
    dados = con.execute("SELECT fundos FROM v_fundos_json").fetchone()[0]
    con.close()
    return {"fundos": json.loads(dados or "[]")}


def _exigir_rede_local(request: Request) -> str:
    """Endpoints das estações: sem login; ver app/rede.py (LAN verdadeira ou token)."""
    return exigir_estacao(request)


@app.get("/api/estacoes/contexto")
def contexto_estacoes(request: Request, fundo: str | None = None) -> dict:
    """Fonte única para fundos e numeração de projetos usada pelas estações.

    Sem `fundo`, devolve os fundos ativos com último/próximo P. Com `fundo`,
    inclui também os projetos existentes daquele fundo para seleção na estação.
    """
    _exigir_rede_local(request)
    con = connect()
    fundos = [dict(r) for r in con.execute("""
        SELECT f.codigo AS codigo_fundo, f.sigla AS prefixo, f.titulo AS nome,
               CASE WHEN COALESCE(MAX(n.numero), 0) = 0 THEN NULL
                    ELSE printf('P%04d', MAX(n.numero)) END AS ultimo_projeto,
               v.proximo AS proximo_projeto
          FROM fundo f
          LEFT JOIN numero_p n ON n.fundo_codigo=f.codigo
          LEFT JOIN v_proximo_p v ON v.fundo_codigo=f.codigo
         WHERE f.ativo=1 AND f.sigla IS NOT NULL
         GROUP BY f.codigo, f.sigla, f.titulo, v.proximo
         ORDER BY f.codigo
    """).fetchall()]
    resposta = {"fundos": fundos}
    if fundo:
        if not any(f["codigo_fundo"] == fundo for f in fundos):
            con.close()
            raise HTTPException(404, f"Fundo {fundo} não existe ou está inativo")
        resposta["projetos"] = [dict(r) for r in con.execute("""
            SELECT codigo, printf('P%04d', numero) AS numero_projeto, titulo AS projeto,
                   ano, cidade, identificacao_original
              FROM projeto
             WHERE fundo_codigo=?
             ORDER BY numero
        """, (fundo,)).fetchall()]
    con.close()
    return resposta


class ReservaProjetoEstacao(BaseModel):
    fundo_codigo: str
    titulo: str
    ano: int = 0
    cidade: str | None = None
    identificacao_original: str | None = None


class HeartbeatEstacao(BaseModel):
    estacao_id: str
    tipo_estacao: str
    app: str
    versao: str | None = None
    hostname: str | None = None
    ip_local: str | None = None
    estado: str = "ocioso"
    fundo_codigo: str | None = None
    projeto_codigo: str | None = None
    operador: str | None = None
    ultimo_erro: str | None = None


@app.post("/api/estacoes/projetos/reservar")
def reservar_projeto_estacao(d: ReservaProjetoEstacao, request: Request) -> dict:
    """Reserva e cria um projeto para a estação usando o contador autoritativo do painel."""
    ip = _exigir_rede_local(request)
    titulo = d.titulo.strip()
    if not titulo:
        raise HTTPException(400, "Nome do projeto é obrigatório")
    if d.ano and not (1800 <= d.ano <= 2100):
        raise HTTPException(400, "Ano inválido (0 para sem data)")
    identificacao = (d.identificacao_original or "").strip() or None
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        f = con.execute("SELECT codigo FROM fundo WHERE codigo=? AND ativo=1", (d.fundo_codigo,)).fetchone()
        if not f:
            raise HTTPException(404, "Fundo não existe ou está inativo")
        prox = con.execute("SELECT proximo FROM v_proximo_p WHERE fundo_codigo=?", (d.fundo_codigo,)).fetchone()[0]
        numero = int(prox[1:])
        codigo = f"{d.fundo_codigo}-{prox}"
        con.execute("INSERT INTO numero_p (fundo_codigo, numero, reservado_por) VALUES (?,?,NULL)",
                    (d.fundo_codigo, numero))
        con.execute("""
            INSERT INTO projeto
                (codigo, fundo_codigo, numero, titulo, ano, cidade, identificacao_original)
            VALUES (?,?,?,?,?,?,?)
        """, (codigo, d.fundo_codigo, numero, titulo, d.ano or 0, d.cidade, identificacao))
        con.execute("""
            INSERT INTO evento (entidade, codigo, tipo, ator, detalhe)
            VALUES ('projeto',?,'criado',?,?)
        """, (codigo, f"estacao@{ip}", json.dumps({
            "titulo": titulo,
            "origem": "estacao",
            "identificacao_original": identificacao,
        }, ensure_ascii=False)))
        con.commit()
    except HTTPException:
        con.rollback()
        raise
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {
        "codigo": codigo,
        "numero_projeto": prox,
        "fundo_codigo": d.fundo_codigo,
        "titulo": titulo,
        "ano": d.ano or 0,
        "cidade": d.cidade,
        "identificacao_original": identificacao,
    }


@app.post("/api/estacoes/heartbeat")
def heartbeat_estacao(d: HeartbeatEstacao, request: Request) -> dict:
    """Heartbeat leve dos apps de captura. Restrito à rede local e sem bloquear a operação."""
    ip_origem = _exigir_rede_local(request)
    estacao_id = d.estacao_id.strip().lower()
    tipo = d.tipo_estacao.strip().lower()
    estado = d.estado.strip().lower()
    if not estacao_id or len(estacao_id) > 64:
        raise HTTPException(400, "estacao_id inválido")
    if tipo not in ("foto", "contex", "universal"):
        raise HTTPException(400, "tipo_estacao inválido")
    if estado not in ("ocioso", "capturando", "finalizando", "backup", "erro"):
        raise HTTPException(400, "estado inválido")
    con = connect()
    con.execute("""
        INSERT INTO estacao_heartbeat
            (estacao_id, tipo_estacao, app, versao, hostname, ip_local, estado,
             fundo_codigo, projeto_codigo, operador, ultimo_erro, recebido_de_ip, atualizado_em)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
        ON CONFLICT(estacao_id) DO UPDATE SET
            tipo_estacao=excluded.tipo_estacao,
            app=excluded.app,
            versao=excluded.versao,
            hostname=excluded.hostname,
            ip_local=excluded.ip_local,
            estado=excluded.estado,
            fundo_codigo=excluded.fundo_codigo,
            projeto_codigo=excluded.projeto_codigo,
            operador=excluded.operador,
            ultimo_erro=excluded.ultimo_erro,
            recebido_de_ip=excluded.recebido_de_ip,
            atualizado_em=datetime('now')
    """, (estacao_id, tipo, d.app[:80], (d.versao or "")[:120] or None,
          (d.hostname or "")[:120] or None, (d.ip_local or "")[:64] or None,
          estado, (d.fundo_codigo or "")[:16] or None, (d.projeto_codigo or "")[:32] or None,
          (d.operador or "")[:160] or None, (d.ultimo_erro or "")[:500] or None, ip_origem))
    con.commit(); con.close()
    return {"ok": True, "estacao_id": estacao_id, "estado": estado}
