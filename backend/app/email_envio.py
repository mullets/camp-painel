"""Envio de e-mail por SMTP (usa a configuração smtp.* do painel). Um destinatário por vez, vindo SEMPRE do banco, nunca do navegador."""
from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage

ENDERECO = re.compile(r"^[^@\s,;<>\"']+@[^@\s,;<>\"']+\.[^@\s,;<>\"']+$")


class EnvioErro(Exception):
    """Falha de envio, com mensagem já segura para mostrar (a senha nunca aparece)."""


def configuracao(con) -> dict:
    def g(chave: str, padrao: str = "") -> str:
        r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
        return (r[0] if r and r[0] is not None else "") or padrao
    try:
        porta = int(g("smtp.porta", "587"))
    except ValueError:
        porta = 587
    usuario = g("smtp.usuario")
    return {"host": g("smtp.host"), "porta": porta, "seguranca": g("smtp.seguranca", "starttls").strip().lower(),
            "usuario": usuario, "senha": g("smtp.senha"), "remetente": g("smtp.remetente") or (usuario if ENDERECO.match(usuario) else "")}


def configurado(c: dict) -> bool:
    return bool(c["host"] and c["remetente"] and ENDERECO.match(c["remetente"]))


def _limpar(texto: str, senha: str) -> str:
    if senha:
        texto = texto.replace(senha, "***")
    return " ".join(texto.split())[:200]


def enviar(c: dict, para: str, assunto: str, corpo: str, responder_para: str | None = None, timeout: int = 20) -> None:
    if not ENDERECO.match(para or ""):
        raise EnvioErro("O endereço do destinatário não é válido")
    if "\n" in assunto or "\r" in assunto:
        raise EnvioErro("O assunto não pode ter quebra de linha")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = c["remetente"], para, assunto
    if responder_para and ENDERECO.match(responder_para):
        msg["Reply-To"] = responder_para
    # quoted-printable (ASCII puro na rede): o padrão do Python mandaria UTF-8 cru em 8 bits, e servidor sem 8BITMIME corrompe a acentuação
    msg.set_content(corpo, charset="utf-8", cte="quoted-printable")
    try:
        if c["seguranca"] == "ssl":
            s = smtplib.SMTP_SSL(c["host"], c["porta"], timeout=timeout, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(c["host"], c["porta"], timeout=timeout)
        with s:
            s.ehlo()
            if c["seguranca"] == "starttls":
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
            if c["usuario"] and c["senha"]:
                s.login(c["usuario"], c["senha"])
            s.send_message(msg)          # só tem To: um destinatário, sem Cc nem Bcc
    except (smtplib.SMTPException, OSError) as e:
        raise EnvioErro(_limpar(f"{type(e).__name__}: {e}", c["senha"])) from e
