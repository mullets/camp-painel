"""E-mails enviados (CAMP-EMAIL, 18/11/2026). Rafael: "temos um painel no admin de e-mails enviados? com log e tudo?"

Uma lista só, de todos os canais, para admin e master (tem dados pessoais: e-mail e nome de quem recebeu):
- o que sai do PAINEL e já fica registrado: e-mail aos Downloads (uso_email, SMTP do painel), Amigos da CAMP (amigo_email, Sender pelo
  site), entrega de material (entrega_link: Sender ou e-mail simples do site), aviso de situação das inscrições (evento), alertas e o
  resumo do dia (alerta_envio, resumo_diario_envio; SMTP do painel, para a equipe);
- o que sai do SITE (pedido recebido, visita, inscrição, Amigos…): buscado pela rota GET /wp-json/camp/v1/painel/emails (contrato 1.14,
  opcional; 404 = site antigo: a tela mostra só o que saiu do painel), de N em N minutos (emails.coleta_min) ou em "Sincronizar agora",
  e guardado em email_site.
Situação de cada e-mail: enviado · falhou (com o motivo) · não saiu pelo Sender (com o motivo; foi o e-mail simples do site) · na fila.
A entrega no Sender (entregue/aberto/clicado) não vem: a API transacional do Sender usada aqui só manda (POST /v2/message/{id}/send) e
devolve o emailId; não há, no que o painel e o site usam, consulta de eventos por mensagem com o mesmo token. A tela mostra o emailId e
"ver no Sender".
LGPD: apagar pessoa limpa o e-mail e o nome destas linhas (apagar_por_email). Nada de e-mail ou nome no log técnico.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from . import auth
from .config import settings
from .db import connect
from .log_tecnico import registrar

router = APIRouter(prefix="/api/emails", tags=["emails"])

FUSO = ZoneInfo("America/Sao_Paulo")
ROTA = "/wp-json/camp/v1/painel/emails"
LIMITE_PAGINA = 200
LIMITE_TELA = 500
REMOVIDO = "(removido)"

CANAIS = {"sender": "Sender", "site": "E-mail simples do site", "smtp": "SMTP do painel"}
ORIGENS = {"formulario": "Formulário do site", "visita": "Visita", "inscricao": "Inscrição", "amigos": "Amigos da CAMP",
           "entrega": "Entrega de material", "downloads": "Downloads (uso do acervo)", "alerta": "Alerta interno", "resumo": "Resumo do dia", "ingressos": "Ingressos"}
SITUACOES = {"enviado": "Enviado", "falhou": "Falhou", "nao_sender": "Não saiu pelo Sender", "na_fila": "Na fila"}
# chave do e-mail => (TR, nome). As do site são as de Camp_AAP_Sender::padroes(); as do painel, as daqui.
MODELOS = {
    "solicitacao_recebida": ("TR04", "Pedido recebido"), "pdf_disponivel": ("TR05", "PDF disponível"),
    "visita_solicitada": ("TR06", "Visita solicitada"), "visita_confirmada": ("TR07", "Visita confirmada"),
    "inscricao_recebida": ("TR08", "Inscrição recebida"), "material_download": ("TR09", "Material para download"),
    "amigo_pre_adesao": ("TR10", "Pré-adesão"), "amigo_adesao": ("TR11", "Adesão: link de pagamento"),
    "amigo_boas_vindas": ("TR12", "Pagamento confirmado: boas-vindas"), "amigo_recusado": ("TR13", "Pagamento recusado"),
    "apoio_recebido": ("TR14", "Proposta de apoio recebida"), "amigo_cobranca": ("TR15", "Cobrança"),
    "amigo_pendente": ("TR16", "Pagamento pendente"), "amigo_lembrete_30": ("TR17", "Lembrete de renovação (faltam mais de 7 dias)"),
    "amigo_lembrete_7": ("TR18", "Lembrete de renovação (faltam 7 dias ou menos)"), "amigo_vencido": ("TR19", "Aviso de vencimento"),
    "amigo_recibo": ("TR20", "Recibo simples"), "amigo_livre": ("TR21", "Texto livre"),
    "inscricao_situacao": ("", "Situação da inscrição"), "uso_livre": ("", "E-mail escrito no painel"),
    "copia_simples": ("", "Cópia simples ao visitante"), "aviso_equipe": ("", "Aviso à equipe"), "aviso_equipe_ingresso": ("", "Ingressos (aviso à equipe)"),
    "alerta": ("", "Alerta crítico ou resolvido"), "pedido_novo": ("", "Aviso de pedido novo"), "resumo": ("", "Resumo do dia"),
}
REGISTRO_ORIGEM = {"camp_solicitacao": "formulario", "camp_contato": "formulario", "camp_agendamento": "visita", "camp_inscricao": "inscricao",
                   "camp_apoio": "amigos", "camp_equip_oferta": "formulario", "camp_ingresso": "ingressos"}
REGISTRO_NOME = {"camp_solicitacao": "pedido do site", "camp_contato": "mensagem pelo contato", "camp_agendamento": "pedido de visita",
                 "camp_inscricao": "inscrição", "camp_apoio": "apoio (Amigos ou adoção)", "camp_equip_oferta": "oferta de equipamento", "camp_ingresso": "ingresso"}
# modelo do Amigo no painel => chave do template no site (o mesmo de amigos.SENDER; linhas antigas da fila não têm modelo_site)
SENDER_AMIGOS = {"boas_vindas": "amigo_boas_vindas", "cobranca": "amigo_cobranca", "cobranca_pendente": "amigo_pendente",
                 "lembrete_renovacao": "amigo_lembrete_30", "aviso_vencido": "amigo_vencido", "recibo": "amigo_recibo", "livre": "amigo_livre"}
ROTULO_INSCRICAO = {"em_analise": "Em análise", "selecionada": "Selecionada", "nao_selecionada": "Não selecionada"}


# ---------------------------------------------------------------- utilidades
def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _estado(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM email_estado WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _estado_set(con, chave: str, valor: str) -> None:
    con.execute("INSERT INTO email_estado (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, valor))


def coleta_min(con) -> int:
    try:
        return max(0, int(_cfg(con, "emails.coleta_min", "15")))
    except ValueError:
        return 15


def _utc(v) -> str:
    """ISO com fuso (do site) ou 'AAAA-MM-DD HH:MM:SS' (sem fuso = UTC) → 'AAAA-MM-DD HH:MM:SS' em UTC. Inválido: ''."""
    s = str(v or "").strip()
    if not s:
        return ""
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if d.tzinfo:
        d = d.astimezone(timezone.utc).replace(tzinfo=None)
    return d.strftime("%Y-%m-%d %H:%M:%S")


def _txt(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def _json(v) -> dict:
    try:
        d = json.loads(v) if v else {}
        return d if isinstance(d, dict) else {}
    except (TypeError, ValueError):
        return {}


def _segundos(a, b) -> float:
    """Segundos entre duas datas 'AAAA-MM-DD HH:MM:SS' (inválida: infinito)."""
    try:
        return (datetime.fromisoformat(str(b)) - datetime.fromisoformat(str(a))).total_seconds()
    except (TypeError, ValueError):
        return float("inf")


def _wp():
    """Cliente do site (os testes trocam por um falso)."""
    return __import__("app.wp", fromlist=["WP"]).WP()


def _tem_site(con) -> bool:
    return bool(_cfg(con, "wp.app_password", settings.WP_APP_PASSWORD))


# ---------------------------------------------------------------- busca no site (site → painel)
def _gravar(con, x: dict) -> int:
    """Grava/atualiza um e-mail vindo do site. Devolve 1 se era novo. A chave é a do site (<registro>:<tipo>)."""
    chave = _txt(x.get("chave"), 120)
    if not chave:
        return 0
    canal = "simples" if str(x.get("canal") or "") == "simples" else "sender"
    sit = str(x.get("situacao") or x.get("status") or "")
    sit = sit if sit in ("enviado", "falhou", "nao_sender") else ("falhou" if sit == "erro" else "enviado")
    vals = (int(x["registro_id"]) if str(x.get("registro_id") or "").isdigit() else None, _txt(x.get("registro"), 40), _txt(x.get("protocolo"), 40),
            _txt(x.get("tipo"), 60), _txt(x.get("template"), 8), _txt(x.get("para"), 200).lower() or None, _txt(x.get("nome"), 200) or None,
            canal, sit, _txt(x.get("motivo"), 500) or None, _txt(x.get("sender_id"), 80) or None,
            int(x["tentativas"]) if str(x.get("tentativas") or "").isdigit() else None, _utc(x.get("em")) or None)
    velho = con.execute("SELECT id, para, nome FROM email_site WHERE chave=?", (chave,)).fetchone()
    if velho:
        if velho["nome"] == REMOVIDO:          # LGPD: apagado no painel, o site não traz o e-mail de volta
            vals = (*vals[:5], None, REMOVIDO, *vals[7:])
        con.execute("""UPDATE email_site SET registro_id=?, registro=?, protocolo=?, tipo=?, template=?, para=?, nome=?, canal=?, situacao=?, motivo=?,
                       sender_id=?, tentativas=?, enviado_em=COALESCE(?, enviado_em), coletado_em=datetime('now') WHERE id=?""", (*vals, velho["id"]))
        return 0
    con.execute("""INSERT INTO email_site (chave, registro_id, registro, protocolo, tipo, template, para, nome, canal, situacao, motivo, sender_id,
                   tentativas, enviado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,COALESCE(?, datetime('now')))""", (chave, *vals))
    return 1


def coletar(con=None, wp=None) -> dict:
    """Uma volta da busca no site. Incremental (desde = começo da volta anterior − 2 min). Nunca levanta."""
    fechar = con is None
    con = con or connect()
    out = {"lidos": 0, "novos": 0, "sem_rota": False, "erro": None}
    try:
        wp = wp or _wp()
        desde = _estado(con, "desde")
        agora = None
        for pagina in range(1, 51):
            params = {"limite": LIMITE_PAGINA, "pagina": pagina}
            if desde:
                params["desde"] = desde
            r = wp.h.get(ROTA, params=params)
            if r.status_code == 404:
                out["sem_rota"] = True              # site sem o contrato 1.14: só o que saiu do painel
                _estado_set(con, "sem_rota", "1")
                con.commit()
                return out
            if r.status_code >= 400:
                raise RuntimeError(f"O site respondeu {r.status_code} ao buscar os e-mails")
            d = r.json()
            if not isinstance(d, dict):
                raise RuntimeError("O site devolveu formato inválido para os e-mails")
            agora = agora or d.get("agora")
            for x in d.get("itens") or []:
                if isinstance(x, dict):
                    out["lidos"] += 1
                    out["novos"] += _gravar(con, x)
            con.commit()
            if not d.get("mais"):
                break
        if agora:
            try:
                t = datetime.fromisoformat(str(agora).replace("Z", "+00:00")) - timedelta(minutes=2)
                _estado_set(con, "desde", t.isoformat())
            except ValueError:
                pass
        _estado_set(con, "sem_rota", "")
        _estado_set(con, "ultimo_erro", "")
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:200]
        _estado_set(con, "ultimo_erro", out["erro"])
        registrar(logging.WARNING, "emails_coleta", "Busca dos e-mails enviados pelo site com problema", erro=out["erro"][:160])
    finally:
        try:
            _estado_set(con, "ultima_busca", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
            _estado_set(con, "ultima_novos", str(out["novos"]))
            con.commit()
        except Exception:  # noqa: BLE001
            pass
        if fechar:
            con.close()
    return out


def rodada(force: bool = False) -> dict:
    """A volta automática (no ritmo de emails.coleta_min; 0 desliga). Sem a senha do site: nada. Nunca levanta."""
    con = connect()
    try:
        m = coleta_min(con)
        if not force:
            if m <= 0:
                return {"desligado": True}
            ult = _estado(con, "ultima_rodada")
            if ult and datetime.now(timezone.utc) - datetime.fromisoformat(ult) < timedelta(minutes=m) - timedelta(seconds=30):
                return {"cedo": True}
        _estado_set(con, "ultima_rodada", datetime.now(timezone.utc).isoformat())
        con.commit()
        if not _tem_site(con):
            return {"sem_site": True}
        return coletar(con)
    except Exception as e:  # noqa: BLE001
        registrar(logging.WARNING, "emails_rodada", "Rodada dos e-mails enviados com problema", erro=type(e).__name__)
        return {"erro": type(e).__name__}
    finally:
        con.close()


# ---------------------------------------------------------------- a lista unificada
def _linha(fonte: str, n, em: str, para, nome, assunto: str, modelo: str, canal: str, origem: str, situacao: str, motivo=None, *,
           sender_id=None, protocolo=None, link: str = "", ligado: str = "", detalhe: dict | None = None) -> dict:
    tr, nome_modelo = MODELOS.get(modelo, ("", modelo or ""))
    return {"id": f"{fonte}:{n}", "fonte": fonte, "em": em or "", "para": para or "", "nome": nome or "", "assunto": assunto or nome_modelo,
            "modelo": modelo or "", "template": tr if canal == "sender" or fonte == "site" else "", "modelo_nome": nome_modelo,
            "canal": canal, "canal_nome": CANAIS.get(canal, canal), "origem": origem, "origem_nome": ORIGENS.get(origem, origem),
            "situacao": situacao, "situacao_nome": SITUACOES.get(situacao, situacao), "motivo": motivo or "", "sender_id": sender_id or "",
            "protocolo": protocolo or "", "link": link, "ligado": ligado, "detalhe": detalhe or {}}


def _tabelas(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def todas(con, desde: str = "", ate: str = "") -> list[dict]:
    """Todas as linhas de todas as fontes, entre desde e ate (UTC 'AAAA-MM-DD HH:MM:SS'; vazio = sem limite), da mais nova à mais velha."""
    t = _tabelas(con)
    d0, d1 = desde or "0000", ate or "9999"
    out: list[dict] = []
    if "uso_email" in t:
        for r in con.execute("""SELECT e.*, d.nome AS d_nome, d.email AS d_email, d.material_codigo AS d_material FROM uso_email e
                                LEFT JOIN uso_download d ON d.id=e.uso_id WHERE e.enviado_em BETWEEN ? AND ?""", (d0, d1)):
            out.append(_linha("uso", r["id"], r["enviado_em"], r["d_email"], r["d_nome"], r["assunto"], "uso_livre", "smtp", "downloads",
                              "enviado" if r["ok"] else "falhou", r["erro"], link="#uso", ligado=f"Download nº {r['uso_id']}",
                              detalhe={"enviado_por": r["enviado_por"], "material": r["d_material"]}))
    if "amigo_email" in t:
        k = {c[1] for c in con.execute("PRAGMA table_info(amigo_email)")}
        for r in con.execute("""SELECT e.*, a.nome AS a_nome, a.email AS a_email, a.protocolo AS a_prot FROM amigo_email e LEFT JOIN amigo a ON a.id=e.amigo_id
                                WHERE COALESCE(e.enviado_em, e.criado_em) BETWEEN ? AND ?""", (d0, d1)):
            ms = (r["modelo_site"] if "modelo_site" in k else None) or SENDER_AMIGOS.get(r["modelo"], "")
            sit = {"enviado": "enviado", "falhou": "falhou"}.get(r["situacao"], "na_fila")
            out.append(_linha("amigo", r["id"], r["enviado_em"] or r["criado_em"], r["para"] or r["a_email"], r["a_nome"], r["assunto"] or "",
                              ms, "smtp" if r["canal"] == "smtp" else "sender", "amigos",
                              sit, r["erro"], sender_id=r["sender_id"] if "sender_id" in k else None, protocolo=r["a_prot"], link="#amigos",
                              ligado=f"Amigo nº {r['amigo_id']}", detalhe={"modelo_painel": r["modelo"], "criado_por": r["criado_por"],
                                                                         "variaveis": _json(r["variaveis"]) if "variaveis" in k else {}, "texto": r["corpo"] or ""}))
            if not out[-1]["modelo"]:
                out[-1]["modelo_nome"] = out[-1]["assunto"] = r["assunto"] or r["modelo"]
    if "entrega_link" in t:
        k = {c[1] for c in con.execute("PRAGMA table_info(entrega_link)")}
        for r in con.execute("""SELECT l.*, s.solicitante AS s_nome FROM entrega_link l LEFT JOIN solicitacao s ON s.id=l.solicitacao_id
                                WHERE l.criado_em BETWEEN ? AND ?""", (d0, d1)):
            erro = r["erro"] if "erro" in k else None
            antigo_falho = bool(not erro and r["revogado_em"] and not r["downloads"] and _segundos(r["criado_em"], r["revogado_em"]) < 300)
            sit = "falhou" if erro or antigo_falho else "enviado"
            mot = erro or ("o envio falhou; o motivo não ficou guardado (envio anterior a esta tela)" if antigo_falho else None)
            canal = "sender" if r["canal"] == "sender" else "site"
            out.append(_linha("entrega", r["id"], r["criado_em"], r["para"], r["s_nome"], "Material para download" + (" (teste)" if r["teste"] else ""),
                              "material_download", canal, "entrega", sit, mot, link="#solicitacoes", ligado=f"Pedido nº {r['solicitacao_id']}",
                              detalhe={"criado_por": r["criado_por"], "link_ate": r["expira_em"], "downloads": r["downloads"], "teste": bool(r["teste"]),
                                       "cancelado_em": r["revogado_em"]}))
    for r in con.execute("""SELECT e.id, e.codigo, e.tipo, e.ator, e.detalhe, e.quando, i.nome AS i_nome, i.email AS i_email, i.protocolo AS i_prot
                            FROM evento e LEFT JOIN inscricao i ON CAST(i.site_id AS TEXT)=e.codigo
                            WHERE e.entidade='inscricao' AND e.tipo IN ('aviso_situacao','aviso_situacao_falhou') AND e.quando BETWEEN ? AND ?""", (d0, d1)) \
            if "inscricao" in t else []:
        d = _json(r["detalhe"])
        canal = "sender" if d.get("canal") == "sender" else "site"
        out.append(_linha("inscricao", r["id"], r["quando"], d.get("para") or r["i_email"], r["i_nome"],
                          "Situação da inscrição: " + ROTULO_INSCRICAO.get(d.get("situacao"), d.get("situacao") or ""), "inscricao_situacao", canal,
                          "inscricao", "enviado" if r["tipo"] == "aviso_situacao" else "falhou", d.get("erro"), protocolo=r["i_prot"], link="#inscricoes",
                          ligado=f"Inscrição nº {r['codigo']}", detalhe={"enviado_por": r["ator"], "situacao": d.get("situacao")}))
    if "alerta_envio" in t:
        for r in con.execute("SELECT * FROM alerta_envio WHERE tipo<>'suprimido' AND enviado_em BETWEEN ? AND ?", (d0, d1)):
            out.append(_linha("alerta", r["id"], r["enviado_em"], r["para"], "", r["titulo"] or "", "pedido_novo" if r["tipo"] == "novo" else "alerta",
                              "smtp", "alerta", "enviado" if r["ok"] else "falhou", r["erro"], link="#estacoes/alertas",
                              detalhe={"assunto_alerta": r["assunto"], "tipo": r["tipo"]}))
    if "resumo_diario_envio" in t:
        for r in con.execute("SELECT * FROM resumo_diario_envio WHERE enviado_em BETWEEN ? AND ?", (d0, d1)):
            out.append(_linha("resumo", r["dia"], r["enviado_em"], r["para"], "", f"Resumo do dia {r['dia']}", "resumo", "smtp", "resumo",
                              "enviado" if r["ok"] else "falhou", r["erro"], link="#estacoes/alertas", detalhe={"numeros": _json(r["conteudo"])}))
    if "email_site" in t:
        for r in con.execute("SELECT * FROM email_site WHERE enviado_em BETWEEN ? AND ?", (d0, d1)):
            reg = r["registro"] or ""
            out.append(_linha("site", r["id"], r["enviado_em"], r["para"], r["nome"], "", r["tipo"] or "", "site" if r["canal"] == "simples" else "sender",
                              REGISTRO_ORIGEM.get(reg, "formulario"), r["situacao"] or "enviado", r["motivo"], sender_id=r["sender_id"],
                              protocolo=r["protocolo"], ligado=(REGISTRO_NOME.get(reg, reg or "registro do site") + (f" nº {r['registro_id']}" if r["registro_id"] else "")),
                              detalhe={"tentativas": r["tentativas"], "tipo_no_site": r["tipo"], "buscado_em": r["coletado_em"]}))
            if r["template"] and not out[-1]["template"]:
                out[-1]["template"] = r["template"]
    out.sort(key=lambda x: (x["em"], x["id"]), reverse=True)
    return out


def _periodo(periodo: str | None, de: str | None, ate: str | None) -> tuple[str, str]:
    """hoje | 7 | 30 | 90 | todos (dias no horário de São Paulo), ou de/ate (AAAA-MM-DD). Devolve limites em UTC."""
    agora = datetime.now(FUSO)
    meia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    f = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")   # noqa: E731
    if de or ate:
        try:
            a = datetime.fromisoformat(de).replace(tzinfo=FUSO) if de else None
            b = datetime.fromisoformat(ate).replace(tzinfo=FUSO) + timedelta(days=1) if ate else None
        except ValueError:
            raise HTTPException(400, "Datas do período inválidas (use AAAA-MM-DD)")
        return (f(a) if a else "", f(b) if b else "")
    p = (periodo or "30").strip()
    if p == "todos":
        return "", ""
    if p == "hoje":
        return f(meia), ""
    if p.isdigit() and 0 < int(p) <= 3650:
        return f(meia - timedelta(days=int(p) - 1)), ""
    raise HTTPException(400, "Período inválido")


def filtrar(itens: list[dict], canal=None, origem=None, situacao=None, modelo=None, q=None) -> list[dict]:
    q = (q or "").strip().lower()
    out = []
    for x in itens:
        if canal and x["canal"] != canal or origem and x["origem"] != origem or situacao and x["situacao"] != situacao or modelo and x["modelo"] != modelo:
            continue
        if q and not any(q in str(x[c]).lower() for c in ("para", "nome", "protocolo", "assunto", "sender_id", "ligado")):
            continue
        out.append(x)
    return out


def numeros(con) -> dict:
    """Os números do topo: hoje e 7 dias (horário de São Paulo)."""
    h0, _ = _periodo("hoje", None, None)
    s0, _ = _periodo("7", None, None)
    sete = todas(con, s0)
    return {"hoje_enviados": sum(1 for x in sete if x["em"] >= h0 and x["situacao"] in ("enviado", "nao_sender")),
            "sete_enviados": sum(1 for x in sete if x["situacao"] in ("enviado", "nao_sender")),
            "sete_falhas": sum(1 for x in sete if x["situacao"] == "falhou"),
            "sete_nao_sender": sum(1 for x in sete if x["situacao"] == "nao_sender")}


def apagar_por_email(con, email: str) -> int:
    """LGPD (apagar pessoa): tira o e-mail e o nome desta pessoa das linhas de e-mails enviados. Não faz commit. Só a contagem."""
    em = (email or "").strip().lower()
    if not em:
        return 0
    t = _tabelas(con)
    n = 0
    if "email_site" in t:
        n += con.execute("UPDATE email_site SET para=NULL, nome=? WHERE lower(para)=?", (REMOVIDO, em)).rowcount
    if "entrega_link" in t:
        n += con.execute("UPDATE entrega_link SET para=NULL WHERE lower(para)=?", (em,)).rowcount
    if "amigo_email" in t:
        n += con.execute("UPDATE amigo_email SET para=NULL, corpo=NULL, assunto=NULL WHERE lower(para)=?", (em,)).rowcount
    for r in con.execute("""SELECT id, detalhe FROM evento WHERE entidade='inscricao' AND tipo IN ('aviso_situacao','aviso_situacao_falhou')
                            AND lower(detalhe) LIKE ?""", (f"%{em}%",)).fetchall():
        d = _json(r["detalhe"])
        if str(d.get("para") or "").strip().lower() == em:
            d["para"] = REMOVIDO
            con.execute("UPDATE evento SET detalhe=? WHERE id=?", (json.dumps(d, ensure_ascii=False), r["id"]))
            n += 1
    return n


# ---------------------------------------------------------------- telas (só admin e master)
@router.get("")
def listar(periodo: str | None = "30", de: str | None = None, ate: str | None = None, canal: str | None = None, origem: str | None = None,
           situacao: str | None = None, modelo: str | None = None, q: str | None = None, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        a, b = _periodo(periodo, de, ate)
        base = todas(con, a, b)
        itens = filtrar(base, canal, origem, situacao, modelo, q)
        por_sit = {}
        for x in filtrar(base, canal, origem, None, modelo, q):
            por_sit[x["situacao"]] = por_sit.get(x["situacao"], 0) + 1
        modelos = sorted({(x["modelo"], x["template"], x["modelo_nome"]) for x in base if x["modelo"]}, key=lambda m: (m[1] or "ZZ", m[2]))
        return {"itens": itens[:LIMITE_TELA], "total": len(itens), "limite": LIMITE_TELA, "por_situacao": por_sit, "numeros": numeros(con),
                "modelos": [{"modelo": m[0], "template": m[1], "nome": m[2]} for m in modelos],
                "canais": CANAIS, "origens": ORIGENS, "situacoes": SITUACOES,
                "site": {"ultima_busca": _estado(con, "ultima_busca") or None, "erro": _estado(con, "ultimo_erro") or None,
                         "sem_rota": _estado(con, "sem_rota") == "1", "minutos": coleta_min(con), "tem_senha": _tem_site(con)}}
    finally:
        con.close()


@router.get("/exportar.csv")
def exportar(periodo: str | None = "30", de: str | None = None, ate: str | None = None, canal: str | None = None, origem: str | None = None,
             situacao: str | None = None, modelo: str | None = None, q: str | None = None, u: dict = Depends(auth.exige("admin"))):
    """Tudo o que o filtro mostra (sem o limite da tela). Sem log de dados pessoais."""
    con = connect()
    try:
        a, b = _periodo(periodo, de, ate)
        itens = filtrar(todas(con, a, b), canal, origem, situacao, modelo, q)
    finally:
        con.close()
    buf = io.StringIO()
    wr = csv.writer(buf, delimiter=";")
    wr.writerow(["data_utc", "destinatario", "nome", "assunto", "template", "modelo", "canal", "origem", "situacao", "motivo", "protocolo", "registro", "id_no_sender"])
    for x in itens:
        wr.writerow([x["em"], x["para"], x["nome"], x["assunto"], x["template"], x["modelo_nome"], x["canal_nome"], x["origem_nome"], x["situacao_nome"],
                     x["motivo"], x["protocolo"], x["ligado"], x["sender_id"]])
    dia = datetime.now(FUSO).date().isoformat()
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="emails-enviados-{dia}.csv"', "Cache-Control": "no-store",
                             "X-Content-Type-Options": "nosniff"})


@router.post("/sincronizar")
def sincronizar(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações: sem ela o painel não busca os e-mails do site")
        return coletar(con)
    finally:
        con.close()
