"""Gestão de usuários e configurações.

Regras:
- master: cria/edita qualquer usuário (inclusive admin e outro master), altera configurações de infraestrutura.
- admin: cria/edita operador e leitura; não toca em admin/master nem em configurações.
- ninguém desativa a si mesmo nem rebaixa o último master.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from . import auth
from .db import connect

router = APIRouter(prefix="/api", tags=["admin"])


class NovoUsuario(BaseModel):
    nome: str
    email: EmailStr
    papel: str


class EdicaoUsuario(BaseModel):
    nome: str | None = None
    papel: str | None = None
    ativo: bool | None = None


def _pode_gerir(ator: dict, papel_alvo: str) -> None:
    if papel_alvo not in auth.PAPEIS:
        raise HTTPException(400, f"Papel inválido: {papel_alvo}")
    if ator["papel"] == "master":
        return
    if ator["papel"] == "admin" and auth.PAPEIS[papel_alvo] <= auth.PAPEIS["operador"]:
        return
    raise HTTPException(403, f"Seu papel ({ator['papel']}) não pode gerir usuários do tipo {papel_alvo}")


def _senha_temporaria() -> str:
    return secrets.token_urlsafe(12)


@router.get("/usuarios")
def listar(u: dict = Depends(auth.exige("admin"))) -> list[dict]:
    con = connect()
    rows = con.execute(
        "SELECT id, nome, email, papel, ativo, ultimo_login, bloqueado_ate, precisa_trocar_senha, "
        "totp_secret IS NOT NULL AS totp FROM usuario ORDER BY papel DESC, nome").fetchall()
    con.close()
    return [dict(r) for r in rows]


@router.post("/usuarios")
def criar(d: NovoUsuario, u: dict = Depends(auth.exige("admin"))) -> dict:
    _pode_gerir(u, d.papel)
    con = connect()
    if con.execute("SELECT 1 FROM usuario WHERE email=?", (d.email.lower(),)).fetchone():
        con.close()
        raise HTTPException(409, "Já existe usuário com esse e-mail")
    con.close()
    senha = _senha_temporaria()
    uid = auth.criar_usuario(d.nome, d.email, senha, d.papel, forcar_troca=True)
    con = connect()
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('usuario',?,'criado_por',?,?)",
                (d.email.lower(), u["email"], f"papel={d.papel}"))
    con.commit(); con.close()
    # a senha temporária é mostrada UMA vez, para o admin repassar; o usuário troca no primeiro login
    return {"id": uid, "email": d.email.lower(), "senha_temporaria": senha}


@router.patch("/usuarios/{uid}")
def editar(uid: int, d: EdicaoUsuario, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    alvo = con.execute("SELECT * FROM usuario WHERE id=?", (uid,)).fetchone()
    if not alvo:
        con.close(); raise HTTPException(404, "Usuário não existe")
    _pode_gerir(u, alvo["papel"])
    if d.papel:
        _pode_gerir(u, d.papel)
    if uid == u["id"] and (d.ativo is False or (d.papel and d.papel != u["papel"])):
        con.close(); raise HTTPException(400, "Você não pode desativar nem mudar o próprio papel")
    if alvo["papel"] == "master" and (d.ativo is False or (d.papel and d.papel != "master")):
        n = con.execute("SELECT COUNT(*) FROM usuario WHERE papel='master' AND ativo=1").fetchone()[0]
        if n <= 1:
            con.close(); raise HTTPException(400, "Não é possível remover o último admin master")
    campos, vals = [], []
    for k in ("nome", "papel"):
        if getattr(d, k) is not None:
            campos.append(f"{k}=?"); vals.append(getattr(d, k))
    if d.ativo is not None:
        campos.append("ativo=?"); vals.append(int(d.ativo))
    if campos:
        con.execute(f"UPDATE usuario SET {', '.join(campos)} WHERE id=?", (*vals, uid))
        if d.ativo is False:
            con.execute("UPDATE sessao SET revogada=1 WHERE usuario_id=?", (uid,))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('usuario',?,'editado',?,?)",
                    (alvo["email"], u["email"], ", ".join(campos)))
        con.commit()
    con.close()
    return {"ok": True}


@router.post("/usuarios/{uid}/redefinir-senha")
def redefinir(uid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    alvo = con.execute("SELECT * FROM usuario WHERE id=?", (uid,)).fetchone()
    if not alvo:
        con.close(); raise HTTPException(404, "Usuário não existe")
    _pode_gerir(u, alvo["papel"])
    senha = _senha_temporaria()
    con.execute("UPDATE usuario SET senha_hash=?, precisa_trocar_senha=1, tentativas_falhas=0, bloqueado_ate=NULL, "
                "totp_secret=NULL WHERE id=?", (auth.pwd.hash(senha), uid))
    con.execute("UPDATE sessao SET revogada=1 WHERE usuario_id=?", (uid,))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator) VALUES ('usuario',?,'senha_redefinida',?)",
                (alvo["email"], u["email"]))
    con.commit(); con.close()
    return {"senha_temporaria": senha}


@router.post("/usuarios/{uid}/desbloquear")
def desbloquear(uid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    con.execute("UPDATE usuario SET tentativas_falhas=0, bloqueado_ate=NULL WHERE id=?", (uid,))
    con.commit(); con.close()
    return {"ok": True}


# ---- configurações (só master) ----
class Valor(BaseModel):
    valor: str


@router.get("/config")
def listar_config(u: dict = Depends(auth.exige("admin"))) -> list[dict]:
    con = connect()
    rows = con.execute("SELECT chave, valor, descricao, sensivel, atualizado_em, atualizado_por FROM configuracao ORDER BY chave").fetchall()
    con.close()
    out = []
    for r in rows:
        d = dict(r)
        if d["sensivel"]:
            d["valor"] = "••••••••" if d["valor"] else ""
        out.append(d)
    return out


@router.put("/config/{chave}")
def salvar_config(chave: str, d: Valor, u: dict = Depends(auth.exige("master"))) -> dict:
    con = connect()
    if not con.execute("SELECT 1 FROM configuracao WHERE chave=?", (chave,)).fetchone():
        con.close(); raise HTTPException(404, "Configuração desconhecida")
    if chave.endswith(".ip") and d.valor and not all(p.isdigit() and 0 <= int(p) <= 255 for p in d.valor.split(".")) or (chave.endswith(".ip") and d.valor and d.valor.count(".") != 3):
        con.close(); raise HTTPException(400, "IP inválido")
    con.execute("UPDATE configuracao SET valor=?, atualizado_em=datetime('now'), atualizado_por=? WHERE chave=?",
                (d.valor, u["email"], chave))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator) VALUES ('config',?,'alterada',?)", (chave, u["email"]))
    con.commit(); con.close()
    return {"ok": True}


def config(chave: str, padrao: str = "") -> str:
    """Leitura interna para o resto do sistema."""
    con = connect()
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    con.close()
    return (r[0] if r and r[0] else padrao)
