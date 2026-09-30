from fastapi import APIRouter, Cookie, Depends, Request, Response
from pydantic import BaseModel, EmailStr

from . import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Login(BaseModel):
    email: EmailStr
    senha: str
    lembrar: bool = False
    codigo_totp: str | None = None


class TrocaSenha(BaseModel):
    senha_atual: str
    senha_nova: str


@router.post("/login")
def login(dados: Login, request: Request, response: Response) -> dict:
    return auth.autenticar(request, response, dados.email, dados.senha, dados.lembrar, dados.codigo_totp)


@router.post("/logout")
def logout(response: Response, camp_sessao: str | None = Cookie(default=None)) -> dict:
    auth.sair(response, camp_sessao)
    return {"ok": True}


@router.get("/eu")
def eu(u: dict = Depends(auth.usuario_atual)) -> dict:
    return {"nome": u["nome"], "email": u["email"], "papel": u["papel"],
            "precisa_trocar_senha": bool(u["precisa_trocar_senha"])}


@router.post("/trocar-senha")
def trocar(dados: TrocaSenha, u: dict = Depends(auth.usuario_atual)) -> dict:
    auth.trocar_senha(u, dados.senha_atual, dados.senha_nova)
    return {"ok": True, "aviso": "Outras sessões foram encerradas. Entre de novo."}
