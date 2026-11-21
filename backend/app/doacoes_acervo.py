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
- CAMP-DOA-TEXTO (20/11/2026, sem mudar o contrato com o site): "Copiar dados para o contrato". GET …/{id}/texto (só admin) monta, em texto
  simples, cabeçalho, dados da pessoa, cada pergunta do formulário do site com a resposta, os dados combinados pela equipe e, só com
  ?notas=1, as notas internas. Anonimizada: "dados apagados (LGPD)" no lugar dos dados pessoais.
- CAMP-DOA-CPF (contrato 1.26, site 1.35.0; Rafael: "coloque no formulario do site, importante.. rg nao precisa, nem estado civil e
  nacionalidade.." e "o valor de doação é bom vir do formulário do site já"). O registro do site traz, OPCIONAIS, `documento` (só dígitos),
  `documento_tipo` (cpf|cnpj), `endereco` {cep, logradouro, numero, complemento, bairro, cidade, uf}, `valor_proposto` e `valor_combinar`;
  ficam em `dados` (sem coluna nova). O detalhe mostra (só admin) e a equipe corrige documento e endereço: vão ao site no POST …/{id} de
  sempre, validados aqui do mesmo jeito (dígitos verificadores, CEP de 8 dígitos, UF). O texto para o contrato ganha "CPF: …"/"CNPJ: …",
  "Endereço: …" e as perguntas novas. LGPD apaga documento e endereço. Site antigo: sem os campos, nada muda (o texto só omite as linhas).
- CAMP-DOA-IMPORTAR (contrato 1.27, site 1.36.0; Rafael: "pode registrar todos, mas não enviaremos email, e a raquel já tá aí"). "Importar
  ficha (CSV do Google Forms)": o CSV da antiga "Ficha de Doação de Acervo" é lido AQUI (BOM, campos com várias linhas, carimbo de
  Brasília), SIMULADO por padrão (linha a linha: vai criar / vai completar (campos vazios) / já igual, com os avisos) e, em "Importar",
  cada linha vai ao site em POST …/importar (cria a intenção, origem ficha_google, NENHUM e-mail; ou completa só o vazio da que já existe,
  achada pelo e-mail). Idempotente pela chave (e-mail + carimbo). O CSV não fica guardado; nada de nome/CPF no log técnico.
- CAMP-DOA-LISTA (21/11/2026, Rafael: "ele sumiu da lista de doações", sem mudar o contrato com o site). "Pedem ação" (o filtro padrão) vai
  até o acervo chegar: só recebido, nao_aprovada e arquivada saem (antes "paga" saía, e com a cobrança junto do contrato a doação costuma
  ser paga antes da assinatura). Na conferência da Autentique, se o site recusar voltar a etapa (cópia daqui atrasada: já paga), vai só a data.
- CAMP-DOA-FUNDO (21/11/2026, Rafael: "e precisa criar quando terminar o fundo e arquiteto automaticamente."; sem mudar o contrato com o site):
  ao passar a "Acervo recebido pela CAMP", POST …/{id}/receber (prévia simulada; com aplicar, cria) — ver a seção no fim deste arquivo.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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
# CAMP-DOA-LISTA (21/11/2026, Rafael: "ele sumiu da lista de doações"): com a cobrança indo junto do contrato, a doação costuma chegar a "paga"
# antes (ou perto) da assinatura, e "paga" não estava aqui: sumia do "Pedem ação" com o acervo ainda por receber. Agora pede ação tudo o que
# não é final: só "Acervo recebido", "Não aprovada" e "Arquivada" saem da lista padrão.
FINAIS = ("recebido", "nao_aprovada", "arquivada")
ABERTAS = tuple(k for k in ETAPAS if k not in FINAIS)   # pedem ação da equipe (inclui "paga": falta receber o acervo)
MINIMO = 1000.0
# CAMP-DOA-CPF (contrato 1.26): dados pessoais que o LGPD apaga em `dados` (o endereço, um dict, também)
PESSOAIS_DADOS = ("nome", "email", "telefone", "descricao", "local", "fotos_link", "autor", "documento", "documento_tipo")
UFS = ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO")
ENDERECO = {"cep": 8, "logradouro": 200, "numero": 20, "complemento": 100, "bairro": 100, "cidade": 100, "uf": 2}
COMBINAR = "A combinar com a equipe"
VERSAO_CPF_SITE = "1.35.0"


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
        for k in PESSOAIS_DADOS:
            d[k] = ""
        d["endereco"] = None
        d["ficha"] = []                                  # CAMP-DOA-IMPORTAR: as respostas da ficha têm CPF, endereço, nome
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
    # CAMP-DOA-CPF: prontos para a tela (vazios nas intenções antigas)
    d["documento_fmt"] = documento_txt(d)
    d["endereco_fmt"] = endereco_txt(d.get("endereco"))
    d["valor_proposto_fmt"] = valor_proposto_txt(d)
    d["ufs"] = list(UFS)
    return d


# ---------------------------------------------------------------- CAMP-DOA-CPF: documento, endereço e valor proposto
def _digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def cpf_ok(d: str) -> bool:
    if not re.fullmatch(r"\d{11}", d or "") or len(set(d)) == 1:
        return False
    for t in (9, 10):
        s_ = sum(int(d[i]) * (t + 1 - i) for i in range(t))
        if (s_ * 10 % 11) % 10 != int(d[t]):
            return False
    return True


def cnpj_ok(d: str) -> bool:
    if not re.fullmatch(r"\d{14}", d or "") or len(set(d)) == 1:
        return False
    w = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for t in (12, 13):
        r_ = sum(int(d[i]) * w[i + 13 - t] for i in range(t)) % 11
        if (0 if r_ < 2 else 11 - r_) != int(d[t]):
            return False
    return True


def documento_de(v) -> tuple[str, str] | None:
    """CPF/CNPJ com ou sem pontuação → (dígitos, "cpf"|"cnpj"); dígitos verificadores errados → None."""
    d = _digitos(v)
    return (d, "cpf") if cpf_ok(d) else ((d, "cnpj") if cnpj_ok(d) else None)


def documento_fmt(d: str) -> str:
    d = str(d or "")
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return d


def documento_txt(d: dict) -> str:
    """"CPF: 123.456.789-09" / "CNPJ: 12.345.678/0001-95" ou "" (sem documento)."""
    doc = _digitos(d.get("documento"))
    if not doc:
        return ""
    tipo = str(d.get("documento_tipo") or ("cnpj" if len(doc) == 14 else "cpf")).upper()
    return f"{tipo}: {documento_fmt(doc)}"


def endereco_txt(e) -> str:
    """"Rua X, 123, apto 4 — Bairro — Cidade/UF — CEP 01234-567" (partes vazias somem; sem partes, o texto livre `texto`)."""
    if not isinstance(e, dict):
        return ""
    g = lambda k: _txt(e.get(k), 300)   # noqa: E731
    rua = ", ".join(x for x in (g("logradouro"), g("numero"), g("complemento")) if x)
    cid = "/".join(x for x in (g("cidade"), g("uf")) if x)
    cep = _digitos(g("cep"))
    cep = f"CEP {cep[:5]}-{cep[5:]}" if len(cep) == 8 else g("cep")
    partes = [x for x in (rua, g("bairro"), cid) if x]
    if not partes and g("texto"):
        partes = [g("texto")]
        if len(_digitos(cep)) == 8 and re.search(_digitos(cep)[:5] + r"-?" + _digitos(cep)[5:], g("texto")):
            cep = ""                                     # o texto livre já traz o CEP
    return " — ".join(x for x in (*partes, cep) if x)


def valor_proposto_txt(d: dict) -> str:
    if d.get("valor_combinar"):
        return COMBINAR
    return _brl(d.get("valor_proposto"))


def _validar_endereco(e: dict) -> tuple[dict, list[str]]:
    """Partes mandadas pela equipe (vazio = não mexe; "__limpar__" apaga). Mesma regra do site."""
    out, erros = {}, []
    for k, n in ENDERECO.items():
        v = str(e.get(k) or "").strip()
        if not v:
            continue
        if v == "__limpar__":
            out[k] = v
            continue
        if k == "cep":
            v = _digitos(v)
            if len(v) != 8:
                erros.append("CEP: 8 números")
                continue
        elif k == "uf":
            v = v.upper()
            if v not in UFS:
                erros.append("UF: a sigla do estado (ex.: SP)")
                continue
        else:
            v = _txt(v, n)
            if len(v) < (1 if k in ("numero", "complemento") else 2):
                erros.append(f"{k}: muito curto")
                continue
        out[k] = v
    return out, erros


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
        for k in PESSOAIS_DADOS:
            d[k] = ""
        d["endereco"] = None
        d["ficha"] = []
        d["notas"], d["n_fotos"] = [], 0
        con.execute("UPDATE doacao_acervo SET nome=?, email=NULL, telefone=NULL, autor=NULL, local=NULL, dados=?, anonimizado=1 WHERE site_id=?",
                    (REMOVIDO, json.dumps(d, ensure_ascii=False), sid))
    return len(ids)


def numeros(con) -> dict:
    """Para a tela e o "Precisa de você": quantas pedem ação (até o acervo chegar), novas (em análise), pagas e pagas com o acervo ainda a receber."""
    try:
        rows = con.execute("SELECT etapa, valor FROM doacao_acervo").fetchall()
    except Exception:  # noqa: BLE001
        return {}
    return {"abertas": sum(1 for r in rows if r[0] in ABERTAS), "novas": sum(1 for r in rows if r[0] == "em_analise"),
            "aguardando_pagamento": sum(1 for r in rows if r[0] == "cobranca"), "a_receber": sum(1 for r in rows if r[0] == "paga"),   # CAMP-DOA-LISTA (campo novo)
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
    x["fundo_vinculo"] = vinculo_fundo(con, sid)     # CAMP-DOA-FUNDO (campo novo, opcional)
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


# ---------------------------------------------------------------- CAMP-DOA-IMPORTAR: ficha antiga do Google Forms (CSV)
FICHA_CABECALHO = ("Carimbo de data/hora", "Nome completo", "Nome do arquiteto(a) ou titular do acervo", "CPF ou CNPJ", "Endereço completo", "Telefone", "E-mail",
                   "Descrição geral do acervo", "Quantidade aproximada de itens", "Período temporal do acervo (ex: 1960–1990)", "Estado de conservação",
                   "Formato dos itens", "Situação dos direitos autorais", "Propriedade do Acervo", "Transferência de Uso Institucional",
                   "Autorização Ampla de Uso Institucional, Editorial e Comercial", "Irrevogabilidade da Doação", "Responsabilidade por Danos Preexistentes",
                   "Valor da contribuição")
FICHA_TERMOS = FICHA_CABECALHO[13:18]
FICHA_TITULO = "FICHA DE DOAÇÃO (Google Forms)"
MAX_CSV = 2 * 1024 * 1024
VERSAO_IMPORTAR_SITE = "1.36.0"
ETAPAS_IMPORTAR = [k for k in ETAPAS if k not in ETAPAS_AUTO]


def _norm(t) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _codigo_de(texto: str, lista: dict, extra: dict | None = None) -> str:
    """Texto livre → código da lista do site quando o texto É o rótulo (ou o código); senão ""."""
    n = _norm(texto)
    if not n:
        return ""
    for k, v in lista.items():
        if n in (_norm(v), _norm(k)):
            return k
    return (extra or {}).get(n, "")


def _valor_ficha(v) -> float | None:
    """"2.000,00" · "R$ 1.000,00" · "1000" · "1.500" → número; texto ("Já combinado", "Material") → None."""
    t = str(v or "").strip()
    if not t or not re.fullmatch(r"(?:R\$\s*)?[\d.,\s]+", t, re.I):
        return None
    n = _valor_br(re.sub(r"(?<=\d)\.(?=\d{3}(?:\D|$))", "", t) if "," not in t else t)
    return n if n and n > 0 else None


def _carimbo(v) -> str:
    """"27/07/2026 14:03:42" (Brasília) → ISO com fuso; inválido → ""."""
    m = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?\s*", str(v or ""))
    if not m:
        return ""
    try:
        d = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0), tzinfo=ZoneInfo("America/Sao_Paulo"))
    except ValueError:
        return ""
    return d.isoformat()


def ler_ficha_csv(texto: str) -> list[dict]:
    """O CSV da ficha (BOM, campos entre aspas com várias linhas) → [{linha, <coluna>: valor}]. Cabeçalho diferente → ValueError."""
    import csv
    import io
    t = (texto or "").lstrip("﻿")
    rd = csv.reader(io.StringIO(t, newline=""))
    try:
        cab = [c.strip() for c in next(rd)]
    except StopIteration:
        raise ValueError("O arquivo está vazio.") from None
    faltam = [c for c in FICHA_CABECALHO if c not in cab]
    if faltam:
        raise ValueError("Este CSV não é a Ficha de Doação de Acervo do Google Forms: faltam as colunas " + ", ".join(f"“{c}”" for c in faltam[:4]) + (" e outras" if len(faltam) > 4 else "") + ".")
    out = []
    for i, row in enumerate(rd, start=2):
        if not any(str(c).strip() for c in row):
            continue
        d = {c: (row[j].strip() if j < len(row) else "") for j, c in enumerate(cab)}
        d["linha"] = i
        out.append(d)
    return out


def _chave_ficha(email: str, carimbo_bruto: str) -> str:
    return hashlib.sha256(f"{(email or '').strip().lower()}|{(carimbo_bruto or '').strip()}".encode()).hexdigest()[:32]


def _mapear_linha(L: dict) -> tuple[dict, list[str]]:
    """Uma linha da ficha → o que vai ao site (campos do contrato 1.27) + avisos. Não inventa: o que não casa fica como texto."""
    av = []
    email = L.get("E-mail", "").strip().lower()
    if not email:
        av.append("sem e-mail: não dá para achar a pessoa no painel; vai como intenção nova")
    elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        av.append("e-mail ilegível: vai como intenção nova, sem e-mail")
        email = ""
    car = _carimbo(L.get("Carimbo de data/hora"))
    if not car:
        av.append("data do carimbo não lida (esperado dd/mm/aaaa hh:mm:ss)")
    doc = _digitos(L.get("CPF ou CNPJ"))
    if L.get("CPF ou CNPJ", "").strip():
        if len(doc) == 11 and not cpf_ok(doc):
            av.append("CPF com dígitos verificadores errados: guardado como veio, confira")
        elif len(doc) == 14 and not cnpj_ok(doc):
            av.append("CNPJ com dígitos verificadores errados: guardado como veio, confira")
        elif len(doc) not in (11, 14):
            av.append("CPF ou CNPJ não lido (nem 11 nem 14 números): fica só na ficha")
            doc = ""
    end_t = L.get("Endereço completo", "").strip()
    m = re.search(r"(?<!\d)(\d{5})-?(\d{3})(?!\d)", end_t)
    cep = (m.group(1) + m.group(2)) if m else ""
    if end_t and not cep:
        av.append("CEP não encontrado no endereço (o endereço fica em texto)")
    corpo = {"nome": _txt(L.get("Nome completo"), 150), "email": email, "telefone": _txt(L.get("Telefone"), 40),
             "autor": _txt(L.get("Nome do arquiteto(a) ou titular do acervo"), 200), "descricao": str(L.get("Descrição geral do acervo") or "").strip()[:4000],
             "periodo": _txt(L.get("Período temporal do acervo (ex: 1960–1990)"), 80), "formato": _txt(L.get("Formato dos itens"), 300),
             "documento": doc, "endereco": {k: v for k, v in (("texto", end_t[:500]), ("cep", cep)) if v}}
    for col, cod_k, txt_k, lista, extra, rot in (
            ("Quantidade aproximada de itens", "quantidade_estimativa_faixa", "quantidade_texto", FAIXAS, {}, "Quantidade"),
            ("Estado de conservação", "conservacao", "conservacao_texto", CONSERVACAO, {"bom": "boa", "bem conservado": "boa", "otimo": "boa", "danificado": "danificados", "nao sei": "nao_sei"}, "Conservação"),
            ("Situação dos direitos autorais", "direitos", "direitos_texto", DIREITOS, {"nao sei": "nao_sei"}, "Direitos autorais")):
        v = str(L.get(col) or "").strip()
        if not v:
            continue
        k = _codigo_de(v, lista, extra)
        if k:
            corpo[cod_k] = k
        else:
            corpo[txt_k] = v[:300]
            av.append(f"{rot}: “{v[:60]}” não é uma das opções do site; guardado como texto")
    vb = str(L.get("Valor da contribuição") or "").strip()
    vn = _valor_ficha(vb)
    if vn is not None:
        corpo["valor_proposto"] = vn
    elif vb:
        av.append(f"Valor da contribuição “{vb[:40]}” não é um número: fica só na ficha (valor não preenchido)")
    corpo["ficha"] = [{"pergunta": c, "resposta": str(L.get(c) or "").strip()} for c in FICHA_CABECALHO[1:] if str(L.get(c) or "").strip()]
    corpo["recebida_em"] = car
    corpo["chave"] = _chave_ficha(email, L.get("Carimbo de data/hora", ""))
    return {k: v for k, v in corpo.items() if v not in ("", None, [], {})}, av


def _vazio(v) -> bool:
    return v in (None, "", [], {}) or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0)


def _plano_linha(con, L: dict) -> dict:
    corpo, av = _mapear_linha(L)
    out = {"linha": L["linha"], "nome": corpo.get("nome", ""), "email": corpo.get("email", ""), "carimbo": L.get("Carimbo de data/hora", ""), "avisos": av,
           "etapa": "em_analise", "corpo": corpo, "completar": [], "diferencas": []}
    ja = con.execute("SELECT 1 FROM evento WHERE entidade='doacao_acervo' AND tipo='ficha_importada' AND detalhe LIKE ?", (f'%"chave": "{corpo["chave"]}"%',)).fetchone()
    r = con.execute("SELECT * FROM doacao_acervo WHERE lower(email)=? AND anonimizado=0 ORDER BY site_id LIMIT 1", (corpo["email"],)).fetchone() if corpo.get("email") else None
    if not r:
        out["acao"] = "igual" if ja else "criar"
        out["ja_importado"] = bool(ja)
        return out
    d = json.loads(r["dados"] or "{}")
    out["site_id"], out["protocolo"], out["ja_importado"] = r["site_id"], r["protocolo"] or "", bool(ja)
    atual = dict(d, valor=r["valor"])
    rot = {"telefone": "Telefone", "documento": "CPF ou CNPJ", "autor": "Arquiteto ou titular", "descricao": "Descrição", "periodo": "Período", "formato": "Formato dos itens",
           "quantidade_estimativa_faixa": "Quantidade", "quantidade_texto": "Quantidade", "conservacao": "Conservação", "conservacao_texto": "Conservação",
           "direitos": "Direitos autorais", "direitos_texto": "Direitos autorais", "valor_proposto": "Valor proposto", "ficha": "Respostas da ficha", "nome": "Nome"}
    for k, v in corpo.items():
        if k in rot:
            if _vazio(atual.get(k)):
                out["completar"].append(rot[k])
            elif k not in ("ficha",) and str(atual.get(k)).strip().lower() != str(v).strip().lower() and not (k == "documento" and _digitos(atual.get(k)) == v):
                out["diferencas"].append(rot[k])
    e0 = d.get("endereco") if isinstance(d.get("endereco"), dict) else {}
    e1 = corpo.get("endereco") or {}
    if e1.get("texto") and not e0.get("texto") and not e0.get("logradouro"):
        out["completar"].append("Endereço")
    elif e1.get("texto") and (e0.get("texto") or e0.get("logradouro")) and _norm(e1["texto"]) != _norm(e0.get("texto") or endereco_txt(e0)):
        out["diferencas"].append("Endereço")
    if e1.get("cep") and not e0.get("cep"):
        out["completar"].append("CEP")
    elif e1.get("cep") and e0.get("cep") != e1["cep"]:
        out["diferencas"].append("CEP")
    if corpo.get("valor_proposto") and _vazio(r["valor"]):
        out["completar"].append("Contribuição (valor)")
    out["completar"] = list(dict.fromkeys(out["completar"]))
    out["diferencas"] = list(dict.fromkeys(out["diferencas"]))
    for x_ in out["diferencas"]:
        av.append(f"{x_}: a ficha diz outra coisa; o painel mantém o que já está (confira)")
    out["acao"] = "igual" if (ja or not out["completar"]) else "completar"
    return out


ACAO_NOME = {"criar": "vai criar", "completar": "vai completar (campos vazios)", "igual": "já igual"}


class ImportarFicha(BaseModel):
    csv: str
    aplicar: bool = False
    etapas: dict[str, str] | None = None    # {"<linha>": etapa} só para as que vão ser criadas (padrão em_analise)


@router.post("/importar")
def importar_ficha(b: ImportarFicha, u: dict = Depends(auth.exige("admin"))) -> dict:
    """SIMULA por padrão (nada muda): linha a linha, o que faria e os avisos. Com aplicar: cada linha vai ao site (cria sem e-mail ou completa
    o vazio), o registro devolvido fica aqui e a linha não é importada de novo (chave e-mail + carimbo)."""
    if len(b.csv.encode("utf-8", "ignore")) > MAX_CSV:
        raise HTTPException(400, "O arquivo passa de 2 MB: confira se é o CSV da ficha.")
    try:
        linhas = ler_ficha_csv(b.csv)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, "Não deu para ler o CSV: salve de novo como CSV (UTF-8) no Google Planilhas.") from e
    con = connect()
    try:
        plano = [_plano_linha(con, L) for L in linhas]
        etapas = {str(k): str(v) for k, v in (b.etapas or {}).items()}
        for p in plano:
            e_ = etapas.get(str(p["linha"]))
            if e_ and p["acao"] == "criar":
                if e_ not in ETAPAS_IMPORTAR:
                    raise HTTPException(400, f"Linha {p['linha']}: etapa desconhecida")
                p["etapa"] = e_
        feitos = 0
        if b.aplicar:
            if not _tem_site(con):
                raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações")
            autor = _txt((u or {}).get("nome") or (u or {}).get("email") or "painel", 60)
            w = _wp()
            for p in plano:
                if p["acao"] == "igual":
                    p["resultado"] = "nada a fazer"
                    continue
                corpo = dict(p["corpo"], autor_painel=autor, etapa=p["etapa"])
                if p["acao"] == "completar":
                    corpo["completar_id"] = int(p["site_id"])
                    corpo.pop("etapa", None)
                try:
                    resp = w.h.post(f"{ROTA}/importar", json=corpo)
                except Exception as e:  # noqa: BLE001
                    registrar(logging.WARNING, "doacoes_acervo_importar", "Importar ficha: o site não respondeu", linha=p["linha"], erro=type(e).__name__)
                    p["resultado"] = "erro: o site não respondeu; tente de novo (as linhas já importadas não se repetem)"
                    continue
                d = _json(resp)
                if resp.status_code == 404 and str(d.get("code") or "") in ("", "rest_no_route"):
                    raise HTTPException(409, f"O site ainda não importa a ficha: avise quem cuida do site (plugin da CAMP {VERSAO_IMPORTAR_SITE} ou mais novo). "
                                             + (f"{feitos} linha(s) já foram importadas." if feitos else "Nada foi importado."))
                if resp.status_code >= 400 or not isinstance(d.get("registro"), dict):
                    p["resultado"] = "erro: " + (_txt(d.get("message"), 200) or f"o site respondeu {resp.status_code}")
                    continue
                _gravar(con, d["registro"])
                sid = int(d["registro"].get("id") or 0)
                con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('doacao_acervo',?,'ficha_importada',?,?)",
                            (str(sid), (u or {}).get("email") or "painel", json.dumps({"chave": p["corpo"]["chave"], "acao": p["acao"], "linha": p["linha"],
                                                                                         "completados": d.get("completados") or []}, ensure_ascii=False)))
                con.commit()
                feitos += 1
                p["site_id"] = sid
                p["protocolo"] = _txt(d["registro"].get("protocolo"), 40)
                p["resultado"] = "já estava importada" if d.get("ja_importado") else ("criada (nenhum e-mail enviado)" if p["acao"] == "criar" else "completada")
            registrar(logging.INFO, "doacoes_acervo_importar", "Ficha do Google Forms importada", linhas=len(plano), feitas=feitos)
        for p in plano:
            p["acao_nome"] = ACAO_NOME[p["acao"]]
            p.pop("corpo", None)
        res = {k: sum(1 for p in plano if p["acao"] == k) for k in ACAO_NOME}
        return {"simulado": not b.aplicar, "aplicado": bool(b.aplicar), "feitos": feitos, "linhas": plano, "resumo": res,
                "avisos": sum(len(p["avisos"]) for p in plano), "etapas": {k: ETAPAS[k] for k in ETAPAS_IMPORTAR}}
    finally:
        con.close()


@router.get("/{sid}")
def detalhe(sid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return _completo(con, sid)
    finally:
        con.close()


# ---------------------------------------------------------------- CAMP-DOA-TEXTO: dados para o contrato (texto simples)
# Rafael (20/11/2026): "preciso poder em formato texto, copiar todos dados do formulario que ela preencheu e suas respostas, pergunta e
# resposta, com os dados dela, valor que vai doar e etc que eh pra enviar para fazer o contrato." As perguntas são as do formulário do site
# (camp-wordpress, class-doacao-acervo.php, Camp_AAP_Doacao_Acervo::form), na ordem dele. O registro do site já traz as respostas com o nome
# (relacao_nome, faixa_nome, tipos_nomes…), que valem por cima das listas abaixo; chave sem rótulo sai como "chave: valor".
TEXTO_TITULO = "Intenção de doação de acervo — CAMP"
TEXTO_LGPD = "dados apagados (LGPD)"
PERGUNTAS = (
    ("nome", "Seu nome completo"),
    ("email", "E-mail"),
    ("telefone", "Telefone / WhatsApp"),
    ("documento", "CPF ou CNPJ"),                       # CAMP-DOA-CPF (site 1.35.0): rótulos exatamente como no formulário
    ("end_cep", "CEP"),
    ("end_logradouro", "Rua, avenida (logradouro)"),
    ("end_numero", "Número"),
    ("end_complemento", "Complemento"),
    ("end_bairro", "Bairro"),
    ("end_cidade", "Cidade"),
    ("end_uf", "UF"),
    ("valor_proposto", "Valor da contribuição de preservação"),
    ("relacao", "Qual é sua relação com o acervo?"),
    ("autor", "Nome do arquiteto, escritório ou pessoa a quem o acervo pertenceu"),
    ("descricao", "O que há no acervo?"),
    ("tipos", "Que tipos de material ele contém?"),
    ("quantidade_estimativa_faixa", "Qual é a quantidade aproximada de material?"),
    ("periodo", "De que período são os documentos?"),
    ("conservacao", "Como está a conservação do material?"),
    ("local", "Em qual cidade e estado o acervo está guardado?"),
    ("fotos", "Anexar fotos gerais"),
    ("fotos_link", "Compartilhar um link com fotos ou inventário"),
    ("sem_fotos", "Ainda não tenho fotos para enviar."),
    ("direitos", "O que você sabe sobre os direitos autorais do material?"),
    ("aceite", "Li e compreendi os termos acima."),
    ("marketing", "Gostaria de receber notícias e convites da CAMP por e-mail?"),
)
RELACOES = {"autor": "Sou o(a) autor(a) ou titular do acervo", "familia": "Sou familiar ou herdeiro(a)", "escritorio": "Represento um escritório ou instituição",
            "guarda": "Sou responsável pela guarda do material", "outra": "Outra situação"}
TIPOS = {"desenhos": "Plantas, desenhos e croquis", "fotografias": "Fotografias, slides ou negativos", "documentos": "Cartas, cadernos e documentos",
         "maquetes": "Maquetes e objetos", "digitais": "Arquivos digitais", "audiovisual": "Vídeos ou áudios", "outros": "Outros / Não sei ao certo"}
CONSERVACAO = {"boa": "Boa", "regular": "Regular", "danificados": "Há documentos danificados", "nao_sei": "Não sei avaliar"}
DIREITOS = {"titular": "Sou titular dos direitos patrimoniais", "herdeiro": "Sou herdeiro(a), mas os direitos precisam ser confirmados",
            "terceiro": "Os direitos pertencem a outra pessoa ou instituição", "varios": "Existem vários autores ou titulares", "nao_sei": "Não sei informar"}
MARKETING = {True: "Sim, quero receber novidades, eventos, publicações e informações sobre a CAMP.",
             False: "Não, desejo receber apenas mensagens relacionadas à minha proposta e, caso avance, ao contrato, pagamento e participação nos Amigos da CAMP."}
# dados pessoais pedidos depois (contrato): saem em "Dados da pessoa" se o registro trouxer
PESSOAIS_EXTRA = (("cpf_cnpj", "CPF/CNPJ"), ("cpf", "CPF"), ("cnpj", "CNPJ"), ("endereco", "Endereço"))
PESSOAIS = {"nome", "email", "telefone", "autor", "descricao", "local", "fotos_link", "fotos", "documento", "end_cep", "end_logradouro", "end_numero",
            "end_complemento", "end_bairro", "end_cidade", "end_uf"} | {k for k, _ in PESSOAIS_EXTRA}
# chaves do registro que já estão no texto (ou são da equipe/sistema): o resto sai como "chave: valor"
CONHECIDAS = {k for k, _ in PERGUNTAS} | {k for k, _ in PESSOAIS_EXTRA} | {
    "id", "protocolo", "recebida_em", "relacao_nome", "tipos_nomes", "faixa_nome", "conservacao_nome", "direitos_nome", "n_fotos", "termos_versao",
    "etapa", "etapa_nome", "aprovada_em", "contrato_link", "assinado_em", "contrato_enviado_em", "contrato_prazo", "avisos", "valor", "minimo", "caixas",
    "rolos", "volume", "quantidade_catalogada", "fundo", "notas", "cobranca", "amigo", "pode_cobrar", "historico", "anonimizado", "alterado_em",
    "documento_tipo", "endereco", "valor_combinar",
    "origem", "ficha", "quantidade_texto", "conservacao_texto", "direitos_texto", "formato", "importado_em",   # CAMP-DOA-IMPORTAR: vão na seção da ficha
}


def _brl(v) -> str:
    n = _num(v)
    return "" if not n else "R$ " + f"{n:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def _data_br(v, hora: bool = False) -> str:
    """'2026-11-20' / ISO / 'AAAA-MM-DD HH:MM:SS' (UTC) → dd/mm/aaaa (com hora: no horário de Brasília)."""
    s = str(v or "").strip()
    if not s:
        return ""
    if hora:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T"))
            d = (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(ZoneInfo("America/Sao_Paulo"))
            return d.strftime("%d/%m/%Y %H:%M")
        except ValueError:
            pass
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else s


def _valor_txt(v) -> str:
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if isinstance(v, (list, tuple)):
        return "; ".join(t for t in (_valor_txt(i) for i in v) if t)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False) if v else ""
    return "" if v is None else str(v).strip()


def _rotulo(d: dict, listas: dict, chave: str, nome_chave: str, lista: str, padrao: dict) -> str:
    cod = str(d.get(chave) or "")
    if not cod:
        return ""
    return str(d.get(nome_chave) or (listas.get(lista) or {}).get(cod) or padrao.get(cod) or cod)


def _resposta(d: dict, listas: dict, chave: str) -> str:
    if chave == "relacao":
        return _rotulo(d, listas, "relacao", "relacao_nome", "relacoes", RELACOES)
    if chave == "quantidade_estimativa_faixa":
        return _rotulo(d, listas, chave, "faixa_nome", "faixas", FAIXAS)
    if chave == "conservacao":
        return _rotulo(d, listas, chave, "conservacao_nome", "conservacao", CONSERVACAO)
    if chave == "direitos":
        return _rotulo(d, listas, chave, "direitos_nome", "direitos", DIREITOS)
    if chave == "tipos":
        nomes = [str(t) for t in (d.get("tipos_nomes") or []) if t]
        if not nomes:
            mapa = {**TIPOS, **(listas.get("tipos") or {})}
            nomes = [str(mapa.get(t, t)) for t in (d.get("tipos") or []) if t]
        return "; ".join(nomes)
    if chave == "fotos":
        n = int(d.get("n_fotos") or 0)
        return f"{n} foto{'s' if n != 1 else ''} anexada{'s' if n != 1 else ''} (ficam no site; veja no painel)" if n > 0 else ""
    if chave == "sem_fotos":
        return "Sim" if d.get("sem_fotos") else ""
    if chave == "aceite":
        tv = _txt(d.get("termos_versao"), 40)
        return f"Sim (termos versão {tv})" if tv else ""
    if chave == "documento":
        return documento_fmt(_digitos(d.get("documento")))
    if chave.startswith("end_"):
        e = d.get("endereco") if isinstance(d.get("endereco"), dict) else {}
        v = _txt(e.get(chave[4:]), 300)
        return f"{_digitos(v)[:5]}-{_digitos(v)[5:]}" if chave == "end_cep" and len(_digitos(v)) == 8 else v
    if chave == "valor_proposto":
        return valor_proposto_txt(d)
    if chave == "marketing":
        return MARKETING[bool(d["marketing"])] if "marketing" in d and d["marketing"] is not None else ""
    return _valor_txt(d.get(chave))


def _bloco(titulo: str, linhas: list[str]) -> list[str]:
    linhas = [l for l in linhas if l]
    return ["", titulo, *linhas] if linhas else []


def texto_contrato(con, sid: int, notas: bool = False) -> str:
    """O resumo em texto simples (UTF-8, \\n, sem HTML) para colar no e-mail ou no documento do contrato. Notas internas só com `notas`.
    Anonimizada (LGPD): nenhum dado pessoal, só "dados apagados (LGPD)"."""
    r = _um(con, sid)
    d = json.loads(r["dados"]) if r["dados"] else {}
    anon = bool(r["anonimizado"]) or bool(d.get("anonimizado"))
    listas = json.loads(_estado(con, "listas") or "{}") or {}
    um = lambda rot, v: f"{rot}: {v}" if str(v or "").strip() else ""   # noqa: E731
    out = [x for x in (TEXTO_TITULO, um("Protocolo", r["protocolo"]), um("Recebida em", _data_br(r["recebida_em"] or d.get("recebida_em"), hora=True))) if x]
    # 2. dados da pessoa
    if anon:
        out += _bloco("DADOS DA PESSOA", [TEXTO_LGPD, um("Relação com o acervo", _resposta(d, listas, "relacao"))])
    else:
        out += _bloco("DADOS DA PESSOA", [um("Nome completo", r["nome"] or d.get("nome")), um("E-mail", r["email"] or d.get("email")),
                                          um("Telefone / WhatsApp", r["telefone"] or d.get("telefone")), documento_txt(d),
                                          um("Endereço", endereco_txt(d.get("endereco"))), um("Relação com o acervo", _resposta(d, listas, "relacao")),
                                          *[um(rot, _valor_txt(d.get(k))) for k, rot in PESSOAIS_EXTRA]])
    # 3. formulário: pergunta e resposta, na ordem do site
    form = []
    for k, rot in PERGUNTAS:
        if anon and k in PESSOAIS:
            continue
        v = _resposta(d, listas, k)
        if v:
            form.append(rot + "\n" + "\n".join("  " + l for l in v.splitlines() if l.strip()) + "\n")
    if not anon:
        for k in sorted(set(d) - CONHECIDAS):
            v = _valor_txt(d.get(k))
            if v:
                form.append(f"{k}: {v}\n")
    if anon:
        form.insert(0, f"Respostas pessoais: {TEXTO_LGPD}\n")
    if form:
        form[-1] = form[-1].rstrip("\n")
    out += _bloco("FORMULÁRIO (pergunta e resposta)", form)
    # 3b. CAMP-DOA-IMPORTAR: a ficha antiga (Google Forms), pergunta → resposta, com a data do carimbo
    ficha = [q for q in (d.get("ficha") or []) if isinstance(q, dict) and str(q.get("pergunta") or "").strip()]
    if ficha and not anon:
        fl = [um("Enviada em", _data_br(r["recebida_em"] or d.get("recebida_em"), hora=True)) + "\n"]
        fl += [str(q["pergunta"]).strip() + "\n" + "\n".join("  " + l for l in str(q.get("resposta") or "").splitlines() if l.strip()) + "\n"
               for q in ficha if str(q.get("resposta") or "").strip()]
        fl[-1] = fl[-1].rstrip("\n")
        out += _bloco(FICHA_TITULO, fl)
    elif ficha and anon:
        out += _bloco(FICHA_TITULO, [f"Respostas: {TEXTO_LGPD}"])
    # 4. dados combinados (equipe)
    cob = d.get("cobranca") if isinstance(d.get("cobranca"), dict) else None
    au = _aut_info(con, sid)
    cl = str(d.get("contrato_link") or "")
    amigo = d.get("amigo") if isinstance(d.get("amigo"), dict) else {}
    num = lambda v: "" if v in (None, "") else str(v)   # noqa: E731
    cob_txt = ""
    if cob:
        cob_txt = " · ".join(x for x in (str(cob.get("situacao_nome") or cob.get("situacao") or ""), _brl(cob.get("valor")),
                                         str(cob.get("external_reference") or ""), ("paga em " + _data_br(cob.get("pago_em"))) if cob.get("pago_em") else "") if x)
    out += _bloco("DADOS COMBINADOS (equipe)", [
        um("Etapa", ETAPAS.get(r["etapa"], r["etapa"])),
        um("Contribuição acordada", _brl(r["valor"] if r["valor"] is not None else d.get("valor"))),
        um("Valor proposto pela pessoa", valor_proposto_txt(d)),
        um("Caixas (aproximado)", num(d.get("caixas"))), um("Rolos (aproximado)", num(d.get("rolos"))), um("Volume físico estimado", d.get("volume")),
        um("Quantidade catalogada", num(d.get("quantidade_catalogada"))), um("Código do fundo", d.get("fundo")),
        um("Link do contrato para assinatura", cl),
        um("Assinatura eletrônica (Autentique)", " · ".join(x for x in ((au or {}).get("situacao_nome", ""), (au or {}).get("link", "") if (au or {}).get("link") != cl else "") if x)),
        um("Contrato enviado para assinatura em", _data_br(d.get("contrato_enviado_em"), hora=True)),
        um("Assinar até", _data_br(d.get("contrato_prazo"))),
        um("Data em que as duas partes assinaram", _data_br(r["assinado_em"] or d.get("assinado_em"))),
        um("Cobrança (Mercado Pago)", cob_txt),
        um("Amigo da CAMP até", amigo.get("validade_br") or _data_br(amigo.get("validade"))),
    ])
    # 5. notas internas: só se pedido (e nunca de quem teve os dados apagados)
    if notas and not anon:
        ns = [n for n in (d.get("notas") or []) if isinstance(n, dict) and str(n.get("texto") or "").strip()]
        out += _bloco("NOTAS INTERNAS", [" · ".join(x for x in (str(n.get("em") or ""), str(n.get("quem") or "")) if x) + ": " + str(n["texto"]).strip()
                                          if (n.get("em") or n.get("quem")) else str(n["texto"]).strip() for n in ns])
    return "\n".join(l for i, l in enumerate(out) if l or (i and out[i - 1])).strip() + "\n"


@router.get("/{sid}/texto")
def texto(sid: int, notas: bool = False, u: dict = Depends(auth.exige("admin"))) -> dict:
    """CAMP-DOA-TEXTO: o texto para o contrato (a tela só busca e copia)."""
    con = connect()
    try:
        return {"texto": texto_contrato(con, sid, notas), "notas": bool(notas)}
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
    documento: str | None = None     # CAMP-DOA-CPF (contrato 1.26): CPF/CNPJ corrigido pela equipe ("__limpar__" apaga)
    endereco: dict | None = None     # CAMP-DOA-CPF: partes do endereço corrigidas (vazio não mexe; "__limpar__" apaga)
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
        end_b = dados_b.pop("endereco", None)
        pessoais = {}                                        # CAMP-DOA-CPF: mesma validação do site
        doc_b = (dados_b.pop("documento", None) or "").strip()
        if doc_b:
            if doc_b == "__limpar__":
                pessoais["documento"] = doc_b
            elif documento_de(doc_b):
                pessoais["documento"] = documento_de(doc_b)[0]
            else:
                raise HTTPException(400, "CPF ou CNPJ: os dígitos verificadores não conferem. Confira os números.")
        if isinstance(end_b, dict):
            e_ok, e_err = _validar_endereco(end_b)
            if e_err:
                raise HTTPException(400, "Endereço: " + "; ".join(e_err))
            if e_ok:
                pessoais["endereco"] = e_ok
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
        corpo.update(pessoais)
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
        if pessoais and isinstance(d.get("registro"), dict) and "documento" not in d["registro"]:   # site antigo: ignorou os campos
            x["dados_pessoais"] = {"salvo": False, "mensagem": f"CPF/CNPJ e endereço não foram guardados: o site ainda não tem esses campos (plugin da CAMP {VERSAO_CPF_SITE} ou mais novo). Avise quem cuida do site."}
        elif pessoais:
            x["dados_pessoais"] = {"salvo": True, "mensagem": "CPF/CNPJ e endereço atualizados no site."}
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
        w = wp or _wp()
        resp = w.h.post(f"{ROTA}/{sid}", json=corpo)
        if resp.status_code == 400 and corpo.get("etapa") and str(_json(resp).get("code") or "") == "camp_valor":
            # CAMP-DOA-LISTA: a cópia daqui estava atrasada (o site já passou da assinatura: cobrança paga antes da conferência) e o site
            # recusou voltar a etapa. Manda só a data, como para quem já passou dessa etapa: a etapa do site fica (nunca volta) e a
            # assinatura não fica pendente para sempre.
            corpo.pop("etapa", None)
            resp = w.h.post(f"{ROTA}/{sid}", json=corpo)
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


# ---------------------------------------------------------------- CAMP-DOA-FUNDO: acervo recebido → fundo e arquiteto no painel
# Rafael (21/11/2026): "e precisa criar quando terminar o fundo e arquiteto automaticamente." Ao passar a doação a "Acervo recebido pela CAMP",
# a tela mostra a prévia ("Vai criar o fundo F0xx · <nome> e o arquiteto <nome>") e, ao confirmar, o painel cria os dois numa transação só,
# com o cadastro de sempre (rotas_fundos.criar_fundo: código de proximo_codigo / v_proximo_fundo; o arquiteto por inserir_agente), guarda o
# vínculo em `doacao_fundo` e só então manda etapa=recebido + fundo ao site (POST de sempre; contrato igual). Site falhou: o fundo fica
# (código não se reusa) e tentar de novo usa o mesmo. Arquiteto ou fundo de mesmo nome (sem acento e sem caixa): a prévia propõe usar o
# existente. Nada pessoal (CPF, endereço, nome de quem doa) vai ao fundo ou ao arquiteto; nada de biografia: só o período dos documentos
# (datas extremas do fundo, se for um intervalo de anos claro), o volume combinado (dimensão e suporte) e a procedência ("Doação à CAMP").
TIPOS_AGENTE = {"pessoa": "pessoa (um arquiteto)", "entidade_coletiva": "escritório ou entidade (vários arquitetos)", "familia": "família (acervo de família)"}   # as da tela de Fundos


def _norm_nome(t) -> str:
    from .similaridade import normalizar
    return normalizar(t)


def sigla_sugerida(con, nome: str) -> str:
    """As iniciais do nome, a mesma regra da tela de Fundos (nfIniciais): "Carlos Henrique Heck" → CHH. Já é de outro fundo → ""."""
    import unicodedata
    t = unicodedata.normalize("NFD", str(nome or "")).encode("ascii", "ignore").decode().upper()
    w = [x for x in re.sub(r"[^A-Z ]", " ", t).split() if x not in ("DE", "DA", "DO", "DOS", "DAS", "E")]
    if not w:
        return ""
    s_ = w[0][0] + w[1][0] + w[-1][0] if len(w) >= 3 else ((w[0][0] + w[1][:2]).ljust(3, "X") if len(w) == 2 else w[0][:3].ljust(3, "X"))
    return "" if con.execute("SELECT 1 FROM fundo WHERE sigla=?", (s_,)).fetchone() else s_


def periodo_anos(txt) -> tuple[int | None, int | None]:
    """"1960–1990", "1960 a 1990", "de 1960 até 1990", "1975" → anos (datas extremas). Qualquer outra coisa ("anos 60", "década de 1970",
    "1960, 1985 e 1990") → nada: não se adivinha data."""
    m = re.fullmatch(r"(?:de )?(\d{4})(?:(?: a| ate)? (\d{4}))?", _norm(re.sub(r"[\u2010-\u2015/-]", " ", str(txt or ""))))
    if not m:
        return None, None
    ini, fim = int(m.group(1)), int(m.group(2) or m.group(1))
    return (ini, fim) if 1800 <= ini <= fim <= 2100 else (None, None)


def _dimensao(d: dict) -> str:
    """O volume combinado pela equipe ("6 caixas, 40 rolos; 2 m lineares") → dimensão e suporte do fundo. Sem nada → ""."""
    def n(k):
        try:
            return int(float(d.get(k) or 0))
        except (TypeError, ValueError):
            return 0
    partes = [f"{n('caixas')} caixa{'s' if n('caixas') != 1 else ''}" if n("caixas") else "", f"{n('rolos')} rolo{'s' if n('rolos') != 1 else ''}" if n("rolos") else ""]
    t = ", ".join(p for p in partes if p)
    v = _txt(d.get("volume"), 120)
    return "; ".join(x for x in (t, v) if x)


def vinculo_fundo(con, sid: int) -> dict | None:
    """O fundo desta doação: o criado/escolhido aqui (doacao_fundo) ou, no caminho manual, o código que o site guardou, se existir no painel."""
    try:
        v = con.execute("""SELECT v.*, f.titulo AS fundo_titulo, a.forma_autorizada AS agente_nome FROM doacao_fundo v JOIN fundo f ON f.codigo=v.fundo_codigo
                           LEFT JOIN agente a ON a.id=v.agente_id WHERE v.site_id=?""", (int(sid),)).fetchone()
    except Exception:  # noqa: BLE001  (banco sem a migração 237)
        v = None
    if v:
        return {"codigo": v["fundo_codigo"], "titulo": v["fundo_titulo"], "agente_id": v["agente_id"], "agente_nome": v["agente_nome"] or "",
                "fundo_criado": bool(v["fundo_criado"]), "agente_criado": bool(v["agente_criado"]), "criado_em": v["criado_em"], "criado_por": v["criado_por"] or "",
                "site_ok": bool(v["site_ok_em"]), "site_erro": v["site_erro"] or "", "pelo_painel": True}
    r = con.execute("SELECT dados FROM doacao_acervo WHERE site_id=?", (int(sid),)).fetchone()
    cod = str((json.loads(r[0]) if r and r[0] else {}).get("fundo") or "").upper()
    f = con.execute("SELECT codigo, titulo FROM fundo WHERE codigo=?", (cod,)).fetchone() if re.fullmatch(r"F\d{3}", cod) else None
    return {"codigo": f["codigo"], "titulo": f["titulo"], "pelo_painel": False} if f else None


def origem_fundo(con, codigo: str) -> dict | None:
    """Para a página do fundo: "Origem: doação de acervo CAMP-2026-…" (a doação que criou/escolheu este fundo; senão a que guardou o código)."""
    try:
        r = con.execute("SELECT d.site_id, d.protocolo FROM doacao_fundo v JOIN doacao_acervo d ON d.site_id=v.site_id WHERE v.fundo_codigo=? ORDER BY v.criado_em LIMIT 1",
                        (codigo,)).fetchone()
        r = r or con.execute("SELECT site_id, protocolo FROM doacao_acervo WHERE upper(json_extract(dados,'$.fundo'))=? ORDER BY site_id LIMIT 1", (codigo,)).fetchone()
    except Exception:  # noqa: BLE001  (banco sem as migrações 232/237)
        return None
    return {"site_id": r["site_id"], "protocolo": r["protocolo"] or ""} if r else None


def _arquitetos_parecidos(con, nome: str) -> list[dict]:
    """Arquitetos com o MESMO nome sem acento e sem caixa (forma autorizada ou grafia do carimbo), com os fundos de que são produtores."""
    alvo = _norm_nome(nome)
    if not alvo:
        return []
    out = []
    for a in con.execute("""SELECT a.id, a.tipo, a.forma_autorizada, (SELECT GROUP_CONCAT(forma, '|') FROM agente_forma_variante v WHERE v.agente_id=a.id) AS formas
                            FROM agente a ORDER BY a.id"""):
        if alvo in {_norm_nome(a["forma_autorizada"]), *(_norm_nome(f) for f in (a["formas"] or "").split("|") if f)}:
            fundos = [dict(f) for f in con.execute("""SELECT f.codigo, f.titulo FROM fundo_agente fa JOIN fundo f ON f.codigo=fa.fundo_codigo
                                                      WHERE fa.agente_id=? AND fa.papel='produtor' ORDER BY f.codigo""", (a["id"],))]
            out.append({"id": a["id"], "nome": a["forma_autorizada"], "tipo": a["tipo"], "fundos": fundos})
    return out


def _fundos_parecidos(con, nome: str, arquiteto: dict | None) -> list[dict]:
    """Fundos do arquiteto escolhido (produtor) e fundos de MESMO nome sem acento e sem caixa."""
    alvo = _norm_nome(nome)
    out = {f["codigo"]: f for f in (arquiteto or {}).get("fundos", [])}
    for f in con.execute("SELECT codigo, titulo FROM fundo ORDER BY codigo"):
        if alvo and _norm_nome(f["titulo"]) == alvo:
            out.setdefault(f["codigo"], dict(f))
    return [out[k] for k in sorted(out)]


class Receber(BaseModel):
    aplicar: bool = False                # padrão: só a prévia (simulada numa transação desfeita)
    fundo: str = "auto"                  # auto (o existente proposto, senão novo) | novo | existente
    fundo_codigo: str | None = None      # com fundo=existente
    fundo_nome: str | None = None
    sigla: str | None = None             # vazio = sem sigla por enquanto (definir depois na página do fundo)
    arquiteto: str = "auto"              # auto | novo | existente
    arquiteto_id: int | None = None      # com arquiteto=existente
    arquiteto_nome: str | None = None
    tipo_agente: str = "pessoa"
    mudanca: Mudanca | None = None       # o resto do Salvar (nota, quantidade catalogada, aviso…); etapa e fundo o painel põe


def _plano(con, r, b: Receber) -> dict:
    """O que vai acontecer (sem gravar nada). Erro de escolha → HTTPException 400/409."""
    d = json.loads(r["dados"]) if r["dados"] else {}
    nome_arq = _txt(b.arquiteto_nome if b.arquiteto_nome is not None else (r["autor"] or d.get("autor")), 200)
    arqs = _arquitetos_parecidos(con, nome_arq)
    modo_a = b.arquiteto if b.arquiteto in ("novo", "existente") else ("existente" if arqs else "novo")
    arq = None
    if modo_a == "existente":
        aid = b.arquiteto_id or (arqs[0]["id"] if arqs else None)
        a = con.execute("SELECT id, tipo, forma_autorizada FROM agente WHERE id=?", (aid,)).fetchone() if aid else None
        if not a:
            raise HTTPException(400, "Escolha o arquiteto que já existe, ou marque criar novo.")
        arq = next((x for x in arqs if x["id"] == a["id"]), None) or {"id": a["id"], "nome": a["forma_autorizada"], "tipo": a["tipo"], "fundos": [
            dict(f) for f in con.execute("SELECT f.codigo, f.titulo FROM fundo_agente fa JOIN fundo f ON f.codigo=fa.fundo_codigo WHERE fa.agente_id=? AND fa.papel='produtor' ORDER BY f.codigo", (a["id"],))]}
    else:
        if not nome_arq:
            raise HTTPException(400, "Informe o nome do arquiteto (o formulário não trouxe a quem o acervo pertenceu).")
        if con.execute("SELECT 1 FROM agente WHERE lower(forma_autorizada)=lower(?)", (nome_arq,)).fetchone():
            raise HTTPException(409, f"Já existe o arquiteto “{nome_arq}”: escolha usar o existente ou mude o nome.")
        if b.tipo_agente not in TIPOS_AGENTE:
            raise HTTPException(400, "Tipo do arquiteto inválido")
    nome_f = _txt(b.fundo_nome if b.fundo_nome is not None else (arq["nome"] if arq else nome_arq), 200)
    fundos = _fundos_parecidos(con, nome_f, arq)
    modo_f = b.fundo if b.fundo in ("novo", "existente") else ("existente" if fundos else "novo")
    plano = {"arquiteto": {"acao": "usar" if arq else "criar", "id": (arq or {}).get("id"), "nome": arq["nome"] if arq else nome_arq,
                           "tipo": (arq or {}).get("tipo") or b.tipo_agente},
             "arquitetos_existentes": arqs, "fundos_existentes": fundos}
    if modo_f == "existente":
        cod = (b.fundo_codigo or (fundos[0]["codigo"] if fundos else "")).strip().upper()
        f = con.execute("SELECT codigo, titulo FROM fundo WHERE codigo=?", (cod,)).fetchone() if cod else None
        if not f:
            raise HTTPException(400, "Escolha o fundo que já existe, ou marque criar novo.")
        plano["fundo"] = {"acao": "usar", "codigo": f["codigo"], "nome": f["titulo"]}
        return plano
    if not nome_f:
        raise HTTPException(400, "Informe o nome do fundo.")
    if con.execute("SELECT 1 FROM fundo WHERE lower(titulo)=lower(?)", (nome_f,)).fetchone():
        raise HTTPException(409, f"Já existe fundo com o nome “{nome_f}”: escolha usar o existente ou mude o nome.")
    sig = (b.sigla if b.sigla is not None else sigla_sugerida(con, nome_f)).strip().upper()
    if sig:
        from .rotas_fundos import _validar_sigla
        sig = _validar_sigla(con, sig)
    ini, fim = periodo_anos(d.get("periodo"))
    plano["fundo"] = {"acao": "criar", "codigo": None, "nome": nome_f, "sigla": sig or None, "data_inicio": ini, "data_fim": fim, "dimensao_suporte": _dimensao(d) or None,
                      "procedencia": "Doação à CAMP."}
    return plano


def _executar(con, sid: int, r, plano: dict, ator: str) -> dict:
    """Grava o plano (fundo, arquiteto, vínculo, eventos). Não faz commit: a prévia desfaz, a confirmação grava tudo de uma vez."""
    from .rotas_fundos import _evento as ev_fundo, criar_fundo, inserir_agente
    a, f = plano["arquiteto"], plano["fundo"]
    prot = r["protocolo"] or str(sid)
    if a["acao"] == "criar":
        aid = inserir_agente(con, a["tipo"], a["nome"])
        ev_fundo(con, "agente", str(aid), "criado", ator, {"nome": a["nome"], "origem": "doacao_acervo", "doacao": prot})
    else:
        aid = a["id"]
    if f["acao"] == "criar":
        cod = criar_fundo(con, f["nome"], f["sigla"], f["data_inicio"], f["data_fim"], a["tipo"], ator, agente_id=aid,
                          detalhe={"titulo": f["nome"], "origem": "doacao_acervo", "doacao": prot, "site_id": int(sid)})["codigo"]
        con.execute("UPDATE fundo SET dimensao_suporte=?, procedencia=? WHERE codigo=?", (f["dimensao_suporte"], f["procedencia"], cod))
    else:
        cod = f["codigo"]
        con.execute("INSERT OR IGNORE INTO fundo_agente (fundo_codigo, agente_id, papel) VALUES (?,?,'produtor')", (cod, aid))
    con.execute("INSERT INTO doacao_fundo (site_id, fundo_codigo, agente_id, fundo_criado, agente_criado, criado_por) VALUES (?,?,?,?,?,?)",
                (int(sid), cod, aid, int(f["acao"] == "criar"), int(a["acao"] == "criar"), ator))
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('doacao_acervo',?,'fundo_vinculado',?,?)",
                (str(int(sid)), ator, json.dumps({"fundo": cod, "fundo_criado": f["acao"] == "criar", "agente_id": aid, "agente_criado": a["acao"] == "criar"}, ensure_ascii=False)))
    return {"codigo": cod, "agente_id": aid}


def _frase(plano: dict, codigo: str) -> str:
    f, a = plano["fundo"], plano["arquiteto"]
    p1 = f"Vai criar o fundo {codigo} · {f['nome']}" if f["acao"] == "criar" else f"Vai usar o fundo {codigo} · {f['nome']}"
    p2 = f"e o arquiteto {a['nome']}" if a["acao"] == "criar" else f"com o arquiteto {a['nome']} (já cadastrado)"
    return f"{p1} {p2}"


@router.post("/{sid}/receber")
def receber(sid: int, b: Receber, u: dict = Depends(auth.exige("admin"))) -> dict:
    """CAMP-DOA-FUNDO: "Acervo recebido pela CAMP" criando fundo e arquiteto. Sem `aplicar`: só a prévia (o plano é executado numa transação
    DESFEITA, para o código mostrado ser o que a criação daria). Com `aplicar`: cria tudo de uma vez, guarda o vínculo e manda ao site
    etapa=recebido + fundo (+ o resto do Salvar). Doação que já tem fundo: usa o mesmo (nunca cria um segundo)."""
    con = connect()
    try:
        r = _um(con, sid)
        ator = (u or {}).get("email") or "painel"
        vinc = vinculo_fundo(con, sid)
        if vinc and not vinc.get("pelo_painel"):
            vinc = None                                   # o código manual não impede criar (a equipe escolhe)
        if not b.aplicar:
            if vinc:
                return {"simulado": True, "vinculado": vinc, "frase": f"Esta doação já tem o fundo {vinc['codigo']} · {vinc['titulo']}: vai usar o mesmo."}
            plano = _plano(con, r, b)
            try:
                cod = _executar(con, sid, r, plano, ator)["codigo"]
            finally:
                con.rollback()                            # prévia: nada fica
            plano["fundo"]["codigo"] = cod
            return {"simulado": True, "vinculado": None, **plano, "frase": _frase(plano, cod), "tipos_agente": TIPOS_AGENTE}
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações: nada foi criado.")
        criado = None
        if not vinc:
            con.execute("BEGIN IMMEDIATE")
            try:
                vinc = vinculo_fundo(con, sid)            # outra aba confirmou ao mesmo tempo: usa o dela
                vinc = vinc if vinc and vinc.get("pelo_painel") else None
                if not vinc:
                    plano = _plano(con, r, b)
                    res_ = _executar(con, sid, r, plano, ator)
                    criado = {"frase": _frase(plano, res_["codigo"]).replace("Vai criar", "Criado").replace("Vai usar", "Usado"), **res_,
                              "fundo_criado": plano["fundo"]["acao"] == "criar", "agente_criado": plano["arquiteto"]["acao"] == "criar"}
                con.commit()
            except Exception:
                con.rollback()
                raise
            vinc = vinc or vinculo_fundo(con, sid)
            registrar(logging.INFO, "doacoes_acervo_fundo", "Fundo da doação de acervo criado/vinculado no painel", site_id=int(sid), fundo=vinc["codigo"],
                      fundo_criado=bool(criado and criado["fundo_criado"]), agente_criado=bool(criado and criado["agente_criado"]))
        cod = vinc["codigo"]
        mud = (b.mudanca or Mudanca()).model_copy()
        mud.etapa, mud.fundo = "recebido", cod
        quem = "o fundo " + f"{cod} · {vinc['titulo']}" + (f" e o arquiteto {vinc['agente_nome']}" if vinc.get("agente_nome") else "")
        nota_aut = ("Criados no painel: " if vinc["fundo_criado"] else "Vinculado no painel: ") + quem + "."
        mud.nota = (nota_aut + (" " + mud.nota.strip() if (mud.nota or "").strip() else ""))[:2000]
        con.close()
        con = None
        try:
            x = mudar(sid, mud, u)
        except HTTPException as e:
            c2 = connect()
            try:
                c2.execute("UPDATE doacao_fundo SET site_erro=? WHERE site_id=?", (str(e.detail)[:300], int(sid)))
                c2.commit()
            finally:
                c2.close()
            raise HTTPException(e.status_code, f"O fundo {cod} ficou criado no painel, mas o site não recebeu a etapa: {e.detail} "
                                               "Tente de novo: o mesmo fundo será usado.") from e
        c2 = connect()
        try:
            c2.execute("UPDATE doacao_fundo SET site_ok_em=datetime('now'), site_erro=NULL WHERE site_id=?", (int(sid),))
            c2.commit()
            x["fundo_vinculo"] = vinculo_fundo(c2, sid)
        finally:
            c2.close()
        x["receber"] = {"criado": criado, "mensagem": (criado["frase"] if criado else f"Usado o fundo {cod} desta doação") + ". Acervo recebido: etapa enviada ao site."}
        return x
    finally:
        if con is not None:
            con.close()
