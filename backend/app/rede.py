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

from fastapi import HTTPException, Request

from .db import connect

CABECALHOS_PROXY = (
    "cf-connecting-ip", "cf-ray", "x-forwarded-for", "x-forwarded-host",
    "x-forwarded-proto", "x-real-ip", "true-client-ip", "forwarded",
)
_REDES_LAN = (ipaddress.ip_network("192.168.0.0/16"), ipaddress.ip_network("10.0.0.0/8"))


def _token_configurado() -> str:
    con = connect()
    try:
        row = con.execute("SELECT valor FROM configuracao WHERE chave='estacao.token'").fetchone()
    finally:
        con.close()
    return ((row[0] if row else "") or "").strip()


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
        raise HTTPException(401, "Token da estação ausente ou inválido")
    if any(h in request.headers for h in CABECALHOS_PROXY):
        raise HTTPException(403, "Acesso externo exige o token da estação (configure estacao.token)")
    if not _ip_lan(ip):
        raise HTTPException(403, "Somente rede local")
    return ip
