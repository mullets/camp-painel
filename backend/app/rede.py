"""Guarda das rotas que não usam login (estações de digitalização, fundos.json).

Regras:
- Requisição que passou por proxy/túnel (Cloudflare Tunnel, nginx...) NUNCA é tratada como rede local:
  o cloudflared conecta de 127.0.0.1, então o IP sozinho não prova nada.
- Com `estacao.token` configurado (Configurações, valor sensível), o cabeçalho X-Camp-Token passa a ser
  obrigatório para todos, inclusive dentro da LAN.
- Sem token configurado (modo legado), vale só a LAN de verdade: 192.168.x.x, 10.x.x.x ou 127.0.0.1
  sem nenhum cabeçalho de proxy.
"""
import hmac
import ipaddress
import logging
import time

from fastapi import HTTPException, Request

from .db import connect
from .log_tecnico import registrar

CABECALHOS_PROXY = (
    "cf-connecting-ip", "cf-ray", "x-forwarded-for", "x-forwarded-host",
    "x-forwarded-proto", "x-real-ip", "true-client-ip", "forwarded",
)
_REDES_LAN = (ipaddress.ip_network("192.168.0.0/16"), ipaddress.ip_network("10.0.0.0/8"))


_ULTIMA_RECUSA: dict = {}


def _nega(request: Request, ip: str, status: int, motivo: str, mensagem: str):
    """Registra o MOTIVO da recusa no log técnico (no máximo 1x por minuto por IP+motivo) e recusa.
    Nunca grava o token: só se ele foi enviado e quais cabeçalhos de proxy vieram."""
    agora = time.time()
    if agora - _ULTIMA_RECUSA.get((ip, motivo), 0) > 60:
        _ULTIMA_RECUSA[(ip, motivo)] = agora
        registrar(logging.WARNING, "estacao_negada", mensagem, ip=ip, rota=request.url.path, motivo=motivo, status=status,
                  cabecalhos_proxy=[h for h in CABECALHOS_PROXY if h in request.headers],
                  enviou_token=bool(request.headers.get("x-camp-token")),
                  user_agent=request.headers.get("user-agent", "")[:80])
        if motivo in ("token_ausente_ou_invalido", "via_proxy_sem_token"):
            _lembrar_negada(ip, motivo, request)
    raise HTTPException(status, mensagem)


def _lembrar_negada(ip: str, motivo: str, request: Request) -> None:
    """A tela Estações avisa que uma máquina está sem o token. Nunca atrapalha a resposta 401/403."""
    try:
        con = connect()
        try:
            con.execute("""INSERT INTO estacao_negada (ip, motivo, enviou_token, rota) VALUES (?,?,?,?)
                           ON CONFLICT(ip, motivo) DO UPDATE SET vezes=vezes+1, ultima_em=datetime('now'), enviou_token=excluded.enviou_token, rota=excluded.rota""",
                        (ip, motivo, int(bool(request.headers.get("x-camp-token"))), request.url.path[:120]))
            con.commit()
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        pass


def negadas_por_token(con, dias: int = 2) -> list[dict]:
    """Máquinas recusadas por falta de token nos últimos dias (mais recente primeiro)."""
    try:
        return [dict(r) for r in con.execute("""SELECT ip, motivo, enviou_token, vezes, ultima_em FROM estacao_negada
                                                 WHERE ultima_em >= datetime('now', ?) ORDER BY ultima_em DESC LIMIT 10""", (f"-{int(dias)} days",))]
    except Exception:  # noqa: BLE001 - banco sem a tabela ainda
        return []


def _token_configurado() -> str:
    con = connect()
    try:
        row = con.execute("SELECT valor FROM configuracao WHERE chave='estacao.token'").fetchone()
    finally:
        con.close()
    return ((row[0] if row else "") or "").strip()


def ip_do_cliente(request: Request) -> str:
    """IP de quem está do outro lado, também atrás do túnel (cloudflared conecta de 127.0.0.1). Só confia no cabeçalho de proxy quando
    quem conectou é a própria máquina (o túnel); de qualquer outro IP o cabeçalho é ignorado, porque qualquer um pode escrever um."""
    peer = request.client.host if request.client else ""
    try:
        loop = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        loop = False
    if loop:
        cf = request.headers.get("cf-connecting-ip", "").strip()
        xff = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        for cand in (cf, xff[-1] if xff else ""):
            try:
                return str(ipaddress.ip_address(cand))
            except ValueError:
                continue
    return peer or "?"


def _ip_lan(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_loopback or any(a in rede for rede in _REDES_LAN)


def exigir_estacao(request: Request) -> str:
    """Autoriza a chamada ou levanta 401/403. Devolve o IP de origem."""
    ip = request.client.host if request.client else ""
    token = _token_configurado()
    if token:
        enviado = request.headers.get("x-camp-token", "")
        if enviado and hmac.compare_digest(enviado.encode(), token.encode()):
            return ip
        _nega(request, ip, 401, "token_ausente_ou_invalido", "Token da estação ausente ou inválido")
    if any(h in request.headers for h in CABECALHOS_PROXY):
        _nega(request, ip, 403, "via_proxy_sem_token", "Acesso externo exige o token da estação (configure estacao.token)")
    if not _ip_lan(ip):
        _nega(request, ip, 403, "fora_da_lan", f"Somente rede local (IP {ip} não é 192.168.x.x, 10.x.x.x ou 127.0.0.1)")
    return ip
