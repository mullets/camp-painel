"""Inscrições da Residência em Acervos de Arquitetura (02/11/2026, CAMP: "quero [as inscrições, com o currículo] no meu adm").

Coleta (contrato 1.6, docs/CONTRATO_UNICO.md): GET /wp-json/camp/v1/inscricoes (só leitura) → grava em `inscricao` e baixa o PDF do
currículo (GET /inscricoes/{id}/cv) para a pasta privada inscricoes_cv/ ao lado do banco → COMMIT → POST /inscricoes/confirmar.
Sem confirmação, o site manda de novo na próxima volta; site_id UNIQUE garante que nada duplica. Uma inscrição cujo PDF não veio
(rede, arquivo inválido) NÃO é confirmada: tenta de novo na próxima volta. Site ainda sem a rota (404): silêncio, nada registrado
como falha. Roda junto com a coleta de pedidos (main._coleta_pedidos_site_periodica e "Buscar agora"), separada dela: um erro aqui
nunca atrapalha os pedidos.

Telas: GET /api/inscricoes, GET/PATCH /api/inscricoes/{id}, GET /api/inscricoes/{id}/cv. Dados pessoais: só admin e master.
"""
from __future__ import annotations

import json
import logging
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import auth
from .config import settings
from .db import connect
from .log_tecnico import registrar

router = APIRouter(prefix="/api", tags=["inscricoes"])

SITUACOES = ("nova", "em_analise", "selecionada", "nao_selecionada", "desistiu")
CV_MAX = 5 * 1024 * 1024
LIMITE_LOTE = 100


def pasta_cv() -> Path:
    p = Path(settings.CAMP_DB_PATH).resolve().parent / "inscricoes_cv"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _txt(v, maximo: int) -> str:
    return str(v or "").strip()[:maximo]


def _baixar_cv(wp, site_id: int) -> tuple[str, int] | None:
    """Baixa o PDF; devolve (arquivo, tamanho) ou None se não veio um PDF válido."""
    r = wp.h.get(f"/wp-json/camp/v1/inscricoes/{int(site_id)}/cv")
    if r.status_code != 200:
        return None
    dados = r.content or b""
    if not dados.startswith(b"%PDF-") or len(dados) > CV_MAX:
        return None
    nome = f"{int(site_id)}-{secrets.token_hex(12)}.pdf"
    destino = pasta_cv() / nome
    destino.write_bytes(dados)
    try:
        destino.chmod(0o640)
    except OSError:
        pass
    return nome, len(dados)


def coletar(con=None, wp=None) -> dict:
    """Uma volta. Nunca levanta. Só confirma no site o que já está no banco (e com o PDF, quando há currículo)."""
    fechar = con is None
    con = con or connect()
    out = {"lidas": 0, "novas": 0, "confirmadas": 0, "sem_rota": False, "erro": None}
    try:
        wp = wp or __import__("app.wp", fromlist=["WP"]).WP()
        r = wp.h.get("/wp-json/camp/v1/inscricoes", params={"limite": LIMITE_LOTE})
        if r.status_code == 404:
            out["sem_rota"] = True          # site ainda na versão antiga do contrato: nada a fazer
            return out
        if r.status_code >= 400:
            raise RuntimeError(f"O site respondeu {r.status_code} ao buscar inscrições")
        dados = r.json()
        if isinstance(dados, dict):
            dados = dados.get("itens")
        if not isinstance(dados, list):
            raise RuntimeError("O site devolveu formato inválido para as inscrições")
        prontos: list[int] = []
        for d in dados:
            if not isinstance(d, dict) or type(d.get("id")) is not int or d["id"] <= 0:
                continue
            out["lidas"] += 1
            sid = d["id"]
            ja = con.execute("SELECT cv_arquivo FROM inscricao WHERE site_id=?", (sid,)).fetchone()
            cv_info = d.get("cv") if isinstance(d.get("cv"), dict) else None
            arquivo = tamanho = None
            if cv_info and not (ja and ja["cv_arquivo"]):
                try:
                    b = _baixar_cv(wp, sid)
                except Exception:  # noqa: BLE001
                    b = None
                if not b:
                    registrar(logging.WARNING, "inscricoes_cv", "Currículo da inscrição não veio; tenta de novo na próxima busca", inscricao=sid)
                    if ja:
                        continue
                    arquivo = None
                else:
                    arquivo, tamanho = b
            if not ja:
                con.execute(
                    """INSERT OR IGNORE INTO inscricao (site_id, curso, turma, nome, email, telefone, cidade, formacao, motivacao, disponivel,
                           portfolio, soube, emkt, cv_arquivo, cv_nome, cv_tamanho, texto, criado_no_site)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (sid, _txt(d.get("curso"), 160), _txt(d.get("turma"), 80), _txt(d.get("nome"), 120) or "(sem nome)", _txt(d.get("email"), 200) or None,
                     _txt(d.get("telefone"), 40) or None, _txt(d.get("cidade"), 80) or None, _txt(d.get("formacao"), 160) or None,
                     _txt(d.get("motivacao"), 2500) or None, d.get("disponivel") if d.get("disponivel") in ("sim", "parte") else "",
                     _txt(d.get("portfolio"), 300) or None, _txt(d.get("soube"), 120) or None, 1 if d.get("emkt") is True else 0,
                     arquivo, _txt((cv_info or {}).get("nome"), 120) or None if arquivo else None, tamanho, _txt(d.get("texto"), 8000) or None,
                     _txt(d.get("criado_em"), 40) or None))
                out["novas"] += 1
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('inscricao',?,'criada','site',?)",
                            (str(sid), json.dumps({"curso": _txt(d.get("curso"), 160), "com_cv": bool(arquivo)}, ensure_ascii=False)))
            elif arquivo:
                con.execute("UPDATE inscricao SET cv_arquivo=?, cv_nome=?, cv_tamanho=? WHERE site_id=?",
                            (arquivo, _txt(cv_info.get("nome"), 120) or None, tamanho, sid))
            if cv_info and not arquivo and not (ja and ja["cv_arquivo"]):
                continue                     # sem o PDF: não confirma, o site manda de novo
            prontos.append(sid)
        con.commit()                         # confirma no site só depois daqui
        if prontos:
            rc = wp.h.post("/wp-json/camp/v1/inscricoes/confirmar", json={"ids": prontos})
            if rc.status_code >= 400:
                raise RuntimeError(f"Não foi possível confirmar as inscrições no site (HTTP {rc.status_code}); serão reenviadas")
            res = rc.json() if hasattr(rc, "json") else {}
            aceitos = set((res or {}).get("confirmados") or []) | set((res or {}).get("ja_confirmados") or [])
            out["confirmadas"] = len(aceitos & set(prontos))
            if aceitos != set(prontos):
                registrar(logging.WARNING, "inscricoes_coleta", "Confirmação parcial das inscrições no site; o resto volta na próxima busca",
                          pedidas=len(prontos), aceitas=len(aceitos & set(prontos)))
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:200]
        registrar(logging.WARNING, "inscricoes_coleta", "Busca de inscrições no site com problema", erro=out["erro"][:160])
    finally:
        if not out["sem_rota"]:
            try:
                con.execute("INSERT INTO inscricao_coleta (lidas, novas, confirmadas, erro) VALUES (?,?,?,?)",
                            (out["lidas"], out["novas"], out["confirmadas"], out["erro"]))
                con.commit()
            except Exception:  # noqa: BLE001
                pass
        if fechar:
            con.close()
    return out


def apagar_por_email(con, email: str) -> int:
    """LGPD (apagar pessoa): apaga as inscrições deste e-mail e os PDFs. Não faz commit (quem chama faz)."""
    em = (email or "").strip().lower()
    if not em:
        return 0
    rows = con.execute("SELECT id, cv_arquivo FROM inscricao WHERE lower(email)=?", (em,)).fetchall()
    for r in rows:
        if r["cv_arquivo"]:
            try:
                (pasta_cv() / Path(r["cv_arquivo"]).name).unlink(missing_ok=True)
            except OSError:
                pass
    if rows:
        con.execute(f"DELETE FROM inscricao WHERE id IN ({','.join('?' * len(rows))})", [r["id"] for r in rows])
    return len(rows)


# ---------------- telas ----------------
def _linha(r) -> dict:
    d = dict(r)
    d["tem_cv"] = bool(d.pop("cv_arquivo", None))
    d["emkt"] = bool(d.get("emkt"))
    return d


@router.get("/inscricoes")
def listar(situacao: str | None = None, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        resumo = {s: 0 for s in SITUACOES}
        for r in con.execute("SELECT situacao, COUNT(*) n FROM inscricao GROUP BY situacao"):
            resumo[r["situacao"]] = r["n"]
        if situacao and situacao != "todas":
            if situacao not in SITUACOES:
                raise HTTPException(400, "Situação inválida")
            rows = con.execute("SELECT * FROM inscricao WHERE situacao=? ORDER BY COALESCE(criado_no_site, importado_em) DESC, id DESC", (situacao,)).fetchall()
        else:
            rows = con.execute("SELECT * FROM inscricao ORDER BY COALESCE(criado_no_site, importado_em) DESC, id DESC").fetchall()
        ult = con.execute("SELECT quando, lidas, novas, confirmadas, erro FROM inscricao_coleta ORDER BY id DESC LIMIT 1").fetchone()
        return {"itens": [_linha(r) for r in rows], "resumo": resumo, "ultima_busca": dict(ult) if ult else None}
    finally:
        con.close()


def _uma(con, iid: int):
    r = con.execute("SELECT * FROM inscricao WHERE id=?", (iid,)).fetchone()
    if not r:
        raise HTTPException(404, "Inscrição não existe")
    return r


@router.get("/inscricoes/{iid}")
def detalhe(iid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return _linha(_uma(con, iid))
    finally:
        con.close()


class EdicaoInscricao(BaseModel):
    situacao: str | None = None
    nota: str | None = None


@router.patch("/inscricoes/{iid}")
def editar(iid: int, d: EdicaoInscricao, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = _uma(con, iid)
        campos, vals, mud = [], [], {}
        if d.situacao is not None:
            if d.situacao not in SITUACOES:
                raise HTTPException(400, "Situação inválida")
            campos.append("situacao=?"); vals.append(d.situacao); mud["situacao"] = [r["situacao"], d.situacao]
        if d.nota is not None:
            campos.append("nota=?"); vals.append(d.nota.strip()[:2000] or None); mud["nota"] = True
        if campos:
            campos.append("atualizado_em=datetime('now')")
            con.execute(f"UPDATE inscricao SET {', '.join(campos)} WHERE id=?", (*vals, iid))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('inscricao',?,'editada',?,?)",
                        (str(r["site_id"]), u["email"], json.dumps(mud, ensure_ascii=False)))
            con.commit()
        return {"ok": True}
    finally:
        con.close()


@router.get("/inscricoes/{iid}/cv")
def baixar_cv(iid: int, u: dict = Depends(auth.exige("admin"))):
    con = connect()
    try:
        r = _uma(con, iid)
    finally:
        con.close()
    if not r["cv_arquivo"]:
        raise HTTPException(404, "Esta inscrição não tem currículo em PDF")
    f = pasta_cv() / Path(r["cv_arquivo"]).name
    if not f.is_file():
        raise HTTPException(404, "O arquivo do currículo não está no painel")
    nome = "curriculo-" + "".join(c if c.isalnum() else "-" for c in (r["nome"] or str(iid)).lower()).strip("-")[:60] + ".pdf"
    return FileResponse(str(f), media_type="application/pdf", filename=nome, headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@router.post("/inscricoes/buscar")
def buscar_agora(u: dict = Depends(auth.exige("admin"))) -> dict:
    return coletar()
