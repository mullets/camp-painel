"""Gestão de usuários e configurações.

Regras:
- master: cria/edita qualquer usuário (inclusive admin e outro master), altera configurações de infraestrutura.
- admin: cria/edita operador e leitura; não toca em admin/master nem em configurações.
- ninguém desativa a si mesmo nem rebaixa o último master.
"""
from __future__ import annotations

import json

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
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
        "totp_secret IS NOT NULL AS totp, foto IS NOT NULL AS tem_foto FROM usuario ORDER BY papel DESC, nome").fetchall()
    con.close()
    return [{**dict(r), "tem_foto": bool(r["tem_foto"])} for r in rows]


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
    campos, vals, antes, depois = [], [], {}, {}
    for k in ("nome", "papel"):
        v = getattr(d, k)
        if v is not None and v != alvo[k]:
            campos.append(f"{k}=?"); vals.append(v); antes[k] = alvo[k]; depois[k] = v
    if d.ativo is not None and int(d.ativo) != alvo["ativo"]:
        campos.append("ativo=?"); vals.append(int(d.ativo)); antes["ativo"] = bool(alvo["ativo"]); depois["ativo"] = bool(d.ativo)
    if campos:
        con.execute(f"UPDATE usuario SET {', '.join(campos)} WHERE id=?", (*vals, uid))
        if d.ativo is False:
            con.execute("UPDATE sessao SET revogada=1 WHERE usuario_id=?", (uid,))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('usuario',?,'editado',?,?)",
                    (alvo["email"], u["email"], json.dumps({"antes": antes, "depois": depois}, ensure_ascii=False)))
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
    atual = con.execute("SELECT valor, sensivel FROM configuracao WHERE chave=?", (chave,)).fetchone()
    if not atual:
        con.close(); raise HTTPException(404, "Configuração desconhecida")
    if chave.endswith(".ip") and d.valor and not all(p.isdigit() and 0 <= int(p) <= 255 for p in d.valor.split(".")) or (chave.endswith(".ip") and d.valor and d.valor.count(".") != 3):
        con.close(); raise HTTPException(400, "IP inválido")
    con.execute("UPDATE configuracao SET valor=?, atualizado_em=datetime('now'), atualizado_por=? WHERE chave=?",
                (d.valor, u["email"], chave))
    antes = "definido" if atual["sensivel"] and atual["valor"] else ("" if atual["sensivel"] else atual["valor"])
    depois = "definido" if atual["sensivel"] and d.valor else ("" if atual["sensivel"] else d.valor)
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('config',?,'alterada',?,?)",
                (chave, u["email"], json.dumps({"antes": {"valor": antes}, "depois": {"valor": depois}}, ensure_ascii=False)))
    con.commit(); con.close()
    return {"ok": True}


def config(chave: str, padrao: str = "") -> str:
    """Leitura interna para o resto do sistema."""
    con = connect()
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    con.close()
    return (r[0] if r and r[0] else padrao)


# ---------------- foto de perfil ----------------
LIMITE_FOTO = 300_000


def _tipo_imagem(b: bytes) -> str | None:
    """Tipo pelo CONTEÚDO (não pelo cabeçalho que o cliente manda): só JPEG e PNG. SVG/HTML nunca entram."""
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return None


def _checa_permissao_foto(con, u: dict, uid: int):
    alvo = con.execute("SELECT id, papel FROM usuario WHERE id=?", (uid,)).fetchone()
    if not alvo:
        raise HTTPException(404, "Usuário não existe")
    if uid != u["id"]:
        if auth.PAPEIS[u["papel"]] < auth.PAPEIS["admin"]:
            raise HTTPException(403, "Só você (ou um administrador) pode trocar esta foto")
        _pode_gerir(u, alvo["papel"])
    return alvo


@router.get("/usuarios/{uid}/foto")
def ver_foto(uid: int, u: dict = Depends(auth.usuario_atual)) -> Response:
    con = connect()
    try:
        r = con.execute("SELECT foto, foto_tipo FROM usuario WHERE id=?", (uid,)).fetchone()
    finally:
        con.close()
    if not r or not r["foto"]:
        raise HTTPException(404, "Sem foto")
    return Response(bytes(r["foto"]), media_type=r["foto_tipo"] or "image/jpeg",
                    headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300", "Content-Disposition": "inline"})


@router.put("/usuarios/{uid}/foto")
async def definir_foto(uid: int, request: Request, u: dict = Depends(auth.usuario_atual)) -> dict:
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > LIMITE_FOTO:
        raise HTTPException(413, "Foto grande demais (máximo 300 KB). Use uma imagem menor.")
    dados = await request.body()
    if len(dados) > LIMITE_FOTO:
        raise HTTPException(413, "Foto grande demais (máximo 300 KB). Use uma imagem menor.")
    tipo = _tipo_imagem(dados)
    if not tipo:
        raise HTTPException(400, "Envie uma foto JPEG ou PNG.")
    con = connect()
    try:
        _checa_permissao_foto(con, u, uid)
        con.execute("UPDATE usuario SET foto=?, foto_tipo=? WHERE id=?", (dados, tipo, uid))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('usuario',?,'foto_atualizada',?,?)",
                    (str(uid), u["email"], json.dumps({"bytes": len(dados), "tipo": tipo})))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "bytes": len(dados)}


@router.delete("/usuarios/{uid}/foto")
def remover_foto(uid: int, u: dict = Depends(auth.usuario_atual)) -> dict:
    con = connect()
    try:
        _checa_permissao_foto(con, u, uid)
        con.execute("UPDATE usuario SET foto=NULL, foto_tipo=NULL WHERE id=?", (uid,))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('usuario',?,'foto_removida',?,'{}')", (str(uid), u["email"]))
        con.commit()
    finally:
        con.close()
    return {"ok": True}
