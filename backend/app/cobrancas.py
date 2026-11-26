"""Cobranças avulsas pelo Mercado Pago (CAMP-COB, 19/11/2026). Rafael: "Quero poder no admin criar uma cobrança de alguém que vai doar
acervo, ex. 2 mil reais, criar a cobrança para pagar com o Mercado Pago, e quero poder saber no extrato o que era."

- Tela Cobranças avulsas (só admin e master: nome, e-mail e telefone de quem paga). Criar: nome, e-mail, telefone (opcional), valor,
  finalidade (lista curta) + descrição livre, vencimento (opcional) e vínculo opcional a um fundo/projeto (rastreável).
- O painel pede ao site (contrato 1.19, docs/CONTRATO_UNICO.md §6) POST /wp-json/camp/v1/painel/cobrancas (idempotente por ref_painel =
  "painel-cob-<id>"); o site abre o Checkout Pro com a chave do Mercado Pago e devolve o link e a referência CAMP-COB-<id do site>.
- EXTRATO: o que aparece no Mercado Pago fica guardado e na tela/CSV: título do item ("CAMP · <Finalidade> · <descrição curta>"),
  external_reference (CAMP-COB-n), statement_descriptor (o que sai na fatura do cartão) e o id do pagamento no Mercado Pago.
- Situação: o site confirma o pagamento pela API do Mercado Pago (webhook e conferência de hora em hora); o painel busca
  GET /painel/cobrancas?desde=… a cada `cobrancas.coleta_min` (10; 0 desliga) e em "Sincronizar agora".
- E-mail ao pagador SÓ pelo Sender (site, TR27 "Cobrança avulsa"): sem template ou sem chave, nada sai e a tela diz o que falta.
- Cancelar (expira o link no Mercado Pago) e Gerar novo link. LGPD: apagar pessoa anonimiza (os valores ficam). Log técnico sem nome/e-mail.
- CAMP-DOA-CONTRATO (contrato 1.25, site 1.34.0): "link do contrato para assinatura" opcional na criação. Com ele, "Enviar por e-mail" manda
  ANTES o e-mail do contrato (TR30, POST …/{id}/email-contrato) e depois o da cobrança (TR27): dois e-mails. Sem o TR30 (ou site antigo)
  nada sai. O TR30 de um mesmo link sai uma vez (reenviar a cobrança não repete o contrato).
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
from pydantic import BaseModel

from . import auth
from .config import settings
from .db import connect
from .log_tecnico import registrar

router = APIRouter(prefix="/api/cobrancas", tags=["cobrancas"])

FUSO = ZoneInfo("America/Sao_Paulo")
ROTA = "/wp-json/camp/v1/painel/cobrancas"
REMOVIDO = "(removido)"
VERSAO_SITE = "1.29.0"
# chave → (rótulo, statement_descriptor que o site usa: o que sai na fatura do cartão)
FINALIDADES = {
    "doacao_acervo": ("Doação de acervo — tratamento/digitalização", "CAMP DOACAO ACERVO"),
    "doacao": ("Doação", "CAMP DOACAO"),
    "patrocinio": ("Patrocínio", "CAMP PATROCINIO"),
    "servico": ("Serviço", "CAMP SERVICO"),
    "outro": ("Outro", "CAMP"),
}
SITUACOES = {"aberta": "Aberta", "em_analise": "Pagamento em análise", "paga": "Paga", "vencida": "Vencida", "cancelada": "Cancelada",
             "recusada": "Recusada", "estornada": "Estornada", "sem_link": "Sem link"}
MEIOS = {"credit_card": "Cartão de crédito", "debit_card": "Cartão de débito", "bank_transfer": "Pix", "pix": "Pix", "account_money": "Saldo do Mercado Pago",
         "ticket": "Boleto", "prepaid_card": "Cartão pré-pago"}
TEMPLATE = ("TR27", "Cobrança avulsa")
TEMPLATE_CONTRATO = ("TR30", "Contrato para assinatura")
VERSAO_SITE_CONTRATO = "1.34.0"
RE_LINK = re.compile(r"^https?://[^\s/]+\.[^\s]+$", re.I)
ONDE_TEMPLATE = "na administração do site, Apoios → Mercado Pago → E-mails pelo Sender (avise quem cuida do site)"
MSG_SITE_ANTIGO = f"O site ainda não cria cobranças avulsas: avise quem cuida do site (plugin da CAMP {VERSAO_SITE} ou mais novo)."


# ---------------------------------------------------------------- utilidades
def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _estado(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM cobranca_avulsa_estado WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _estado_set(con, chave: str, valor: str) -> None:
    con.execute("INSERT INTO cobranca_avulsa_estado (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, valor))


def coleta_min(con) -> int:
    try:
        return max(0, int(_cfg(con, "cobrancas.coleta_min", "10")))
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


def _hoje() -> str:
    return datetime.now(FUSO).strftime("%Y-%m-%d")


def _brl(v) -> str:
    s = f"{float(v or 0):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


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


def _evento(con, cid: int, tipo: str, ator: str, detalhe: dict | None = None) -> None:
    """Histórico da cobrança (tabela evento; sem nome nem e-mail de quem paga)."""
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('cobranca_avulsa',?,?,?,?)",
                (str(cid), tipo, ator, json.dumps(detalhe or {}, ensure_ascii=False)))


def situacao_efetiva(r) -> str:
    """Aberta com o vencimento já passado (São Paulo) aparece como vencida, mesmo antes de o site marcar."""
    s = r["situacao"] or "sem_link"
    if s == "aberta" and r["vence"] and r["vence"] < _hoje():
        return "vencida"
    return s


# ---------------------------------------------------------------- site → painel
_CAMPOS_SITE = ("site_id", "situacao", "link", "preferencia_id", "external_reference", "mp_titulo", "statement_descriptor", "modo",
                "mp_pagamento_id", "pago_em", "valor_pago", "valor_liquido", "tarifa", "meio", "pagamentos", "historico_site", "cancelada_em", "alterado_em")


def _do_site(x: dict) -> dict:
    """Campos que o site manda (registro do contrato 1.19) → colunas do painel."""
    mp = x.get("mp") if isinstance(x.get("mp"), dict) else {}
    pg = x.get("pagamento") if isinstance(x.get("pagamento"), dict) else None
    pgs = [p for p in (x.get("pagamentos") or []) if isinstance(p, dict)]
    hist = [str(h)[:300] for h in (x.get("historico") or []) if isinstance(h, (str, int, float))]
    sit = str(x.get("situacao") or "")
    meio = str((pg or {}).get("metodo") or (pg or {}).get("meio") or "")
    return {
        "site_id": int(x.get("id") or 0) or None, "situacao": sit if sit in SITUACOES else "sem_link", "link": _txt(x.get("link"), 500) or None,
        "preferencia_id": _txt(x.get("preferencia_id"), 80) or None, "external_reference": _txt(x.get("external_reference") or mp.get("external_reference"), 80) or None,
        "mp_titulo": _txt(mp.get("titulo"), 256) or None, "statement_descriptor": _txt(mp.get("statement_descriptor"), 22) or None, "modo": _txt(x.get("modo"), 10) or None,
        "mp_pagamento_id": _txt((pg or {}).get("id"), 40) or None, "pago_em": _utc((pg or {}).get("pago_em")) or None,
        "valor_pago": _num((pg or {}).get("valor")) if pg else None, "valor_liquido": _num((pg or {}).get("liquido")) if pg else None,
        "tarifa": _num((pg or {}).get("tarifa")) if pg else None, "meio": meio[:30] or None,
        "pagamentos": json.dumps(pgs, ensure_ascii=False) if pgs else None, "historico_site": json.dumps(hist[-60:], ensure_ascii=False) if hist else None,
        "cancelada_em": _utc(x.get("cancelada_em")) or None, "alterado_em": _utc(x.get("alterado_em")) or None,
    }


def _aplicar_site(con, cid: int, x: dict, ator: str = "site") -> None:
    """Atualiza a linha do painel com o registro do site e anota as mudanças de situação/pagamento no histórico."""
    velho = con.execute("SELECT * FROM cobranca_avulsa WHERE id=?", (cid,)).fetchone()
    v = _do_site(x)
    con.execute(f"UPDATE cobranca_avulsa SET {', '.join(c + '=?' for c in _CAMPOS_SITE)}, erro=NULL WHERE id=?", (*[v[c] for c in _CAMPOS_SITE], cid))
    if velho and velho["situacao"] != v["situacao"] and not (velho["situacao"] == "sem_link" and v["situacao"] == "aberta"):   # link novo já tem o evento "link"
        _evento(con, cid, "situacao", ator, {"de": velho["situacao"], "para": v["situacao"]})
    if velho and v["mp_pagamento_id"] and velho["mp_pagamento_id"] != v["mp_pagamento_id"]:
        _evento(con, cid, "pago", ator, {"pagamento_mp": v["mp_pagamento_id"], "valor": v["valor_pago"], "liquido": v["valor_liquido"]})


def _gravar_site(con, x: dict) -> int:
    """Uma cobrança vinda da coleta. Casa pela ref_painel (criada aqui) ou pelo id do site. Devolve 1 se era nova no painel."""
    sid = int(x.get("id") or 0)
    if sid <= 0:
        return 0
    ref = _txt(x.get("ref_painel"), 80)
    r = con.execute("SELECT id, anonimizado FROM cobranca_avulsa WHERE site_id=?", (sid,)).fetchone() or \
        (con.execute("SELECT id, anonimizado FROM cobranca_avulsa WHERE ref_painel=?", (ref,)).fetchone() if ref else None)
    if r:
        _aplicar_site(con, r["id"], x)
        return 0
    fin = str(x.get("finalidade") or "")
    vin = _txt(x.get("vinculo"), 20).upper()
    cur = con.execute("""INSERT INTO cobranca_avulsa (ref_painel, nome, email, telefone, valor, finalidade, descricao, vence, vinculo_tipo, vinculo_codigo,
                         criado_por, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (ref or f"site-cob-{sid}", _txt(x.get("nome"), 200) or None, _txt(x.get("email"), 200).lower() or None, _txt(x.get("telefone"), 40) or None,
                       _num(x.get("valor")) or 0.0, fin if fin in FINALIDADES else "outro", str(x.get("descricao") or "")[:600], _txt(x.get("vence"), 10) or None,
                       ("projeto" if "-P" in vin else "fundo") if vin else None, vin or None, "site", _utc(x.get("criado_em")) or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))
    _aplicar_site(con, cur.lastrowid, x)
    return 1


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
            out["sem_rota"] = True                   # site sem o contrato 1.19
            _estado_set(con, "sem_rota", "1")
            con.commit()
            return out
        if r.status_code >= 400:
            raise RuntimeError(f"O site respondeu {r.status_code} ao buscar as cobranças")
        d = _json(r)
        for x in d.get("itens") or []:
            if isinstance(x, dict):
                out["lidos"] += 1
                out["novos"] += _gravar_site(con, x)
        if "mp_ativo" in d:
            _estado_set(con, "mp", json.dumps({"ativo": bool(d.get("mp_ativo")), "modo": str(d.get("modo") or "")}))
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
        registrar(logging.WARNING, "cobrancas_coleta", "Busca das cobranças avulsas no site com problema", erro=out["erro"][:160])
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
    """A volta automática (cobrancas.coleta_min; 0 desliga). Sem a senha do site ou sem cobrança nenhuma: nada. Nunca levanta."""
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
        if not con.execute("SELECT 1 FROM cobranca_avulsa LIMIT 1").fetchone() and _estado(con, "desde"):
            return {"vazio": True}
        return coletar(con)
    except Exception as e:  # noqa: BLE001
        registrar(logging.WARNING, "cobrancas_rodada", "Rodada das cobranças avulsas com problema", erro=type(e).__name__)
        return {"erro": type(e).__name__}
    finally:
        con.close()


def _col(r, k: str):
    """Coluna que pode faltar num banco sem a migração 235."""
    try:
        return r[k]
    except (IndexError, KeyError):
        return None


# ---------------------------------------------------------------- linha para a tela
def _linha(r) -> dict:
    sit = situacao_efetiva(r)
    fin = FINALIDADES.get(r["finalidade"], (r["finalidade"], ""))
    return {"id": r["id"], "site_id": r["site_id"], "ref_painel": r["ref_painel"], "nome": r["nome"] or "", "email": r["email"] or "", "telefone": r["telefone"] or "",
            "valor": r["valor"] or 0.0, "finalidade": r["finalidade"], "finalidade_nome": fin[0], "descricao": r["descricao"] or "", "vence": r["vence"] or "",
            "vinculo_tipo": r["vinculo_tipo"] or "", "vinculo": r["vinculo_codigo"] or "", "situacao": sit, "situacao_nome": SITUACOES.get(sit, sit),
            "link": r["link"] or "", "modo": r["modo"] or "", "erro": r["erro"] or "",
            "extrato": {"titulo": r["mp_titulo"] or "", "external_reference": r["external_reference"] or "", "statement_descriptor": r["statement_descriptor"] or fin[1],
                        "pagamento_id": r["mp_pagamento_id"] or ""},
            "pago_em": r["pago_em"] or "", "valor_pago": r["valor_pago"], "valor_liquido": r["valor_liquido"], "tarifa": r["tarifa"],
            "meio": MEIOS.get(r["meio"] or "", r["meio"] or ""), "email_enviado_em": r["email_enviado_em"] or "",
            "contrato_link": _col(r, "contrato_link") or "", "contrato_email_link": _col(r, "contrato_email_link") or "",
            "criado_em": r["criado_em"] or "", "criado_por": r["criado_por_nome"] or "", "cancelada_em": r["cancelada_em"] or ""}


def mensagem(x: dict) -> str:
    """Texto para mandar pelo WhatsApp (ou colar onde quiser), com o link."""
    nome = (x["nome"] or "").split(" ")[0] if x["nome"] and x["nome"] != REMOVIDO else ""
    t = f"Olá{', ' + nome if nome else ''}! Segue o link para o pagamento de {_brl(x['valor'])} à CAMP ({x['finalidade_nome']}): {x['descricao'].splitlines()[0] if x['descricao'] else ''}."
    if x["link"]:
        t += f"\nPague com Pix ou cartão pelo Mercado Pago: {x['link']}"
    if x["vence"]:
        t += f"\nVence em {'/'.join(reversed(x['vence'].split('-')))}."
    if x["extrato"]["external_reference"]:
        t += f"\nReferência: {x['extrato']['external_reference']}."
    return t + "\nObrigado! CAMP – Casa da Arquitetura Moderna Paulista"


def filtrar(con, situacao: str = "", finalidade: str = "", de: str = "", ate: str = "", q: str = "") -> list[dict]:
    for d_ in (de, ate):
        if d_ and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d_):
            raise HTTPException(400, "Data inválida (AAAA-MM-DD)")
    rows = con.execute("SELECT * FROM cobranca_avulsa ORDER BY criado_em DESC, id DESC").fetchall()
    itens = [_linha(r) for r in rows]
    if situacao:
        itens = [x for x in itens if x["situacao"] == situacao]
    if finalidade:
        itens = [x for x in itens if x["finalidade"] == finalidade]
    if de:
        itens = [x for x in itens if x["criado_em"][:10] >= de]
    if ate:
        itens = [x for x in itens if x["criado_em"][:10] <= ate]
    if q:
        qq = q.strip().lower()
        itens = [x for x in itens if qq in " ".join((x["nome"], x["email"], x["descricao"], x["extrato"]["external_reference"], x["extrato"]["pagamento_id"], x["vinculo"], x["extrato"]["titulo"])).lower()]
    return itens


def anonimizar_por_email(con, email: str) -> int:
    """LGPD (apagar pessoa): tira nome, e-mail e telefone; ficam valor, finalidade, referência e pagamento (receita). Não faz commit."""
    em = (email or "").strip().lower()
    if not em:
        return 0
    try:
        return con.execute("UPDATE cobranca_avulsa SET nome=?, email=NULL, telefone=NULL, anonimizado=1 WHERE lower(email)=?", (REMOVIDO, em)).rowcount
    except Exception:  # noqa: BLE001  (banco sem a migração 231)
        return 0


# ---------------------------------------------------------------- chamadas ao site
def _erro_site(r, acao: str) -> HTTPException:
    """Resposta de erro do site → mensagem da tela (sem repetir o texto do site, que fala da administração dele)."""
    d = _json(r)
    cod = str(d.get("code") or "")
    if r.status_code == 404 and cod in ("", "rest_no_route"):
        return HTTPException(409, MSG_SITE_ANTIGO)
    if cod == "camp_mp_desligado":
        return HTTPException(409, "O Mercado Pago está desligado no site (sem a chave): avise quem cuida do site. Nada foi cobrado.")
    if cod == "camp_cob_paga":
        return HTTPException(409, "Esta cobrança já foi paga: não dá para " + acao + ".")
    if cod == "camp_cob_nao_existe":
        return HTTPException(404, "Esta cobrança não existe mais no site.")
    if cod == "camp_valor":
        return HTTPException(400, "O site recusou os dados: " + _txt(d.get("message"), 300))
    if cod == "camp_mp_falhou":
        return HTTPException(502, "O Mercado Pago não abriu o pagamento agora. Tente Gerar novo link em instantes.")
    return HTTPException(502, f"O site respondeu {r.status_code} ao {acao}")


def _pedir_link(con, r, ator: str) -> str | None:
    """Cria (ou reabre, se o site já tem a ref_painel) a cobrança no site. Devolve None se deu certo, senão a mensagem de erro."""
    corpo = {"ref_painel": r["ref_painel"], "nome": r["nome"], "email": r["email"], "telefone": r["telefone"] or "", "valor": r["valor"],
             "finalidade": r["finalidade"], "descricao": r["descricao"], "vence": r["vence"] or "", "vinculo": r["vinculo_codigo"] or ""}
    try:
        resp = _wp().h.post(ROTA, json=corpo)
    except Exception as e:  # noqa: BLE001
        msg = "O site não respondeu agora: tente Gerar novo link em instantes."
        registrar(logging.WARNING, "cobranca_criar", "Criar cobrança no site falhou", cobranca=r["id"], erro=type(e).__name__)
        con.execute("UPDATE cobranca_avulsa SET erro=? WHERE id=?", (msg, r["id"]))
        return msg
    if resp.status_code >= 400:
        err = _erro_site(resp, "criar a cobrança")
        d = _json(resp)
        sid = (d.get("data") or {}).get("id") if isinstance(d.get("data"), dict) else None
        if sid:
            con.execute("UPDATE cobranca_avulsa SET site_id=? WHERE id=?", (int(sid), r["id"]))
        con.execute("UPDATE cobranca_avulsa SET erro=? WHERE id=?", (err.detail, r["id"]))
        _evento(con, r["id"], "sem_link", ator, {"erro": err.detail})
        return err.detail
    d = _json(resp)
    reg = d.get("registro") if isinstance(d.get("registro"), dict) else dict(id=d.get("id"), link=d.get("link"), external_reference=d.get("external_reference"), situacao="aberta")
    _aplicar_site(con, r["id"], reg, ator)
    _evento(con, r["id"], "link", ator, {"external_reference": reg.get("external_reference"), "statement_descriptor": (reg.get("mp") or {}).get("statement_descriptor")})
    return None


def _post_site(con, r, caminho: str, corpo: dict, acao: str):
    if not _tem_site(con):
        raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações")
    try:
        resp = _wp().h.post(f"{ROTA}/{int(r['site_id'])}{caminho}", json=corpo)
    except Exception as e:  # noqa: BLE001
        registrar(logging.WARNING, "cobranca_site", "Chamada ao site falhou", cobranca=r["id"], erro=type(e).__name__)
        raise HTTPException(502, "O site não respondeu agora: tente de novo em instantes") from e
    return resp


# ---------------------------------------------------------------- telas (só admin e master)
class NovaCobranca(BaseModel):
    nome: str
    email: str
    telefone: str | None = None
    valor: float
    finalidade: str
    descricao: str
    vence: str | None = None
    vinculo: str | None = None
    contrato_link: str | None = None     # CAMP-DOA-CONTRATO: link do contrato para assinatura (opcional, http/https)


def _validar(con, b: NovaCobranca) -> dict:
    nome = _txt(b.nome, 120)
    email = _txt(b.email, 200).lower()
    desc = str(b.descricao or "").strip()[:600]
    vence = (b.vence or "").strip()
    vin = (b.vinculo or "").strip().upper()
    if len(nome) < 2:
        raise HTTPException(400, "Informe o nome de quem vai pagar")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "E-mail inválido")
    valor = round(float(b.valor or 0), 2)
    if valor < 1 or valor > 1_000_000:
        raise HTTPException(400, "Valor entre R$ 1,00 e R$ 1.000.000,00")
    if b.finalidade not in FINALIDADES:
        raise HTTPException(400, "Escolha a finalidade")
    if len(desc) < 3:
        raise HTTPException(400, "Escreva o que é a cobrança (descrição), ex.: Tratamento do acervo de Fulano – 1ª parcela")
    if vence and (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", vence) or vence < _hoje()):
        raise HTTPException(400, "Vencimento: hoje ou uma data futura")
    tipo = None
    if vin:
        if re.fullmatch(r"F\d{3}-P\d{4}", vin) and con.execute("SELECT 1 FROM projeto WHERE codigo=?", (vin,)).fetchone():
            tipo = "projeto"
        elif re.fullmatch(r"F\d{3}", vin) and con.execute("SELECT 1 FROM fundo WHERE codigo=?", (vin,)).fetchone():
            tipo = "fundo"
        else:
            raise HTTPException(400, f"Vínculo {vin} não encontrado: escolha um fundo ou projeto da lista")
    cl = (b.contrato_link or "").strip()
    if cl and (not RE_LINK.match(cl) or len(cl) > 500):
        raise HTTPException(400, "Link do contrato para assinatura: um endereço que comece com http:// ou https://")
    return {"contrato_link": cl or None, "nome": nome, "email": email, "telefone": _txt(b.telefone, 40) or None, "valor": valor, "finalidade": b.finalidade, "descricao": desc,
            "vence": vence or None, "vinculo_tipo": tipo, "vinculo_codigo": vin or None}


def _um(con, cid: int):
    r = con.execute("SELECT * FROM cobranca_avulsa WHERE id=?", (cid,)).fetchone()
    if not r:
        raise HTTPException(404, "Cobrança não encontrada")
    return r


def _detalhe(con, cid: int) -> dict:
    x = _linha(_um(con, cid))
    r = _um(con, cid)
    x["pagamentos"] = json.loads(r["pagamentos"]) if r["pagamentos"] else []
    x["historico_site"] = json.loads(r["historico_site"]) if r["historico_site"] else []
    x["historico"] = [{"quando": e["quando"], "tipo": e["tipo"], "ator": e["ator"], "detalhe": json.loads(e["detalhe"] or "{}")}
                      for e in con.execute("SELECT quando, tipo, ator, detalhe FROM evento WHERE entidade='cobranca_avulsa' AND codigo=? ORDER BY id DESC LIMIT 100", (str(cid),))]
    x["mensagem"] = mensagem(x)
    return x


@router.get("")
def listar(situacao: str = "", finalidade: str = "", de: str = "", ate: str = "", q: str = "", u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        itens = filtrar(con, situacao, finalidade, de, ate, q)
        todos = [_linha(r) for r in con.execute("SELECT * FROM cobranca_avulsa")]
        ab = [x for x in todos if x["situacao"] in ("aberta", "em_analise", "sem_link")]
        pg = [x for x in itens if x["situacao"] == "paga"]
        venc = [x for x in todos if x["situacao"] == "vencida"]
        mp = json.loads(_estado(con, "mp") or "{}") or {}
        return {"itens": itens, "situacoes": SITUACOES, "finalidades": {k: {"nome": v[0], "statement_descriptor": v[1]} for k, v in FINALIDADES.items()},
                "numeros": {"abertas": len(ab), "abertas_valor": round(sum(x["valor"] for x in ab), 2), "pagas": len(pg),
                            "pagas_valor": round(sum((x["valor_pago"] or x["valor"]) for x in pg), 2),
                            "pagas_liquido": round(sum(x["valor_liquido"] for x in pg if x["valor_liquido"] is not None), 2), "vencidas": len(venc)},
                "site": {"ultima_busca": _estado(con, "ultima_busca") or None, "erro": _estado(con, "ultimo_erro") or None, "sem_rota": _estado(con, "sem_rota") == "1",
                         "minutos": coleta_min(con), "tem_senha": _tem_site(con), "mp_ativo": mp.get("ativo"), "modo": mp.get("modo") or ""}}
    finally:
        con.close()


@router.get("/exportar.csv")
def exportar(situacao: str = "", finalidade: str = "", de: str = "", ate: str = "", q: str = "", u: dict = Depends(auth.exige("admin"))):
    """Planilha para conferir com o extrato do Mercado Pago (separador ;, UTF-8 com BOM, valores com vírgula, sem fórmulas)."""
    con = connect()
    try:
        itens = filtrar(con, situacao, finalidade, de, ate, q)
    finally:
        con.close()

    def cel(v):
        s = f"{v:.2f}".replace(".", ",") if isinstance(v, float) else str(v if v is not None else "")
        return "'" + s if s[:1] in ("=", "+", "-", "@") else s

    def dbr(s):
        return "/".join(reversed(s[:10].split("-"))) + (s[10:16] if len(s) > 10 else "") if s else ""

    buf = io.StringIO()
    wr = csv.writer(buf, delimiter=";")
    wr.writerow(["Criada em", "Nome", "E-mail", "Telefone", "Finalidade", "Descrição", "Valor (R$)", "Vencimento", "Situação", "Vínculo",
                 "Título no Mercado Pago", "Referência externa (external_reference)", "Descrição na fatura (statement_descriptor)",
                 "ID do pagamento no Mercado Pago", "Pago em (UTC)", "Valor pago (R$)", "Líquido recebido (R$)", "Tarifa (R$)", "Meio", "Link"])
    for x in itens:
        wr.writerow([cel(v) for v in (dbr(x["criado_em"]), x["nome"], x["email"], x["telefone"], x["finalidade_nome"], x["descricao"], float(x["valor"]),
                                       dbr(x["vence"]), x["situacao_nome"], x["vinculo"], x["extrato"]["titulo"], x["extrato"]["external_reference"],
                                       x["extrato"]["statement_descriptor"], x["extrato"]["pagamento_id"], dbr(x["pago_em"]),
                                       float(x["valor_pago"]) if x["valor_pago"] is not None else "", float(x["valor_liquido"]) if x["valor_liquido"] is not None else "",
                                       float(x["tarifa"]) if x["tarifa"] is not None else "", x["meio"], x["link"])])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="cobrancas-avulsas-{_hoje()}.csv"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/sincronizar")
def sincronizar(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações: sem ela o painel não busca as cobranças")
        return coletar(con)
    finally:
        con.close()


@router.post("")
def criar(b: NovaCobranca, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Grava a cobrança e pede o link ao site. Sem resposta boa do site, a cobrança fica 'Sem link' com o motivo (Gerar novo link tenta de novo)."""
    con = connect()
    try:
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações: sem ela o painel não cria a cobrança no Mercado Pago")
        d = _validar(con, b)
        cur = con.execute("""INSERT INTO cobranca_avulsa (nome, email, telefone, valor, finalidade, descricao, vence, vinculo_tipo, vinculo_codigo, situacao,
                             statement_descriptor, criado_por, criado_por_nome) VALUES (?,?,?,?,?,?,?,?,?,'sem_link',?,?,?)""",
                          (d["nome"], d["email"], d["telefone"], d["valor"], d["finalidade"], d["descricao"], d["vence"], d["vinculo_tipo"], d["vinculo_codigo"],
                           FINALIDADES[d["finalidade"]][1], u["id"], u["nome"]))
        cid = cur.lastrowid
        con.execute("UPDATE cobranca_avulsa SET ref_painel=? WHERE id=?", (f"painel-cob-{cid}", cid))
        if d["contrato_link"]:
            con.execute("UPDATE cobranca_avulsa SET contrato_link=? WHERE id=?", (d["contrato_link"], cid))
        _evento(con, cid, "criado", u["email"], {"valor": d["valor"], "finalidade": d["finalidade"], "vence": d["vence"], "vinculo": d["vinculo_codigo"],
                                                 **({"contrato_link": True} if d["contrato_link"] else {})})
        con.commit()
        erro = _pedir_link(con, _um(con, cid), u["email"])
        if erro and erro.startswith("O site recusou os dados"):
            con.execute("DELETE FROM cobranca_avulsa WHERE id=?", (cid,))
            con.execute("DELETE FROM evento WHERE entidade='cobranca_avulsa' AND codigo=?", (str(cid),))
            con.commit()
            raise HTTPException(400, erro)
        con.commit()
        registrar(logging.INFO, "cobranca_criada", "Cobrança avulsa criada no painel", cobranca=cid, com_link=not erro)
        return {"cobranca": _detalhe(con, cid), "erro": erro}
    finally:
        con.close()


@router.get("/{cid}")
def detalhe(cid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return _detalhe(con, cid)
    finally:
        con.close()


class NovoLink(BaseModel):
    vence: str | None = None


@router.post("/{cid}/novo-link")
def novo_link(cid: int, b: NovoLink | None = None, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Gera outro link (o anterior expira). Sem cobrança no site ainda, tenta criar de novo (a mesma ref_painel: não duplica)."""
    con = connect()
    try:
        r = _um(con, cid)
        if situacao_efetiva(r) in ("paga", "estornada"):
            raise HTTPException(409, "Esta cobrança já foi paga: não dá para gerar outro link")
        vence = ((b.vence if b else None) or "").strip()
        if vence and (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", vence) or vence < _hoje()):
            raise HTTPException(400, "Vencimento: hoje ou uma data futura")
        if not vence and r["vence"] and r["vence"] < _hoje():
            raise HTTPException(400, "O vencimento desta cobrança já passou: informe um novo vencimento")
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações")
        if not r["site_id"] or not r["link"]:      # ainda sem link: o site acha pela ref_painel e tenta abrir o pagamento de novo
            if vence:
                con.execute("UPDATE cobranca_avulsa SET vence=? WHERE id=?", (vence, cid))
            erro = _pedir_link(con, _um(con, cid), u["email"])
            con.commit()
            if erro:
                raise HTTPException(502 if "não respondeu" in erro or "Mercado Pago não abriu" in erro else 409, erro)
            return {"cobranca": _detalhe(con, cid)}
        resp = _post_site(con, r, "", {"acao": "novo_link", **({"vence": vence} if vence else {})}, "gerar o novo link")
        if resp.status_code >= 400:
            raise _erro_site(resp, "gerar outro link")
        d = _json(resp)
        if vence:
            con.execute("UPDATE cobranca_avulsa SET vence=? WHERE id=?", (vence, cid))
        if isinstance(d.get("registro"), dict):
            _aplicar_site(con, cid, d["registro"], u["email"])
        _evento(con, cid, "novo_link", u["email"], {"vence": vence or r["vence"]})
        con.commit()
        return {"cobranca": _detalhe(con, cid)}
    finally:
        con.close()


@router.post("/{cid}/cancelar")
def cancelar(cid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Cancela: o site expira o link no Mercado Pago (quem abrir não consegue mais pagar)."""
    con = connect()
    try:
        r = _um(con, cid)
        if r["situacao"] == "cancelada":
            return {"cobranca": _detalhe(con, cid)}
        aviso = cancelar_cobranca(con, cid, u["email"])
        return {"cobranca": _detalhe(con, cid), "aviso": aviso}
    finally:
        con.close()


def cancelar_cobranca(con, cid: int, ator_email: str, extra: dict | None = None) -> str | None:
    """O cancelamento de "Cancelar" (o site expira o link no Mercado Pago), reaproveitado pelo reenvio de um pedido com valor novo
    (CAMP-ENTREGA, 26/11/2026). Devolve o aviso (ou None); erro do site = HTTPException; paga/estornada = 409; já cancelada = nada."""
    r = _um(con, cid)
    if situacao_efetiva(r) in ("paga", "estornada"):
        raise HTTPException(409, "Esta cobrança já foi paga: não dá para cancelar")
    if r["situacao"] == "cancelada":
        return None
    aviso = None
    if r["site_id"]:
        resp = _post_site(con, r, "", {"acao": "cancelar"}, "cancelar")
        if resp.status_code >= 400:
            raise _erro_site(resp, "cancelar")
        d = _json(resp)
        if isinstance(d.get("registro"), dict):
            _aplicar_site(con, cid, d["registro"], ator_email)
        if d.get("mp_expirou") is False:
            aviso = "Cancelada no painel e no site, mas o Mercado Pago não confirmou que o link expirou: confira lá se precisar."
    else:
        con.execute("UPDATE cobranca_avulsa SET situacao='cancelada', cancelada_em=datetime('now') WHERE id=?", (cid,))
    _evento(con, cid, "cancelado", ator_email, extra or {})
    con.commit()
    return aviso


@router.post("/{cid}/consultar")
def consultar(cid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Pede ao site para perguntar ao Mercado Pago agora (o pagamento só vale confirmado pela API)."""
    con = connect()
    try:
        r = _um(con, cid)
        if not r["site_id"]:
            raise HTTPException(409, "Esta cobrança ainda não existe no site: use Gerar novo link")
        resp = _post_site(con, r, "", {"acao": "consultar"}, "consultar")
        if resp.status_code >= 400:
            raise _erro_site(resp, "consultar")
        d = _json(resp)
        if isinstance(d.get("registro"), dict):
            _aplicar_site(con, cid, d["registro"], "site")
        con.commit()
        return {"cobranca": _detalhe(con, cid)}
    finally:
        con.close()


@router.post("/{cid}/email")
def enviar_email(cid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Manda a cobrança por e-mail SÓ pelo Sender (template TR27 no site). Sem template ou sem chave: não sai nada e a tela diz o que falta."""
    con = connect()
    try:
        r = _um(con, cid)
        sit = situacao_efetiva(r)
        if sit in ("paga", "estornada", "cancelada"):
            raise HTTPException(409, f"Esta cobrança está {SITUACOES[sit].lower()}: nada foi enviado")
        if not r["site_id"] or not r["link"]:
            raise HTTPException(409, "Esta cobrança está sem link: use Gerar novo link antes de enviar")
        if not r["email"]:
            raise HTTPException(409, "Sem e-mail de quem paga")
        contrato = _enviar_contrato(con, r, u)        # e-mail 1 (TR30), antes e separado; sem ele, nada sai
        resp = _post_site(con, r, "/email", {}, "enviar o e-mail")
        d = _json(resp)
        cod = str(d.get("code") or "")
        msg = None
        if resp.status_code == 404 and cod in ("", "rest_no_route"):
            msg = "não enviado: " + MSG_SITE_ANTIGO
        elif cod == "camp_sender_sem_template":
            msg = f"não enviado: falta o template {TEMPLATE[0]} ({TEMPLATE[1]}) do Sender no site. Crie no Sender e cole o ID {ONDE_TEMPLATE}"
        elif cod == "camp_sender_sem_chave":
            msg = "não enviado: o Sender está desligado no site (sem o token). Avise quem cuida do site"
        elif cod == "camp_cob_sem_link":
            msg = "não enviado: a cobrança está sem link no site. Use Gerar novo link"
        elif resp.status_code >= 400:
            msg = "não enviado: o Sender recusou o e-mail" if cod == "camp_sender_falhou" else f"não enviado: o site respondeu {resp.status_code}"
        if msg:
            _evento(con, cid, "email_falhou", u["email"], {"template": TEMPLATE[0], "modelo": "cobranca_avulsa", "erro": msg})
            con.commit()
            if contrato:
                msg = "O e-mail do contrato saiu, mas o da cobrança não: " + msg.removeprefix("não enviado: ") + ". Depois de arrumar, use Enviar por e-mail de novo (o contrato não é repetido)."
            raise HTTPException(409 if resp.status_code in (404, 409) else 502, msg)
        con.execute("UPDATE cobranca_avulsa SET email_enviado_em=datetime('now') WHERE id=?", (cid,))
        _evento(con, cid, "email_enviado", u["email"], {"template": TEMPLATE[0], "modelo": "cobranca_avulsa", "canal": "sender", "sender_id": str((d.get("sender") or {}).get("id") or "")})
        con.commit()
        registrar(logging.INFO, "cobranca_email", "Cobrança avulsa enviada pelo Sender", cobranca=cid, contrato=bool(contrato))
        return {"ok": True, "enviado": True, "template": TEMPLATE[0], "contrato_enviado": bool(contrato), "cobranca": _detalhe(con, cid)}
    finally:
        con.close()


def _enviar_contrato(con, r, u) -> bool:
    """Com link de contrato ainda não mandado: TR30 pelo site ANTES da cobrança. True = saiu agora; False = não havia o que mandar.
    Qualquer falha levanta (e nada da cobrança sai): sem TR30, sem chave, site antigo."""
    link = _col(r, "contrato_link") or ""
    if not link or link == (_col(r, "contrato_email_link") or ""):
        return False
    resp = _post_site(con, r, "/email-contrato", {"contrato_link": link}, "enviar o contrato")
    d = _json(resp)
    cod = str(d.get("code") or "")
    msg = None
    if resp.status_code == 404 and cod in ("", "rest_no_route"):
        msg = f"nada foi enviado: o site ainda não manda o contrato para assinatura. Avise quem cuida do site (plugin da CAMP {VERSAO_SITE_CONTRATO} ou mais novo)"
    elif cod == "camp_sender_sem_template":
        msg = f"nada foi enviado: falta o template {TEMPLATE_CONTRATO[0]} ({TEMPLATE_CONTRATO[1]}) do Sender. Crie no Sender e cole o ID em E-mails → Modelos do Sender"
    elif cod == "camp_sender_sem_chave":
        msg = "nada foi enviado: o Sender está desligado no site (sem o token). Avise quem cuida do site"
    elif resp.status_code >= 400:
        msg = "nada foi enviado: o Sender recusou o e-mail do contrato" if cod == "camp_sender_falhou" else f"nada foi enviado: o site respondeu {resp.status_code} ao enviar o contrato"
    if msg:
        _evento(con, r["id"], "email_falhou", u["email"], {"template": TEMPLATE_CONTRATO[0], "modelo": "contrato_assinatura", "erro": msg})
        con.commit()
        raise HTTPException(409 if resp.status_code in (404, 409) else 502, msg)
    con.execute("UPDATE cobranca_avulsa SET contrato_email_link=? WHERE id=?", (link, r["id"]))
    _evento(con, r["id"], "email_enviado", u["email"], {"template": TEMPLATE_CONTRATO[0], "modelo": "contrato_assinatura", "canal": "sender",
                                                        "sender_id": str((d.get("sender") or {}).get("id") or "")})
    con.commit()
    return True

