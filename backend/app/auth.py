"""Autenticação e autorização do painel.

- Senha com Argon2id (passlib), nunca em texto puro.
- Sessão em cookie HttpOnly + Secure + SameSite=Strict; no banco fica só o hash do token,
  então um vazamento do banco não dá sessão a ninguém. Sessões são revogáveis.
- Bloqueio progressivo após tentativas erradas (por usuário) e limite por IP.
- Três papéis: admin, operador, leitura. Rotas declaram o mínimo exigido.
- 2FA por TOTP opcional (Google Authenticator etc.), obrigatório para admin se ativado.
- Tudo registrado em `evento` (login, falha, bloqueio, logout).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from passlib.context import CryptContext

from .config import settings
from .db import connect

COOKIE = "camp_sessao"
SESSAO_HORAS = 12
SESSAO_HORAS_LEMBRAR = 24 * 14
MAX_TENTATIVAS = 5              # por usuário antes de bloquear
BLOQUEIO_MIN = 15               # dobra a cada novo bloqueio
IP_MAX_POR_MIN = 20             # tentativas por IP por minuto

PAPEIS = {"leitura": 0, "operador": 1, "admin": 2, "master": 3}

pwd = CryptContext(schemes=["argon2"], deprecated="auto")
_ip_tentativas: dict[str, deque] = defaultdict(deque)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _evento(con: sqlite3.Connection, codigo: str, tipo: str, ator: str, detalhe: str = "") -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('usuario',?,?,?,?)",
                (codigo, tipo, ator, detalhe))


def _ip_estourou(ip: str) -> bool:
    fila = _ip_tentativas[ip]
    agora = time.time()
    while fila and agora - fila[0] > 60:
        fila.popleft()
    fila.append(agora)
    return len(fila) > IP_MAX_POR_MIN


def verificar_senha_forte(senha: str) -> None:
    if len(senha) < 12:
        raise HTTPException(400, "Senha precisa ter pelo menos 12 caracteres")
    if senha.lower() in {"camparquitetura", "casadaarquitetura", "123456789012"}:
        raise HTTPException(400, "Senha fraca demais")


def _tem_corrida(s: str, n: int = 8) -> bool:
    """Sequência óbvia: n caracteres seguidos subindo ou descendo de 1 em 1 (12345678, abcdefgh, 87654321)."""
    for i in range(len(s) - n + 1):
        d = [ord(s[i + k + 1]) - ord(s[i + k]) for k in range(n - 1)]
        if all(x == 1 for x in d) or all(x == -1 for x in d):
            return True
    return False


def verificar_senha_da_troca(senha_nova: str, senha_atual: str) -> None:
    """Regras da TROCA feita pela própria pessoa (a senha temporária escolhida pelo administrador não passa por aqui).
    Sem isso, a troca obrigatória do primeiro acesso podia ser contornada digitando a mesma senha."""
    if senha_nova == senha_atual:
        raise HTTPException(400, "A nova senha precisa ser diferente da atual")
    if len(set(senha_nova)) <= 3:
        raise HTTPException(400, "Senha fraca demais: use mais variedade de caracteres")
    if any(senha_nova == senha_nova[:k] * (len(senha_nova) // k) and len(senha_nova) % k == 0 for k in range(1, 9) if len(senha_nova) // k >= 2):
        raise HTTPException(400, "Senha fraca demais: não repita o mesmo trecho")
    if _tem_corrida(senha_nova.lower()):
        raise HTTPException(400, "Senha fraca demais: evite sequências como 12345678 ou abcdefgh")


def criar_usuario(nome: str, email: str, senha: str, papel: str, forcar_troca: bool = True) -> int:
    if papel not in PAPEIS:
        raise ValueError(f"papel inválido: {papel}")
    verificar_senha_forte(senha)
    con = connect()
    cur = con.execute(
        "INSERT INTO usuario (nome, email, papel, senha_hash, precisa_trocar_senha) VALUES (?,?,?,?,?)",
        (nome, email.lower().strip(), papel, pwd.hash(senha), int(forcar_troca)),
    )
    _evento(con, email, "criado", "sistema", f"papel={papel}")
    con.commit()
    uid = cur.lastrowid
    con.close()
    return uid


def autenticar(request: Request, response: Response, email: str, senha: str, lembrar: bool = False,
               codigo_totp: str | None = None) -> dict:
    ip = request.client.host if request.client else "?"
    if _ip_estourou(ip):
        raise HTTPException(429, "Muitas tentativas. Aguarde um minuto.")
    email = email.lower().strip()
    con = connect()
    u = con.execute("SELECT * FROM usuario WHERE email=? AND ativo=1", (email,)).fetchone()

    # resposta idêntica para usuário inexistente e senha errada (não revela quem existe)
    erro = HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha incorretos")
    if not u or not u["senha_hash"]:
        pwd.dummy_verify()
        _evento(con, email, "login_falhou", ip, "usuário desconhecido")
        con.commit(); con.close()
        raise erro

    if u["bloqueado_ate"] and u["bloqueado_ate"] > _iso(_agora()):
        con.close()
        raise HTTPException(423, f"Conta bloqueada até {u['bloqueado_ate']} UTC")

    if not pwd.verify(senha, u["senha_hash"]):
        falhas = u["tentativas_falhas"] + 1
        bloqueio = None
        if falhas >= MAX_TENTATIVAS:
            minutos = BLOQUEIO_MIN * (2 ** ((falhas - MAX_TENTATIVAS) // MAX_TENTATIVAS))
            bloqueio = _iso(_agora() + timedelta(minutes=minutos))
            _evento(con, email, "bloqueado", ip, f"{falhas} falhas, até {bloqueio}")
        con.execute("UPDATE usuario SET tentativas_falhas=?, bloqueado_ate=? WHERE id=?", (falhas, bloqueio, u["id"]))
        _evento(con, email, "login_falhou", ip, f"falha {falhas}")
        con.commit(); con.close()
        raise erro

    if u["totp_secret"] and not u["totp_secret"].startswith("PENDENTE:"):
        if not codigo_totp or not _totp_ok(u["totp_secret"], codigo_totp):
            con.close()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Código do autenticador inválido")

    # sucesso
    token = secrets.token_urlsafe(48)
    horas = SESSAO_HORAS_LEMBRAR if lembrar else SESSAO_HORAS
    expira = _agora() + timedelta(hours=horas)
    con.execute("INSERT INTO sessao (id, usuario_id, expira_em, ip, agente) VALUES (?,?,?,?,?)",
                (_hash_token(token), u["id"], _iso(expira), ip, (request.headers.get("user-agent") or "")[:120]))
    con.execute("UPDATE usuario SET tentativas_falhas=0, bloqueado_ate=NULL, ultimo_login=datetime('now') WHERE id=?",
                (u["id"],))
    _evento(con, email, "login", ip)
    con.commit(); con.close()

    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").startswith("https")
    response.set_cookie(COOKIE, token, max_age=horas * 3600, httponly=True, secure=bool(settings.CAMP_COOKIE_SECURE and https),
                        samesite="lax", path="/")
    return {"nome": u["nome"], "email": u["email"], "papel": u["papel"],
            "precisa_trocar_senha": bool(u["precisa_trocar_senha"])}


def sair(response: Response, token: str | None) -> None:
    if token:
        con = connect()
        con.execute("UPDATE sessao SET revogada=1 WHERE id=?", (_hash_token(token),))
        con.commit(); con.close()
    response.delete_cookie(COOKIE, path="/")


def usuario_atual(camp_sessao: str | None = Cookie(default=None)) -> dict:
    if not camp_sessao:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Faça login")
    con = connect()
    row = con.execute(
        "SELECT u.id, u.nome, u.email, u.papel, u.precisa_trocar_senha, s.expira_em, (u.totp_secret IS NOT NULL AND u.totp_secret NOT LIKE 'PENDENTE:%') AS totp FROM sessao s "
        "JOIN usuario u ON u.id=s.usuario_id WHERE s.id=? AND s.revogada=0 AND u.ativo=1",
        (_hash_token(camp_sessao),)).fetchone()
    con.close()
    if not row or row["expira_em"] < _iso(_agora()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada")
    return dict(row)


def exige(papel_minimo: str) -> Callable:
    """Dependência: `Depends(exige("operador"))` — bloqueia quem tem papel menor."""
    def _dep(u: dict = Depends(usuario_atual)) -> dict:
        if PAPEIS[u["papel"]] < PAPEIS[papel_minimo]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requer papel {papel_minimo}")
        if u["precisa_trocar_senha"]:
            raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, "Troque a senha antes de continuar")
        return u
    return _dep


def trocar_senha(u: dict, senha_atual: str, senha_nova: str, token_atual: str | None = None) -> None:
    verificar_senha_forte(senha_nova)
    verificar_senha_da_troca(senha_nova, senha_atual)
    con = connect()
    row = con.execute("SELECT senha_hash FROM usuario WHERE id=?", (u["id"],)).fetchone()
    if not pwd.verify(senha_atual, row["senha_hash"]):
        con.close()
        raise HTTPException(400, "Senha atual incorreta")
    con.execute("UPDATE usuario SET senha_hash=?, precisa_trocar_senha=0 WHERE id=?", (pwd.hash(senha_nova), u["id"]))
    con.execute("UPDATE sessao SET revogada=1 WHERE usuario_id=? AND id<>?", (u["id"], _hash_token(token_atual or "")))   # derruba só as OUTRAS sessões
    _evento(con, u["email"], "senha_trocada", u["email"])
    con.commit(); con.close()


# ---- TOTP (RFC 6238) sem dependência externa ----
def _totp(secret_b32: str, t: int) -> str:
    import base64, struct
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    msg = struct.pack(">Q", t // 30)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def _totp_ok(secret: str, codigo: str) -> bool:
    agora = int(time.time())
    return any(hmac.compare_digest(_totp(secret, agora + d), codigo.strip()) for d in (-30, 0, 30))


def gerar_totp_secret() -> str:
    import base64
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
