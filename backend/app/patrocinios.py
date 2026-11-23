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
        out = coletar(con)
        out["autentique"] = conferir_pendentes(con)      # CAMP-PAT-AUTENTIQUE
        return out
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


def _detalhe(r, con=None) -> dict:
    d = json.loads(r["dados"]) if r["dados"] else {}
    d.update(_linha(r))
    if con is not None:
        d["autentique"] = _aut_info(con, int(r["site_id"]))
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
    if cod in ("camp_pat_pago", "camp_pat_consulta", "camp_mp_desligado", "camp_pat_etapa", "camp_pat_email"):
        return HTTPException(409, msg or "O site recusou.")
    if cod == "camp_pat_email_falhou":
        return HTTPException(502, msg or "O e-mail não saiu agora. Tente de novo em instantes.")
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
        return {"itens": filtrar(con, etapa, q), "etapas": ETAPAS, "autentique": {"ativo": aut.ativo(con), "max_pdf": aut.MAX_PDF}, "etapas_auto": list(ETAPAS_AUTO), "fluxo": FLUXO, "numeros": numeros(con),
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
        return _detalhe(_um(con, sid), con)
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
        return _detalhe(_um(con, sid), con)
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


# ---------------------------------------------------------------- CAMP-PAT-AUTENTIQUE: contrato pela Autentique (23/11/2026)
# Rafael: "sim, igual da doação no autentique, tem até lá já os dados salvos da api". Mesmo token/chave da doação (autentique.py).
# O painel cria o documento (o responsável entra por NOME: a Autentique não manda e-mail e devolve o link), o SITE manda o e-mail do
# contrato com o link (POST …/enviar-contrato, contrato 1.32, TR33 ou e-mail simples) e, se pedido, o link de pagamento junto.
# Quando todos assinam: etapa "Contrato assinado" (POST de sempre). PDF assinado: o painel só repassa da Autentique (não guarda).
RE_LINK = re.compile(r"^https?://[^\s/]+\.[^\s]+$", re.I)
SIT_AUT = {"criado": "Criado na Autentique (o e-mail ainda não saiu)", "pendente": "Aguardando assinaturas", "assinado": "Assinado por todos",
           "recusado": "Recusado na Autentique"}
ETAPAS_ANTES_ASSINADO = ("recebida", "em_conversa", "aguardando_pagamento", "contrato_enviado")   # passam a contrato_assinado
MSG_SITE_SEM_ENVIO = "O site ainda não manda o contrato do patrocínio: avise quem cuida do site (plugin da CAMP 1.41.0 ou mais novo). Nada foi enviado."


class EnvioContrato(BaseModel):
    contrato_link: str | None = None
    prazo: str | None = None
    pagamento: bool = False
    pdf_base64: str | None = None
    pdf_nome: str | None = None


def _pdf_do_corpo(con, b: EnvioContrato) -> bytes:
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
        raise HTTPException(409, "Os dados do responsável foram apagados (LGPD): não dá para mandar contrato.")
    sha = hashlib.sha256(pdf).hexdigest()
    v = con.execute("SELECT id, documento_id, link FROM patrocinio_autentique WHERE site_id=? AND situacao='criado' AND pdf_sha256=? ORDER BY id DESC LIMIT 1",
                    (sid, sha)).fetchone()
    if v and v["link"]:
        return {"linha": v["id"], "id": v["documento_id"], "link": v["link"], "reaproveitado": True}
    nome_doc = f"Contrato de patrocínio · {r['empresa'] or ''} · {r['protocolo'] or sid}".replace(" ·  · ", " · ")
    try:
        d = aut.criar_documento(aut.token(con), nome_doc, pdf, nome_arq, r["nome"] or (r["empresa"] or "Responsável da empresa"), aut.assinante_camp(con))
    except aut.ErroAutentique as e:
        registrar(logging.WARNING, "autentique_criar", "Autentique não criou o contrato do patrocínio", site_id=sid)
        raise HTTPException(502, f"{e} Nada foi enviado.") from e
    if not RE_LINK.match(d["link"]) or len(d["link"]) > 500:
        raise HTTPException(502, "A Autentique devolveu um link de assinatura estranho. Nada foi enviado: confira o documento na Autentique.")
    assin = [dict(x, papel="empresa" if x.get("papel") == "doador" else x.get("papel")) for x in d["assinantes"]]
    cur = con.execute("INSERT INTO patrocinio_autentique (site_id, documento_id, link, pdf_sha256, assinantes, situacao, criado_por) VALUES (?,?,?,?,?, 'criado', ?)",
                      (sid, d["id"], d["link"], sha, json.dumps(assin, ensure_ascii=False), ator))
    con.commit()                                  # o documento existe na Autentique: fica guardado mesmo se o e-mail falhar (reaproveita)
    registrar(logging.INFO, "autentique_criar", "Contrato do patrocínio criado na Autentique", site_id=sid)
    return {"linha": cur.lastrowid, "id": d["id"], "link": d["link"], "reaproveitado": False}


def _aut_info(con, sid: int) -> dict | None:
    try:
        v = con.execute("SELECT * FROM patrocinio_autentique WHERE site_id=? ORDER BY id DESC LIMIT 1", (int(sid),)).fetchone()
    except Exception:  # noqa: BLE001  (banco sem a migração 247)
        return None
    if not v:
        return None
    a = json.loads(v["assinantes"] or "[]")
    return {"documento_id": v["documento_id"], "situacao": v["situacao"], "situacao_nome": SIT_AUT.get(v["situacao"], v["situacao"]),
            "link": v["link"] or "", "assinantes": len(a), "assinaram": sum(1 for x in a if x.get("assinado_em")),
            "assinado_em": v["assinado_em"] or "", "criado_em": v["criado_em"], "conferido_em": v["conferido_em"] or "", "erro": v["erro"] or ""}


@router.post("/{sid}/enviar-contrato")
def enviar_contrato(sid: int, b: EnvioContrato, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Cria o contrato na Autentique (PDF anexado) ou usa o link colado; o site manda o e-mail com o link (e o de pagamento, se pedido)."""
    con = connect()
    try:
        r = _um(con, sid)
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações")
        pdf = _pdf_do_corpo(con, b) if b.pdf_base64 else None
        link = "" if pdf else (b.contrato_link or "").strip()
        if not pdf and not link:
            raise HTTPException(400, "Informe o link do contrato para assinatura" + (" ou anexe o PDF do contrato" if aut.ativo(con) else ""))
        if not pdf and (not RE_LINK.match(link) or len(link) > 500):
            raise HTTPException(400, "Link do contrato para assinatura: um endereço que comece com http:// ou https://")
        prazo = (b.prazo or "").strip()
        if prazo and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", prazo):
            raise HTTPException(400, "Prazo para assinar: uma data (AAAA-MM-DD)")
        ator = (u or {}).get("email") or "painel"
        doc_aut = None
        if pdf:
            doc_aut = _criar_na_autentique(con, r, pdf, b.pdf_nome or "", ator)
            link = doc_aut["link"]
        corpo = {"contrato_link": link, "pagamento": bool(b.pagamento), "autor_painel": _txt((u or {}).get("nome") or (u or {}).get("email") or "painel", 60)}
        if prazo:
            corpo["prazo"] = prazo
        try:
            resp = _wp().h.post(f"{ROTA}/{int(sid)}/enviar-contrato", json=corpo)
        except Exception as e:  # noqa: BLE001
            registrar(logging.WARNING, "patrocinios_contrato", "Envio do contrato: o site não respondeu", site_id=int(sid), erro=type(e).__name__)
            raise HTTPException(502, "O site não respondeu agora: nada foi enviado. Tente de novo em instantes") from e
        if resp.status_code >= 400:
            if resp.status_code == 404 and str(_json(resp).get("code") or "") in ("", "rest_no_route"):
                raise HTTPException(409, MSG_SITE_SEM_ENVIO)
            ex = _erro_site(resp)
            raise HTTPException(ex.status_code, ex.detail if str(ex.detail).endswith("enviado.") or "Nada foi" in str(ex.detail) else f"{ex.detail} Nada foi enviado.")
        d = _json(resp)
        if isinstance(d.get("registro"), dict):
            _gravar(con, d["registro"])
        if doc_aut:
            con.execute("UPDATE patrocinio_autentique SET situacao='pendente' WHERE id=?", (doc_aut["linha"],))
        con.commit()
        via = "pelo Sender (TR33)" if d.get("via") == "sender" else "como e-mail simples (o modelo TR33 ainda não tem ID no Sender)"
        msg = ("Contrato criado na Autentique e e-mail com o link de assinatura enviado " if doc_aut else "E-mail do contrato enviado ") + via + (
            ", com o link de pagamento." if d.get("link_pagamento") else ".")
        registrar(logging.INFO, "patrocinios_contrato", "Contrato do patrocínio enviado pelo painel", site_id=int(sid), autentique=bool(doc_aut), pagamento=bool(b.pagamento))
        return {"mensagem": msg, "patrocinio": _detalhe(_um(con, sid), con)}
    finally:
        con.close()


def _conferir_um(con, v, wp=None) -> dict:
    """Confere um documento pendente. Todos assinaram → etapa contrato_assinado (se ainda antes dela) + nota, pelo site. Levanta ErroAutentique."""
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
    con.execute("UPDATE patrocinio_autentique SET assinantes=?, conferido_em=?, erro=NULL WHERE id=?", (json.dumps(lista, ensure_ascii=False), agora, v["id"]))
    if any(s_["recusado_em"] for s_ in sigs):
        con.execute("UPDATE patrocinio_autentique SET situacao='recusado' WHERE id=?", (v["id"],))
        con.commit()
        return {"situacao": "recusado", "mensagem": "Alguém recusou o contrato na Autentique. A etapa não mudou: fale com a empresa."}
    if not sigs or not all(s_["assinado_em"] for s_ in sigs):
        con.commit()
        n = sum(1 for s_ in sigs if s_["assinado_em"])
        return {"situacao": "pendente", "mensagem": f"Ainda faltam assinaturas na Autentique ({n} de {len(sigs)} assinaram)."}
    dia = max(aut.data_iso(s_["assinado_em"]) for s_ in sigs)
    r = _um(con, sid)
    corpo = {"nota": f"Contrato assinado por todos na Autentique em {dia[8:10]}/{dia[5:7]}/{dia[:4]} (documento {v['documento_id']}).", "autor_painel": "Autentique (painel)"}
    if r["etapa"] in ETAPAS_ANTES_ASSINADO:
        corpo["etapa"] = "contrato_assinado"     # já pago ou adiante: só a nota (a etapa não volta)
    resp = (wp or _wp()).h.post(f"{ROTA}/{sid}", json=corpo)
    if resp.status_code >= 400:
        raise aut.ErroAutentique(f"Todos assinaram, mas o site não aceitou a etapa agora: {_erro_site(resp).detail}")
    d = _json(resp)
    if isinstance(d.get("registro"), dict):
        _gravar(con, d["registro"])
    con.execute("UPDATE patrocinio_autentique SET situacao='assinado', assinado_em=? WHERE id=?", (dia, v["id"]))
    con.commit()
    registrar(logging.INFO, "autentique_assinado", "Contrato do patrocínio assinado por todos na Autentique", site_id=sid)
    return {"situacao": "assinado", "assinado_em": dia, "mensagem": "Todos assinaram na Autentique: " + (
        "o patrocínio passou a Contrato assinado." if corpo.get("etapa") else "a assinatura ficou registrada nas notas.")}


def conferir_pendentes(con, wp=None) -> dict:
    """Na rodada: confere os documentos pendentes (só com a Autentique ligada e com token). Nunca levanta."""
    out = {"conferidos": 0, "assinados": 0, "erros": 0}
    try:
        if not aut.ativo(con):
            return out
        for v in con.execute("SELECT * FROM patrocinio_autentique WHERE situacao='pendente' ORDER BY id LIMIT 30").fetchall():
            try:
                res = _conferir_um(con, v, wp)
                out["conferidos"] += 1
                out["assinados"] += 1 if res["situacao"] == "assinado" else 0
            except Exception as e:  # noqa: BLE001
                out["erros"] += 1
                msg = str(e)[:300] if isinstance(e, aut.ErroAutentique) else "Não consegui conferir agora."
                con.execute("UPDATE patrocinio_autentique SET erro=?, conferido_em=datetime('now') WHERE id=?", (msg, v["id"]))
                con.commit()
                registrar(logging.WARNING, "autentique_conferir", "Conferência do contrato do patrocínio com problema", site_id=int(v["site_id"]), erro=type(e).__name__)
    except Exception as e:  # noqa: BLE001
        registrar(logging.WARNING, "autentique_conferir", "Conferência dos contratos de patrocínio com problema", erro=type(e).__name__)
    return out


@router.post("/{sid}/conferir-assinatura")
def conferir_assinatura(sid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        _um(con, sid)
        if not aut.ativo(con):
            raise HTTPException(409, "A assinatura eletrônica (Autentique) está desligada ou sem o token (Doações de acervo → Assinatura eletrônica).")
        v = con.execute("SELECT * FROM patrocinio_autentique WHERE site_id=? ORDER BY id DESC LIMIT 1", (int(sid),)).fetchone()
        if not v:
            raise HTTPException(404, "Este patrocínio não tem contrato na Autentique.")
        if v["situacao"] == "assinado":
            return {"situacao": "assinado", "mensagem": "Já estava assinado por todos.", "patrocinio": _detalhe(_um(con, sid), con)}
        try:
            res = _conferir_um(con, v)
        except aut.ErroAutentique as e:
            con.execute("UPDATE patrocinio_autentique SET erro=?, conferido_em=datetime('now') WHERE id=?", (str(e)[:300], v["id"]))
            con.commit()
            raise HTTPException(502, str(e)) from e
        res["patrocinio"] = _detalhe(_um(con, sid), con)
        return res
    finally:
        con.close()


@router.get("/{sid}/contrato-assinado")
def contrato_assinado(sid: int, u: dict = Depends(auth.exige("admin"))):
    """Repassa o PDF assinado da Autentique (não guarda no painel)."""
    con = connect()
    try:
        _um(con, sid)
        v = con.execute("SELECT documento_id FROM patrocinio_autentique WHERE site_id=? AND situacao='assinado' ORDER BY id DESC LIMIT 1", (int(sid),)).fetchone()
        if not v or not aut.ativo(con):
            raise HTTPException(404, "Ainda não há contrato assinado na Autentique.")
        tk = aut.token(con)
    finally:
        con.close()
    try:
        _sigs, url = aut.consultar_doc(tk, v["documento_id"])
        pdf = aut.baixar_assinado(tk, url)
    except aut.ErroAutentique as e:
        raise HTTPException(502, str(e)) from e
    return Response(pdf, media_type="application/pdf", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                                                                "Content-Disposition": f'attachment; filename="patrocinio-{int(sid)}-contrato-assinado.pdf"'})
