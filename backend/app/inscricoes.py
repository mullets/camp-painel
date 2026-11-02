"""Inscrições em cursos e "Avise-me da próxima turma" (02/11/2026, CAMP: "quero [as inscrições, com o currículo] no meu adm";
"o avise-me também tem que ir para o painel, para quando tiver novos cursos avisar esse povo").

Cada registro tem `tipo` (inscricao | interesse) e `curso_id` (slug estável do curso; site antigo sem os campos = inscricao e "").

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
SITUACOES_INTERESSE = ("aguardando", "avisado")
TIPOS = ("inscricao", "interesse")
CV_MAX = 5 * 1024 * 1024
LIMITE_LOTE = 100
SEM_CURSO = "(curso não informado)"


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
                tipo = "interesse" if d.get("tipo") == "interesse" else "inscricao"
                con.execute(
                    """INSERT OR IGNORE INTO inscricao (site_id, tipo, curso_id, situacao, curso, turma, nome, email, telefone, cidade, formacao, motivacao, disponivel,
                           portfolio, soube, emkt, cv_arquivo, cv_nome, cv_tamanho, texto, criado_no_site)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (sid, tipo, _txt(d.get("curso_id"), 80).lower(), "aguardando" if tipo == "interesse" else "nova", _txt(d.get("curso"), 160), _txt(d.get("turma"), 80), _txt(d.get("nome"), 120) or "(sem nome)", _txt(d.get("email"), 200) or None,
                     _txt(d.get("telefone"), 40) or None, _txt(d.get("cidade"), 80) or None, _txt(d.get("formacao"), 160) or None,
                     _txt(d.get("motivacao"), 2500) or None, d.get("disponivel") if d.get("disponivel") in ("sim", "parte") else "",
                     _txt(d.get("portfolio"), 300) or None, _txt(d.get("soube"), 120) or None, 1 if d.get("emkt") is True else 0,
                     arquivo, _txt((cv_info or {}).get("nome"), 120) or None if arquivo else None, tamanho, _txt(d.get("texto"), 8000) or None,
                     _txt(d.get("criado_em"), 40) or None))
                out["novas"] += 1
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('inscricao',?,'criada','site',?)",
                            (str(sid), json.dumps({"tipo": tipo, "curso": _txt(d.get("curso"), 160), "com_cv": bool(arquivo)}, ensure_ascii=False)))
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
    d["curso"] = d.get("curso") or SEM_CURSO
    d["chave_curso"] = d.get("curso_id") or "nome:" + d["curso"]
    return d


def _filtros(tipo: str | None, curso_id: str | None, curso: str | None) -> tuple[list[str], list]:
    """tipo (padrão inscricao) + curso: `curso_id` é o slug, ou "nome:<curso>" para curso sem slug; `curso` filtra pelo nome legível."""
    t = tipo or "inscricao"
    if t not in TIPOS:
        raise HTTPException(400, "Tipo inválido")
    onde, vals = ["tipo=?"], [t]
    if curso_id and curso_id != "todos":
        if curso_id.startswith("nome:"):
            onde.append("curso_id='' AND COALESCE(NULLIF(curso,''), ?)=?"); vals += [SEM_CURSO, curso_id[5:]]
        else:
            onde.append("curso_id=?"); vals.append(curso_id)
    if curso and curso != "todos":
        onde.append("COALESCE(NULLIF(curso,''), ?)=?"); vals += [SEM_CURSO, curso]
    return onde, vals


@router.get("/inscricoes")
def listar(tipo: str | None = None, situacao: str | None = None, curso_id: str | None = None, curso: str | None = None,
           u: dict = Depends(auth.exige("admin"))) -> dict:
    """Filtros combináveis: tipo (inscricao | interesse), curso e situação. `resumo` conta por situação dentro do tipo e do curso;
    `cursos` lista os cursos daquele tipo, com a chave do filtro, o nome e o total (e, no interesse, quantos aguardam aviso);
    `totais` conta cada tipo."""
    t = tipo or "inscricao"
    sits = SITUACOES_INTERESSE if t == "interesse" else SITUACOES
    con = connect()
    try:
        onde, vals = _filtros(t, curso_id, curso)
        w = " AND ".join(onde)
        resumo = {s: 0 for s in sits}
        for r in con.execute(f"SELECT situacao, COUNT(*) n FROM inscricao WHERE {w} GROUP BY situacao", vals):
            resumo[r["situacao"]] = r["n"]
        cursos = [{"chave": r["curso_id"] or "nome:" + r["c"], "curso_id": r["curso_id"], "curso": r["c"], "n": r["n"], "aguardando": r["ag"]}
                  for r in con.execute("""SELECT curso_id, COALESCE(NULLIF(MAX(curso),''), ?) c, COUNT(*) n, SUM(situacao='aguardando') ag FROM inscricao
                                          WHERE tipo=? GROUP BY curso_id, CASE WHEN curso_id='' THEN COALESCE(NULLIF(curso,''), ?) ELSE '' END ORDER BY c""", (SEM_CURSO, t, SEM_CURSO))]
        totais = {k: 0 for k in TIPOS}
        for r in con.execute("SELECT tipo, COUNT(*) n, SUM(situacao IN ('nova','aguardando')) novos FROM inscricao GROUP BY tipo"):
            if r["tipo"] in totais:
                totais[r["tipo"]] = r["n"]
                totais[r["tipo"] + "_novos"] = r["novos"]
        if situacao and situacao not in ("todas", "todos"):
            if situacao not in sits:
                raise HTTPException(400, "Situação inválida")
            onde.append("situacao=?"); vals.append(situacao)
        rows = con.execute(f"SELECT * FROM inscricao WHERE {' AND '.join(onde)} ORDER BY COALESCE(criado_no_site, importado_em) DESC, id DESC", vals).fetchall()
        ult = con.execute("SELECT quando, lidas, novas, confirmadas, erro FROM inscricao_coleta ORDER BY id DESC LIMIT 1").fetchone()
        return {"itens": [_linha(r) for r in rows], "resumo": resumo, "cursos": cursos, "totais": totais, "ultima_busca": dict(ult) if ult else None}
    finally:
        con.close()


class Avisados(BaseModel):
    ids: list[int]


@router.post("/inscricoes/avisados")
def marcar_avisados(d: Avisados, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Avise-me: marca como avisadas (avisado_em) as pessoas da lista. Só vale para tipo interesse."""
    ids = sorted({int(i) for i in d.ids if int(i) > 0})[:2000]
    if not ids:
        return {"ok": True, "marcados": 0}
    con = connect()
    try:
        n = con.execute(f"UPDATE inscricao SET situacao='avisado', avisado_em=datetime('now'), atualizado_em=datetime('now') WHERE tipo='interesse' AND situacao<>'avisado' AND id IN ({','.join('?' * len(ids))})", ids).rowcount
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('inscricao','interesse','avisados',?,?)",
                    (u["email"], json.dumps({"marcados": n}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "marcados": n}
    finally:
        con.close()


@router.get("/inscricoes/interesse.csv")
def interesse_csv(curso_id: str | None = None, todos: int = 0, u: dict = Depends(auth.exige("admin"))):
    """CSV (nome, email, curso, data) do Avise-me do curso filtrado; por padrão só quem ainda não foi avisado. Sem log dos e-mails."""
    import csv
    import io
    from fastapi.responses import Response
    con = connect()
    try:
        onde, vals = _filtros("interesse", curso_id, None)
        if not todos:
            onde.append("situacao='aguardando'")
        rows = con.execute(f"SELECT nome, email, curso, turma, COALESCE(criado_no_site, importado_em) quando FROM inscricao WHERE {' AND '.join(onde)} ORDER BY quando", vals).fetchall()
    finally:
        con.close()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["nome", "email", "curso", "data"])
    for r in rows:
        w.writerow([r["nome"], r["email"] or "", r["curso"] or SEM_CURSO, (r["quando"] or "")[:10]])
    nome = "avise-me-" + ("".join(ch if ch.isalnum() else "-" for ch in (curso_id or "todos").replace("nome:", "")).strip("-")[:50] or "todos") + ".csv"
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


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
    avisar: bool = True                  # 02/11: mudou para em análise/selecionada/não selecionada → e-mail à pessoa (dá para desmarcar)
    mensagem: str | None = None          # recado opcional no e-mail do aviso


@router.get("/inscricoes/{iid}/aviso")
def previa_aviso(iid: int, situacao: str, u: dict = Depends(auth.exige("admin"))) -> dict:
    """O e-mail que a pessoa recebe se a situação mudar para `situacao` (para a tela mostrar antes de salvar)."""
    from . import inscricoes_aviso
    con = connect()
    try:
        return inscricoes_aviso.previa(con, _uma(con, iid), situacao)
    finally:
        con.close()


@router.patch("/inscricoes/{iid}")
def editar(iid: int, d: EdicaoInscricao, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = _uma(con, iid)
        campos, vals, mud = [], [], {}
        if d.situacao is not None:
            if d.situacao not in (SITUACOES_INTERESSE if r["tipo"] == "interesse" else SITUACOES):
                raise HTTPException(400, "Situação inválida")
            campos.append("situacao=?"); vals.append(d.situacao); mud["situacao"] = [r["situacao"], d.situacao]
            if r["tipo"] == "interesse":
                campos.append("avisado_em=" + ("datetime('now')" if d.situacao == "avisado" else "NULL"))
        if d.nota is not None:
            campos.append("nota=?"); vals.append(d.nota.strip()[:2000] or None); mud["nota"] = True
        if campos:
            campos.append("atualizado_em=datetime('now')")
            con.execute(f"UPDATE inscricao SET {', '.join(campos)} WHERE id=?", (*vals, iid))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('inscricao',?,'editada',?,?)",
                        (str(r["site_id"]), u["email"], json.dumps(mud, ensure_ascii=False)))
            con.commit()
        aviso = None
        if d.situacao is not None and d.situacao != r["situacao"] and r["tipo"] == "inscricao" and d.avisar:
            from . import inscricoes_aviso
            if d.situacao in inscricoes_aviso.AVISA:
                aviso = inscricoes_aviso.enviar(con, _uma(con, iid), d.situacao, d.mensagem or "", u)
        return {"ok": True, "aviso": aviso}
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
