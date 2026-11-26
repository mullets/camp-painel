"""E-mails do site (CAMP-SENDER, 20/11/2026). Rafael: "Cria uma página de configuração de TODOS os e-mails transacionais do site, mais
fácil do que ficar onde está hoje."

Antes os IDs dos modelos do Sender ficavam em dois lugares: TR04–TR09 em Configurações → E-mail e avisos (iam ao site por
POST /wp-json/camp/v1/painel/sender) e TR10–TR29 na administração do site. Agora há uma tela só (menu E-mails → aba Modelos do Sender; CAMP-EMAIL 20/11 juntou as três telas de e-mail):
- O SITE guarda (fonte única: opção camp_aap_sender). GET /painel/sender (contrato 1.23, campos opcionais) devolve o catálogo de todos os
  modelos (TR, área, nome, quando sai, para quem, variáveis, o que acontece sem ID, ID atual, situação), de onde vem a chave do Sender
  (site | plugin; nunca o token) e a chave de emergência. POST /painel/sender {"templates": {chave: ID}} grava um ID (vazio não muda,
  "__limpar__" deixa sem ID, regra do hub). POST /painel/sender/teste {chave, para} manda o modelo com valores de exemplo.
- Site antigo (sem "catalogo"): a tela mostra o que dá (TR04–TR31 com os IDs que o site devolver) e pede "atualize o site".
- TR04–TR09: ao gravar aqui, a configuração antiga do painel (sender.tr04_… em Configurações) passa a ter o mesmo valor, para que o botão
  "Enviar a configuração do Sender ao site" nunca devolva ao site um ID velho.
- "Último envio" e falhas em 30 dias vêm de E-mails enviados (emails_enviados.todas: email_site + o que saiu do painel).
Só admin e master (a tela mostra e-mails de teste e mexe no que sai para o público). O token nunca passa por aqui: só a origem.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api/emails-site", tags=["emails_site"])

ROTA = "/wp-json/camp/v1/painel/sender"
ROTA_TESTE = "/wp-json/camp/v1/painel/sender/teste"
LIMPAR = "__limpar__"
RE_ID = re.compile(r"^[A-Za-z0-9]{3,32}$")
RE_CHAVE = re.compile(r"^[a-z0-9_]{2,40}$")
SENDER_URL = "https://app.sender.net/"          # o Sender não tem endereço público conhecido por modelo: abre o app (menu Transactional emails)
GUIA_DIR = Path(__file__).resolve().parents[2] / "docs" / "sender-modelos"
AREAS = ["Pedidos e visitas", "Cursos e inscrições", "Amigos da CAMP", "Área do Amigo", "Ingressos", "Cobranças e doações", "Acervo"]
SEM_ID = {"simples": "sai o e-mail simples do site", "nao_sai": "não sai nada (o painel avisa qual modelo falta)",
          "login": "o link de entrada não sai e a área do Amigo não abre", "painel": "quem manda é o painel, com o ID de Configurações",
          "nao_usado": "nenhum envio usa hoje"}
# Site antigo (sem "catalogo"): o mínimo para a tela não ficar vazia. A lista de verdade vem do site (Camp_AAP_Sender::CATALOGO).
CATALOGO_PAINEL = [
    ("TR04", "solicitacao_recebida", "Pedidos e visitas", "Pedido recebido", "simples"),
    ("TR05", "pdf_disponivel", "Acervo", "PDF disponível", "nao_usado"),
    ("TR06", "visita_solicitada", "Pedidos e visitas", "Visita solicitada", "simples"),
    ("TR07", "visita_confirmada", "Pedidos e visitas", "Visita confirmada", "simples"),
    ("TR08", "inscricao_recebida", "Cursos e inscrições", "Inscrição recebida", "simples"),
    ("TR09", "material_download", "Acervo", "Material para download", "painel"),
    ("TR10", "amigo_pre_adesao", "Amigos da CAMP", "Pré-adesão (pagamento desligado)", "simples"),
    ("TR11", "amigo_adesao", "Amigos da CAMP", "Adesão: falta o pagamento", "simples"),
    ("TR12", "amigo_boas_vindas", "Amigos da CAMP", "Pagamento confirmado: boas-vindas", "simples"),
    ("TR13", "amigo_recusado", "Amigos da CAMP", "Pagamento recusado", "simples"),
    ("TR14", "apoio_recebido", "Amigos da CAMP", "Proposta de apoio recebida", "simples"),
    ("TR15", "amigo_cobranca", "Amigos da CAMP", "Cobrança", "nao_sai"),
    ("TR16", "amigo_pendente", "Amigos da CAMP", "Pagamento pendente", "nao_sai"),
    ("TR17", "amigo_lembrete_30", "Amigos da CAMP", "Lembrete de renovação (faltam mais de 7 dias)", "nao_sai"),
    ("TR18", "amigo_lembrete_7", "Amigos da CAMP", "Lembrete de renovação (faltam 7 dias ou menos)", "nao_sai"),
    ("TR19", "amigo_vencido", "Amigos da CAMP", "Aviso de vencimento", "nao_sai"),
    ("TR20", "amigo_recibo", "Amigos da CAMP", "Recibo simples", "nao_sai"),
    ("TR21", "amigo_livre", "Amigos da CAMP", "Texto livre", "nao_sai"),
    ("TR22", "amigo_acesso", "Área do Amigo", "Link de acesso à área do Amigo", "login"),
    ("TR23", "ingresso_visita", "Ingressos", "Ingresso da visita (Residência João Marino)", "simples"),
    ("TR24", "amigo_categoria_pedida", "Área do Amigo", "Mudança de categoria registrada", "nao_sai"),
    ("TR25", "amigo_categoria_cancelada", "Área do Amigo", "Mudança de categoria cancelada", "nao_sai"),
    ("TR26", "amigo_nao_renovar", "Área do Amigo", "Renovação encerrada", "nao_sai"),
    ("TR27", "cobranca_avulsa", "Cobranças e doações", "Cobrança avulsa", "nao_sai"),
    ("TR28", "doacao_recebida", "Cobranças e doações", "Intenção de doação de acervo recebida", "simples"),
    ("TR29", "ingresso_cobranca", "Ingressos", "Ingresso da visita: link de pagamento", "nao_sai"),
    ("TR30", "contrato_assinatura", "Cobranças e doações", "Contrato para assinatura", "nao_sai"),      # CAMP-DOA-CONTRATO (contrato 1.25)
    ("TR31", "doacao_andamento", "Cobranças e doações", "Andamento da doação", "nao_sai"),              # CAMP-DOA-AVISOS (contrato 1.25)
]
CRITICOS = {"amigo_acesso", "amigo_cobranca", "cobranca_avulsa", "amigo_boas_vindas", "contrato_assinatura"}
CAMPOS_MODELO = ("tr", "chave", "area", "nome", "quando", "para", "variaveis", "sem_id", "sem_id_texto", "critico", "id", "id_padrao", "situacao")
SITUACOES = ("ativo", "sem_id", "sem_chave", "emergencia")
ATUALIZE = "Atualize o site (plugin da CAMP 1.32.0 ou mais novo) para ver e configurar todos os modelos aqui."


class SiteSemRota(RuntimeError):
    """O site não tem a rota pedida (404): plugin antigo."""


def _wp():
    """Cliente do site (os testes trocam por um falso)."""
    return __import__("app.wp", fromlist=["WP"]).WP()


def _config_painel() -> dict:
    """chave do modelo no site -> chave em `configuracao` (só TR04–TR09, os que o painel guardava)."""
    from .wp import SENDER_MODELOS
    return {v: k for k, v in SENDER_MODELOS.items()}


# ---------------------------------------------------------------- site → painel (sempre sem o token)
def _txt(v, n: int = 400) -> str:
    return str(v if v is not None else "").strip()[:n]


def _modelo_limpo(x: dict) -> dict | None:
    """Só os campos conhecidos do catálogo; nada que possa ser o token passa."""
    if not isinstance(x, dict) or not RE_CHAVE.match(str(x.get("chave") or "")):
        return None
    m = {k: x.get(k) for k in CAMPOS_MODELO}
    m["chave"] = str(m["chave"])
    for k in ("tr", "area", "nome", "quando", "para", "sem_id", "sem_id_texto", "id", "id_padrao", "situacao"):
        m[k] = _txt(m[k])
    m["variaveis"] = [str(v) for v in (x.get("variaveis") or []) if re.fullmatch(r"[a-z0-9_]{1,40}", str(v))]
    m["critico"] = bool(x.get("critico"))
    if m["situacao"] not in SITUACOES:
        m["situacao"] = "sem_id" if not m["id"] else "ativo"
    if not m["sem_id_texto"]:
        m["sem_id_texto"] = SEM_ID.get(m["sem_id"], "")
    return m


def _estado_limpo(j) -> dict:
    if not isinstance(j, dict):
        raise RuntimeError("O site respondeu num formato inesperado")
    tpl = j.get("templates") if isinstance(j.get("templates"), dict) else {}
    cat = [m for m in (_modelo_limpo(x) for x in (j.get("catalogo") or []) if isinstance(j.get("catalogo"), list)) if m]
    origem = str(j.get("token_origem") or "")
    return {"token_preenchido": bool(j.get("token_preenchido")), "token_origem": origem if origem in ("site", "plugin", "") else "",
            "tem_origem": "token_origem" in j, "emergencia": bool(j.get("emergencia")), "teste": bool(j.get("teste")),
            "templates": {str(k): _txt(v, 64) for k, v in tpl.items() if RE_CHAVE.match(str(k))}, "catalogo": cat}


def _ler_site(w) -> dict:
    r = w.h.get(ROTA)
    if r.status_code == 404:
        raise SiteSemRota("O site ainda não recebe a configuração do Sender: atualize o site.")
    if r.status_code == 401:
        raise RuntimeError("O site recusou as credenciais (401). Confira usuário e senha de aplicativo do site em Configurações")
    if r.status_code >= 400:
        raise RuntimeError(f"O site recusou mostrar a configuração do Sender ({r.status_code})")
    try:
        return _estado_limpo(r.json())
    except ValueError:
        raise RuntimeError("O site respondeu num formato inesperado")


def _catalogo_antigo(templates: dict, token: bool, emergencia: bool) -> list[dict]:
    out = []
    for tr, chave, area, nome, sem in CATALOGO_PAINEL:
        id_ = templates.get(chave, "")
        out.append({"tr": tr, "chave": chave, "area": area, "nome": nome, "quando": "", "para": "", "variaveis": [], "sem_id": sem,
                    "sem_id_texto": SEM_ID[sem], "critico": chave in CRITICOS, "id": id_, "id_padrao": "",
                    "situacao": "emergencia" if emergencia else ("sem_chave" if not token else ("ativo" if id_ else "sem_id"))})
    return out


def _envios(con) -> dict:
    """Por modelo, nos últimos 30 dias: último envio (data e situação), enviados e falhas (falhou ou não saiu pelo Sender)."""
    from . import emails_enviados as ee
    try:
        a, _b = ee._periodo("30", None, None)
        itens = ee.todas(con, a, "")
    except Exception:                       # noqa: BLE001 — sem a tabela ou sem dados: a coluna fica vazia, a tela segue
        return {}
    out: dict[str, dict] = {}
    for x in itens:                          # mais novos primeiro
        k = x.get("modelo") or ""
        if not k:
            continue
        e = out.setdefault(k, {"ultimo": x.get("em") or "", "ultimo_situacao": x.get("situacao") or "", "ultimo_motivo": "",
                               "enviados": 0, "falhas": 0, "nao_sender": 0})
        if e["ultimo_situacao"] != "enviado" and not e["ultimo_motivo"]:
            e["ultimo_motivo"] = _txt(x.get("motivo"), 200)
        s = x.get("situacao")
        if s == "enviado":
            e["enviados"] += 1
        elif s == "falhou":
            e["falhas"] += 1
        elif s == "nao_sender":
            e["nao_sender"] += 1
    return out


def montar(con, w=None) -> dict:
    """O que a tela mostra. Nunca levanta por causa do site: diz o que houve em `site` e `aviso`."""
    out = {"site": "ok", "site_antigo": False, "aviso": "", "token": {"preenchido": False, "origem": "", "conhecida": False},
           "emergencia": False, "teste": False, "modelos": [], "areas": AREAS, "sender_url": SENDER_URL, "numeros": {}}
    try:
        e = _ler_site(w or _wp())
        out["token"] = {"preenchido": e["token_preenchido"] or e["token_origem"] in ("site", "plugin"),
                        "origem": e["token_origem"], "conhecida": e["tem_origem"]}
        out["emergencia"], out["teste"] = e["emergencia"], e["teste"]
        if e["catalogo"]:
            out["modelos"] = e["catalogo"]
        else:
            out["site_antigo"], out["aviso"] = True, ATUALIZE
            out["modelos"] = _catalogo_antigo(e["templates"], e["token_preenchido"], e["emergencia"])
    except SiteSemRota:
        out.update(site="sem_rota", site_antigo=True, aviso=ATUALIZE, modelos=_catalogo_antigo({}, False, False))
        for m in out["modelos"]:
            m["situacao"] = ""
    except Exception as ex:                  # noqa: BLE001 — frase, nunca o erro cru
        msg = str(ex) if isinstance(ex, RuntimeError) else f"Não consegui falar com o site ({type(ex).__name__})"
        out.update(site="erro", aviso=msg[:300], modelos=_catalogo_antigo({}, False, False))
        for m in out["modelos"]:
            m["situacao"] = ""
    env = _envios(con)
    vazio = {"ultimo": "", "ultimo_situacao": "", "ultimo_motivo": "", "enviados": 0, "falhas": 0, "nao_sender": 0}
    for m in out["modelos"]:
        m["envios"] = env.get(m["chave"], dict(vazio))
    usados = [m for m in out["modelos"] if m["sem_id"] != "nao_usado"]
    out["numeros"] = {"total": len(out["modelos"]), "ativos": sum(m["situacao"] == "ativo" for m in usados),
                      "faltando": sum(not m["id"] for m in usados if m["sem_id"] != "painel"),
                      "criticos": sum(1 for m in usados if m["critico"] and m["situacao"] != "ativo"),
                      "criticos_lista": [m["tr"] for m in usados if m["critico"] and m["situacao"] != "ativo"],
                      "falhas_30": sum(m["envios"]["falhas"] + m["envios"]["nao_sender"] for m in out["modelos"])}
    return out


def _erro_site_http(e: Exception) -> HTTPException:
    if isinstance(e, SiteSemRota):
        return HTTPException(409, f"O site ainda não tem esta função: {ATUALIZE[0].lower()}{ATUALIZE[1:]}")
    if isinstance(e, RuntimeError):
        return HTTPException(502, str(e)[:300])
    return HTTPException(502, f"Não consegui falar com o site ({type(e).__name__}). Nada mudou no site.")


def salvar_id(con, chave: str, valor: str, ator: str, w=None) -> dict:
    """Grava no site o ID de um modelo. Vazio = deixar sem ID ("__limpar__"). Devolve o modelo como o site ficou."""
    chave = (chave or "").strip()
    valor = (valor or "").strip()
    if not RE_CHAVE.match(chave):
        raise HTTPException(400, "Modelo desconhecido")
    if valor and not RE_ID.match(valor):
        raise HTTPException(400, "ID inválido: só letras e números, de 3 a 32 (como egx4Z6)")
    w = w or _wp()
    enviar = valor or LIMPAR
    try:
        r = w.h.post(ROTA, json={"templates": {chave: enviar}})
    except Exception as e:                   # noqa: BLE001
        raise _erro_site_http(e)
    if r.status_code == 404:
        raise _erro_site_http(SiteSemRota())
    if r.status_code == 400 and not valor:
        raise HTTPException(409, "Este site ainda não sabe deixar um modelo sem ID: " + ATUALIZE[0].lower() + ATUALIZE[1:])
    if r.status_code == 401:
        raise HTTPException(502, "O site recusou as credenciais (401). Confira usuário e senha de aplicativo do site em Configurações")
    if r.status_code >= 400:
        try:
            msg = _txt((r.json() or {}).get("erro"), 200)
        except ValueError:
            msg = ""
        raise HTTPException(502, f"O site recusou o ID ({r.status_code}){': ' + msg if msg else ''}")
    try:
        e = _estado_limpo(r.json())
    except (ValueError, RuntimeError):
        raise HTTPException(502, "O site respondeu num formato inesperado")
    ficou = e["templates"].get(chave, valor)
    cfg = _config_painel().get(chave)
    if cfg:                                  # TR04–TR09: a configuração antiga do painel acompanha (o botão antigo não volta o ID velho)
        con.execute("UPDATE configuracao SET valor=?, atualizado_em=datetime('now'), atualizado_por=? WHERE chave=?", (valor, ator, cfg))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('config','sender','sender_modelo_salvo',?,?)",
                (ator, json.dumps({"modelo": chave, "id": valor or "(sem ID)"}, ensure_ascii=False)))
    con.commit()
    modelo = next((m for m in e["catalogo"] if m["chave"] == chave), None)
    return {"ok": True, "chave": chave, "id": ficou, "modelo": modelo, "site_antigo": not e["catalogo"]}


def testar(chave: str, para: str, w=None) -> dict:
    """Pede ao site que mande o modelo `chave` a `para` com valores de exemplo (só pelo Sender)."""
    if not RE_CHAVE.match(chave or ""):
        raise HTTPException(400, "Modelo desconhecido")
    para = (para or "").strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", para) or len(para) > 200:
        raise HTTPException(400, "E-mail de destino inválido")
    w = w or _wp()
    try:
        r = w.h.post(ROTA_TESTE, json={"chave": chave, "para": para})
    except Exception as e:                   # noqa: BLE001
        raise _erro_site_http(e)
    if r.status_code == 404:
        raise _erro_site_http(SiteSemRota())
    try:
        d = r.json() or {}
    except ValueError:
        d = {}
    d = d if isinstance(d, dict) else {}
    if r.status_code == 200 and d.get("enviado"):
        return {"ok": True, "enviado": True, "tr": _txt(d.get("tr"), 8), "para": para, "email_id": _txt(d.get("email_id"), 64)}
    erro = _txt(d.get("erro"), 300) or f"O site respondeu {r.status_code}"
    raise HTTPException(409 if r.status_code in (400, 409) else 502, erro)


def _md_modelo(m: dict) -> str:
    """O guia de um modelo: o texto do guia da CAMP (docs/sender-modelos/), com o lugar de colar o ID de agora e as variáveis que o site
    manda hoje; sem arquivo, gerado do catálogo."""
    arq = next(iter(sorted(GUIA_DIR.glob(f"{m['tr']}-*.md"))), None) if m.get("tr") else None
    vars_ = ", ".join("{{" + v + "}}" for v in m.get("variaveis") or [])
    onde = (f"5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **{m['tr']}** e clique em **Salvar**. "
            "Depois use **Enviar teste** (vai para o seu e-mail, com valores de exemplo).")
    if arq:
        t = arq.read_text(encoding="utf-8")
        t = re.sub(r"(?m)^5\. .*$", onde.replace("\\", "\\\\"), t, count=1)
    else:
        linhas = [f"# {m['tr']} · {m['nome']}", "", f"**Chave no sistema:** `{m['chave']}`", "", "## Para que serve", m.get("quando") or "—", "",
                  "## Para quem vai", m.get("para") or "—", "", "## Variáveis"]
        linhas += [f"- `{{{{{v}}}}}`" for v in m.get("variaveis") or []] or ["Nenhuma."]
        linhas += ["", "## Como cadastrar", "", "1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.",
                   "2. Escreva as variáveis **exatamente** como na lista, com chaves duplas.", "3. Salve e copie o **ID** do e-mail.", "4. —", onde]
        t = "\n".join(linhas) + "\n"
    rodape = [f"\n## Situação no site ({datetime.now(timezone.utc).strftime('%d/%m/%Y')})",
              f"- ID atual: {'`' + m['id'] + '`' if m.get('id') else 'sem ID'}",
              f"- Sem ID: {m.get('sem_id_texto') or SEM_ID.get(m.get('sem_id'), '')}"]
    if vars_:
        rodape.append(f"- Variáveis que o site manda hoje: {vars_}")
    return t.rstrip() + "\n" + "\n".join(rodape) + "\n"


def guia_zip(dados: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        tab = ["# E-mails da CAMP no Sender", "", "Um arquivo por modelo. Onde colar o ID de qualquer modelo: painel → menu **E-mails** → aba **Modelos do Sender**.", "",
               "| Modelo | Área | Situação | ID | Arquivo |", "|---|---|---|---|---|"]
        rot = {"ativo": "Ativo", "sem_id": "Sem ID", "sem_chave": "Sem chave do Sender", "emergencia": "Sender desligado", "": "—"}
        for m in dados["modelos"]:
            nome = f"{m['tr']}-{m['chave']}.md" if m.get("tr") else f"{m['chave']}.md"
            z.writestr(nome, _md_modelo(m))
            tab.append(f"| {m['tr']} · {m['nome']} | {m['area']} | {rot.get(m['situacao'], m['situacao'])} | {m['id'] or '—'} | [{nome}]({nome}) |")
        if dados.get("aviso"):
            tab += ["", f"**Atenção:** {dados['aviso']}"]
        z.writestr("00-LEIA-ME.md", "\n".join(tab) + "\n")
    return buf.getvalue()


# ---------------------------------------------------------------- telas (só admin e master)
class IdModelo(BaseModel):
    id: str = ""


class Teste(BaseModel):
    para: str = ""


@router.get("")
def ver(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        d = montar(con)
        d["eu"] = u.get("email") or ""
        return d
    finally:
        con.close()


@router.get("/guia.zip")
def baixar_guia(u: dict = Depends(auth.exige("admin"))):
    con = connect()
    try:
        corpo = guia_zip(montar(con))
    finally:
        con.close()
    return Response(corpo, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="guia-modelos-sender.zip"'})


class IdPainel(BaseModel):
    id: str = ""


@router.get("/painel/entrega-cobranca")
def ver_entrega_cobranca(u: dict = Depends(auth.exige("admin"))) -> dict:
    """CAMP-ENTREGA (26/11/2026): o modelo PRÓPRIO do painel para a entrega com cobrança (não é do site): o ID e as variáveis para colar no Sender."""
    from .entrega import CAMPANHA_COBRANCA, VARIAVEIS_COBRANCA
    con = connect()
    try:
        r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (CAMPANHA_COBRANCA,)).fetchone()
        return {"chave": CAMPANHA_COBRANCA, "id": (r[0] if r else "") or "", "variaveis": list(VARIAVEIS_COBRANCA)}
    finally:
        con.close()


@router.put("/painel/entrega-cobranca")
def salvar_entrega_cobranca(b: IdPainel, u: dict = Depends(auth.exige("admin"))) -> dict:
    from .entrega import CAMPANHA_COBRANCA
    novo = (b.id or "").strip()
    if novo and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", novo):
        raise HTTPException(400, "Isso não parece um ID do Sender.net (letras, números, - e _).")
    con = connect()
    try:
        r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (CAMPANHA_COBRANCA,)).fetchone()
        if r is None:
            raise HTTPException(409, "Falta a migração 265 (atualize o painel).")
        con.execute("UPDATE configuracao SET valor=?, atualizado_em=datetime('now'), atualizado_por=? WHERE chave=?", (novo, u["email"], CAMPANHA_COBRANCA))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('config',?,'alterada',?,?)",
                    (CAMPANHA_COBRANCA, u["email"], json.dumps({"antes": {"valor": r[0] or ""}, "depois": {"valor": novo}}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "id": novo}
    finally:
        con.close()


@router.put("/{chave}")
def salvar(chave: str, b: IdModelo, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return salvar_id(con, chave, b.id, u["email"])
    finally:
        con.close()


@router.post("/{chave}/teste")
def enviar_teste(chave: str, b: Teste, u: dict = Depends(auth.exige("admin"))) -> dict:
    r = testar(chave, b.para or u.get("email") or "")
    con = connect()
    try:
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('config','sender','sender_teste',?,?)",
                    (u["email"], json.dumps({"modelo": chave, "enviado": True}, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    return r
