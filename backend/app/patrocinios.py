"""Patrocínio de empresas (CAMP-PAT-EMPRESA, 23/11/2026). Rafael: "na parte de patrocínio por empresa, vamos fazer tudo pelo site? mesmo fluxo
da doação de acervo, no painel mesma coisa só que de patrocínios de empresa".

O site tem a página das cotas (/patrocinio-e-apoio/cotas/, plugin 1.40.0) e o pagamento (à vista = cobrança avulsa CAMP-COB; 12 meses =
assinatura mensal CAMP-PAT). O site é a fonte; o painel acompanha e decide as etapas:
- Busca (contrato 1.31, docs/CONTRATO_UNICO.md §6): GET /wp-json/camp/v1/painel/patrocinios?desde=… (incremental) → `patrocinio`
  (chave site_id; o registro inteiro em `dados`). Site sem a rota (404): silêncio e aviso. A cada `patrocinios.coleta_min` (10; 0 desliga)
  e em "Sincronizar agora".
- Etapa, nota, novo link de pagamento e consulta ao Mercado Pago: POST /wp-json/camp/v1/painel/patrocinios/{id}; o site valida
  ("aguardando_pagamento" e "pago" só o sistema marca) e devolve o registro.
- Manual de marca (PDF) e logos (ZIP): o painel só repassa (GET …/{id}/arquivo/manual|logos); não guarda.
- Tela Patrocínios (só admin e master). LGPD: apagar pessoa anonimiza o responsável; empresa, cota e valores ficam. Sem nome/e-mail no log.
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

router = APIRouter(prefix="/api/patrocinios", tags=["patrocinios"])

ROTA = "/wp-json/camp/v1/painel/patrocinios"
REMOVIDO = "(removido)"
MSG_SITE_ANTIGO = "O site ainda não tem as cotas de patrocínio: avise quem cuida do site (plugin da CAMP 1.40.0 ou mais novo)."
ETAPAS = {
    "recebida": "Recebida", "em_conversa": "Em conversa com a equipe", "aguardando_pagamento": "Aguardando pagamento", "pago": "Pagamento confirmado",
    "contrato_enviado": "Contrato enviado", "contrato_assinado": "Contrato assinado", "marca_aplicada": "Marca aplicada (site e materiais)",
    "ativa": "Patrocínio em andamento", "encerrada": "Encerrada", "cancelada": "Cancelada / desistência",
}
ETAPAS_AUTO = ("aguardando_pagamento", "pago")
FLUXO = ["recebida", "contrato_enviado", "contrato_assinado", "aguardando_pagamento", "pago", "marca_aplicada", "ativa", "encerrada"]   # CAMP-PAT-INTENCAO: contrato antes do pagamento
ABERTAS = ("recebida", "em_conversa", "aguardando_pagamento", "pago", "contrato_enviado", "contrato_assinado")   # pedem ação da equipe
COTAS = {"parceiro": "Parceiro", "mantenedor": "Mantenedor", "institucional": "Institucional", "master": "Master"}


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _estado(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM patrocinio_estado WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _estado_set(con, chave: str, valor: str) -> None:
    con.execute("INSERT INTO patrocinio_estado (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, valor))


def coleta_min(con) -> int:
    try:
        return max(0, int(_cfg(con, "patrocinios.coleta_min", "10")))
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
        return 0.0


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


# ---------------------------------------------------------------- busca no site
PESSOAIS = ("nome", "email", "telefone", "cargo", "mensagem")


def _gravar(con, x: dict) -> int:
    """Grava/atualiza uma proposta do site. Devolve 1 se era nova. Anonimizada aqui não recebe o responsável de volta."""
    try:
        sid = int(x.get("id") or 0)
    except (TypeError, ValueError):
        sid = 0
    if sid <= 0:
        return 0
    velho = con.execute("SELECT anonimizado FROM patrocinio WHERE site_id=?", (sid,)).fetchone()
    anon = bool(velho and velho["anonimizado"]) or bool(x.get("anonimizado"))
    d = dict(x)
    if anon:
        for k in PESSOAIS:
            d[k] = ""
        d["notas"], d["arquivos"] = [], []
    et = str(x.get("etapa") or "")
    vals = {
        "protocolo": _txt(x.get("protocolo"), 40), "recebida_em": _utc(x.get("recebida_em")) or None, "cota": _txt(x.get("cota"), 20),
        "modalidade": _txt(x.get("modalidade"), 10), "empresa": _txt(x.get("nome_marca"), 120) or None, "razao_social": _txt(x.get("razao_social"), 200) or None,
        "cnpj": _txt(x.get("cnpj"), 20) or None, "nome": REMOVIDO if anon else (_txt(x.get("nome"), 150) or None),
        "email": None if anon else (_txt(x.get("email"), 200).lower() or None), "telefone": None if anon else (_txt(x.get("telefone"), 40) or None),
        "etapa": et if et in ETAPAS else "recebida", "valor_anual": _num(x.get("valor_anual")), "valor_pago": _num(x.get("valor_pago")),
        "meses_pagos": int(x.get("meses_pagos") or 0), "dados": json.dumps(d, ensure_ascii=False), "anonimizado": 1 if anon else 0, "alterado_em": _utc(x.get("alterado_em")) or None,
    }
    cols = list(vals)
    if velho:
        con.execute(f"UPDATE patrocinio SET {', '.join(c + '=?' for c in cols)}, visto_em=datetime('now') WHERE site_id=?", (*vals.values(), sid))
        return 0
    con.execute(f"INSERT INTO patrocinio (site_id, {', '.join(cols)}) VALUES (?, {', '.join('?' * len(cols))})", (sid, *vals.values()))
    return 1


def coletar(con=None, wp=None) -> dict:
    """Uma volta da busca no site (incremental: desde = agora da volta anterior − 2 min). Nunca levanta."""
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
            out["sem_rota"] = True
            _estado_set(con, "sem_rota", "1")
            con.commit()
            return out
        if r.status_code >= 400:
            raise RuntimeError(f"O site respondeu {r.status_code} ao buscar os patrocínios")
        d = r.json()
        if not isinstance(d, dict):
            raise RuntimeError("O site devolveu formato inválido para os patrocínios")
        for x in d.get("itens") or []:
            if isinstance(x, dict):
                out["lidos"] += 1
                out["novos"] += _gravar(con, x)
        listas = {k: d[k] for k in ("etapas", "cotas", "modalidades", "pagina") if k in d}
        if listas:
            _estado_set(con, "listas", json.dumps(listas, ensure_ascii=False))
        if d.get("agora"):
            try:
                _estado_set(con, "desde", (datetime.fromisoformat(str(d["agora"]).replace("Z", "+00:00")) - timedelta(minutes=2)).isoformat())
            except ValueError:
                pass
        _estado_set(con, "sem_rota", "")
        _estado_set(con, "ultimo_erro", "")
        con.commit()
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:200]
        _estado_set(con, "ultimo_erro", out["erro"])
        registrar(logging.WARNING, "patrocinios_coleta", "Busca dos patrocínios no site com problema", erro=out["erro"][:160])
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
    """A volta automática (patrocinios.coleta_min; 0 desliga). Sem a senha do site: nada. Nunca levanta."""
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
        registrar(logging.WARNING, "patrocinios_rodada", "Rodada dos patrocínios com problema", erro=type(e).__name__)
        return {"erro": type(e).__name__}
    finally:
        con.close()


# ---------------------------------------------------------------- leitura
def _linha(r) -> dict:
    d = json.loads(r["dados"]) if r["dados"] else {}
    ass = d.get("assinatura") if isinstance(d.get("assinatura"), dict) else {}
    cob = d.get("cobranca") if isinstance(d.get("cobranca"), dict) else None
    return {
        "id": r["site_id"], "protocolo": r["protocolo"] or "", "recebida_em": r["recebida_em"] or "", "cota": r["cota"] or "", "cota_nome": COTAS.get(r["cota"] or "", r["cota"] or ""),
        "modalidade": r["modalidade"] or "", "modalidade_nome": d.get("modalidade_nome") or "", "empresa": r["empresa"] or "", "razao_social": r["razao_social"] or "",
        "cnpj": r["cnpj"] or "", "nome": r["nome"] or "", "email": r["email"] or "", "telefone": r["telefone"] or "", "etapa": r["etapa"], "etapa_nome": ETAPAS.get(r["etapa"], r["etapa"]),
        "valor_anual": r["valor_anual"] or 0.0, "valor_pago": r["valor_pago"] or 0.0, "meses_pagos": r["meses_pagos"] or 0, "consulta": bool(d.get("consulta")),
        "assinatura_status": ass.get("status") or "", "cobranca_situacao": (cob or {}).get("situacao") or "", "anonimizado": bool(r["anonimizado"]), "alterado_em": r["alterado_em"] or "",
    }


def _detalhe(r) -> dict:
    d = json.loads(r["dados"]) if r["dados"] else {}
    d.update(_linha(r))
    return d


def filtrar(con, etapa: str = "", q: str = "") -> list[dict]:
    itens = [_linha(r) for r in con.execute("SELECT * FROM patrocinio ORDER BY recebida_em DESC, site_id DESC")]
    if etapa == "abertas":
        itens = [x for x in itens if x["etapa"] in ABERTAS]
    elif etapa in ETAPAS:
        itens = [x for x in itens if x["etapa"] == etapa]
    if q:
        qq = q.strip().lower()
        itens = [x for x in itens if qq in f"{x['empresa']} {x['razao_social']} {x['cnpj']} {x['nome']} {x['email']} {x['protocolo']}".lower()]
    return itens


def numeros(con) -> dict:
    try:
        rows = con.execute("SELECT etapa, valor_pago, modalidade FROM patrocinio").fetchall()
    except Exception:  # noqa: BLE001
        return {}
    pagos = [r for r in rows if (r[1] or 0) > 0]
    return {"propostas": len(rows), "abertas": sum(1 for r in rows if r[0] in ABERTAS), "aguardando_pagamento": sum(1 for r in rows if r[0] == "aguardando_pagamento"),
            "pagos": len(pagos), "recebido": round(sum(r[1] or 0 for r in rows), 2), "mensais": sum(1 for r in pagos if r[2] == "mensal")}


def anonimizar_por_email(con, email: str) -> int:
    """LGPD (apagar pessoa): tira o responsável; empresa, cota e valores ficam. Não faz commit."""
    em = (email or "").strip().lower()
    if not em:
        return 0
    try:
        ids = [r[0] for r in con.execute("SELECT site_id FROM patrocinio WHERE lower(email)=?", (em,))]
    except Exception:  # noqa: BLE001  (banco sem a migração 245)
        return 0
    for sid in ids:
        r = con.execute("SELECT dados FROM patrocinio WHERE site_id=?", (sid,)).fetchone()
        d = json.loads(r[0]) if r and r[0] else {}
        for k in PESSOAIS:
            d[k] = ""
        d["notas"], d["arquivos"] = [], []
        con.execute("UPDATE patrocinio SET nome=?, email=NULL, telefone=NULL, dados=?, anonimizado=1 WHERE site_id=?", (REMOVIDO, json.dumps(d, ensure_ascii=False), sid))
    return len(ids)


# ---------------------------------------------------------------- telas (só admin e master)
def _erro_site(r) -> HTTPException:
    d = _json(r)
    cod = str(d.get("code") or "")
    msg = _txt(d.get("message"), 300)
    if r.status_code == 404 and cod in ("", "rest_no_route"):
        return HTTPException(409, MSG_SITE_ANTIGO)
    if cod == "camp_pat_nao_existe":
        return HTTPException(404, "Esta proposta não existe mais no site.")
    if cod in ("camp_pat_pago", "camp_pat_consulta", "camp_mp_desligado"):
        return HTTPException(409, msg or "O site não deixou abrir outro pagamento.")
    if cod == "camp_valor":
        return HTTPException(400, msg or "O site recusou os dados.")
    if cod == "camp_mp_falhou":
        return HTTPException(502, "O Mercado Pago não abriu o pagamento agora. Tente de novo em instantes.")
    return HTTPException(502, f"O site respondeu {r.status_code}")


def _um(con, sid: int):
    r = con.execute("SELECT * FROM patrocinio WHERE site_id=?", (sid,)).fetchone()
    if not r:
        raise HTTPException(404, "Proposta de patrocínio não encontrada no painel")
    return r


@router.get("")
def listar(etapa: str = "", q: str = "", u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return {"itens": filtrar(con, etapa, q), "etapas": ETAPAS, "etapas_auto": list(ETAPAS_AUTO), "fluxo": FLUXO, "numeros": numeros(con),
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
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações: sem ela o painel não busca os patrocínios")
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
    acao: str | None = None          # novo_link | consultar


@router.post("/{sid}")
def mudar(sid: int, b: Mudanca, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        _um(con, sid)
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações")
        corpo = {k: v for k, v in b.model_dump().items() if v is not None and str(v).strip() != ""}
        if corpo.get("etapa") and corpo["etapa"] not in ETAPAS:
            raise HTTPException(400, "Etapa desconhecida")
        if corpo.get("etapa") in ETAPAS_AUTO:
            raise HTTPException(400, f"“{ETAPAS[corpo['etapa']]}” é marcada pelo sistema (pagamento aberto / confirmado pelo Mercado Pago)")
        if corpo.get("acao") and corpo["acao"] not in ("novo_link", "consultar"):
            raise HTTPException(400, "Ação desconhecida")
        if not corpo:
            raise HTTPException(400, "Nada para mudar")
        corpo["autor_painel"] = _txt((u or {}).get("nome") or (u or {}).get("email") or "painel", 60)
        try:
            resp = _wp().h.post(f"{ROTA}/{int(sid)}", json=corpo)
        except Exception as e:  # noqa: BLE001
            registrar(logging.WARNING, "patrocinios_site", "Chamada ao site falhou", site_id=int(sid), erro=type(e).__name__)
            raise HTTPException(502, "O site não respondeu agora: tente de novo em instantes") from e
        if resp.status_code >= 400:
            raise _erro_site(resp)
        d = _json(resp)
        if isinstance(d.get("registro"), dict):
            _gravar(con, d["registro"])
            con.commit()
        registrar(logging.INFO, "patrocinios_mudanca", "Patrocínio atualizado pelo painel", site_id=int(sid), etapa=corpo.get("etapa") or "", acao=corpo.get("acao") or "")
        return _detalhe(_um(con, sid))
    finally:
        con.close()


@router.get("/{sid}/arquivo/{tipo}")
def arquivo(sid: int, tipo: str, u: dict = Depends(auth.exige("admin"))):
    """Repassa o manual de marca (PDF) ou os logos (ZIP) do site. Não ficam guardados no painel."""
    if tipo not in ("manual", "logos"):
        raise HTTPException(404, "Arquivo não encontrado")
    con = connect()
    try:
        _um(con, sid)
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações")
    finally:
        con.close()
    try:
        r = _wp().h.get(f"{ROTA}/{int(sid)}/arquivo/{tipo}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, "O site não respondeu agora") from e
    ct = str((getattr(r, "headers", {}) or {}).get("content-type", "")).split(";")[0].strip()
    if r.status_code != 200 or ct not in ("application/pdf", "application/zip"):
        raise HTTPException(404, "Arquivo não encontrado")
    ext = "pdf" if ct == "application/pdf" else "zip"
    return Response(r.content, media_type=ct, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                                                       "Content-Disposition": f'attachment; filename="patrocinio-{int(sid)}-{tipo}.{ext}"'})
