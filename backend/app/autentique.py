"""Assinatura eletrônica pela Autentique (CAMP-AUTENTIQUE, 20/11/2026). Rafael: ao clicar "Enviar contrato para assinatura" numa doação de
acervo, o contrato é criado sozinho na Autentique (plano grátis: 10 documentos por mês, API inclusa); quando todos assinam, a doação passa a
"Contrato assinado pelas partes" sozinha.

- API GraphQL v2: POST https://api.autentique.com.br/v2/graphql, `Authorization: Bearer <token>` (docs.autentique.com.br/api).
  · Testar conexão: `query { me { name email subscription { documents credits } } }` (só lê).
  · Criar: mutation `createDocument(document, signers, file)` (document.footer = BOTTOM: rodapé em todas as páginas) em multipart (graphql-multipart-request-spec: `operations`, `map`, `file`).
    Quem doa entra por NOME (não por e-mail): assim a Autentique NÃO manda e-mail a ela e devolve `link { short_link }`, que vai no NOSSO
    e-mail TR30 (rota enviar-contrato de sempre do site). Quem assina pela CAMP (opcional, `autentique.assinante_camp`) entra por e-mail:
    esse recebe o link da própria Autentique.
  · Conferir: `query { document(id) { signatures { public_id action { name } signed { created_at } rejected { created_at } } } }`.
    Assinatura sem `action` (o dono da conta, se a Autentique listar) não conta.
- Token sensível (configuracao.sensivel=1): nunca no log, nunca na resposta à tela (só "configurada: sim/não"). Tempo curto (20 s).
  Erros viram frases em português (token inválido, limite de documentos do mês, arquivo, muitas tentativas, Autentique sem resposta).
- Conferência em segundo plano no ritmo do coletor das doações (doacoes_acervo.coleta_min); nunca levanta. Nada de chamada de verdade
  nos testes: `_cliente` é trocado por um falso.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

import httpx

URL = os.environ.get("CAMP_AUTENTIQUE_URL") or "https://api.autentique.com.br/v2/graphql"   # a variável só serve ao teste de navegador (Autentique falsa)
TEMPO_S = 20
MAX_PDF = 5 * 1024 * 1024        # o plano grátis da Autentique aceita até 5 MB por arquivo (o profissional, 20 MB)

Q_ME = "query { me { name email subscription { documents credits } } }"
M_CRIAR = ("mutation CreateDocumentMutation($document: DocumentInput!, $signers: [SignerInput!]!, $file: Upload!) "
           "{ createDocument(document: $document, signers: $signers, file: $file) "
           "{ id name created_at signatures { public_id name email action { name } link { short_link } } } }")
Q_DOC = ("query { document(id: \"%s\") { id name signatures { public_id name email action { name } link { short_link } "
         "signed { created_at } rejected { created_at } } } }")

MSG_TOKEN = "A Autentique recusou o token: confira o token da API (perfil → API na Autentique) e cole de novo."
MSG_LIMITE = "Acabaram os documentos do mês na Autentique (plano grátis: 10 por mês): use o link colado ou espere o mês virar."


class ErroAutentique(Exception):
    """Frase pronta para a tela (nunca traz o token nem o corpo enviado)."""


def _cliente() -> httpx.Client:
    """Cliente HTTP (os testes trocam por um falso)."""
    return httpx.Client(timeout=TEMPO_S)


# ---------------------------------------------------------------- configuração
def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def token(con) -> str:
    try:
        return _cfg(con, "autentique.token").strip()
    except Exception:  # noqa: BLE001  (banco sem a migração 236)
        return ""


def ligado(con) -> bool:
    try:
        return _cfg(con, "autentique.ligado", "0").strip() in ("1", "true", "sim")
    except Exception:  # noqa: BLE001
        return False


def ativo(con) -> bool:
    """Ligado E com token: só assim o PDF aparece na prévia."""
    return ligado(con) and bool(token(con))


def assinante_camp(con) -> str:
    try:
        return _cfg(con, "autentique.assinante_camp").strip().lower()
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- chamadas
def _erro_graphql(erros) -> str:
    """Lista `errors` da Autentique → frase. Códigos de docs.autentique.com.br/api (Mensagens de erro)."""
    txt = json.dumps(erros, ensure_ascii=False).lower()
    if "unauthorized" in txt or "unauthenticated" in txt or "not authenticated" in txt:
        return MSG_TOKEN
    if "unavailable_credits" in txt or "run out of documents" in txt:
        return MSG_LIMITE
    if "must_be_a_valid_file" in txt or "must_be_a_file" in txt or "failed_to_upload" in txt or "could_not_upload_file" in txt:
        return "A Autentique não aceitou o arquivo: mande um PDF de até 5 MB."
    if "document_not_found" in txt or "document not found" in txt:
        return "O documento não existe mais na Autentique (foi apagado lá?)."
    if "must_be_a_valid_email_address" in txt:
        return "A Autentique recusou o e-mail de quem assina pela CAMP: confira em Assinatura eletrônica (Autentique)."
    if "without_permission" in txt or "not_a_member_of_organization" in txt:
        return "A conta da Autentique deste token não tem permissão para isso (precisa ser administradora da organização)."
    return "A Autentique recusou o pedido. Tente de novo; se continuar, confira o token e a conta na Autentique."


def _pedir(tk: str, **kw) -> dict:
    """Um POST na API. Devolve `data` ou levanta ErroAutentique com a frase. Nunca deixa o token sair na mensagem."""
    if not tk:
        raise ErroAutentique("Falta o token da Autentique: cole em Doações de acervo → Assinatura eletrônica (Autentique).")
    try:
        with _cliente() as cl:
            r = cl.post(URL, headers={"Authorization": f"Bearer {tk}", "Accept": "application/json"}, **kw)
    except httpx.TimeoutException as e:
        raise ErroAutentique("A Autentique demorou demais para responder (mais de 20 s). Nada foi enviado: tente de novo em instantes.") from e
    except Exception as e:  # noqa: BLE001
        raise ErroAutentique("Não consegui falar com a Autentique agora (rede ou Autentique sem resposta). Tente de novo em instantes.") from e
    st = r.status_code
    if st in (401, 403):
        raise ErroAutentique(MSG_TOKEN)
    if st == 429:
        raise ErroAutentique("Muitas tentativas seguidas na Autentique (limite de 60 por minuto). Espere um minuto e tente de novo.")
    if st == 413:
        raise ErroAutentique("A Autentique não aceitou o arquivo: mande um PDF de até 5 MB.")
    try:
        d = r.json()
    except Exception:  # noqa: BLE001
        d = None
    if not isinstance(d, dict):
        raise ErroAutentique(f"A Autentique respondeu {st} sem dados. Tente de novo em instantes.")
    if d.get("errors"):
        raise ErroAutentique(_erro_graphql(d["errors"]))
    if st >= 400:
        raise ErroAutentique(f"A Autentique respondeu {st}. Tente de novo em instantes.")
    return d.get("data") or {}


def testar(tk: str) -> dict:
    """Testar conexão: só lê a conta (`me`). Devolve nome/e-mail da conta e os documentos do plano (sem o token)."""
    me = (_pedir(tk, json={"query": Q_ME}).get("me") or {})
    if not me:
        raise ErroAutentique(MSG_TOKEN)
    sub = me.get("subscription") if isinstance(me.get("subscription"), dict) else {}
    return {"ok": True, "conta": str(me.get("name") or "")[:120], "email": str(me.get("email") or "")[:200],
            "documentos": sub.get("documents"), "creditos": sub.get("credits")}


def _assinaturas(lst) -> list[dict]:
    out = []
    for s in lst or []:
        if not isinstance(s, dict):
            continue
        act = s.get("action") if isinstance(s.get("action"), dict) else None
        out.append({"public_id": str(s.get("public_id") or ""), "nome": str(s.get("name") or ""), "email": str(s.get("email") or "").lower(),
                    "acao": str((act or {}).get("name") or ""), "link": str(((s.get("link") or {}) if isinstance(s.get("link"), dict) else {}).get("short_link") or ""),
                    "assinado_em": str(((s.get("signed") or {}) if isinstance(s.get("signed"), dict) else {}).get("created_at") or ""),
                    "recusado_em": str(((s.get("rejected") or {}) if isinstance(s.get("rejected"), dict) else {}).get("created_at") or "")})
    return out


def criar_documento(tk: str, nome_doc: str, pdf: bytes, nome_arquivo: str, nome_doador: str, email_camp: str = "") -> dict:
    """Cria o documento com quem doa (por NOME: sem e-mail da Autentique, volta o link) e, se houver, quem assina pela CAMP (por e-mail).
    Devolve {id, link (de quem doa), assinantes: [{public_id, papel}]}."""
    signers = [{"name": nome_doador[:120] or "Quem doa o acervo", "action": "SIGN"}]
    if email_camp:
        signers.append({"email": email_camp, "action": "SIGN"})
    # Rodapé de autenticação em todas as páginas (Rafael 20/11/2026: "rodapé em todas"): ninguém troca uma página do meio.
    doc_in = {"name": nome_doc[:180], "footer": "BOTTOM"}
    ops = {"query": M_CRIAR, "variables": {"document": doc_in, "signers": signers, "file": None}}
    arq = re.sub(r"[^\w.\- ]", "_", nome_arquivo or "contrato.pdf")[:100] or "contrato.pdf"
    if not arq.lower().endswith(".pdf"):
        arq += ".pdf"
    d = _pedir(tk, data={"operations": json.dumps(ops, ensure_ascii=False), "map": json.dumps({"file": ["variables.file"]})},
               files={"file": (arq, pdf, "application/pdf")})
    doc = d.get("createDocument") if isinstance(d.get("createDocument"), dict) else None
    if not doc or not doc.get("id"):
        raise ErroAutentique("A Autentique não devolveu o documento criado. Confira na Autentique antes de tentar de novo.")
    sigs = [s for s in _assinaturas(doc.get("signatures")) if s["acao"]]
    doador = next((s for s in sigs if s["link"] and (not email_camp or s["email"] != email_camp)), None)
    if not doador:
        raise ErroAutentique("A Autentique criou o documento mas não devolveu o link de assinatura. Abra o documento na Autentique e cole o link.")
    assin = [{"public_id": s["public_id"], "papel": "doador" if s is doador else "camp"} for s in sigs]
    return {"id": str(doc["id"]), "link": doador["link"], "assinantes": assin}


def consultar(tk: str, doc_id: str) -> list[dict]:
    """As assinaturas do documento (só as que têm ação: o dono da conta sem ação não conta)."""
    did = re.sub(r"[^A-Za-z0-9_-]", "", str(doc_id or ""))[:80]   # vai literal na query (o tipo do argumento muda entre versões da API)
    if not did:
        raise ErroAutentique("Documento da Autentique sem id.")
    d = _pedir(tk, json={"query": Q_DOC % did})
    doc = d.get("document") if isinstance(d.get("document"), dict) else None
    if not doc:
        raise ErroAutentique("O documento não existe mais na Autentique (foi apagado lá?).")
    return [s for s in _assinaturas(doc.get("signatures")) if s["acao"]]


def data_iso(v: str) -> str:
    """created_at da Autentique ("2026-11-20 14:03:00", ISO com fuso ou "20/11/2026 …") → AAAA-MM-DD (horário de Brasília)."""
    s = str(v or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
        return m.group(1) if m else ""
    if d.tzinfo:
        from zoneinfo import ZoneInfo
        try:
            d = d.astimezone(ZoneInfo("America/Sao_Paulo"))
        except Exception:  # noqa: BLE001
            d = d.astimezone(timezone.utc)
    return d.strftime("%Y-%m-%d")
