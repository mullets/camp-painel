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
"""
from __future__ import annotations

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
    if velho:
        con.execute(f"UPDATE doacao_acervo SET {', '.join(c + '=?' for c in cols)}, visto_em=datetime('now') WHERE site_id=?", (*vals.values(), sid))
        return 0
    con.execute(f"INSERT INTO doacao_acervo (site_id, {', '.join(cols)}) VALUES (?, {', '.join('?' * len(cols))})", (sid, *vals.values()))
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
        listas = {k: d[k] for k in ("etapas", "relacoes", "tipos", "faixas", "conservacao", "direitos", "minimo", "formulario") if k in d}
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
        return coletar(con)
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


def _um(con, sid: int):
    r = con.execute("SELECT * FROM doacao_acervo WHERE site_id=?", (sid,)).fetchone()
    if not r:
        raise HTTPException(404, "Intenção de doação não encontrada no painel")
    return r


@router.get("")
def listar(etapa: str = "", q: str = "", u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return {"itens": filtrar(con, etapa, q), "etapas": ETAPAS, "etapas_auto": list(ETAPAS_AUTO), "faixas": FAIXAS, "minimo": MINIMO, "numeros": numeros(con),
                "listas": json.loads(_estado(con, "listas") or "{}") or {},
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
        return _detalhe(_um(con, sid))
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


@router.post("/{sid}")
def mudar(sid: int, b: Mudanca, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Etapa, nota, contrato, valor, volume, fundo e/ou ação (gerar_cobranca, consultar): vai ao site, que valida e devolve o registro."""
    con = connect()
    try:
        _um(con, sid)
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações")
        corpo = {k: (str(v) if not isinstance(v, str) else v) for k, v in b.model_dump().items() if v is not None and str(v).strip() != ""}
        if corpo.get("etapa") and corpo["etapa"] not in ETAPAS:
            raise HTTPException(400, "Etapa desconhecida")
        if corpo.get("etapa") in ETAPAS_AUTO:
            raise HTTPException(400, f"“{ETAPAS[corpo['etapa']]}” é marcada pelo sistema (gerar a cobrança / pagamento confirmado)")
        if corpo.get("acao") and corpo["acao"] not in ("gerar_cobranca", "consultar"):
            raise HTTPException(400, "Ação desconhecida")
        if not corpo:
            raise HTTPException(400, "Nada para mudar")
        corpo["autor_painel"] = _txt((u or {}).get("nome") or (u or {}).get("email") or "painel", 60)
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
            con.commit()
        registrar(logging.INFO, "doacoes_acervo_mudanca", "Intenção de doação atualizada pelo painel", site_id=int(sid),
                  etapa=corpo.get("etapa") or "", acao=corpo.get("acao") or "")
        return _detalhe(_um(con, sid))
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
