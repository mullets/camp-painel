"""Quem aceitou receber e-mails da CAMP, para exportar ao Sender.net (03/11/2026).

Rafael: "mostrar no painel quem aceitou receber e-mails da CAMP, para exportar a lista para o Sender.net".

Fontes (montadas na hora, nada copiado):
- inscrições em curso e "Avise-me" com `emkt` = 1 (marcou "Quero receber e-mails da CAMP" no site);
- cadastros de download (Fluent Forms, tabela uso_download) com o aceite `consentimento_base` (a caixa do cadastro de download,
  plugin do site 1.23.3), sem os anonimizados e apagados (LGPD).
Uma linha por e-mail: o nome e a instituição mais recentes, as origens juntas, a data do aceite mais recente. Quem está em
`contato_descadastro` (pediu para sair, ou a equipe tirou) não entra na lista nem no CSV.
CSV no formato que o importador do Sender.net reconhece: email, firstname, lastname (+ origem, instituicao, consentiu_em).
"""
from __future__ import annotations

import csv
import io
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import auth
from .db import connect
from .email_envio import ENDERECO

router = APIRouter(prefix="/api", tags=["contatos_emkt"])
_SIM = {"on", "yes", "sim", "1", "true", "accepted", "aceito"}


def _aceitou(valor) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, list):
        return any(_aceitou(v) for v in valor)
    return str(valor or "").strip().lower() in _SIM


def _resp(txt) -> dict:
    try:
        d = json.loads(txt or "{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def listar(con, incluir_fora: bool = False) -> list[dict]:
    pessoas: dict[str, dict] = {}

    def juntar(email, nome, inst, origem, quando):
        e = (email or "").strip().lower()
        if not ENDERECO.match(e):
            return
        p = pessoas.setdefault(e, {"email": e, "nome": "", "instituicao": "", "origens": [], "consentiu_em": ""})
        q = str(quando or "")
        if q >= p["consentiu_em"]:
            p["consentiu_em"] = q
            p["nome"] = (nome or "").strip() or p["nome"]
            p["instituicao"] = (inst or "").strip() or p["instituicao"]
        else:
            p["nome"] = p["nome"] or (nome or "").strip()
            p["instituicao"] = p["instituicao"] or (inst or "").strip()
        if origem not in p["origens"]:
            p["origens"].append(origem)

    try:
        for r in con.execute("SELECT email, nome, tipo, curso, COALESCE(criado_no_site, importado_em) q FROM inscricao WHERE emkt=1"):
            juntar(r["email"], r["nome"], "", ("avise-me: " if r["tipo"] == "interesse" else "inscrição: ") + (r["curso"] or "curso"), r["q"])
    except Exception:  # noqa: BLE001 - banco sem a tabela de inscrições
        pass
    for r in con.execute("""SELECT email, nome, instituicao, recebida_em, resposta_json FROM uso_download
                             WHERE anonimizada=0 AND apagada=0 AND email IS NOT NULL AND resposta_json LIKE '%consentimento_base%'"""):
        if _aceitou(_resp(r["resposta_json"]).get("consentimento_base")):
            juntar(r["email"], r["nome"], r["instituicao"], "cadastro de download", r["recebida_em"])
    fora = {r[0]: {"quando": r[1], "motivo": r[2]} for r in con.execute("SELECT email, quando, motivo FROM contato_descadastro")}
    out = []
    for p in sorted(pessoas.values(), key=lambda x: x["consentiu_em"], reverse=True):
        if p["email"] in fora:
            if not incluir_fora:
                continue
            p["fora"] = fora[p["email"]]
        out.append(p)
    return out


def _nome(n: str) -> tuple[str, str]:
    partes = (n or "").split()
    return (partes[0], " ".join(partes[1:])) if partes else ("", "")


def csv_sender(itens: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "firstname", "lastname", "origem", "instituicao", "consentiu_em"])
    for p in itens:
        pn, sn = _nome(p["nome"])
        w.writerow([p["email"], pn, sn, "; ".join(p["origens"]), p["instituicao"], (p["consentiu_em"] or "")[:10]])
    return buf.getvalue()


@router.get("/contatos-email")
def ver(u: dict = Depends(auth.exige("admin"))) -> dict:
    """A lista (quem aceitou e não saiu) e quem saiu, com as contagens por origem."""
    con = connect()
    try:
        todos = listar(con, incluir_fora=True)
    finally:
        con.close()
    lista = [p for p in todos if "fora" not in p]
    por = {}
    for p in lista:
        for o in p["origens"]:
            chave = o.split(":")[0]
            por[chave] = por.get(chave, 0) + 1
    return {"total": len(lista), "por_origem": por, "itens": lista, "fora": [p for p in todos if "fora" in p]}


@router.get("/contatos-email.csv")
def baixar_csv(u: dict = Depends(auth.exige("admin"))):
    con = connect()
    try:
        itens = listar(con)
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('contatos_email','lista','exportada',?,?)",
                    (u["email"], json.dumps({"pessoas": len(itens)})))
        con.commit()
    finally:
        con.close()
    return Response(content="﻿" + csv_sender(itens), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="camp-contatos-email-sender.csv"', "Cache-Control": "no-store"})


class Pessoa(BaseModel):
    email: str
    motivo: str | None = None


@router.post("/contatos-email/tirar")
def tirar(d: Pessoa, u: dict = Depends(auth.exige("admin"))) -> dict:
    """A pessoa sai da lista (pediu para não receber mais, ou a equipe decidiu). Não volta sozinha num cadastro novo."""
    e = d.email.strip().lower()
    if not ENDERECO.match(e):
        raise HTTPException(400, "E-mail inválido")
    con = connect()
    try:
        con.execute("INSERT OR REPLACE INTO contato_descadastro (email, motivo, por) VALUES (?,?,?)",
                    (e, re.sub(r"\s+", " ", d.motivo or "").strip()[:200] or None, u["email"]))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('contatos_email',?,'tirado',?,?)",
                    (e, u["email"], json.dumps({"motivo": d.motivo}, ensure_ascii=False)))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


@router.post("/contatos-email/devolver")
def devolver(d: Pessoa, u: dict = Depends(auth.exige("admin"))) -> dict:
    e = d.email.strip().lower()
    con = connect()
    try:
        n = con.execute("DELETE FROM contato_descadastro WHERE email=?", (e,)).rowcount
        if n:
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('contatos_email',?,'devolvido',?,'{}')", (e, u["email"]))
        con.commit()
        return {"ok": True, "devolvido": bool(n)}
    finally:
        con.close()
