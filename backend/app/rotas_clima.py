"""Clima das salas do acervo no painel (lido do que o coletor guardou; nunca fala com a Tuya na requisição). Ver clima.py."""
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import auth, clima, contagens, site_agora
from .db import connect
from .rede import CABECALHOS_PROXY, _ip_lan

router = APIRouter(tags=["clima"])
PAGINA = Path(__file__).resolve().parents[2] / "frontend" / "clima.html"


@router.get("/api/clima")
def ver(u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        return clima.resumo(con)
    finally:
        con.close()


@router.get("/api/clima/resumo")
def ver_resumo(u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Só o que a barra do topo precisa (média, pior nível, frase); leve para ler a cada 5 min. Ver clima.resumo_barra."""
    con = connect()
    try:
        return clima.resumo_barra(con)
    finally:
        con.close()


@router.get("/api/clima/serie")
def serie(sensor: str, dias: int = 7, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM clima_sensor WHERE id=?", (sensor,)).fetchone():
            raise HTTPException(404, "Sensor não encontrado")
        return {"sensor": sensor, "dias": dias, "faixa": clima.faixa(con), "serie": clima.serie(con, sensor, dias, 300)}
    finally:
        con.close()


@router.post("/api/clima/coletar")
def coletar_agora(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Pede uma leitura agora (admin). Roda em segundo plano: a tela espera alguns segundos e relê /api/clima."""
    if clima.em_andamento():
        return {"ok": True, "ja_em_andamento": True}
    threading.Thread(target=clima.coletar, daemon=True).start()
    return {"ok": True, "iniciada": True}


@router.get("/api/clima/sensores")
def listar_sensores(u: dict = Depends(auth.exige("admin"))) -> dict:
    """CAMP-CLIMA: a tela "Sensores" (admin), aberta pela pílula do clima. Só o que o coletor guardou (nunca fala com a Tuya aqui)."""
    con = connect()
    try:
        return clima.lista_sensores(con)
    finally:
        con.close()


class SensorIn(BaseModel):
    nome: str | None = None
    ativo: bool | None = None
    removido: bool | None = None     # CAMP-CLIMA: True = "Remover da lista" (ativo vai a 0; as leituras ficam); False = "Devolver à lista"


@router.put("/api/clima/sensores/{sensor_id}")
def editar_sensor(sensor_id: str, d: SensorIn, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Nome mostrado no painel (ex.: a sala), se o sensor entra no clima e "Remover da lista". Não muda nada no app da Tuya
    e nunca apaga leitura (o histórico do sensor fica)."""
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM clima_sensor WHERE id=?", (sensor_id,)).fetchone():
            raise HTTPException(404, "Sensor não encontrado")
        if d.nome is not None:
            nome = d.nome.strip()[:80]
            if len(nome) < 2:
                raise HTTPException(422, "Escreva o nome do sensor")
            con.execute("UPDATE clima_sensor SET nome=? WHERE id=?", (nome, sensor_id))
        if d.ativo is not None:
            con.execute("UPDATE clima_sensor SET ativo=? WHERE id=?", (int(d.ativo), sensor_id))
        if d.removido is True:
            con.execute("UPDATE clima_sensor SET removido=1, ativo=0, removido_em=datetime('now') WHERE id=?", (sensor_id,))
        elif d.removido is False:
            con.execute("UPDATE clima_sensor SET removido=0, removido_em=NULL WHERE id=?", (sensor_id,))
        con.execute("UPDATE clima_sensor SET alterado_em=datetime('now'), alterado_por=? WHERE id=?", (str(u.get("email") or u.get("nome") or "")[:120], sensor_id))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


def _so_rede_local(request: Request) -> None:
    """O tablet de parede não faz login: a leitura vale só de dentro da rede do escritório, nunca pelo túnel (ver rede.py)."""
    ip = request.client.host if request.client else ""
    if any(h in request.headers for h in CABECALHOS_PROXY) or not _ip_lan(ip):
        raise HTTPException(403, "O clima sem login só abre na rede do escritório")


def _site(con) -> dict:
    """Números do site para a parede, todos do que já está guardado: pessoas agora (site_agora), visitas dos últimos 7 dias
    (a coleta diária das Visitas ao site) e quanto do acervo está no site (a mesma conta do painel: contagens.no_site)."""
    v = con.execute("SELECT de, ate, usuarios, sessoes, visualizacoes FROM visita_periodo WHERE chave='7d'").fetchone()
    n = contagens.no_site(con)
    return {"agora": site_agora.ultima(con),
            "visitas_7d": {"pessoas": v["usuarios"], "visualizacoes": v["visualizacoes"], "de": v["de"], "ate": v["ate"]} if v else None,
            "no_site": {"fundos": n["fundos"]["no_ar"], "projetos": n["projetos"]["no_ar"], "folhas": n["folhas"]["no_ar"]}}


@router.get("/api/clima/parede")
def parede(request: Request) -> dict:
    """Só leitura, sem login, só na rede local: temperatura e umidade de cada sensor. Não devolve configuração nem credencial."""
    _so_rede_local(request)
    con = connect()
    try:
        r = clima.resumo(con)
        site = _site(con)
    finally:
        con.close()
    coleta = r["coleta"] or {}
    return {"site": site, "sensores": [{k: s[k] for k in ("nome", "online", "idade_s", "sem_leitura_recente", "temperatura_c", "umidade_pct",
                                             "bateria_pct", "nivel", "dia", "serie")} for s in r["sensores"]],
            "faixa": r["faixa"], "ligado": r["ligado"], "idade_coleta_s": coleta.get("idade_s"), "com_erro": bool(coleta.get("erro"))}


@router.get("/clima", include_in_schema=False)
def pagina() -> FileResponse:
    """Página leve para o tablet de parede (navegador antigo: sem o painel inteiro)."""
    return FileResponse(PAGINA, headers={"Cache-Control": "no-cache"})
