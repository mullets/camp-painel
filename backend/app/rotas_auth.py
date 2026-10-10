from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr

from . import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Login(BaseModel):
    email: EmailStr
    senha: str
    lembrar: bool = False
    codigo_totp: str | None = None


class Preferencia(BaseModel):
    chave: str
    valor: str | None = None      # None apaga ("mostrar de novo")


class TrocaSenha(BaseModel):
    senha_atual: str
    senha_nova: str


@router.post("/login")
def login(dados: Login, request: Request, response: Response) -> dict:
    r = auth.autenticar(request, response, dados.email, dados.senha, dados.lembrar, dados.codigo_totp)
    if isinstance(r, dict) and r.get("email"):   # mesmo perfil do /eu: o avatar aparece logo após o login, sem recarregar
        from .db import connect
        con = connect()
        try:
            row = con.execute("SELECT id, foto IS NOT NULL FROM usuario WHERE lower(email)=lower(?)", (r["email"],)).fetchone()
        finally:
            con.close()
        if row:
            r = {**r, "id": row[0], "tem_foto": bool(row[1])}
    return r


@router.post("/logout")
def logout(response: Response, camp_sessao: str | None = Cookie(default=None)) -> dict:
    auth.sair(response, camp_sessao)
    return {"ok": True}


@router.get("/eu")
def eu(u: dict = Depends(auth.usuario_atual)) -> dict:
    from .db import connect
    con = connect()
    try:
        tem_foto = bool(con.execute("SELECT foto IS NOT NULL FROM usuario WHERE id=?", (u["id"],)).fetchone()[0])
    finally:
        con.close()
    return {"id": u["id"], "nome": u["nome"], "email": u["email"], "papel": u["papel"], "tem_foto": tem_foto,
            "precisa_trocar_senha": bool(u["precisa_trocar_senha"]), "totp": bool(u.get("totp"))}


@router.get("/eu/preferencias")
def preferencias(u: dict = Depends(auth.usuario_atual)) -> dict:
    """Preferências da pessoa logada (hoje: 'ajuda.<página>' = a versão da caixa 'Como funciona esta página' que ela já viu)."""
    from .db import connect
    con = connect()
    try:
        return {r[0]: r[1] for r in con.execute("SELECT chave, valor FROM usuario_preferencia WHERE usuario_id=?", (u["id"],))}
    finally:
        con.close()


@router.put("/eu/preferencias")
def gravar_preferencia(d: Preferencia, u: dict = Depends(auth.usuario_atual)) -> dict:
    import re
    from .db import connect
    if not re.fullmatch(r"ajuda\.[a-z_]{1,40}", d.chave or ""):
        raise HTTPException(400, "Preferência desconhecida")
    if d.valor is not None and len(d.valor) > 40:
        raise HTTPException(400, "Valor longo demais")
    con = connect()
    try:
        if d.valor is None:
            con.execute("DELETE FROM usuario_preferencia WHERE usuario_id=? AND chave=?", (u["id"], d.chave))
        else:
            con.execute("""INSERT INTO usuario_preferencia (usuario_id, chave, valor) VALUES (?,?,?)
                           ON CONFLICT(usuario_id, chave) DO UPDATE SET valor=excluded.valor, atualizado_em=datetime('now')""", (u["id"], d.chave, d.valor))
        con.commit()
    finally:
        con.close()
    return {"ok": True}


@router.post("/trocar-senha")
def trocar(dados: TrocaSenha, u: dict = Depends(auth.usuario_atual), camp_sessao: str | None = Cookie(default=None)) -> dict:
    auth.trocar_senha(u, dados.senha_atual, dados.senha_nova, camp_sessao)
    return {"ok": True, "aviso": "Senha alterada. Outras sessões foram encerradas; esta continua."}


# ---- perfil ----
from fastapi import Body  # noqa: E402
from .db import connect  # noqa: E402


@router.get("/sessoes")
def sessoes(u: dict = Depends(auth.usuario_atual)) -> list[dict]:
    con = connect()
    rows = con.execute("SELECT id, criada_em, expira_em, ip, agente FROM sessao WHERE usuario_id=? AND revogada=0 AND expira_em > datetime('now') ORDER BY criada_em DESC", (u["id"],)).fetchall()
    con.close()
    return [{**dict(r), "id": r["id"][:8]} for r in rows]


@router.post("/sessoes/encerrar-outras")
def encerrar_outras(u: dict = Depends(auth.usuario_atual), camp_sessao: str | None = Cookie(default=None)) -> dict:
    con = connect()
    con.execute("UPDATE sessao SET revogada=1 WHERE usuario_id=? AND id<>?", (u["id"], auth._hash_token(camp_sessao or "")))
    con.commit(); con.close()
    return {"ok": True}


@router.post("/2fa/iniciar")
def iniciar_2fa(u: dict = Depends(auth.usuario_atual)) -> dict:
    """Gera segredo provisório; só vale depois de confirmar com um código."""
    secret = auth.gerar_totp_secret()
    con = connect()
    con.execute("UPDATE usuario SET totp_secret=? WHERE id=?", ("PENDENTE:" + secret, u["id"]))
    con.commit(); con.close()
    uri = f"otpauth://totp/CAMP%20Acervos:{u['email']}?secret={secret}&issuer=CAMP%20Acervos&digits=6&period=30"
    return {"secret": secret, "otpauth": uri}


@router.post("/2fa/confirmar")
def confirmar_2fa(codigo: str = Body(embed=True), u: dict = Depends(auth.usuario_atual)) -> dict:
    con = connect()
    row = con.execute("SELECT totp_secret FROM usuario WHERE id=?", (u["id"],)).fetchone()
    s = (row["totp_secret"] or "")
    if not s.startswith("PENDENTE:"):
        con.close(); raise HTTPException(400, "Nenhuma ativação em andamento")
    secret = s.split(":", 1)[1]
    if not auth._totp_ok(secret, codigo):
        con.close(); raise HTTPException(400, "Código inválido. Confira o relógio do celular e tente de novo.")
    con.execute("UPDATE usuario SET totp_secret=? WHERE id=?", (secret, u["id"]))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator) VALUES ('usuario',?,'2fa_ativado',?)", (u["email"], u["email"]))
    con.commit(); con.close()
    return {"ok": True}


@router.post("/2fa/desativar")
def desativar_2fa(senha: str = Body(embed=True), u: dict = Depends(auth.usuario_atual)) -> dict:
    con = connect()
    row = con.execute("SELECT senha_hash FROM usuario WHERE id=?", (u["id"],)).fetchone()
    if not auth.pwd.verify(senha, row["senha_hash"]):
        con.close(); raise HTTPException(400, "Senha incorreta")
    con.execute("UPDATE usuario SET totp_secret=NULL WHERE id=?", (u["id"],))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator) VALUES ('usuario',?,'2fa_desativado',?)", (u["email"], u["email"]))
    con.commit(); con.close()
    return {"ok": True}
