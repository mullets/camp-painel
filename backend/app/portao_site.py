"""CAMP-SITE-CARGA (26/11/2026): o painel nunca mais martela o site.

Site sem responder desde 26/11 ~10:00: o plano do site tem só 3 processos PHP; cada PATCH do painel ocupa um e dispara a remontagem da lista
de ~5 mil documentos. Com várias edições de fichas em segundo plano ao mesmo tempo (um BackgroundTask por "salvar"), os 3 ficavam presos,
a memória estourava e o visitante via erro.

Toda requisição do cliente do site (wp.WP, httpx) passa por aqui (TransporteSite):
- ESCRITA (POST/PUT/PATCH/DELETE): uma de cada vez no processo inteiro (trava única) e com uma pausa mínima entre duas
  (`site.envio_pausa_ms`, padrão 5000).
- DISJUNTOR: resposta 5xx/429, tempo esgotado ou erro de rede abrem o disjuntor: nenhuma requisição ao site (nem leitura) até
  "pausado até HH:MM". Espera exponencial: 2 min, 4, 8… até 30 min (`site.backoff_inicio_s`, `site.backoff_max_s`). Sucesso zera.
  Sem retentativa curta: quem tentou recebe SitePausado (um erro de rede passageiro: quem já guarda pendência a mantém e o coletor
  tenta de novo depois).
- PAUSA MANUAL: `site.envios_pausados` = 1 (Máquinas → "Pausar envios ao site") segura as escritas até "Retomar"; leituras seguem.
O painel roda num único processo (uvicorn sem workers), então a trava e o estado ficam em memória; a pausa manual fica no banco.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime

import httpx

PAUSA_MS_PADRAO = 5000
BACKOFF_INICIO_S = 120
BACKOFF_MAX_S = 1800
LOTE_PADRAO = 25


class SitePausado(httpx.ConnectError):
    """O painel não foi ao site: disjuntor aberto ou envios pausados. É 'passageiro' (wp.erro_passageiro): a pendência fica."""


_ESCRITA = threading.Lock()          # uma escrita por vez, no processo inteiro
_ESTADO = threading.Lock()
_st: dict = {"ultimo_envio": 0.0, "pausado_ate": 0.0, "falhas": 0, "motivo": "", "na_fila": 0, "enviados": 0, "ultima_falha_em": None}
_CFG: dict = {"t": 0.0, "v": {}}


def _cfg() -> dict:
    """Configurações lidas do banco no máximo a cada 5 s (não pesa em cada requisição)."""
    agora = time.monotonic()
    if agora - _CFG["t"] < 5 and _CFG["v"]:
        return _CFG["v"]
    v = {"pausa_ms": PAUSA_MS_PADRAO, "inicio": BACKOFF_INICIO_S, "max": BACKOFF_MAX_S, "manual": False, "lote": LOTE_PADRAO}
    try:
        from .db import connect
        con = connect()
        try:
            rows = dict(con.execute("""SELECT chave, valor FROM configuracao WHERE chave IN
                ('site.envio_pausa_ms','site.backoff_inicio_s','site.backoff_max_s','site.envios_pausados','site.envio_lote')""").fetchall())
        finally:
            con.close()
        def num(k, d):
            try:
                return max(0, int(float(str(rows.get(k, d)).strip())))
            except (TypeError, ValueError):
                return d
        v = {"pausa_ms": num("site.envio_pausa_ms", PAUSA_MS_PADRAO), "inicio": max(1, num("site.backoff_inicio_s", BACKOFF_INICIO_S)),
             "max": max(1, num("site.backoff_max_s", BACKOFF_MAX_S)), "manual": str(rows.get("site.envios_pausados", "")).strip() == "1",
             "lote": max(1, num("site.envio_lote", LOTE_PADRAO))}
    except Exception:  # noqa: BLE001  (banco indisponível: padrões)
        pass
    if os.environ.get("CAMP_SITE_PAUSA_MS", "").strip().isdigit():      # a suíte de testes zera a pausa (sites falsos)
        v["pausa_ms"] = int(os.environ["CAMP_SITE_PAUSA_MS"])
    v["disjuntor"] = os.environ.get("CAMP_SITE_DISJUNTOR", "1").strip() != "0"   # a suíte desliga, salvo no modo que testa o disjuntor
    _CFG.update(t=agora, v=v)
    return v


def esquecer_cfg() -> None:
    _CFG.update(t=0.0, v={})


def lote() -> int:
    return _cfg()["lote"]


def _hhmm(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def estado() -> dict:
    """Para Máquinas: fila, pausa (disjuntor ou manual) e motivo."""
    c = _cfg()
    with _ESTADO:
        s = dict(_st)
    agora = time.time()
    aberto = s["pausado_ate"] > agora
    return {"na_fila": s["na_fila"], "enviados": s["enviados"], "falhas_seguidas": s["falhas"],
            "disjuntor_aberto": aberto, "pausado_ate": datetime.fromtimestamp(s["pausado_ate"]).isoformat(timespec="seconds") if aberto else None,
            "pausado_ate_hhmm": _hhmm(s["pausado_ate"]) if aberto else None, "motivo": s["motivo"] if aberto else "",
            "pausa_manual": c["manual"], "pausa_entre_envios_ms": c["pausa_ms"], "lote": c["lote"],
            "ultima_falha_em": s["ultima_falha_em"]}


def retomar() -> None:
    """'Retomar agora': fecha o disjuntor (a pausa manual é desligada por quem chama, no banco)."""
    with _ESTADO:
        _st.update(pausado_ate=0.0, falhas=0, motivo="")
    esquecer_cfg()


def registrar_falha(motivo: str) -> float:
    c = _cfg()
    if not c.get("disjuntor", True):
        return 0.0
    with _ESTADO:
        _st["falhas"] += 1
        espera = min(c["max"], c["inicio"] * (2 ** (_st["falhas"] - 1)))
        _st["pausado_ate"] = max(_st["pausado_ate"], time.time() + espera)
        _st["motivo"] = motivo[:160]
        _st["ultima_falha_em"] = datetime.now().isoformat(timespec="seconds")
        return _st["pausado_ate"]


def registrar_sucesso() -> None:
    with _ESTADO:
        _st.update(falhas=0, pausado_ate=0.0, motivo="")


def checar(request: httpx.Request | None = None, escrita: bool = False) -> None:
    """Levanta SitePausado se o disjuntor está aberto (qualquer requisição) ou os envios estão pausados à mão (só escrita)."""
    with _ESTADO:
        ate, motivo = _st["pausado_ate"], _st["motivo"]
    if ate > time.time():
        raise SitePausado(f"site sobrecarregado: envios pausados até {_hhmm(ate)} ({motivo})", request=request)
    if escrita and _cfg()["manual"]:
        raise SitePausado("envios ao site pausados em Máquinas (Retomar para voltar a enviar)", request=request)


def _falha_da_resposta(status: int) -> bool:
    return status >= 500 or status == 429


class TransporteSite(httpx.BaseTransport):
    """Transporte do cliente do site: serializa escritas, espaça, e abre o disjuntor em 5xx/429/tempo esgotado/rede."""

    def __init__(self, interno: httpx.BaseTransport | None = None) -> None:
        self.interno = interno or httpx.HTTPTransport()

    def _ir(self, request: httpx.Request) -> httpx.Response:
        try:
            resp = self.interno.handle_request(request)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
            if not isinstance(e, SitePausado):
                registrar_falha("tempo esgotado" if isinstance(e, httpx.TimeoutException) else "o site não respondeu")
            raise
        if _falha_da_resposta(resp.status_code):
            registrar_falha(f"o site respondeu {resp.status_code}")
        else:
            registrar_sucesso()
        return resp

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        escrita = request.method.upper() not in ("GET", "HEAD", "OPTIONS")
        checar(request, escrita)
        if not escrita:
            return self._ir(request)
        with _ESTADO:
            _st["na_fila"] += 1
        try:
            with _ESCRITA:
                checar(request, escrita)                     # o disjuntor pode ter aberto enquanto esperava a vez
                pausa = _cfg()["pausa_ms"] / 1000.0
                falta = _st["ultimo_envio"] + pausa - time.monotonic()
                if falta > 0:
                    time.sleep(falta)
                    checar(request, escrita)
                try:
                    return self._ir(request)
                finally:
                    with _ESTADO:
                        _st["ultimo_envio"] = time.monotonic()
                        _st["enviados"] += 1
        finally:
            with _ESTADO:
                _st["na_fila"] -= 1

    def close(self) -> None:
        self.interno.close()
