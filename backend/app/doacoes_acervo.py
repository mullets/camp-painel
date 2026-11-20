"""Intenções de doação de acervo (CAMP-DOA-ACERVO, 20/11/2026). Rafael: "Vamos pôr a parte de doação de acervo no site! … com infos no
painel administrativo, e estágios."

O formulário está no site (/intencao-de-doacao-de-acervo/, plugin 1.30.0). O site é a fonte; o painel acompanha e decide:
- Busca (contrato 1.20, docs/CONTRATO_UNICO.md §6): GET /wp-json/camp/v1/painel/doacoes-acervo?desde=… (incremental) → `doacao_acervo`
  (chave site_id; o registro inteiro em `dados`). Site sem a rota (404): silêncio e aviso na tela. Roda no coletor, a cada
  `doacoes_acervo.coleta_min` (padrão 10; 0 desliga), e em "Sincronizar agora".
- Etapas, notas, contrato, valor, volume e a cobrança: POST /wp-json/camp/v1/painel/doacoes-acervo/{id}; o site valida (a cobrança só
  abre com o contrato assinado pelas partes e valor ≥ R$ 1.000; "cobranca" e "paga" só pelo sistema) e devolve o registro, que fica aqui.
- Fotos gerais: o painel só repassa (GET …/{id}/foto/{n}); não guarda.
- Tela Doações de acervo (só admin e master: dados pessoais). LGPD: apagar pessoa anonimiza (etapa e valores ficam). Sem nome ou e-mail
  no log técnico.
- CAMP-DOA-CONTRATO (contrato 1.25, site 1.34.0). Rafael: "No painel preciso poder pôr o link do contrato pra assinatura, e gerar a cobrança
  no mercado livre quando enviar o contrato pra assinatura em e-mails separados". "Enviar contrato para assinatura": 1º
  POST …/{id}/enviar-contrato (o site manda SÓ o TR30 com o link e passa a etapa a "Contrato enviado"); depois, se pedido,
  POST …/{id} {acao: gerar_cobranca} (abre o Mercado Pago e manda o TR27): dois e-mails, nessa ordem. Sem TR30 nada sai. A cobrança
  passa a abrir com o contrato ENVIADO (decisão do Rafael); pago só pela API do Mercado Pago, como antes.
- CAMP-DOA-AVISOS (contrato 1.25): ao mudar a etapa, "Avisar a pessoa por e-mail" (TR31, só pelo Sender; texto pronto por etapa,
  editável, + mensagem). Sem TR31: a etapa muda e nada sai. Pagamento confirmado avisa sozinho com doacao.avisar_pagamento (padrão 1).
- Todo e-mail da doação (TR30, TR27, TR31) fica no histórico (site) e em E-mails → Enviados (tabela evento, entidade doacao_acervo).
- CAMP-AUTENTIQUE (20/11/2026, sem mudar o contrato com o site): com a Autentique ligada e com token (autentique.py), a prévia oferece
  "Anexar o PDF do contrato". O painel cria o documento na Autentique (quem doa por nome → link; quem assina pela CAMP, opcional, por
  e-mail), guarda o id em `doacao_autentique` e usa o link de assinatura como `contrato_link` no enviar-contrato de sempre (TR30). Falhou
  na Autentique: nada sai. Na rodada (e em "Conferir assinatura agora"), os documentos pendentes são conferidos; todos assinaram →
  POST …/{id} {etapa: contrato_assinado, assinado_em: data da última assinatura} (só a data se a doação já passou dessa etapa).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import auth, autentique as aut
from .config import settings
from .db import connect
from .log_tecnico import registrar

router = APIRouter(prefix="/api/doacoes-acervo", tags=["doacoes_acervo"])

ROTA = "/wp-json/camp/v1/painel/doacoes-acervo"
REMOVIDO = "(removido)"
MSG_SITE_ANTIGO = "O site ainda não tem as intenções de doação de acervo: avise quem cuida do site (plugin da CAMP 1.30.0 ou mais novo)."
ETAPAS = {
    "em_analise": "Em análise", "info": "Aguardando informações do proponente", "visita": "Visita agendada", "aprovada": "Aprovada",
    "nao_aprovada": "Não aprovada", "contrato_enviado": "Contrato enviado para assinatura", "contrato_assinado": "Contrato assinado pelas partes",
    "cobranca": "Cobrança enviada (Mercado Pago)", "paga": "Contribuição paga · Amigo por 12 meses", "recebido": "Acervo recebido pela CAMP",
    "arquivada": "Arquivada (desistência ou sem retorno)",
}
ETAPAS_AUTO = ("cobranca", "paga")
FAIXAS = {"ate_50": "Até 50 itens", "51_500": "De 51 a 500 itens", "mais_500": "Mais de 500 itens", "nao_sei": "Não sei informar"}
# CAMP-DOA-AVISOS: etapas com aviso opcional (as mesmas do site; o site manda os textos dele em `aviso_textos`, que valem por cima)
AVISO_TEXTOS = {
    "info": "Para continuarmos a análise da sua proposta, precisamos de mais algumas informações. Vamos falar com você por e-mail ou WhatsApp; se preferir, responda este e-mail.",
    "visita": "Agendamos uma visita para conhecer o acervo. Confirmaremos com você a data, o horário e quem vai da CAMP.",
    "aprovada": "Boa notícia: a CAMP aprovou a proposta de doação do acervo. O próximo passo é o contrato, que enviaremos para você ler e assinar.",
    "nao_aprovada": "Agradecemos muito a confiança. Depois de avaliar a proposta, a CAMP não poderá receber este acervo neste momento.",
    "paga": "Recebemos a contribuição para a preservação do acervo. Obrigado! Você passa a ser Amigo da CAMP por 12 meses.",
    "recebido": "O acervo chegou à CAMP. Agora começam a conservação, o acondicionamento e a catalogação. Avisaremos quando houver novidades.",
    "arquivada": "Arquivamos a sua proposta de doação. Se quiser retomar a conversa, é só responder este e-mail.",
}
AVISO_PADRAO = ["info", "visita", "aprovada", "nao_aprovada", "paga", "recebido"]   # marcadas por padrão (arquivada fica desmarcada)
TPL = {"contrato_assinatura": ("TR30", "Contrato para assinatura"), "cobranca_avulsa": ("TR27", "Cobrança avulsa"), "doacao_andamento": ("TR31", "Andamento da doação")}
ONDE_TEMPLATE = "em E-mails → Modelos do Sender"
VERSAO_CONTRATO_SITE = "1.34.0"
MSG_SITE_SEM_CONTRATO = f"O site ainda não manda o contrato para assinatura: avise quem cuida do site (plugin da CAMP {VERSAO_CONTRATO_SITE} ou mais novo). Nada foi enviado."
RE_LINK = re.compile(r"^https?://[^\s/]+\.[^\s]+$", re.I)
ABERTAS = ("em_analise", "info", "visita", "aprovada", "contrato_enviado", "contrato_assinado", "cobranca")   # pedem ação da equipe
MINIMO = 1000.0


# ---------------------------------------------------------------- utilidades
def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _estado(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM doacao_acervo_estado WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _estado_set(con, chave: str, valor: str) -> None:
    con.execute("INSERT INTO doacao_acervo_estado (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, valor))


def coleta_min(con) -> int:
    try:
        return max(0, int(_cfg(con, "doacoes_acervo.coleta_min", "10")))
    except ValueError:
        return 10


def _utc(v) -> str:
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


def _num(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _wp():
    """Cliente do site (os testes trocam por um falso)."""
    return __import__("app.wp", fromlist=["WP"]).WP()


def _tem_site(con) -> bool:
    return bool(_cfg(con, "wp.app_password", settings.WP_APP_PASSWORD))


def _json(r) -> dict:
    try:
        d = r.json()
    except Exception:  # noqa: BLE001
        return {}
    return d if isinstance(d, dict) else {}


# ---------------------------------------------------------------- busca no site (site → painel)
def _gravar(con, x: dict) -> int:
    """Grava/atualiza uma intenção vinda do site. Devolve 1 se era nova. Anonimizada aqui não recebe os dados pessoais de volta."""
    try:
        sid = int(x.get("id") or 0)
    except (TypeError, ValueError):
        sid = 0
    if sid <= 0:
        return 0
    et = str(x.get("etapa") or "")
    velho = con.execute("SELECT anonimizado FROM doacao_acervo WHERE site_id=?", (sid,)).fetchone()
    anon = bool(velho and velho["anonimizado"]) or bool(x.get("anonimizado"))
    d = {k: v for k, v in x.items() if k != "fotos"}
    d["n_fotos"] = len([f for f in (x.get("fotos") or []) if isinstance(f, dict)])
    if anon:
        for k in ("nome", "email", "telefone", "descricao", "local", "fotos_link", "autor"):
            d[k] = ""
        d["notas"] = []
        d["n_fotos"] = 0
    vals = {
        "protocolo": _txt(x.get("protocolo"), 40), "recebida_em": _utc(x.get("recebida_em")) or None,
        "nome": REMOVIDO if anon else (_txt(x.get("nome"), 200) or None), "email": None if anon else (_txt(x.get("email"), 200).lower() or None),
        "telefone": None if anon else (_txt(x.get("telefone"), 40) or None), "autor": None if anon else (_txt(x.get("autor"), 200) or None),
        "local": None if anon else (_txt(x.get("local"), 120) or None), "faixa": _txt(x.get("quantidade_estimativa_faixa"), 20) or None,
        "etapa": et if et in ETAPAS else "em_analise", "valor": _num(x.get("valor")) or None, "assinado_em": _txt(x.get("assinado_em"), 10) or None,
        "dados": json.dumps(d, ensure_ascii=False), "anonimizado": 1 if anon else 0, "alterado_em": _utc(x.get("alterado_em")) or None,
    }
    cols = list(vals)
    _avisos_do_site(con, sid, x)
    if velho:
        con.execute(f"UPDATE doacao_acervo SET {', '.join(c + '=?' for c in cols)}, visto_em=datetime('now') WHERE site_id=?", (*vals.values(), sid))
        return 0
    con.execute(f"INSERT INTO doacao_acervo (site_id, {', '.join(cols)}) VALUES (?, {', '.join('?' * len(cols))})", (sid, *vals.values()))
    return 1


def _evento_email(con, sid: int, modelo: str, ok: bool, ator: str, extra: dict | None = None) -> None:
    """Um e-mail da doação (TR30/TR27/TR31) para o histórico do painel e E-mails → Enviados (sem nome nem e-mail: vêm da linha da doação)."""
    tr, nome = TPL.get(modelo, ("", modelo))
    d = {"template": tr, "modelo": modelo, "nome_modelo": nome, "canal": "sender", **(extra or {})}
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('doacao_acervo',?,?,?,?)",
                (str(int(sid)), "email_enviado" if ok else "email_falhou", ator, json.dumps(d, ensure_ascii=False)))


def _avisos_do_site(con, sid: int, x: dict) -> None:
    """Os avisos de etapa (TR31) que o site registrou (`avisos`, 1.25; o de pagamento sai sozinho lá) viram e-mails aqui, uma vez cada."""
    for a in x.get("avisos") or []:
        if not isinstance(a, dict) or not a.get("em"):
            continue
        chave = f"aviso:{_txt(a.get('em'), 40)}:{_txt(a.get('etapa'), 30)}"
        if con.execute("SELECT 1 FROM evento WHERE entidade='doacao_acervo' AND codigo=? AND detalhe LIKE ?", (str(sid), f'%"chave": "{chave}"%')).fetchone():
            continue
        et = _txt(a.get("etapa"), 30)
        _evento_email(con, sid, "doacao_andamento", bool(a.get("enviado")), "sistema" if a.get("auto") else "site",
                      {"chave": chave, "etapa": et, "etapa_nome": ETAPAS.get(et, et), "sender_id": _txt(a.get("sender_id"), 80),
                       "erro": _txt(a.get("erro"), 300), "em_site": _utc(a.get("em"))})


def coletar(con=None, wp=None) -> dict:
    """Uma volta da busca no site. Incremental (desde = agora da volta anterior − 2 min). Nunca levanta."""
    fechar = con is None
    con = con or connect()
    out = {"lidos": 0, "novos": 0, "sem_rota": False, "erro": None}
    try:
        wp = wp or _wp()
        params = {}
        desde = _estado(con, "desde")
        if desde:
            params["desde"] = desde
        r = wp.h.get(ROTA, params=params)
        if r.status_code == 404:
            out["sem_rota"] = True                   # site sem o contrato 1.20
            _estado_set(con, "sem_rota", "1")
            con.commit()
            return out
        if r.status_code >= 400:
            raise RuntimeError(f"O site respondeu {r.status_code} ao buscar as intenções de doação")
        d = r.json()
        if not isinstance(d, dict):
            raise RuntimeError("O site devolveu formato inválido para as intenções de doação")
        for x in d.get("itens") or []:
            if isinstance(x, dict):
                out["lidos"] += 1
                out["novos"] += _gravar(con, x)
        listas = {k: d[k] for k in ("etapas", "relacoes", "tipos", "faixas", "conservacao", "direitos", "minimo", "formulario", "aviso_textos", "aviso_padrao") if k in d}
        if listas:
            _estado_set(con, "listas", json.dumps(listas, ensure_ascii=False))
        agora = d.get("agora")
        if agora:
            try:
                _estado_set(con, "desde", (datetime.fromisoformat(str(agora).replace("Z", "+00:00")) - timedelta(minutes=2)).isoformat())
            except ValueError:
                pass
        _estado_set(con, "sem_rota", "")
        _estado_set(con, "ultimo_erro", "")
        con.commit()
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:200]
        _estado_set(con, "ultimo_erro", out["erro"])
        registrar(logging.WARNING, "doacoes_acervo_coleta", "Busca das intenções de doação no site com problema", erro=out["erro"][:160])
    finally:
        try:
            _estado_set(con, "ultima_busca", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
            con.commit()
        except Exception:  # noqa: BLE001
            pass
        if fechar:
            con.close()
    return out


def rodada(force: bool = False) -> dict:
    """A volta automática (doacoes_acervo.coleta_min; 0 desliga). Sem a senha do site: nada. Nunca levanta."""
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
        out = coletar(con)
        out["autentique"] = conferir_pendentes(con)
        return out
    except Exception as e:  # noqa: BLE001
        registrar(logging.WARNING, "doacoes_acervo_rodada", "Rodada das intenções de doação com problema", erro=type(e).__name__)
        return {"erro": type(e).__name__}
    finally:
        con.close()


# ---------------------------------------------------------------- leitura
def _linha(r) -> dict:
    d = json.loads(r["dados"]) if r["dados"] else {}
    cob = d.get("cobranca") if isinstance(d.get("cobranca"), dict) else None
    return {
        "id": r["site_id"], "protocolo": r["protocolo"] or "", "recebida_em": r["recebida_em"] or "", "nome": r["nome"] or "", "email": r["email"] or "",
        "telefone": r["telefone"] or "", "autor": r["autor"] or "", "local": r["local"] or "", "faixa": r["faixa"] or "", "faixa_nome": FAIXAS.get(r["faixa"] or "", ""),
        "etapa": r["etapa"], "etapa_nome": ETAPAS.get(r["etapa"], r["etapa"]), "valor": r["valor"], "assinado_em": r["assinado_em"] or "",
        "tipos_nomes": d.get("tipos_nomes") or [], "n_fotos": int(d.get("n_fotos") or 0), "fotos_link": d.get("fotos_link") or "", "sem_fotos": bool(d.get("sem_fotos")),
        "cobranca_situacao": (cob or {}).get("situacao", ""), "amigo_ate": ((d.get("amigo") or {}) if isinstance(d.get("amigo"), dict) else {}).get("validade", ""),
        "anonimizado": bool(r["anonimizado"]), "alterado_em": r["alterado_em"] or "",
    }


def _detalhe(r) -> dict:
    d = json.loads(r["dados"]) if r["dados"] else {}
    d.update(_linha(r))
    d["fotos"] = [{"n": i} for i in range(int(d.get("n_fotos") or 0))]
    return d


def filtrar(con, etapa: str = "", q: str = "") -> list[dict]:
    rows = con.execute("SELECT * FROM doacao_acervo ORDER BY recebida_em DESC, site_id DESC").fetchall()
    itens = [_linha(r) for r in rows]
    if etapa == "abertas":
        itens = [x for x in itens if x["etapa"] in ABERTAS]
    elif etapa in ETAPAS:
        itens = [x for x in itens if x["etapa"] == etapa]
    if q:
        qq = q.strip().lower()
        itens = [x for x in itens if qq in f"{x['nome']} {x['email']} {x['autor']} {x['protocolo']} {x['local']}".lower()]
    return itens


def anonimizar_por_email(con, email: str) -> int:
    """LGPD (apagar pessoa): tira os dados pessoais; ficam etapa, faixa e valores. Não faz commit."""
    em = (email or "").strip().lower()
    if not em:
        return 0
    try:
        ids = [r[0] for r in con.execute("SELECT site_id FROM doacao_acervo WHERE lower(email)=?", (em,))]
    except Exception:  # noqa: BLE001  (banco sem a migração 232)
        return 0
    for sid in ids:
        r = con.execute("SELECT dados FROM doacao_acervo WHERE site_id=?", (sid,)).fetchone()
        d = json.loads(r[0]) if r and r[0] else {}
        for k in ("nome", "email", "telefone", "descricao", "local", "fotos_link", "autor"):
            d[k] = ""
        d["notas"], d["n_fotos"] = [], 0
        con.execute("UPDATE doacao_acervo SET nome=?, email=NULL, telefone=NULL, autor=NULL, local=NULL, dados=?, anonimizado=1 WHERE site_id=?",
                    (REMOVIDO, json.dumps(d, ensure_ascii=False), sid))
    return len(ids)


def numeros(con) -> dict:
    """Para a tela e o "Precisa de você": quantas pedem ação, novas (em análise) e contribuições pagas."""
    try:
        rows = con.execute("SELECT etapa, valor FROM doacao_acervo").fetchall()
    except Exception:  # noqa: BLE001
        return {}
    return {"abertas": sum(1 for r in rows if r[0] in ABERTAS), "novas": sum(1 for r in rows if r[0] == "em_analise"),
            "aguardando_pagamento": sum(1 for r in rows if r[0] == "cobranca"),
            "pagas": sum(1 for r in rows if r[0] in ("paga", "recebido") and r[1]), "pagas_valor": round(sum((r[1] or 0) for r in rows if r[0] in ("paga", "recebido")), 2)}


# ---------------------------------------------------------------- telas (só admin e master)
def _erro_site(r) -> HTTPException:
    d = _json(r)
    cod = str(d.get("code") or "")
    msg = _txt(d.get("message"), 300)
    if r.status_code == 404 and cod in ("", "rest_no_route"):
        return HTTPException(409, MSG_SITE_ANTIGO)
    if cod == "camp_doa_nao_existe":
        return HTTPException(404, "Esta intenção de doação não existe mais no site.")
    if cod in ("camp_doa_sem_contrato", "camp_doa_sem_valor", "camp_doa_ja_paga"):
        return HTTPException(409, msg or "O site não deixou gerar a cobrança.")
    if cod == "camp_mp_desligado":
        return HTTPException(409, "O Mercado Pago está desligado no site (sem a chave): avise quem cuida do site. Nada foi cobrado.")
    if cod == "camp_valor":
        return HTTPException(400, msg or "O site recusou os dados.")
    if cod == "camp_mp_falhou":
        return HTTPException(502, "O Mercado Pago não abriu o pagamento agora. Tente de novo em instantes.")
    return HTTPException(502, f"O site respondeu {r.status_code}")


def _avisar_pagamento(con) -> bool:
    return _cfg(con, "doacao.avisar_pagamento", "1").strip() not in ("0", "", "false", "nao", "não")


def _historico_emails(con, sid: int) -> list[dict]:
    return [{"quando": e["quando"], "tipo": e["tipo"], "ator": e["ator"], "detalhe": json.loads(e["detalhe"] or "{}")}
            for e in con.execute("SELECT quando, tipo, ator, detalhe FROM evento WHERE entidade='doacao_acervo' AND codigo=? AND tipo IN ('email_enviado','email_falhou') ORDER BY id DESC LIMIT 50", (str(sid),))]


def _completo(con, sid: int) -> dict:
    """O detalhe da tela: registro, e-mails da doação e a assinatura na Autentique (sem token)."""
    x = _detalhe(_um(con, sid))
    x["emails"] = _historico_emails(con, sid)
    x["autentique"] = _aut_info(con, sid)
    return x


def _um(con, sid: int):
    r = con.execute("SELECT * FROM doacao_acervo WHERE site_id=?", (sid,)).fetchone()
    if not r:
        raise HTTPException(404, "Intenção de doação não encontrada no painel")
    return r


@router.get("")
def listar(etapa: str = "", q: str = "", u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        listas = json.loads(_estado(con, "listas") or "{}") or {}
        textos = {**AVISO_TEXTOS, **{k: str(v) for k, v in (listas.get("aviso_textos") or {}).items() if k in AVISO_TEXTOS}}
        return {"itens": filtrar(con, etapa, q), "etapas": ETAPAS, "etapas_auto": list(ETAPAS_AUTO), "faixas": FAIXAS, "minimo": MINIMO, "numeros": numeros(con),
                "listas": listas, "aviso_textos": textos, "aviso_padrao": AVISO_PADRAO, "avisar_pagamento": _avisar_pagamento(con),
                "autentique": {"ativo": aut.ativo(con), "max_pdf": aut.MAX_PDF},
                "site": {"ultima_busca": _estado(con, "ultima_busca") or None, "erro": _estado(con, "ultimo_erro") or None,
                         "sem_rota": _estado(con, "sem_rota") == "1", "minutos": coleta_min(con), "tem_senha": _tem_site(con)}}
    finally:
        con.close()


@router.post("/sincronizar")
def sincronizar(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações: sem ela o painel não busca as intenções de doação")
        return coletar(con)
    finally:
        con.close()


@router.get("/{sid}")
def detalhe(sid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return _completo(con, sid)
    finally:
        con.close()


class Mudanca(BaseModel):
    etapa: str | None = None
    nota: str | None = None
    contrato_link: str | None = None
    assinado_em: str | None = None
    valor: str | float | None = None
    caixas: str | int | None = None
    rolos: str | int | None = None
    volume: str | None = None
    quantidade_catalogada: str | int | None = None
    fundo: str | None = None
    acao: str | None = None          # gerar_cobranca | consultar
    avisar: bool | None = None       # CAMP-DOA-AVISOS: avisar a pessoa por e-mail (TR31) da etapa nova
    aviso_texto: str | None = None   # o texto pronto da etapa, editado
    mensagem: str | None = None      # nota da equipe, vai depois do texto
    aviso_link: str | None = None    # opcional (https)


@router.post("/{sid}")
def mudar(sid: int, b: Mudanca, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Etapa, nota, contrato, valor, volume, fundo e/ou ação (gerar_cobranca, consultar): vai ao site, que valida e devolve o registro."""
    con = connect()
    try:
        _um(con, sid)
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações")
        dados_b = b.model_dump()
        avisar = bool(dados_b.pop("avisar", None))
        aviso = {k: _txt(dados_b.pop(k, None), 3000 if k != "aviso_link" else 500) for k in ("aviso_texto", "mensagem", "aviso_link")}
        corpo = {k: (str(v) if not isinstance(v, str) else v) for k, v in dados_b.items() if v is not None and str(v).strip() != ""}
        cl = (corpo.get("contrato_link") or "").strip()
        if cl and cl != "__limpar__" and not RE_LINK.match(cl):
            raise HTTPException(400, "Link do contrato para assinatura: um endereço que comece com http:// ou https://")
        if corpo.get("etapa") and corpo["etapa"] not in ETAPAS:
            raise HTTPException(400, "Etapa desconhecida")
        if corpo.get("etapa") in ETAPAS_AUTO:
            raise HTTPException(400, f"“{ETAPAS[corpo['etapa']]}” é marcada pelo sistema (gerar a cobrança / pagamento confirmado)")
        if corpo.get("acao") and corpo["acao"] not in ("gerar_cobranca", "consultar"):
            raise HTTPException(400, "Ação desconhecida")
        if not corpo:
            raise HTTPException(400, "Nada para mudar")
        if avisar:
            if corpo.get("etapa") not in AVISO_TEXTOS:
                raise HTTPException(400, "Esta etapa não tem aviso por e-mail (Em análise, contrato e cobrança já têm os e-mails deles)")
            corpo.update({"avisar": True, **{k: v for k, v in aviso.items() if v}})
        corpo["autor_painel"] = _txt((u or {}).get("nome") or (u or {}).get("email") or "painel", 60)
        corpo["avisar_pagamento"] = "1" if _avisar_pagamento(con) else "0"
        try:
            resp = _wp().h.post(f"{ROTA}/{int(sid)}", json=corpo)
        except Exception as e:  # noqa: BLE001
            registrar(logging.WARNING, "doacoes_acervo_site", "Chamada ao site falhou", site_id=int(sid), erro=type(e).__name__)
            raise HTTPException(502, "O site não respondeu agora: tente de novo em instantes") from e
        if resp.status_code >= 400:
            raise _erro_site(resp)
        d = _json(resp)
        if isinstance(d.get("registro"), dict):
            _gravar(con, d["registro"])
        email_cob = _email_cobranca(con, sid, corpo, d, u)
        con.commit()
        registrar(logging.INFO, "doacoes_acervo_mudanca", "Intenção de doação atualizada pelo painel", site_id=int(sid),
                  etapa=corpo.get("etapa") or "", acao=corpo.get("acao") or "")
        x = _completo(con, sid)
        if avisar:
            x["aviso"] = _aviso_resposta(d)
        if email_cob is not None:
            x["email_cobranca"] = email_cob
        return x
    finally:
        con.close()


def _aviso_resposta(d: dict) -> dict:
    """O que a tela diz do aviso (TR31). Site antigo não manda "aviso": a etapa mudou e nada saiu."""
    a = d.get("aviso") if isinstance(d.get("aviso"), dict) else None
    if a is None:
        return {"enviado": False, "mensagem": f"Etapa mudada, mas o aviso não saiu: o site ainda não manda o aviso de andamento (plugin da CAMP {VERSAO_CONTRATO_SITE} ou mais novo)."}
    if a.get("enviado"):
        return {"enviado": True, "mensagem": "Etapa mudada e a pessoa foi avisada por e-mail (TR31 pelo Sender)."}
    cod = str(a.get("codigo") or "")
    if cod == "camp_sender_sem_template":
        return {"enviado": False, "falta": "TR31", "mensagem": f"Etapa mudada, mas o aviso não saiu: falta o template TR31 (Andamento da doação) do Sender. Crie no Sender e cole o ID {ONDE_TEMPLATE}."}
    if cod == "camp_sender_sem_chave":
        return {"enviado": False, "mensagem": "Etapa mudada, mas o aviso não saiu: o Sender está desligado no site (sem o token). Avise quem cuida do site."}
    return {"enviado": False, "mensagem": "Etapa mudada, mas o aviso não saiu: " + (_txt(a.get("erro"), 200) or "o Sender recusou")}


def _email_cobranca(con, sid: int, corpo: dict, d: dict, u: dict) -> dict | None:
    """Depois de gerar_cobranca: o e-mail TR27 (1.25, `email_cobranca`) vai para os e-mails da doação. Site antigo: None (não diz)."""
    if corpo.get("acao") != "gerar_cobranca" or not isinstance(d.get("email_cobranca"), dict):
        return None
    e = d["email_cobranca"]
    ok = bool(e.get("enviado"))
    _evento_email(con, sid, "cobranca_avulsa", ok, (u or {}).get("email") or "painel",
                  {"sender_id": _txt(e.get("sender_id"), 80), "erro": _txt(e.get("erro"), 300)})
    if ok:
        return {"enviado": True, "mensagem": "E-mail da cobrança enviado (TR27 pelo Sender)."}
    falta = "falta o template TR27 (Cobrança avulsa) do Sender" if e.get("codigo") == "camp_sender_sem_template" else (_txt(e.get("erro"), 200) or "o Sender recusou")
    return {"enviado": False, "mensagem": f"A cobrança foi gerada, mas o e-mail dela não saiu: {falta}. Copie o link e mande, ou use Gerar novo link de pagamento depois de arrumar."}


def _valor_br(v):
    """2000 · "2000" · "2.000,00" · "R$ 1.500,50" → float; inválido → None."""
    if isinstance(v, (int, float)):
        return _num(v)
    t = re.sub(r"[^\d,.]", "", str(v or ""))
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    return _num(t) if t else None


class EnvioContrato(BaseModel):
    contrato_link: str | None = None
    valor: str | float | None = None
    prazo: str | None = None
    gerar_cobranca: bool = False
    pdf_base64: str | None = None    # CAMP-AUTENTIQUE: o PDF do contrato (em vez do link), criado na Autentique
    pdf_nome: str | None = None


def _msg_envio_erro(r) -> tuple[int, str]:
    d = _json(r)
    cod = str(d.get("code") or "")
    if r.status_code == 404 and cod in ("", "rest_no_route"):
        return 409, MSG_SITE_SEM_CONTRATO
    if cod == "camp_sender_sem_template":
        return 409, f"Nada foi enviado: falta o template TR30 (Contrato para assinatura) do Sender. Crie no Sender e cole o ID {ONDE_TEMPLATE}."
    if cod == "camp_sender_sem_chave":
        return 409, "Nada foi enviado: o Sender está desligado no site (sem o token). Avise quem cuida do site."
    if cod == "camp_sender_email":
        return 409, "Nada foi enviado: a pessoa não tem e-mail válido."
    if cod == "camp_sender_falhou":
        return 502, "Nada foi enviado: o Sender recusou o e-mail do contrato. Tente de novo em instantes."
    if cod == "camp_doa_nao_existe":
        return 404, "Esta intenção de doação não existe mais no site."
    if cod in ("camp_doa_sem_link", "camp_doa_etapa", "camp_doa_ja_paga", "camp_doa_sem_valor", "camp_valor"):
        return (400 if cod == "camp_valor" else 409), (_txt(d.get("message"), 300) or "O site recusou.")
    if cod == "camp_mp_desligado":
        return 409, "Nada foi enviado: o Mercado Pago está desligado no site (sem a chave), e a cobrança não abriria. Avise quem cuida do site."
    return 502, f"Nada foi enviado: o site respondeu {r.status_code}"


@router.post("/{sid}/enviar-contrato")
def enviar_contrato(sid: int, b: EnvioContrato, u: dict = Depends(auth.exige("admin"))) -> dict:
    """E-mail 1 (TR30, o contrato com o link) e, se pedido, e-mail 2 (a cobrança do Mercado Pago, TR27), separados e nessa ordem.
    Sem o e-mail 1, nada sai. Se o 1 sai e a cobrança falha, a resposta diz e o "Gerar cobrança" continua lá."""
    con = connect()
    try:
        r = _um(con, sid)
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações")
        pdf = _pdf_do_corpo(con, b) if b.pdf_base64 else None
        link = "" if pdf else ((b.contrato_link or "").strip() or (json.loads(r["dados"] or "{}").get("contrato_link") or ""))
        if not pdf and not link:
            raise HTTPException(400, "Informe o link do contrato para assinatura" + (" ou anexe o PDF do contrato" if aut.ativo(con) else ""))
        if not pdf and (not RE_LINK.match(link) or len(link) > 500):
            raise HTTPException(400, "Link do contrato para assinatura: um endereço que comece com http:// ou https://")
        valor = _valor_br(b.valor) if b.valor not in (None, "") else r["valor"]
        if b.valor not in (None, "") and valor is None:
            raise HTTPException(400, "Contribuição: um valor em reais, como 2000 ou 2.000,00")
        if b.gerar_cobranca and (valor or 0) < MINIMO:
            raise HTTPException(400, "Para gerar a cobrança junto, informe a contribuição (mínimo R$ 1.000)")
        prazo = (b.prazo or "").strip()
        if prazo and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", prazo):
            raise HTTPException(400, "Prazo para assinar: uma data (AAAA-MM-DD)")
        autor = _txt((u or {}).get("nome") or (u or {}).get("email") or "painel", 60)
        doc_aut = None
        if pdf:                                  # CAMP-AUTENTIQUE: o documento nasce na Autentique; o link dela vai no TR30. Falhou: nada sai.
            doc_aut = _criar_na_autentique(con, r, pdf, b.pdf_nome or "", (u or {}).get("email") or "painel")
            link = doc_aut["link"]
        corpo = {"contrato_link": link, "cobranca": bool(b.gerar_cobranca), "autor_painel": autor, "avisar_pagamento": "1" if _avisar_pagamento(con) else "0"}
        if b.valor not in (None, ""):
            corpo["valor"] = str(valor)
        if prazo:
            corpo["prazo"] = prazo
        w = _wp()
        try:
            resp = w.h.post(f"{ROTA}/{int(sid)}/enviar-contrato", json=corpo)
        except Exception as e:  # noqa: BLE001
            registrar(logging.WARNING, "doacoes_acervo_contrato", "Envio do contrato: o site não respondeu", site_id=int(sid), erro=type(e).__name__)
            raise HTTPException(502, "O site não respondeu agora: nada foi enviado. Tente de novo em instantes") from e
        if resp.status_code >= 400:
            st, msg = _msg_envio_erro(resp)
            if str(_json(resp).get("code") or "").startswith("camp_sender_"):
                _evento_email(con, sid, "contrato_assinatura", False, (u or {}).get("email") or "painel", {"erro": msg})
                con.commit()
            raise HTTPException(st, msg)
        d1 = _json(resp)
        if isinstance(d1.get("registro"), dict):
            _gravar(con, d1["registro"])
        if doc_aut:
            con.execute("UPDATE doacao_autentique SET situacao='pendente' WHERE id=?", (doc_aut["linha"],))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('doacao_acervo',?,'autentique_enviado',?,?)",
                        (str(int(sid)), (u or {}).get("email") or "painel", json.dumps({"documento_id": doc_aut["id"], "reaproveitado": doc_aut["reaproveitado"]}, ensure_ascii=False)))
        _evento_email(con, sid, "contrato_assinatura", True, (u or {}).get("email") or "painel",
                      {"sender_id": _txt((d1.get("sender") or {}).get("id") if isinstance(d1.get("sender"), dict) else "", 80), "link_contrato": link[:500]})
        con.commit()
        out = {"contrato": {"enviado": True, "mensagem": "Contrato criado na Autentique e e-mail com o link de assinatura enviado (TR30 pelo Sender)." if doc_aut
                            else "E-mail do contrato enviado (TR30 pelo Sender)."}, "cobranca": None, "email_cobranca": None}
        if b.gerar_cobranca:
            c2 = {"acao": "gerar_cobranca", "autor_painel": autor, "avisar_pagamento": corpo["avisar_pagamento"]}
            try:
                r2 = w.h.post(f"{ROTA}/{int(sid)}", json=c2)
            except Exception as e:  # noqa: BLE001
                registrar(logging.WARNING, "doacoes_acervo_contrato", "Cobrança depois do contrato: o site não respondeu", site_id=int(sid), erro=type(e).__name__)
                r2 = None
            if r2 is None or r2.status_code >= 400:
                det = _erro_site(r2).detail if r2 is not None else "o site não respondeu"
                out["cobranca"] = {"gerada": False, "mensagem": f"O contrato foi enviado, mas a cobrança não foi gerada: {det} Use Gerar cobrança no Mercado Pago para tentar de novo."}
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('doacao_acervo',?,?,?,?)",
                            (str(int(sid)), "cobranca_falhou", (u or {}).get("email") or "painel", json.dumps({"erro": det}, ensure_ascii=False)))
            else:
                d2 = _json(r2)
                if isinstance(d2.get("registro"), dict):
                    _gravar(con, d2["registro"])
                out["cobranca"] = {"gerada": True, "mensagem": "Cobrança gerada no Mercado Pago."}
                out["email_cobranca"] = _email_cobranca(con, sid, c2, d2, u) or {"enviado": None, "mensagem": "O site não disse se o e-mail da cobrança saiu: confira o histórico."}
            con.commit()
        registrar(logging.INFO, "doacoes_acervo_contrato", "Contrato enviado para assinatura pelo painel", site_id=int(sid), cobranca=bool(b.gerar_cobranca))
        out["doacao"] = _completo(con, sid)
        return out
    finally:
        con.close()


# ---------------------------------------------------------------- CAMP-AUTENTIQUE: assinatura eletrônica
SIT_AUT = {"criado": "Criado na Autentique (o e-mail ainda não saiu)", "pendente": "Aguardando assinaturas", "assinado": "Assinado por todos",
           "recusado": "Recusado na Autentique"}
ETAPAS_ANTES_ASSINADO = ("em_analise", "info", "visita", "aprovada", "contrato_enviado")   # passam a contrato_assinado
ETAPAS_FECHADAS = ("nao_aprovada", "arquivada")                                             # não mexe no site (só registra aqui)


def _pdf_do_corpo(con, b: "EnvioContrato") -> bytes:
    if not aut.ativo(con):
        raise HTTPException(409, "A assinatura eletrônica (Autentique) está desligada ou sem o token: cole o link do contrato. Nada foi enviado.")
    try:
        pdf = base64.b64decode(re.sub(r"^data:[^,]*,", "", b.pdf_base64 or "").strip(), validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(400, "O PDF do contrato chegou incompleto: anexe de novo.") from e
    if not pdf.startswith(b"%PDF-"):
        raise HTTPException(400, "Anexe o contrato em PDF (outro tipo de arquivo não vai para a Autentique).")
    if len(pdf) > aut.MAX_PDF:
        raise HTTPException(400, "O PDF do contrato passa de 5 MB, o limite do plano grátis da Autentique: diminua o arquivo ou cole o link.")
    return pdf


def _criar_na_autentique(con, r, pdf: bytes, nome_arq: str, ator: str) -> dict:
    """Cria (ou reaproveita, se o mesmo PDF já foi criado e o e-mail não saiu) o documento. Erro → HTTPException (nada foi enviado)."""
    sid = int(r["site_id"])
    if r["anonimizado"]:
        raise HTTPException(409, "Os dados desta pessoa foram apagados (LGPD): não dá para mandar contrato.")
    sha = hashlib.sha256(pdf).hexdigest()
    v = con.execute("SELECT id, documento_id, link FROM doacao_autentique WHERE site_id=? AND situacao='criado' AND pdf_sha256=? ORDER BY id DESC LIMIT 1",
                    (sid, sha)).fetchone()
    if v and v["link"]:
        return {"linha": v["id"], "id": v["documento_id"], "link": v["link"], "reaproveitado": True}
    nome_doc = f"Contrato de doação de acervo · {r['protocolo'] or sid}"
    try:
        d = aut.criar_documento(aut.token(con), nome_doc, pdf, nome_arq, r["nome"] or "", aut.assinante_camp(con))
    except aut.ErroAutentique as e:
        registrar(logging.WARNING, "autentique_criar", "Autentique não criou o contrato", site_id=sid)
        raise HTTPException(502, f"{e} Nada foi enviado.") from e
    if not RE_LINK.match(d["link"]) or len(d["link"]) > 500:
        raise HTTPException(502, "A Autentique devolveu um link de assinatura estranho. Nada foi enviado: confira o documento na Autentique.")
    cur = con.execute("INSERT INTO doacao_autentique (site_id, documento_id, link, pdf_sha256, assinantes, situacao, criado_por) VALUES (?,?,?,?,?, 'criado', ?)",
                      (sid, d["id"], d["link"], sha, json.dumps(d["assinantes"], ensure_ascii=False), ator))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('doacao_acervo',?,'autentique_criado',?,?)",
                (str(sid), ator, json.dumps({"documento_id": d["id"], "assinantes": len(d["assinantes"])}, ensure_ascii=False)))
    con.commit()                                  # o documento existe na Autentique: fica guardado mesmo se o e-mail falhar (reaproveita)
    registrar(logging.INFO, "autentique_criar", "Contrato criado na Autentique", site_id=sid)
    return {"linha": cur.lastrowid, "id": d["id"], "link": d["link"], "reaproveitado": False}


def _aut_info(con, sid: int) -> dict | None:
    try:
        v = con.execute("SELECT * FROM doacao_autentique WHERE site_id=? ORDER BY id DESC LIMIT 1", (int(sid),)).fetchone()
    except Exception:  # noqa: BLE001  (banco sem a migração 236)
        return None
    if not v:
        return None
    a = json.loads(v["assinantes"] or "[]")
    return {"documento_id": v["documento_id"], "situacao": v["situacao"], "situacao_nome": SIT_AUT.get(v["situacao"], v["situacao"]),
            "link": v["link"] or "", "assinantes": len(a), "assinaram": sum(1 for x in a if x.get("assinado_em")),
            "assinado_em": v["assinado_em"] or "", "criado_em": v["criado_em"], "conferido_em": v["conferido_em"] or "", "erro": v["erro"] or ""}


def _conferir_um(con, v, wp=None, ator: str = "sistema") -> dict:
    """Confere um documento pendente. Todos assinaram → etapa contrato_assinado + assinado_em pelo site de sempre. Levanta ErroAutentique."""
    sid = int(v["site_id"])
    sigs = aut.consultar(aut.token(con), v["documento_id"])
    nossos = {x.get("public_id"): x for x in json.loads(v["assinantes"] or "[]")}
    if nossos:
        sigs = [s_ for s_ in sigs if s_["public_id"] in nossos] or sigs
    for s_ in sigs:
        if s_["public_id"] in nossos:
            nossos[s_["public_id"]].update({"assinado_em": aut.data_iso(s_["assinado_em"]), "recusado_em": aut.data_iso(s_["recusado_em"])})
    lista = list(nossos.values()) if nossos else [{"public_id": s_["public_id"], "assinado_em": aut.data_iso(s_["assinado_em"])} for s_ in sigs]
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    con.execute("UPDATE doacao_autentique SET assinantes=?, conferido_em=?, erro=NULL WHERE id=?", (json.dumps(lista, ensure_ascii=False), agora, v["id"]))
    if any(s_["recusado_em"] for s_ in sigs):
        con.execute("UPDATE doacao_autentique SET situacao='recusado' WHERE id=?", (v["id"],))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('doacao_acervo',?,'autentique_recusado',?,?)",
                    (str(sid), ator, json.dumps({"documento_id": v["documento_id"]}, ensure_ascii=False)))
        con.commit()
        return {"situacao": "recusado", "mensagem": "Alguém recusou o contrato na Autentique. A etapa não mudou: fale com a pessoa."}
    if not sigs or not all(s_["assinado_em"] for s_ in sigs):
        con.commit()
        n = sum(1 for s_ in sigs if s_["assinado_em"])
        return {"situacao": "pendente", "mensagem": f"Ainda faltam assinaturas na Autentique ({n} de {len(sigs)} assinaram)."}
    dia = max(aut.data_iso(s_["assinado_em"]) for s_ in sigs)
    r = _um(con, sid)
    corpo = None
    if r["etapa"] in ETAPAS_ANTES_ASSINADO:
        corpo = {"etapa": "contrato_assinado", "assinado_em": dia}
    elif r["etapa"] not in ETAPAS_FECHADAS and not r["assinado_em"]:
        corpo = {"assinado_em": dia}             # já em cobrança/paga/recebido: só a data (a etapa não volta)
    if corpo:
        corpo.update({"nota": f"Contrato assinado por todos na Autentique em {dia[8:10]}/{dia[5:7]}/{dia[:4]} (documento {v['documento_id']}).",
                      "autor_painel": "Autentique (painel)", "avisar_pagamento": "1" if _avisar_pagamento(con) else "0"})
        resp = (wp or _wp()).h.post(f"{ROTA}/{sid}", json=corpo)
        if resp.status_code >= 400:
            raise aut.ErroAutentique(f"Todos assinaram, mas o site não aceitou a etapa agora: {_erro_site(resp).detail}")
        d = _json(resp)
        if isinstance(d.get("registro"), dict):
            _gravar(con, d["registro"])
    con.execute("UPDATE doacao_autentique SET situacao='assinado', assinado_em=? WHERE id=?", (dia, v["id"]))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('doacao_acervo',?,'autentique_assinado',?,?)",
                (str(sid), ator, json.dumps({"documento_id": v["documento_id"], "assinado_em": dia, "etapa": (corpo or {}).get("etapa", "")}, ensure_ascii=False)))
    con.commit()
    registrar(logging.INFO, "autentique_assinado", "Contrato assinado por todos na Autentique", site_id=sid)
    return {"situacao": "assinado", "assinado_em": dia, "mensagem": "Todos assinaram na Autentique: " + (
        "a doação passou a Contrato assinado pelas partes." if corpo and corpo.get("etapa") else "a data da assinatura foi guardada.")}


def conferir_pendentes(con, wp=None) -> dict:
    """Na rodada: confere os documentos pendentes (só com a Autentique ligada e com token). Nunca levanta."""
    out = {"conferidos": 0, "assinados": 0, "erros": 0}
    try:
        if not aut.ativo(con):
            return {"desligado": True}
        for v in con.execute("SELECT * FROM doacao_autentique WHERE situacao='pendente' ORDER BY id LIMIT 30").fetchall():
            try:
                rr = _conferir_um(con, v, wp)
                out["conferidos"] += 1
                out["assinados"] += rr["situacao"] == "assinado"
            except Exception as e:  # noqa: BLE001
                out["erros"] += 1
                msg = str(e)[:300] if isinstance(e, (aut.ErroAutentique, HTTPException)) else type(e).__name__
                con.execute("UPDATE doacao_autentique SET erro=?, conferido_em=datetime('now') WHERE id=?", (msg, v["id"]))
                con.commit()
                registrar(logging.WARNING, "autentique_conferir", "Conferência da assinatura na Autentique com problema", site_id=int(v["site_id"]), erro=type(e).__name__)
    except Exception as e:  # noqa: BLE001
        registrar(logging.WARNING, "autentique_conferir", "Conferência das assinaturas com problema", erro=type(e).__name__)
        out["erro"] = type(e).__name__
    return out


class ConfigAutentique(BaseModel):
    token: str | None = None           # vazio/None = não mexe; "__limpar__" apaga
    ligado: bool | None = None
    assinante_camp: str | None = None


def _aut_config(con) -> dict:
    return {"configurada": bool(aut.token(con)), "ligado": aut.ligado(con), "ativo": aut.ativo(con), "assinante_camp": aut.assinante_camp(con),
            "pendentes": con.execute("SELECT COUNT(*) FROM doacao_autentique WHERE situacao='pendente'").fetchone()[0]}


def _set_cfg(con, chave: str, valor: str, ator: str, sensivel: bool) -> None:
    antes = _cfg(con, chave)
    if antes == valor:
        return
    con.execute("UPDATE configuracao SET valor=?, atualizado_em=datetime('now'), atualizado_por=? WHERE chave=?", (valor, ator, chave))
    a, d = (("definido" if antes else ""), ("definido" if valor else "")) if sensivel else (antes, valor)
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('config',?,'alterada',?,?)",
                (chave, ator, json.dumps({"antes": {"valor": a}, "depois": {"valor": d}}, ensure_ascii=False)))


@router.get("/autentique/config")
def autentique_config(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return _aut_config(con)
    finally:
        con.close()


@router.put("/autentique/config")
def autentique_salvar(b: ConfigAutentique, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Token (sensível; nunca volta), ligar/desligar e o e-mail de quem assina pela CAMP. Ligar sem token: 400."""
    con = connect()
    try:
        ator = (u or {}).get("email") or "painel"
        tk = (b.token or "").strip()
        if tk and tk != "__limpar__" and (len(tk) < 20 or len(tk) > 500 or re.search(r"\s", tk)):
            raise HTTPException(400, "Esse não parece um token da Autentique: copie de novo em perfil → API na Autentique (sem espaços).")
        em = (b.assinante_camp or "").strip().lower() if b.assinante_camp is not None else None
        if em and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", em):
            raise HTTPException(400, "E-mail de quem assina pela CAMP: um e-mail válido (ou deixe vazio).")
        novo_tk = "" if tk == "__limpar__" else (tk or aut.token(con))
        if b.ligado and not novo_tk:
            raise HTTPException(400, "Para ligar, cole antes o token da API da Autentique.")
        if tk:
            _set_cfg(con, "autentique.token", novo_tk, ator, True)
        if b.ligado is not None:
            _set_cfg(con, "autentique.ligado", "1" if b.ligado and novo_tk else "0", ator, False)
        elif tk == "__limpar__":
            _set_cfg(con, "autentique.ligado", "0", ator, False)
        if em is not None:
            _set_cfg(con, "autentique.assinante_camp", em, ator, False)
        con.commit()
        return _aut_config(con)
    finally:
        con.close()


class TesteAutentique(BaseModel):
    token: str | None = None           # o que está no campo (antes de salvar); vazio = o guardado


@router.post("/autentique/testar")
def autentique_testar(b: TesteAutentique | None = None, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Testar conexão: `me` na Autentique (só lê; não gasta documento). Nunca devolve o token."""
    con = connect()
    try:
        tk = ((b.token if b else "") or "").strip() or aut.token(con)
    finally:
        con.close()
    try:
        d = aut.testar(tk)
    except aut.ErroAutentique as e:
        raise HTTPException(409 if "token" in str(e).lower() else 502, str(e)) from e
    docs = d.get("documentos")
    return {"ok": True, "mensagem": f"Conexão com a Autentique funcionando (conta {d['conta'] or d['email'] or 'sem nome'})."
            + (f" Documentos do plano: {docs}." if docs not in (None, "") else ""), "conta": d["conta"], "email": d["email"], "documentos": docs}


@router.post("/{sid}/conferir-assinatura")
def conferir_assinatura(sid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Conferir assinatura agora (o mesmo da rodada, para uma doação)."""
    con = connect()
    try:
        _um(con, sid)
        if not aut.token(con):
            raise HTTPException(409, "Falta o token da Autentique: cole em Assinatura eletrônica (Autentique).")
        v = con.execute("SELECT * FROM doacao_autentique WHERE site_id=? ORDER BY id DESC LIMIT 1", (int(sid),)).fetchone()
        if not v:
            raise HTTPException(404, "Esta doação não tem contrato na Autentique.")
        if v["situacao"] == "criado":
            res = {"situacao": "criado", "mensagem": "O contrato foi criado na Autentique, mas o e-mail com o link ainda não saiu: use Enviar contrato para assinatura."}
        elif v["situacao"] != "pendente":
            res = {"situacao": v["situacao"], "mensagem": SIT_AUT.get(v["situacao"], v["situacao"]) + "."}
        else:
            if not _tem_site(con):
                raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações")
            try:
                res = _conferir_um(con, v, ator=(u or {}).get("email") or "painel")
            except aut.ErroAutentique as e:
                con.execute("UPDATE doacao_autentique SET erro=?, conferido_em=datetime('now') WHERE id=?", (str(e)[:300], v["id"]))
                con.commit()
                raise HTTPException(502, str(e)) from e
            except Exception as e:  # noqa: BLE001
                registrar(logging.WARNING, "autentique_conferir", "Conferir assinatura: o site não respondeu", site_id=int(sid), erro=type(e).__name__)
                raise HTTPException(502, "O site não respondeu agora: tente de novo em instantes") from e
        return {"resultado": res, "doacao": _completo(con, sid)}
    finally:
        con.close()


@router.get("/{sid}/foto/{n}")
def foto(sid: int, n: int, u: dict = Depends(auth.exige("admin"))):
    """Repassa a foto geral do site (privada). Não fica guardada no painel."""
    con = connect()
    try:
        _um(con, sid)
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações")
    finally:
        con.close()
    if n < 0 or n > 4:
        raise HTTPException(404, "Foto não encontrada")
    try:
        r = _wp().h.get(f"{ROTA}/{int(sid)}/foto/{int(n)}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, "O site não respondeu agora") from e
    tipo = str((getattr(r, "headers", {}) or {}).get("content-type", "")).split(";")[0].strip()
    if r.status_code != 200 or tipo not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(404, "Foto não encontrada")
    return Response(r.content, media_type=tipo, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                                                        "Content-Disposition": f'inline; filename="doacao-{int(sid)}-foto-{int(n) + 1}"'})
