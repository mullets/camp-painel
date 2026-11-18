"""Quem aceitou receber e-mails da CAMP (03/11/2026; com o Sender desde 18/11/2026).

Rafael (03/11): "mostrar no painel quem aceitou receber e-mails da CAMP, para exportar a lista para o Sender.net".
Rafael (18/11): "quem aceitou receber e-mails da CAMP… seria bom saber e conseguir filtrar. E cadastrar esses no mailing: pelo site,
aceitou → direto no Sender". O SITE inscreve sozinho no grupo do Sender (plugin 1.25.15, contrato 1.15); o painel busca a lista do
site (GET /wp-json/camp/v1/painel/emkt?desde=, tabela emkt_site) a cada emkt.coleta_min minutos ou em "Sincronizar agora".

Fontes (uma linha por e-mail; só quem marcou a caixa OPCIONAL de e-mails — LGPD: consentimento livre):
- a lista do site (emkt_site): todos os formulários do site com a caixa marcada, com a situação no Sender;
- inscrições em curso e "Avise-me" com `emkt` = 1; Amigos da CAMP e adoções com `emkt` = 1;
- cadastros de download (tabela uso_download) com a caixa `consentimento_emkt` marcada (a caixa obrigatória `consentimento_base`
  é da base de pesquisadores, NÃO é aceite de e-mails: deixou de contar em 18/11), sem os anonimizados e apagados.
Quem está em `contato_descadastro` (pediu para sair, ou a equipe tirou) não entra na lista nem no CSV.
Situação no Sender (por e-mail): cancelou (algum registro cancelou) > inscrito > erro > pendente; "sem" = o site ainda não contou.
CSV no formato que o importador do Sender.net reconhece: email, firstname, lastname (+ origem, instituicao, consentiu_em, situacao_sender).
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import auth
from .config import settings
from .db import connect
from .email_envio import ENDERECO
from .log_tecnico import registrar

router = APIRouter(prefix="/api", tags=["contatos_emkt"])
_SIM = {"on", "yes", "sim", "1", "true", "accepted", "aceito"}
ROTA = "/wp-json/camp/v1/painel/emkt"
SITUACOES = ("inscrito", "pendente", "erro", "cancelou")
ORIGENS = {"inscricao": "Inscrição em curso", "interesse": "Avise-me da próxima turma", "download": "Cadastro de download",
           "apoio": "Amigos e adoções", "pedido": "Pedido do acervo", "agendamento": "Visita ou biblioteca", "contato": "Contato",
           "equipamento": "Doação de equipamento", "outro": "Formulário do site"}


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


def _tem_tabela(con, nome: str) -> bool:
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)).fetchone())


def listar(con, incluir_fora: bool = False) -> list[dict]:
    pessoas: dict[str, dict] = {}

    def juntar(email, nome, inst, origem, quando, versao=""):
        e = (email or "").strip().lower()
        if not ENDERECO.match(e):
            return None
        p = pessoas.setdefault(e, {"email": e, "nome": "", "instituicao": "", "origens": [], "origem_chaves": [], "consentiu_em": "",
                                   "versao": "", "situacoes": []})
        q = str(quando or "")
        if q >= p["consentiu_em"]:
            p["consentiu_em"] = q
            p["nome"] = (nome or "").strip() or p["nome"]
            p["instituicao"] = (inst or "").strip() or p["instituicao"]
            p["versao"] = versao or p["versao"]
        else:
            p["nome"] = p["nome"] or (nome or "").strip()
            p["instituicao"] = p["instituicao"] or (inst or "").strip()
            p["versao"] = p["versao"] or versao or ""
        chave = origem if origem in ORIGENS else "outro"
        if chave not in p["origem_chaves"]:
            p["origem_chaves"].append(chave)
            p["origens"].append(ORIGENS[chave])
        return p

    if _tem_tabela(con, "emkt_site"):
        for r in con.execute("SELECT * FROM emkt_site"):
            p = juntar(r["email"], r["nome"], "", r["origem"], r["aceite_em"], r["versao"] or "")
            if p is not None:
                p["situacoes"].append((r["situacao"], r["erro"] or "", r["sender_em"] or ""))
    try:
        for r in con.execute("SELECT email, nome, tipo, curso, COALESCE(criado_no_site, importado_em) q FROM inscricao WHERE emkt=1"):
            juntar(r["email"], r["nome"], "", "interesse" if r["tipo"] == "interesse" else "inscricao", r["q"])
    except Exception:  # noqa: BLE001 - banco sem a tabela de inscrições
        pass
    try:
        for r in con.execute("SELECT email, nome, empresa, COALESCE(criado_no_site, importado_em) q FROM amigo WHERE emkt=1 AND anonimizado=0 AND email IS NOT NULL"):
            juntar(r["email"], r["nome"], r["empresa"], "apoio", r["q"])
    except Exception:  # noqa: BLE001 - banco sem a tabela dos Amigos
        pass
    for r in con.execute("""SELECT email, nome, instituicao, recebida_em, resposta_json FROM uso_download
                             WHERE anonimizada=0 AND apagada=0 AND email IS NOT NULL AND resposta_json LIKE '%consentimento_emkt%'"""):
        if _aceitou(_resp(r["resposta_json"]).get("consentimento_emkt")):
            juntar(r["email"], r["nome"], r["instituicao"], "download", r["recebida_em"])
    fora = {r[0]: {"quando": r[1], "motivo": r[2]} for r in con.execute("SELECT email, quando, motivo FROM contato_descadastro")}
    out = []
    for p in sorted(pessoas.values(), key=lambda x: x["consentiu_em"], reverse=True):
        sits = p.pop("situacoes")
        nomes = [s_[0] for s_ in sits]
        p["situacao_sender"] = next((s_ for s_ in ("cancelou", "inscrito", "erro", "pendente") if s_ in nomes), "sem")
        p["erro_sender"] = next((s_[1] for s_ in sits if s_[0] == p["situacao_sender"] and s_[1]), "")
        if p["email"] in fora:
            if not incluir_fora:
                continue
            p["fora"] = fora[p["email"]]
        out.append(p)
    return out


def filtrar(itens: list[dict], origem: str | None = None, de: str | None = None, ate: str | None = None,
            situacao: str | None = None, q: str | None = None) -> list[dict]:
    """Filtros da tela (os mesmos no CSV): origem, período do aceite (AAAA-MM-DD), situação no Sender e busca por nome/e-mail."""
    if situacao and situacao not in (*SITUACOES, "sem", "todas"):
        raise HTTPException(400, "Situação inválida")
    if origem and origem not in (*ORIGENS, "todas"):
        raise HTTPException(400, "Origem inválida")
    for d_ in (de, ate):
        if d_ and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d_):
            raise HTTPException(400, "Data inválida (use AAAA-MM-DD)")
    t = (q or "").strip().lower()
    out = []
    for p in itens:
        dia = (p["consentiu_em"] or "")[:10]
        if origem and origem != "todas" and origem not in p["origem_chaves"]:
            continue
        if situacao and situacao != "todas" and p["situacao_sender"] != situacao:
            continue
        if de and (not dia or dia < de):
            continue
        if ate and (not dia or dia > ate):
            continue
        if t and t not in p["email"] and t not in (p["nome"] or "").lower():
            continue
        out.append(p)
    return out


def aceita(con, email: str | None) -> str:
    """Para outras listas do painel (Amigos): 'sim' (aceita e está na lista), 'cancelou' ou 'nao'."""
    e = (email or "").strip().lower()
    if not e:
        return "nao"
    return mapa_aceite(con).get(e, "nao")


def mapa_aceite(con) -> dict[str, str]:
    m = {}
    for p in listar(con, incluir_fora=True):
        m[p["email"]] = "cancelou" if ("fora" in p or p["situacao_sender"] == "cancelou") else "sim"
    return m


# ---------------------------------------------------------------- busca no site (contrato 1.15)
def _estado(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM emkt_estado WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _estado_set(con, chave: str, valor: str) -> None:
    con.execute("INSERT INTO emkt_estado (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, valor))


def coleta_min(con) -> int:
    r = con.execute("SELECT valor FROM configuracao WHERE chave='emkt.coleta_min'").fetchone()
    v = str((r[0] if r else "") or "60").strip()
    return max(0, min(1440, int(v))) if v.isdigit() else 60


def _txt(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def _wp():
    return __import__("app.wp", fromlist=["WP"]).WP()


def sincronizar(con=None, wp=None, tudo: bool = False) -> dict:
    """Uma busca no site (GET /painel/emkt?desde=). Nunca levanta; site antigo (404) = sem_rota, nada muda."""
    fechar = con is None
    con = con or connect()
    out = {"lidos": 0, "novos": 0, "sem_rota": False, "erro": None}
    try:
        wp = wp or _wp()
        desde = "" if tudo else _estado(con, "desde")
        r = wp.h.get(ROTA, params={"desde": desde} if desde else None)
        if r.status_code == 404:
            out["sem_rota"] = True
            return out
        if r.status_code >= 400:
            raise RuntimeError(f"O site respondeu {r.status_code} ao buscar a lista de e-mails")
        d = r.json()
        if not isinstance(d, dict) or not isinstance(d.get("itens"), list):
            raise RuntimeError("O site devolveu formato inválido para a lista de e-mails")
        for x in d["itens"]:
            if not isinstance(x, dict):
                continue
            sid, em = _txt(x.get("id"), 40), _txt(x.get("email"), 200).lower()
            if not re.fullmatch(r"(post|ff)-\d+", sid) or not ENDERECO.match(em):
                continue
            sit = x.get("situacao") if x.get("situacao") in SITUACOES else "pendente"
            novo = not con.execute("SELECT 1 FROM emkt_site WHERE site_id=?", (sid,)).fetchone()
            con.execute("""INSERT INTO emkt_site (site_id, email, nome, origem, origem_nome, aceite_em, versao, situacao, sender_em, erro, visto_em)
                           VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))
                           ON CONFLICT(site_id) DO UPDATE SET email=excluded.email, nome=excluded.nome, origem=excluded.origem,
                             origem_nome=excluded.origem_nome, aceite_em=excluded.aceite_em, versao=excluded.versao, situacao=excluded.situacao,
                             sender_em=excluded.sender_em, erro=excluded.erro, visto_em=excluded.visto_em""",
                        (sid, em, _txt(x.get("nome"), 160), _txt(x.get("origem"), 30) or "outro", _txt(x.get("origem_nome"), 80),
                         _txt(x.get("aceite_em"), 30), _txt(x.get("versao"), 30), sit, _txt(x.get("sender_em"), 30), _txt(x.get("erro"), 300)))
            out["lidos"] += 1
            out["novos"] += int(novo)
        if d.get("grupo") is not None:
            _estado_set(con, "grupo", _txt(d.get("grupo"), 40))
        try:
            t = datetime.fromisoformat(str(d.get("agora") or "").replace("Z", "+00:00")) - timedelta(minutes=2)
            _estado_set(con, "desde", t.isoformat())
        except ValueError:
            pass
        con.commit()
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:200]
        registrar(logging.WARNING, "emkt_coleta", "Busca da lista de e-mails no site com problema", erro=out["erro"][:160])
    finally:
        try:
            _estado_set(con, "ultima", json.dumps({"quando": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), **out}))
            con.commit()
        except Exception:  # noqa: BLE001
            pass
        if fechar:
            con.close()
    return out


def rodada(force: bool = False) -> dict:
    """A volta do coletor (no ritmo emkt.coleta_min). Sem a senha do site, não faz nada. Nunca levanta."""
    con = connect()
    try:
        m = coleta_min(con)
        if not force:
            if m <= 0:
                return {"desligado": True}
            ult = _estado(con, "ultima_rodada")
            if ult and datetime.now(timezone.utc) - datetime.fromisoformat(ult) < timedelta(minutes=m) - timedelta(seconds=30):
                return {"cedo": True}
        r = con.execute("SELECT valor FROM configuracao WHERE chave='wp.app_password'").fetchone()
        if not ((r[0] if r else "") or settings.WP_APP_PASSWORD):
            return {"sem_site": True}
        _estado_set(con, "ultima_rodada", datetime.now(timezone.utc).isoformat())
        con.commit()
        return sincronizar(con)
    except Exception as e:  # noqa: BLE001
        return {"erro": type(e).__name__}
    finally:
        con.close()


def apagar_por_email(con, email: str) -> int:
    """LGPD (apagar pessoa): a cópia da lista do site some do painel. Não faz commit."""
    em = (email or "").strip().lower()
    if not em or not _tem_tabela(con, "emkt_site"):
        return 0
    return con.execute("DELETE FROM emkt_site WHERE email=?", (em,)).rowcount


def _nome(n: str) -> tuple[str, str]:
    partes = (n or "").split()
    return (partes[0], " ".join(partes[1:])) if partes else ("", "")


def csv_sender(itens: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "firstname", "lastname", "origem", "instituicao", "consentiu_em", "situacao_sender"])
    for p in itens:
        pn, sn = _nome(p["nome"])
        w.writerow([p["email"], pn, sn, "; ".join(p["origens"]), p["instituicao"], (p["consentiu_em"] or "")[:10], p.get("situacao_sender", "")])
    return buf.getvalue()


def _contagem(itens: list[dict], campo: str) -> dict:
    c: dict = {}
    for p in itens:
        for k in (p[campo] if isinstance(p[campo], list) else [p[campo]]):
            c[k] = c.get(k, 0) + 1
    return c


@router.get("/contatos-email")
def ver(origem: str | None = None, de: str | None = None, ate: str | None = None, situacao: str | None = None, q: str | None = None,
        u: dict = Depends(auth.exige("admin"))) -> dict:
    """A lista (quem aceitou e não saiu) com os filtros, as contagens (da lista inteira) e quem saiu."""
    con = connect()
    try:
        todos = listar(con, incluir_fora=True)
        ult = _estado(con, "ultima")
        grupo = _estado(con, "grupo")
        minutos = coleta_min(con)
    finally:
        con.close()
    lista = [p for p in todos if "fora" not in p]
    itens = filtrar(lista, origem, de, ate, situacao, q)
    return {"total": len(lista), "filtrados": len(itens), "por_origem": _contagem(lista, "origem_chaves"),
            "por_situacao": {k: _contagem(lista, "situacao_sender").get(k, 0) for k in (*SITUACOES, "sem")},
            "origens": ORIGENS, "itens": itens, "fora": [p for p in todos if "fora" in p],
            "ultima_busca": json.loads(ult) if ult else None, "grupo": grupo or None, "minutos": minutos}


def _csv_resposta(con, itens: list[dict], u: dict, filtro: dict) -> Response:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('contatos_email','lista','exportada',?,?)",
                (u["email"], json.dumps({"pessoas": len(itens), **{k: v for k, v in filtro.items() if v}}, ensure_ascii=False)))
    con.commit()
    return Response(content="\ufeff" + csv_sender(itens), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="camp-contatos-email-sender.csv"', "Cache-Control": "no-store"})


@router.get("/contatos-email.csv")
def baixar_csv(origem: str | None = None, de: str | None = None, ate: str | None = None, situacao: str | None = None, q: str | None = None,
               u: dict = Depends(auth.exige("admin"))):
    con = connect()
    try:
        filtro = {"origem": origem, "de": de, "ate": ate, "situacao": situacao, "busca": bool(q)}
        return _csv_resposta(con, filtrar(listar(con), origem, de, ate, situacao, q), u, filtro)
    finally:
        con.close()


class Selecao(BaseModel):
    emails: list[str]


@router.post("/contatos-email.csv")
def baixar_csv_selecionados(d: Selecao, u: dict = Depends(auth.exige("admin"))):
    """Só os selecionados na tela (POST: os e-mails não vão na URL nem no log de acesso)."""
    quer = {e.strip().lower() for e in d.emails[:20000]}
    con = connect()
    try:
        return _csv_resposta(con, [p for p in listar(con) if p["email"] in quer], u, {"selecionados": True})
    finally:
        con.close()


@router.post("/contatos-email/sincronizar")
def sincronizar_agora(u: dict = Depends(auth.exige("admin"))) -> dict:
    """"Sincronizar agora": busca no site a lista inteira (quem aceitou e a situação no Sender)."""
    out = sincronizar(tudo=True)
    if out["sem_rota"]:
        raise HTTPException(409, "O site ainda não tem a lista de e-mails: atualize o site (plugin 1.25.15 ou mais novo).")
    if out["erro"]:
        raise HTTPException(502, "Não consegui buscar no site: " + out["erro"])
    return out


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
