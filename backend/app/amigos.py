"""Amigos da CAMP no painel (18/11/2026, Rafael: "Amigos da CAMP, podemos pôr no painel? Aí teremos um valor x por ano já programado,
e conseguiria controlar quem já pagou ou não, alterar status etc. Disparar e-mail etc.").

O site continua com o formulário público e o pagamento pelo Mercado Pago (class-apoio.php / class-mercadopago.php); o painel é o lugar
de trabalho da equipe:
- Coleta (contrato 1.11, docs/CONTRATO_UNICO.md §6): GET /wp-json/camp/v1/painel/apoios?desde=…&pagina=N (só leitura, incremental) →
  grava em `amigo` (chave site_id; os três tipos: amigo, projeto, arquiteto) e os pagamentos em `amigo_pagamento`. Site sem a rota (404):
  silêncio. Roda junto com a coleta de pedidos, a cada `amigos.coleta_min` (padrão 10; 0 desliga), e no "Sincronizar agora".
- Volta ao site: toda mudança feita aqui (situação, validade, notas, situação do pedido, pagamento registrado à mão) fica em
  `amigo.pendente_site` no mesmo commit e vai por POST /painel/apoios/{id} (vazio nunca apaga; "__limpar__" apaga). Enquanto não foi,
  a coleta não sobrescreve esses campos; falhou, a rodada seguinte refaz.
- Situação do Amigo: pago · pendente · vencido · recusado · isento · cancelado (o site guarda ativo/aguardando/… em _camp_mp_situacao;
  a tradução está em DO_SITE/PARA_SITE). Pago com a validade passada vira vencido sozinho (e vai ao site).
- Pagamento registrado à mão (Pix, transferência, dinheiro…): marca pago e calcula a validade por `amigos.validade_regra`
  (12_meses a partir do pagamento, padrão, ou do fim da validade atual quando ainda vale; fim_do_ano = 31/12).
- E-mails: modelos com prévia; envio em fila (`amigo_email`), um por vez, SEMPRE pelo Sender (Rafael, 18/11/2026: "sempre Sender"),
  pela rota do site POST /painel/apoios/{id}/email (contrato 1.12) com o template TR do modelo (SENDER). Nunca pelo SMTP do painel nem
  pelo wp_mail: site antigo, Sender sem chave ou template sem ID = nada sai e o histórico diz o que fazer. Lembretes automáticos (renovação N dias antes e
  vencido) atrás de `amigos.lembretes_auto` = desligado (padrão) | simular | ligado; a chave do lembrete (modelo:amigo:validade:marco)
  é única: o mesmo lembrete nunca sai duas vezes.
- Dados pessoais: só admin e master; nada de nome/e-mail no log técnico (só contagens e ids). LGPD: apagar pessoa anonimiza.
- Desativar / Reativar e Apagar (CAMP-AMIGO-APAGAR, 21/11/2026, Rafael: "opção de desativar um amigo, apagar também por favor"; contrato
  1.28, migração 239), só admin. Desativar: inativo_em (a situação de pagamento não muda); sem cobrança, lembrete nem e-mail automático,
  fora do "Enviar cobrança" e da lista padrão (filtro Inativos); o site cancela a assinatura mensal do Mercado Pago (sem reembolso) e para
  o código e os benefícios — o site falhou = nada muda aqui. Apagar: prévia + confirmação digitando o nome ou APAGAR; o site cancela a
  assinatura e apaga primeiro (falhou = nada é apagado); aqui saem os dados pessoais e o Amigo some do painel; ficam, anônimos, os
  pagamentos (valor, data, meio, chave/referência) e o número de Amigo Fundador (não volta). Histórico sem dado pessoal.
- Um Amigo por e-mail (CAMP-AMIGO-DUP, 21/11/2026, Rafael: "por que ele conseguiu fazer 2 cadastros como amigo?"; contrato 1.29, sem migração):
  o site passou a reaproveitar o cadastro não pago e a bloquear quem já é Amigo; aqui, o mesmo e-mail normalizado (normaliza_email, igual ao
  do site) em dois cadastros ganha "e-mail repetido" e o filtro Repetidos. "Juntar cadastros" (só admin): prévia (o site simula), escolha de
  qual fica, confirmação JUNTAR; o site junta primeiro (POST /painel/apoios/{id}/juntar) e só então pagamentos, e-mails, histórico e notas
  passam para o que fica e o que sai é apagado aqui (sem tirar a pessoa da lista de e-mails).
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import secrets
import threading
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import auth, email_envio, protocolo
from .config import settings
from .db import connect
from .log_tecnico import registrar

router = APIRouter(prefix="/api/amigos", tags=["amigos"])

FUSO = ZoneInfo("America/Sao_Paulo")
ROTA = "/wp-json/camp/v1/painel/apoios"
LIMPAR = "__limpar__"
LIMITE_PAGINA = 200
TIPOS = ("amigo", "projeto", "arquiteto")
SITUACOES = ("pago", "pendente", "vencido", "recusado", "isento", "cancelado")
INATIVOS = "inativos"                # filtro da lista (desativados; não é uma situação de pagamento)
REPETIDOS = "repetidos"              # CAMP-AMIGO-DUP: filtro da lista (o mesmo e-mail em mais de um cadastro de Amigo)
# CAMP-AMIGO-APAGAR: o que NÃO sai para quem está inativo (cobrança, lembretes TR16–TR19, boas-vindas). Recibo e texto livre a equipe ainda manda.
MODELOS_BLOQUEADOS_INATIVO = ("cobranca", "cobranca_pendente", "lembrete_renovacao", "aviso_vencido", "boas_vindas")
STATUS_PEDIDO = ("novo", "em_contato", "proposta", "fechado", "arquivado")
MEIOS = ("pix", "transferencia", "dinheiro", "cartao", "outro")
APROVADO = ("approved", "accredited", "authorized")
DO_SITE = {"ativo": "pago", "aguardando": "pendente", "pendente": "pendente", "recusado": "recusado", "vencido": "vencido",
           "cancelado": "cancelado", "estornado": "cancelado", "isento": "isento", "": "pendente"}
PARA_SITE = {"pago": "ativo", "pendente": "aguardando", "vencido": "vencido", "recusado": "recusado", "isento": "isento", "cancelado": "cancelado"}
CATEGORIAS_PADRAO = {"estudante": ("Estudante / Professor", 200, 20), "amigo": ("Amigo", 450, 45),
                     "guardiao": ("Guardião", 1500, 150), "patrono": ("Patrono", 6000, 600)}
ROTULO_MEIO = {"pix": "Pix", "transferencia": "transferência", "dinheiro": "dinheiro", "cartao": "cartão", "outro": "outro meio",
               "credit_card": "cartão de crédito", "debit_card": "cartão de débito", "account_money": "saldo do Mercado Pago", "ticket": "boleto",
               "bank_transfer": "Pix/transferência"}

_HOJE: date | None = None            # testes fixam o dia


def hoje() -> date:
    return _HOJE or datetime.now(FUSO).date()


# ---------------------------------------------------------------- configuração e estado
def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    v = (r[0] if r and r[0] is not None else "") or ""
    return v.strip() or padrao


def _estado(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM amigo_estado WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _estado_set(con, chave: str, valor: str) -> None:
    con.execute("INSERT INTO amigo_estado (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, valor))


def coleta_min(con) -> int:
    v = _cfg(con, "amigos.coleta_min", "10")
    return max(0, min(1440, int(v))) if v.isdigit() else 10


def lembrete_dias(con) -> list[int]:
    dias = sorted({int(x) for x in re.findall(r"\d+", _cfg(con, "amigos.lembrete_dias", "30,7")) if 0 < int(x) <= 120}, reverse=True)
    return dias or [30, 7]


def modo_lembretes(con) -> str:
    m = _cfg(con, "amigos.lembretes_auto", "desligado").lower()
    return m if m in ("desligado", "simular", "ligado") else "desligado"


def _evento(con, amigo_id: int, tipo: str, ator: str, detalhe: dict | None = None) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('amigo',?,?,?,?)",
                (str(amigo_id), tipo, ator or "painel", json.dumps(detalhe or {}, ensure_ascii=False)))


def _txt(v, maximo: int) -> str:
    return str(v if v is not None else "").strip()[:maximo]


def _dia_sp(iso: str | None) -> str | None:
    """'2027-11-18T02:59:59+00:00' (ou só a data) → '2027-11-17' (dia de São Paulo)."""
    s = str(iso or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(FUSO).date().isoformat()


def _data(s: str | None) -> date | None:
    try:
        return date.fromisoformat(str(s or "")[:10])
    except ValueError:
        return None


def _mais_um_ano(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:                 # 29/02
        return d.replace(year=d.year + 1, day=28)


def nova_validade(con, pago_em: date, validade_atual: date | None) -> date:
    """`amigos.validade_regra`: 12_meses (padrão) = 12 meses a partir do pagamento, ou do fim da validade atual quando ela ainda vale
    nessa data (renovação antecipada não perde dias); fim_do_ano = 31/12 do ano do pagamento (do ano seguinte, se já valia até lá)."""
    regra = _cfg(con, "amigos.validade_regra", "12_meses")
    ainda_vale = validade_atual is not None and validade_atual >= pago_em
    if regra == "fim_do_ano":
        ano = pago_em.year
        if ainda_vale and validade_atual >= date(pago_em.year, 12, 31):
            ano = validade_atual.year + 1
        return date(ano, 12, 31)
    return _mais_um_ano(validade_atual if ainda_vale else pago_em)


# ---------------------------------------------------------------- preços por ano
def precos(con) -> dict[int, dict[str, dict]]:
    out: dict[int, dict[str, dict]] = {}
    for r in con.execute("SELECT ano, categoria, nome, anual, mensal FROM amigo_preco ORDER BY ano, anual"):
        out.setdefault(r["ano"], {})[r["categoria"]] = {"categoria": r["categoria"], "nome": r["nome"], "anual": r["anual"], "mensal": r["mensal"]}
    return out


def categorias_do_site(con) -> dict:
    try:
        d = json.loads(_estado(con, "categorias_site") or "{}")
    except ValueError:
        d = {}
    return d if isinstance(d, dict) else {}


def _tabela_do_ano(con, ano: int) -> dict[str, dict]:
    """Os valores daquele ano (sem tabela: os do ano anterior mais próximo; antes do 1º ano: os do 1º); senão os do site; senão os do código."""
    p = precos(con)
    anos = sorted(a for a in p if a <= ano) or sorted(p)[:1]
    if anos:                               # cada ano vale por cima dos anteriores (categoria que não mudou segue com o valor anterior)
        out: dict[str, dict] = {}
        for a in anos:
            out.update(p[a])
        return out
    site = categorias_do_site(con)
    if site:
        return {k: {"categoria": k, "nome": v.get("nome") or k, "anual": float(v.get("anual") or 0), "mensal": float(v.get("mensal") or 0)} for k, v in site.items()}
    return {k: {"categoria": k, "nome": n, "anual": a, "mensal": m} for k, (n, a, m) in CATEGORIAS_PADRAO.items()}


def nome_categoria(con, cat: str | None) -> str:
    if not cat:
        return ""
    for tabela in (_tabela_do_ano(con, hoje().year), categorias_do_site(con)):
        if cat in tabela:
            return tabela[cat].get("nome") or cat
    return CATEGORIAS_PADRAO.get(cat, (cat,))[0]


def valor_previsto(con, r, ano: int | None = None) -> float | None:
    t = _tabela_do_ano(con, ano or hoje().year).get(r["categoria"] or "")
    if t:
        return float(t["mensal"] if r["modalidade"] == "mensal" else t["anual"])
    return float(r["valor_cobrado"]) if r["valor_cobrado"] else None


# ---------------------------------------------------------------- coleta (site → painel)
def _situacao_de(sit_site: str, validade: str | None) -> str:
    s = DO_SITE.get((sit_site or "").strip().lower(), "pendente")
    if s == "pago" and validade and validade < hoje().isoformat():
        return "vencido"
    return s


_FONTE = {"situacao": ("situacao_pagamento",), "situacao_site": ("situacao_pagamento",), "status_pedido": ("status",), "faixa": ("faixa", "faixa_nome"),
          "area": ("area", "area_nome"), "origem_pagina": ("origem",), "valor_cobrado": ("valor_cobrado", "valor"), "criado_no_site": ("criado_em",),
          "alterado_no_site": ("alterado_em",), "tipo": ("tipo",)}
_CAMPOS_PESSOAIS = ("nome", "empresa", "cargo", "email", "telefone", "vinculo", "mensagem", "origem_pagina")
# campo do painel → chave do POST ao site (para saber o que a coleta NÃO deve sobrescrever enquanto está pendente)
_PEND_CAMPO = {"situacao": "situacao", "validade": "validade", "notas": "notas", "status_pedido": "status", "categoria": "categoria", "modalidade": "modalidade"}


def _gravar(con, x: dict, out: dict) -> None:
    sid = x.get("id")
    if type(sid) is not int or sid <= 0:
        return
    tipo = x.get("tipo") if x.get("tipo") in TIPOS else "amigo"
    out["lidos"] += 1
    validade = _dia_sp(x.get("validade"))
    sit_site = _txt(x.get("situacao_pagamento"), 30).lower()
    dados = {
        "tipo": tipo, "protocolo": protocolo.do_site(x.get("protocolo"), sid, x.get("criado_em")),
        "categoria": _txt(x.get("categoria"), 40).lower() or None, "modalidade": "mensal" if x.get("modalidade") == "mensal" else ("anual" if tipo == "amigo" else None),
        "perfil": _txt(x.get("perfil"), 40) or None, "nome": _txt(x.get("nome"), 160) or "(sem nome)", "empresa": _txt(x.get("empresa"), 160) or None,
        "cargo": _txt(x.get("cargo"), 120) or None, "email": _txt(x.get("email"), 200) or None, "telefone": _txt(x.get("telefone"), 40) or None,
        "vinculo": _txt(x.get("vinculo"), 160) or None, "nome_publico": 1 if x.get("nome_publico") is True else 0, "emkt": 1 if x.get("emkt") is True else 0,
        "faixa": _txt(x.get("faixa_nome") or x.get("faixa"), 80) or None, "area": _txt(x.get("area_nome") or x.get("area"), 80) or None,
        "mensagem": _txt(x.get("mensagem"), 4000) or None, "origem_pagina": _txt(x.get("origem"), 200) or None,
        "status_pedido": x.get("status") if x.get("status") in STATUS_PEDIDO else "novo", "notas": _txt(x.get("notas"), 4000) or None,
        "situacao": _situacao_de(sit_site, validade) if tipo == "amigo" else None, "situacao_site": sit_site or None,
        "valor_cobrado": float(x.get("valor_cobrado") or x.get("valor") or 0) or None, "inicio": _dia_sp(x.get("inicio")), "validade": validade,
        "codigo": _txt(x.get("codigo"), 40) or None, "fundador": int(x.get("fundador") or 0) or None, "renova": 1 if x.get("renova") is True else 0,
        "criado_no_site": _txt(x.get("criado_em"), 40) or None, "alterado_no_site": _txt(x.get("alterado_em"), 40) or None,
    }
    ja = con.execute("SELECT * FROM amigo WHERE site_id=?", (sid,)).fetchone()
    if ja:                                 # campo que não veio (site mais antigo, resposta parcial) não muda o que já está aqui
        dados = {k: v for k, v in dados.items() if any(f in x for f in _FONTE.get(k, (k,)))}
        try:
            pend = json.loads(ja["pendente_site"] or "{}")
        except ValueError:
            pend = {}
        travados = {campo for campo, chave in _PEND_CAMPO.items() if chave in pend}
        if "situacao" in travados:
            travados.add("situacao_site")
        if ja["anonimizado"] or ja["apagado_em"] or x.get("apagado") is True:
            travados |= set(_CAMPOS_PESSOAIS)
        mud = {k: v for k, v in dados.items() if k not in travados and ja[k] != v}
        if mud:
            con.execute(f"UPDATE amigo SET {', '.join(k + '=?' for k in mud)}, atualizado_em=datetime('now') WHERE id=?", (*mud.values(), ja["id"]))
            out["atualizados"] += 1
            if "situacao" in mud and ja["situacao"]:
                _evento(con, ja["id"], "situacao_site", "site", {"de": ja["situacao"], "para": mud["situacao"]})
        aid = ja["id"]
        if x.get("apagado") is True and not ja["apagado_em"]:      # contrato 1.28: apagado no site (o painel segue igual)
            _anonimizar_amigo(con, aid)
    else:
        cols = list(dados)
        cur = con.execute(f"INSERT INTO amigo (site_id, {', '.join(cols)}) VALUES (?{',?' * len(cols)})", (sid, *dados.values()))
        aid = cur.lastrowid
        out["novos"] += 1
        if x.get("apagado") is True:
            _anonimizar_amigo(con, aid)
        _evento(con, aid, "criado", "site", {"tipo": tipo, "categoria": dados["categoria"], "situacao": dados["situacao"]})
    for p in x.get("pagamentos") or []:
        if not isinstance(p, dict) or not str(p.get("id") or "").strip():
            continue
        pid = str(p["id"]).strip()[:80]
        chave = pid if pid.startswith("painel-") else "mp-" + pid
        dia = _dia_sp(p.get("data")) or (dados["criado_no_site"] or "")[:10] or hoje().isoformat()
        status = _txt(p.get("status"), 30).lower() or "approved"
        n = con.execute("INSERT OR IGNORE INTO amigo_pagamento (amigo_id, chave, data, valor, meio, nota, origem, status, criado_por) VALUES (?,?,?,?,?,?,?,?, 'site')",
                        (aid, chave, dia, float(p.get("valor") or 0), _txt(p.get("meio"), 40) or None, _txt(p.get("nota"), 300) or None,
                         "manual" if chave.startswith("painel-") else "mp", status)).rowcount
        if not n:
            con.execute("UPDATE amigo_pagamento SET status=? WHERE chave=? AND origem='mp'", (status, chave))
    _recalcular_pagamento(con, aid)


def _recalcular_pagamento(con, aid: int) -> None:
    r = con.execute(f"SELECT data, valor, origem FROM amigo_pagamento WHERE amigo_id=? AND status IN ({','.join('?' * len(APROVADO))}) ORDER BY data DESC, id DESC LIMIT 1",
                    (aid, *APROVADO)).fetchone()
    if r:
        con.execute("UPDATE amigo SET pago_em=?, ultimo_valor=?, origem_pagamento=? WHERE id=?", (r["data"], r["valor"], "manual" if r["origem"] == "manual" else "site", aid))


def coletar(con=None, wp=None) -> dict:
    """Uma volta da coleta (site → painel). Nunca levanta."""
    fechar = con is None
    con = con or connect()
    out = {"lidos": 0, "novos": 0, "atualizados": 0, "sem_rota": False, "erro": None}
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
                out["sem_rota"] = True          # site ainda sem o contrato 1.11: nada a fazer
                return out
            if r.status_code >= 400:
                raise RuntimeError(f"O site respondeu {r.status_code} ao buscar os apoios")
            d = r.json()
            if isinstance(d, list):
                itens, mais = d, False
            elif isinstance(d, dict):
                itens, mais = d.get("itens") or [], bool(d.get("mais"))
                agora = agora or d.get("agora")
                if pagina == 1:
                    if isinstance(d.get("categorias"), dict) and d["categorias"]:
                        _estado_set(con, "categorias_site", json.dumps(d["categorias"], ensure_ascii=False))
                    if isinstance(d.get("fundadores"), dict):
                        _estado_set(con, "fundadores_site", json.dumps(d["fundadores"], ensure_ascii=False))
            else:
                raise RuntimeError("O site devolveu formato inválido para os apoios")
            for x in itens:
                if isinstance(x, dict):
                    _gravar(con, x, out)
            con.commit()
            if not mais:
                break
        if agora:                          # próxima volta: só o que mudou desde o começo desta (2 min de folga)
            try:
                t = datetime.fromisoformat(str(agora).replace("Z", "+00:00")) - timedelta(minutes=2)
                _estado_set(con, "desde", t.isoformat())
            except ValueError:
                pass
        _estado_set(con, "ultima_coleta", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        con.commit()
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:200]
        registrar(logging.WARNING, "amigos_coleta", "Busca dos Amigos da CAMP no site com problema", erro=out["erro"][:160])
    finally:
        if not out["sem_rota"]:
            try:
                con.execute("INSERT INTO amigo_coleta (lidos, novos, enviados, erro) VALUES (?,?,?,?)", (out["lidos"], out["novos"], out.get("enviados", 0), out["erro"]))
                con.commit()
            except Exception:  # noqa: BLE001
                pass
        if fechar:
            con.close()
    return out


# ---------------------------------------------------------------- volta ao site (painel → site)
def _marcar_pendente(con, aid: int, campos: dict) -> None:
    r = con.execute("SELECT site_id, pendente_site FROM amigo WHERE id=?", (aid,)).fetchone()
    if not r or not r["site_id"]:
        return                             # registrado só no painel: não há o que mandar
    try:
        pend = json.loads(r["pendente_site"] or "{}")
    except ValueError:
        pend = {}
    for k, v in campos.items():
        if k == "pagamentos":
            vistos = {p.get("id") for p in pend.get("pagamentos", [])}
            pend["pagamentos"] = pend.get("pagamentos", []) + [p for p in v if p.get("id") not in vistos]
        else:
            pend[k] = v
    con.execute("UPDATE amigo SET pendente_site=?, erro_site=NULL WHERE id=?", (json.dumps(pend, ensure_ascii=False), aid))


def enviar_pendentes(con=None, wp=None, so: int | None = None) -> dict:
    """Manda ao site o que mudou no painel. Falha fica guardada (e a próxima rodada refaz). Nunca levanta."""
    fechar = con is None
    con = con or connect()
    out = {"enviados": 0, "falhas": 0, "erro": None}
    try:
        q = "SELECT id, site_id, pendente_site FROM amigo WHERE pendente_site IS NOT NULL AND site_id IS NOT NULL" + (" AND id=?" if so else "") + " ORDER BY id LIMIT 200"
        rows = con.execute(q, (so,) if so else ()).fetchall()
        if not rows:
            return out
        wp = wp or _wp()
        for r in rows:
            corpo = json.loads(r["pendente_site"])
            try:
                resp = wp.h.post(f"{ROTA}/{int(r['site_id'])}", json=corpo)
            except Exception as e:  # noqa: BLE001
                con.execute("UPDATE amigo SET erro_site=? WHERE id=?", (f"Não consegui falar com o site ({type(e).__name__})", r["id"]))
                out["falhas"] += 1
                continue
            if resp.status_code == 200:
                d = {}
                try:
                    d = resp.json() or {}
                except ValueError:
                    pass
                reg = d.get("registro") if isinstance(d.get("registro"), dict) else {}
                atual = con.execute("SELECT pendente_site FROM amigo WHERE id=?", (r["id"],)).fetchone()
                resto = None
                if atual and atual["pendente_site"] and atual["pendente_site"] != r["pendente_site"]:
                    resto = atual["pendente_site"]      # mudou de novo enquanto mandava: fica para a próxima
                con.execute("UPDATE amigo SET pendente_site=?, erro_site=NULL, codigo=COALESCE(?, codigo), fundador=COALESCE(?, fundador) WHERE id=?",
                            (resto, _txt(reg.get("codigo"), 40) or None, int(reg.get("fundador") or 0) or None, r["id"]))
                _evento(con, r["id"], "enviado_site", "painel", {"campos": sorted(corpo)})
                out["enviados"] += 1
            else:
                txt = getattr(resp, "text", "") or ""
                if resp.status_code == 404 and "rest_no_route" in txt:
                    msg = "o site ainda não recebe as mudanças dos Amigos: avise quem cuida do site"
                elif resp.status_code == 404:
                    msg = "este registro não existe mais no site"
                else:
                    try:
                        msg = str((resp.json() or {}).get("message") or "")[:200]
                    except ValueError:
                        msg = ""
                    msg = f"o site recusou ({resp.status_code}){': ' + msg if msg else ''}"
                con.execute("UPDATE amigo SET erro_site=? WHERE id=?", (msg, r["id"]))
                out["falhas"] += 1
        con.commit()
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:200]
        registrar(logging.WARNING, "amigos_envio_site", "Envio das mudanças dos Amigos ao site com problema", erro=out["erro"][:160])
    finally:
        if fechar:
            con.close()
    return out


def _disparar_envio(aid: int) -> None:
    """Depois de uma mudança: tenta mandar já, em segundo plano (sem senha do site configurada, fica para a rodada)."""
    con = connect()
    try:
        tem = _cfg(con, "wp.app_password", settings.WP_APP_PASSWORD)
    finally:
        con.close()
    if tem:
        threading.Thread(target=enviar_pendentes, kwargs={"so": aid}, daemon=True).start()


# ---------------------------------------------------------------- regras locais
def vencer(con, ator: str = "painel (automático)") -> int:
    """Pago com a validade passada → vencido (e avisa o site)."""
    rows = con.execute("SELECT id FROM amigo WHERE tipo='amigo' AND situacao='pago' AND validade IS NOT NULL AND validade < ?", (hoje().isoformat(),)).fetchall()
    for r in rows:
        con.execute("UPDATE amigo SET situacao='vencido', atualizado_em=datetime('now') WHERE id=?", (r["id"],))
        _evento(con, r["id"], "vencido", ator, {})
        _marcar_pendente(con, r["id"], {"situacao": PARA_SITE["vencido"]})
    if rows:
        con.commit()
    return len(rows)


def _um(con, aid: int, apagado_ok: bool = False):
    r = con.execute("SELECT * FROM amigo WHERE id=?", (aid,)).fetchone()
    if not r or (r["apagado_em"] and not apagado_ok):
        raise HTTPException(404, "Registro não existe")
    return r


def registrar_pagamento(con, aid: int, data_pg: str, valor: float, meio: str, nota: str, ator: str) -> dict:
    r = _um(con, aid)
    if r["tipo"] != "amigo":
        raise HTTPException(400, "Pagamento só se registra para Amigos da CAMP")
    d = _data(data_pg)
    if not d or d > hoje() + timedelta(days=1):
        raise HTTPException(400, "Data do pagamento inválida")
    if not (0 < float(valor) <= 1_000_000):
        raise HTTPException(400, "Valor inválido")
    if meio not in MEIOS:
        raise HTTPException(400, "Meio de pagamento inválido")
    chave = "painel-" + secrets.token_hex(6)
    nota = _txt(nota, 300)
    con.execute("INSERT INTO amigo_pagamento (amigo_id, chave, data, valor, meio, nota, origem, status, criado_por) VALUES (?,?,?,?,?,?, 'manual', 'approved', ?)",
                (aid, chave, d.isoformat(), float(valor), meio, nota or None, ator))
    validade = nova_validade(con, d, _data(r["validade"]))
    sit = "pago" if validade >= hoje() else "vencido"
    con.execute("UPDATE amigo SET situacao=?, validade=?, atualizado_em=datetime('now') WHERE id=?", (sit, validade.isoformat(), aid))
    _recalcular_pagamento(con, aid)
    _evento(con, aid, "pagamento_manual", ator, {"data": d.isoformat(), "valor": float(valor), "meio": meio, "validade": validade.isoformat(), "de": r["situacao"]})
    _marcar_pendente(con, aid, {"situacao": PARA_SITE[sit], "validade": validade.isoformat(),
                                "pagamentos": [{"id": chave, "data": d.isoformat(), "valor": float(valor), "meio": meio, "nota": nota}]})
    con.commit()
    return {"ok": True, "situacao": sit, "validade": validade.isoformat(), "chave": chave}


def mudar(con, aid: int, campos: dict, ator: str) -> dict:
    r = _um(con, aid)
    upd, pend, mud = {}, {}, {}
    if campos.get("situacao") is not None:
        s = campos["situacao"]
        if r["tipo"] != "amigo" or s not in SITUACOES:
            raise HTTPException(400, "Situação inválida")
        if s != r["situacao"]:
            upd["situacao"] = s; pend["situacao"] = PARA_SITE[s]; mud["situacao"] = [r["situacao"], s]
    if campos.get("status_pedido") is not None:
        s = campos["status_pedido"]
        if s not in STATUS_PEDIDO:
            raise HTTPException(400, "Situação do pedido inválida")
        if s != r["status_pedido"]:
            upd["status_pedido"] = s; pend["status"] = s; mud["status_pedido"] = [r["status_pedido"], s]
    if campos.get("validade") is not None:
        v = str(campos["validade"]).strip()
        if v == "":
            if r["validade"]:
                upd["validade"] = None; pend["validade"] = LIMPAR; mud["validade"] = [r["validade"], None]
        else:
            d = _data(v)
            if not d or len(v) != 10:
                raise HTTPException(400, "Validade inválida (use AAAA-MM-DD)")
            if v != r["validade"]:
                upd["validade"] = v; pend["validade"] = v; mud["validade"] = [r["validade"], v]
    if campos.get("categoria") is not None or campos.get("modalidade") is not None:
        if r["tipo"] != "amigo":
            raise HTTPException(400, "Categoria só existe para Amigos da CAMP")
        cat = campos.get("categoria") or r["categoria"]
        mod = campos.get("modalidade") or r["modalidade"] or "anual"
        if cat not in _tabela_do_ano(con, hoje().year) or mod not in ("anual", "mensal"):
            raise HTTPException(400, "Categoria ou modalidade inválida")
        if cat != r["categoria"]:
            upd["categoria"] = cat; pend["categoria"] = cat; mud["categoria"] = [r["categoria"], cat]
        if mod != r["modalidade"]:
            upd["modalidade"] = mod; pend["modalidade"] = mod; mud["modalidade"] = [r["modalidade"], mod]
        if "categoria" in upd or "modalidade" in upd:     # o valor segue a tabela do ano
            mud["valor"] = [valor_previsto(con, r), valor_previsto(con, {"categoria": cat, "modalidade": mod, "valor_cobrado": None})]
    if campos.get("notas") is not None:
        n = _txt(campos["notas"], 4000)
        if (n or None) != r["notas"]:
            upd["notas"] = n or None; pend["notas"] = n or LIMPAR; mud["notas"] = True
    if not upd:
        return {"ok": True, "mudou": False}
    con.execute(f"UPDATE amigo SET {', '.join(k + '=?' for k in upd)}, atualizado_em=datetime('now') WHERE id=?", (*upd.values(), aid))
    _evento(con, aid, "editado", ator, mud)
    _marcar_pendente(con, aid, pend)
    con.commit()
    return {"ok": True, "mudou": True}


# ---------------------------------------------------------------- e-mails
MODELOS = {
    "boas_vindas": ("Pagamento confirmado: boas-vindas", "Boas-vindas ao Amigos da CAMP",
                    "Olá, {nome}.\n\nSeu pagamento foi confirmado. Boas-vindas ao Amigos da CAMP!\n\nCategoria: {categoria}\nVálido até: {validade}\n"
                    "{linha_codigo}{linha_fundador}\nApresente o código ao reservar visitas e cursos para usar os benefícios da sua categoria, "
                    "conforme o regulamento.\n\n{linha_protocolo}Equipe CAMP\n"),
    "lembrete_renovacao": ("Lembrete de renovação", "Sua participação no Amigos da CAMP vence em {validade}",
                           "Olá, {nome}.\n\nSua participação no Amigos da CAMP, categoria {categoria}, vale até {validade}.\n\n"
                           "Para continuar apoiando a CAMP, renove pelo site ({link}) ou responda este e-mail que combinamos o pagamento "
                           "(valor atual: {valor}).\n\nObrigado por estar com a gente.\n\n{linha_protocolo}Equipe CAMP\n"),
    "cobranca_pendente": ("Pagamento pendente", "Falta concluir o pagamento do Amigos da CAMP",
                          "Olá, {nome}.\n\nRecebemos sua adesão ao Amigos da CAMP, categoria {categoria} ({valor}), mas o pagamento ainda não "
                          "foi concluído.\n\nPara concluir, use o site ({link}) ou responda este e-mail que combinamos outra forma de pagamento.\n\n"
                          "{linha_protocolo}Equipe CAMP\n"),
    "recibo": ("Recibo simples", "Recibo da sua contribuição ao Amigos da CAMP",
               "Olá, {nome}.\n\nRecebemos de {nome_completo} o valor de {valor_pago}, em {pago_em}, por {meio}, referente à contribuição ao "
               "Amigos da CAMP, categoria {categoria}, válida até {validade}.\n\nEste recibo não substitui documento fiscal.\n\n"
               "{linha_protocolo}Equipe CAMP\n"),
    "cobranca": ("Cobrança", "Amigos da CAMP: pagamento de {valor}",
                 "Olá, {nome}.\n\nSegue a cobrança da sua participação no Amigos da CAMP.\n\nCategoria: {categoria}\nValor: {valor}\n"
                 "Pagar até: {vence_cobranca}\n\n{pagamento}\n\nSe já pagou, desconsidere este e-mail. Qualquer dúvida, é só responder.\n\n"
                 "{linha_protocolo}Equipe CAMP\n"),
    "aviso_vencido": ("Aviso de vencimento", "Sua participação no Amigos da CAMP venceu",
                      "Olá, {nome}.\n\nSua participação no Amigos da CAMP, categoria {categoria}, venceu em {validade}.\n\n"
                      "Se quiser continuar apoiando a CAMP, renove pelo site ({link}) ou responda este e-mail que combinamos o pagamento "
                      "(valor atual: {valor}).\n\n{linha_protocolo}Equipe CAMP\n"),
    "livre": ("Texto livre", "", ""),
}
VARIAVEIS = ("nome", "nome_completo", "categoria", "valor", "validade", "codigo", "fundador", "protocolo", "link", "pago_em", "valor_pago", "meio", "vence_cobranca")


class _Seguro(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def _reais(v) -> str:
    if v is None:
        return "—"
    s = f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + (s[:-3] if s.endswith(",00") else s)


def _data_br(s: str | None) -> str:
    d = _data(s)
    return d.strftime("%d/%m/%Y") if d else "—"


def variaveis(con, r) -> dict:
    nome = (r["nome"] or "").strip()
    pg = con.execute(f"SELECT data, valor, meio FROM amigo_pagamento WHERE amigo_id=? AND status IN ({','.join('?' * len(APROVADO))}) ORDER BY data DESC, id DESC LIMIT 1",
                     (r["id"], *APROVADO)).fetchone()
    vp = valor_previsto(con, r)
    valor = (_reais(vp) + (" por mês" if r["modalidade"] == "mensal" else " por ano")) if vp else "—"
    return {"nome": nome.split()[0] if nome else "olá", "nome_completo": nome, "categoria": nome_categoria(con, r["categoria"]) or "—",
            "valor": valor, "validade": _data_br(r["validade"]), "codigo": r["codigo"] or "", "fundador": str(r["fundador"] or ""),
            "protocolo": r["protocolo"] or "", "link": _cfg(con, "amigos.link_pagina", "https://camp.arq.br/amigos/"),
            "pago_em": _data_br(pg["data"]) if pg else "—", "valor_pago": _reais(pg["valor"]) if pg else "—",
            "meio": ROTULO_MEIO.get((pg["meio"] or "") if pg else "", (pg["meio"] or "—") if pg else "—"),
            "linha_codigo": f"Seu código de Amigo: {r['codigo']}\n" if r["codigo"] else "",
            "linha_fundador": f"Você é o Amigo Fundador nº {r['fundador']}.\n" if r["fundador"] else "",
            "linha_protocolo": f"Protocolo: {r['protocolo']}\n\n" if r["protocolo"] else "",
            "vence_cobranca": _data_br(r["cobranca_vence"]) if r["cobranca_vence"] else _data_br((hoje() + timedelta(days=prazo_cobranca(con))).isoformat()),
            "pagamento": (f"Pague com segurança pelo Mercado Pago:\n{r['cobranca_link']}" if r["cobranca_tipo"] == "mp" and r["cobranca_link"]
                          else "Para pagar:\n" + (_cfg(con, "amigos.cobranca_pix") or "(o link de pagamento é criado no envio)"))}


def montar(con, r, modelo: str, assunto: str = "", texto: str = "") -> dict:
    if modelo not in MODELOS:
        raise HTTPException(400, "Modelo de e-mail inválido")
    _, a, t = MODELOS[modelo]
    if modelo == "livre":
        a, t = _txt(assunto, 200), str(texto or "").strip()[:8000]
        if not a or not t:
            raise HTTPException(400, "Escreva o assunto e o texto")
    v = _Seguro(variaveis(con, r))
    return {"assunto": " ".join(a.format_map(v).split())[:200], "texto": t.format_map(v)}


# Sempre Sender (18/11/2026). modelo do painel → chave do template no site (Camp_AAP_MP::PAINEL) e TR; o lembrete de renovação usa
# o TR17 com mais de 7 dias para vencer e o TR18 com 7 ou menos. As variáveis de cada template são exatamente as que o site aceita.
TEMPLATES_SITE = {
    "amigo_boas_vindas": ("TR12", "Pagamento confirmado: boas-vindas", ("nome", "categoria", "validade", "codigo", "fundador", "protocolo", "link")),
    "amigo_cobranca":    ("TR15", "Cobrança", ("nome", "categoria", "valor", "vence", "pagamento", "link", "pix", "protocolo")),
    "amigo_pendente":    ("TR16", "Pagamento pendente", ("nome", "categoria", "valor", "link", "protocolo")),
    "amigo_lembrete_30": ("TR17", "Lembrete de renovação (faltam mais de 7 dias)", ("nome", "categoria", "validade", "dias", "valor", "link", "protocolo")),
    "amigo_lembrete_7":  ("TR18", "Lembrete de renovação (faltam 7 dias ou menos)", ("nome", "categoria", "validade", "dias", "valor", "link", "protocolo")),
    "amigo_vencido":     ("TR19", "Aviso de vencimento", ("nome", "categoria", "validade", "valor", "link", "protocolo")),
    "amigo_recibo":      ("TR20", "Recibo simples", ("nome", "nome_completo", "valor_pago", "pago_em", "meio", "categoria", "validade", "protocolo")),
    "amigo_livre":       ("TR21", "Texto livre", ("nome", "assunto", "texto", "protocolo")),
}
SENDER = {"boas_vindas": "amigo_boas_vindas", "cobranca": "amigo_cobranca", "cobranca_pendente": "amigo_pendente",
          "lembrete_renovacao": "amigo_lembrete_30", "aviso_vencido": "amigo_vencido", "recibo": "amigo_recibo", "livre": "amigo_livre"}
ONDE_TEMPLATES = "na administração do site, Apoios → Mercado Pago → E-mails pelo Sender (avise quem cuida do site)"
ROTULO_CANAL = {"sender": "Sender (pelo site)"}
SEM_SITE = "os e-mails dos Amigos saem pelo Sender do site: falta a senha do site (Application Password) em Configurações"


def _wp():
    """Cliente do site (os testes trocam por um falso)."""
    return __import__("app.wp", fromlist=["WP"]).WP()


def canal(con) -> str:
    """Sempre o Sender, pelo site: precisa da senha do site. Sem ela: ''. O SMTP do painel não é usado nos Amigos."""
    return "sender" if _cfg(con, "wp.app_password", settings.WP_APP_PASSWORD) else ""


def para_sender(con, r, modelo: str, assunto: str = "", texto: str = "") -> tuple[str, dict]:
    """(chave do template no site, variáveis que vão ao Sender) para um Amigo e um modelo do painel."""
    if modelo not in SENDER:
        raise HTTPException(400, "Modelo de e-mail inválido")
    v = variaveis(con, r)
    chave = SENDER[modelo]
    out = {"nome": v["nome"], "nome_completo": v["nome_completo"], "categoria": v["categoria"], "valor": v["valor"], "validade": v["validade"],
           "codigo": v["codigo"], "protocolo": v["protocolo"], "link": v["link"], "pago_em": v["pago_em"], "valor_pago": v["valor_pago"], "meio": v["meio"]}
    if modelo == "boas_vindas":
        out["fundador"] = f"Você é o Amigo Fundador nº {r['fundador']}." if r["fundador"] else ""
    elif modelo == "cobranca":
        mp = r["cobranca_tipo"] == "mp" and bool(r["cobranca_link"])
        out.update(vence=v["vence_cobranca"], pagamento=v["pagamento"], link=r["cobranca_link"] if mp else "",
                   pix="" if mp else _cfg(con, "amigos.cobranca_pix"))
    elif modelo == "lembrete_renovacao":
        val = _data(r["validade"])
        dias = (val - hoje()).days if val else None
        out["dias"] = str(dias) if dias is not None else ""
        if dias is not None and dias <= 7:
            chave = "amigo_lembrete_7"
    elif modelo == "livre":
        m = montar(con, r, modelo, assunto, texto)
        out.update(assunto=m["assunto"], texto=m["texto"])
    return chave, {k: out.get(k, "") for k in TEMPLATES_SITE[chave][2]}


class SiteErro(Exception):
    """Envio pelo site/Sender que não saiu. `parar`: o resto da fila espera a próxima rodada (limite do site)."""
    def __init__(self, msg: str, parar: bool = False):
        super().__init__(msg)
        self.parar = parar


def _msg_site(resp, chave: str) -> str:
    """Mensagem para a equipe a partir da resposta do site (contrato 1.12)."""
    tr, rot = TEMPLATES_SITE.get(chave, ("", ""))[:2]
    txt = getattr(resp, "text", "") or ""
    try:
        d = resp.json() or {}
    except ValueError:
        d = {}
    d = d if isinstance(d, dict) else {}
    cod = str(d.get("code") or "")
    if resp.status_code == 404 and ("rest_no_route" in txt or cod == "rest_no_route"):
        return "não enviado: o site ainda não manda os e-mails dos Amigos pelo Sender. Atualize o site (plugin da CAMP 1.25.12 ou mais novo)"
    if cod == "camp_sender_sem_template":
        return f"não enviado: falta o template {tr} ({rot}) do Sender no site. Crie no Sender e cole o ID {ONDE_TEMPLATES}"
    if cod == "camp_sender_sem_chave":
        return "não enviado: o Sender está desligado no site (sem o token). Preencha o token do Sender em Configurações → E-mail e avisos e envie ao site"
    if cod == "camp_apoio_nao_existe":
        return "não enviado: este registro não existe mais no site"
    msg = str(d.get("message") or "")[:200]
    if cod == "camp_sender_falhou":
        return f"não enviado: o Sender recusou ({msg or resp.status_code})"
    return f"não enviado: o site respondeu {resp.status_code}{': ' + msg if msg else ''}"


def _enviar_sender(con, wp, a, para: str, chave: str, vars_: dict, simular: bool = False) -> str:
    """Um e-mail pelo site → Sender. Devolve o id do Sender. Levanta SiteErro com mensagem segura (sem token)."""
    corpo = {"modelo": chave, "variaveis": vars_, "para": para, "nome": (a["nome"] or "") if a else ""}
    if simular:
        corpo["simular"] = True
    sid = int(a["site_id"]) if a and a["site_id"] else 0
    try:
        resp = wp.h.post(f"{ROTA}/{sid}/email", json=corpo)
    except Exception as e:  # noqa: BLE001
        raise SiteErro(f"não enviado: não consegui falar com o site ({type(e).__name__})") from e
    if resp.status_code == 200:
        try:
            d = resp.json() or {}
        except ValueError:
            d = {}
        if not simular and not (isinstance(d, dict) and d.get("enviado")):
            raise SiteErro("não enviado: o site não confirmou o envio pelo Sender")
        return str(((d.get("sender") or {}) if isinstance(d, dict) else {}).get("id") or "")
    if resp.status_code == 429:
        raise SiteErro("não enviado agora: o site limitou os envios (429); fica na fila", parar=True)
    raise SiteErro(_msg_site(resp, chave))


def conferir_site(con, wp, rows, modelo: str, assunto: str = "", texto: str = "") -> list[dict]:
    """Pergunta ao site (simular, nada sai) se cada template que este envio usaria está pronto. Um pedido por template."""
    vistos, out = {}, []
    for r in rows:
        chave, vars_ = para_sender(con, r, modelo, assunto, texto)
        if chave not in vistos:
            vistos[chave] = (r, vars_)
    for chave, (r, vars_) in vistos.items():
        tr, rot = TEMPLATES_SITE[chave][:2]
        try:
            _enviar_sender(con, wp, r, r["email"], chave, vars_, simular=True)
            out.append({"template": tr, "rotulo": rot, "pronto": True, "mensagem": ""})
        except SiteErro as e:
            out.append({"template": tr, "rotulo": rot, "pronto": False, "mensagem": str(e)})
    return out


def previa(con, ids: list[int], modelo: str, assunto: str = "", texto: str = "", wp=None) -> dict:
    rows = _linhas(con, ids)
    com = [r for r in rows if email_envio.ENDERECO.match(r["email"] or "")]
    exemplos = []
    for r in com[:3]:
        m = montar(con, r, modelo, assunto, texto)
        chave, vars_ = para_sender(con, r, modelo, assunto, texto)
        exemplos.append({"id": r["id"], "nome": r["nome"], "para": r["email"], **m, "template": TEMPLATES_SITE[chave][0],
                         "rotulo_template": TEMPLATES_SITE[chave][1], "variaveis": vars_})
    if not com and rows:
        montar(con, rows[0], modelo, assunto, texto)          # valida o modelo/texto mesmo sem destinatário
    semana = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    rep = 0
    if com:
        rep = con.execute(f"SELECT COUNT(DISTINCT amigo_id) FROM amigo_email WHERE modelo=? AND situacao<>'falhou' AND criado_em>=? AND amigo_id IN ({','.join('?' * len(com))})",
                          (modelo, semana, *[r["id"] for r in com])).fetchone()[0]
    c = canal(con) if wp is None else "sender"
    return {"total": len(rows), "com_email": len(com), "sem_email": [r["nome"] for r in rows if r not in com][:50], "exemplos": exemplos,
            "canal": c, "rotulo_canal": ROTULO_CANAL.get(c, ""), "repetidos_7_dias": rep, "site": _conferir_seguro(con, wp, com, c, modelo, assunto, texto)}


def _conferir_seguro(con, wp, com, c, modelo, assunto="", texto="") -> list[dict]:
    if not com or not c:
        return []
    try:
        return conferir_site(con, wp or _wp(), com, modelo, assunto, texto)
    except Exception:  # noqa: BLE001  (a prévia nunca quebra por causa do site)
        return []


def _linhas(con, ids: list[int]):
    ids = sorted({int(i) for i in ids if int(i) > 0})[:2000]
    if not ids:
        return []
    return con.execute(f"SELECT * FROM amigo WHERE id IN ({','.join('?' * len(ids))}) ORDER BY nome", ids).fetchall()


def enfileirar(con, ids: list[int], modelo: str, assunto: str, texto: str, ator: str, chave: str | None = None) -> int:
    n = 0
    for r in _linhas(con, ids):
        if not email_envio.ENDERECO.match(r["email"] or "") or _bloqueado(r, modelo):
            continue
        m = montar(con, r, modelo, assunto, texto)
        ms, vars_ = para_sender(con, r, modelo, assunto, texto)
        cur = con.execute("INSERT OR IGNORE INTO amigo_email (amigo_id, modelo, assunto, corpo, para, chave, criado_por, modelo_site, variaveis) VALUES (?,?,?,?,?,?,?,?,?)",
                          (r["id"], modelo, m["assunto"], m["texto"], r["email"], chave.format(id=r["id"]) if chave else None, ator, ms,
                           json.dumps(vars_, ensure_ascii=False)))
        n += cur.rowcount
    con.commit()
    return n


def processar_fila(con=None, limite: int = 60, wp=None) -> dict:
    """Manda os e-mails na fila, um por vez, SEMPRE pelo Sender do site (POST /painel/apoios/{id}/email). Registra cada envio
    (ou o motivo de não ter saído: site antigo, Sender sem chave, template sem ID) no histórico do Amigo. Nunca levanta."""
    fechar = con is None
    con = con or connect()
    out = {"enviados": 0, "falhas": 0}
    try:
        c = "sender" if wp is not None else canal(con)
        for e in con.execute("SELECT * FROM amigo_email WHERE situacao='na_fila' ORDER BY id LIMIT ?", (limite,)).fetchall():
            a = con.execute("SELECT * FROM amigo WHERE id=?", (e["amigo_id"],)).fetchone()
            chave = e["modelo_site"] or ""
            try:
                if not c:
                    raise SiteErro("não enviado: " + SEM_SITE)
                if not a or a["apagado_em"]:
                    raise SiteErro("não enviado: o Amigo não existe mais no painel")
                if _bloqueado(a, e["modelo"]):
                    raise SiteErro("não enviado: o Amigo está inativo")
                try:
                    vars_ = json.loads(e["variaveis"]) if e["variaveis"] else None
                except ValueError:
                    vars_ = None
                if not chave or vars_ is None:          # entrou na fila antes do "sempre Sender": monta agora
                    chave, vars_ = para_sender(con, a, e["modelo"], e["assunto"] or "", e["corpo"] or "") if e["modelo"] != "livre" else \
                        ("amigo_livre", {"nome": variaveis(con, a)["nome"], "assunto": e["assunto"] or "", "texto": e["corpo"] or "", "protocolo": a["protocolo"] or ""})
                wp = wp or _wp()
                sid = _enviar_sender(con, wp, a, e["para"], chave, vars_)
            except (SiteErro, HTTPException) as err:
                msg = str(getattr(err, "detail", None) or err)[:240]
                if getattr(err, "parar", False):        # o site limita: o resto fica na fila para a próxima rodada
                    break
                con.execute("UPDATE amigo_email SET situacao='falhou', canal=?, erro=?, modelo_site=COALESCE(modelo_site, ?) WHERE id=?",
                            (c or None, msg, chave or None, e["id"]))
                _evento(con, e["amigo_id"], "email_falhou", e["criado_por"] or "painel", {"modelo": e["modelo"], "canal": c, "template": TEMPLATES_SITE.get(chave, ("",))[0], "erro": msg})
                out["falhas"] += 1
            else:
                con.execute("UPDATE amigo_email SET situacao='enviado', canal=?, erro=NULL, enviado_em=datetime('now'), sender_id=?, modelo_site=? WHERE id=?",
                            (c, sid or None, chave, e["id"]))
                _evento(con, e["amigo_id"], "email_enviado", e["criado_por"] or "painel", {"modelo": e["modelo"], "canal": c, "template": TEMPLATES_SITE[chave][0], "assunto": e["assunto"]})
                out["enviados"] += 1
            con.commit()
    except Exception as err:  # noqa: BLE001
        registrar(logging.WARNING, "amigos_email", "Fila de e-mails dos Amigos com problema", erro=f"{type(err).__name__}")
    finally:
        if fechar:
            con.close()
    if out["enviados"] or out["falhas"]:
        registrar(logging.INFO, "amigos_email", "E-mails dos Amigos enviados", enviados=out["enviados"], falhas=out["falhas"])
    return out


def prazo_cobranca(con) -> int:
    v = _cfg(con, "amigos.cobranca_prazo_dias", "7")
    return max(1, min(90, int(v))) if v.isdigit() else 7


def intervalo_cobranca(con) -> int:
    v = _cfg(con, "amigos.cobranca_intervalo_dias", "3")
    return max(0, min(60, int(v))) if v.isdigit() else 3


def _cobranca_recente(con, r) -> bool:
    if not r["cobranca_em"]:
        return False
    limite = (datetime.now(timezone.utc) - timedelta(days=intervalo_cobranca(con))).strftime("%Y-%m-%d %H:%M:%S")
    return r["cobranca_em"] >= limite


def previa_cobranca(con, ids: list[int]) -> dict:
    todas = [r for r in _linhas(con, ids) if r["tipo"] == "amigo"]
    rows = [r for r in todas if not _bloqueado(r, "cobranca")]
    com = [r for r in rows if email_envio.ENDERECO.match(r["email"] or "")]
    ex = None
    if com:
        chave, vars_ = para_sender(con, com[0], "cobranca")
        ex = {"para": com[0]["email"], **montar(con, com[0], "cobranca"), "template": TEMPLATES_SITE[chave][0],
              "rotulo_template": TEMPLATES_SITE[chave][1], "variaveis": vars_}
    c = canal(con)
    return {"total": len(rows), "com_email": len(com), "sem_email": [r["nome"] for r in rows if r not in com][:50], "exemplo": ex,
            "repetidas": [{"id": r["id"], "nome": r["nome"], "em": r["cobranca_em"]} for r in com if _cobranca_recente(con, r)],
            "canal": c, "rotulo_canal": ROTULO_CANAL.get(c, ""), "pix": bool(_cfg(con, "amigos.cobranca_pix")), "prazo_dias": prazo_cobranca(con),
            "intervalo_dias": intervalo_cobranca(con), "site": _conferir_seguro(con, None, com[:1], c, "cobranca"),
            "inativos": [r["nome"] for r in todas if r not in rows][:50]}


def _link_mp(con, wp, r) -> tuple[str | None, str]:
    """Pede ao site o link do Mercado Pago (contrato 1.11, POST /painel/apoios/{id}/cobranca). → (link, motivo de não ter)."""
    if not r["site_id"]:
        return None, "registrado só no painel"
    if wp is None:
        try:
            wp = _wp()
        except Exception:  # noqa: BLE001
            return None, "sem a senha do site"
    corpo = {"categoria": r["categoria"], "modalidade": r["modalidade"] or "anual"}
    vp = valor_previsto(con, r)
    if vp:
        corpo["valor"] = vp
    try:
        resp = wp.h.post(f"{ROTA}/{int(r['site_id'])}/cobranca", json=corpo)
    except Exception as e:  # noqa: BLE001
        return None, f"não consegui falar com o site ({type(e).__name__})"
    if resp.status_code == 200:
        try:
            link = str((resp.json() or {}).get("link") or "")
        except ValueError:
            link = ""
        if re.match(r"^https://(www\.|sandbox\.)?mercadopago\.com(\.br)?/", link):
            return link, ""
        return None, "o site não devolveu um link do Mercado Pago"
    txt = getattr(resp, "text", "") or ""
    if resp.status_code == 404 and "rest_no_route" in txt:
        return None, "o site ainda não cria cobranças pelo painel"
    try:
        msg = str((resp.json() or {}).get("message") or "")[:200]
    except ValueError:
        msg = ""
    return None, msg or f"o site respondeu {resp.status_code}"


def cobrar(con, ids: list[int], ator: str, forcar: bool = False, wp=None) -> dict:
    """Cobrança: link do Mercado Pago (pelo site) ou, com o pagamento online desligado, as instruções de Pix do painel; vai por
    e-mail (fila). A mesma pessoa não é cobrada de novo antes de `amigos.cobranca_intervalo_dias` sem `forcar`."""
    out = {"na_fila": 0, "mp": 0, "manual": 0, "repetidas": [], "sem_email": [], "erros": [], "inativos": []}
    if not canal(con) and wp is None:
        raise HTTPException(409, "Os e-mails dos Amigos saem pelo Sender do site: preencha a senha do site (Application Password) em Configurações.")
    pix = _cfg(con, "amigos.cobranca_pix")
    for r in _linhas(con, ids):
        if r["tipo"] != "amigo":
            continue
        if _bloqueado(r, "cobranca"):                     # desativado ou apagado: nunca cobra (nem com "forcar")
            out["inativos"].append(r["nome"]); continue
        if not email_envio.ENDERECO.match(r["email"] or ""):
            out["sem_email"].append(r["nome"]); continue
        if _cobranca_recente(con, r) and not forcar:
            out["repetidas"].append({"id": r["id"], "nome": r["nome"], "em": r["cobranca_em"]}); continue
        link, motivo = _link_mp(con, wp, r)
        if not link and not pix:
            out["erros"].append({"id": r["id"], "nome": r["nome"], "erro": f"sem link do Mercado Pago ({motivo}) e sem o texto de pagamento manual (Pix) em Valores e regras"})
            continue
        tipo = "mp" if link else "manual"
        vence = (hoje() + timedelta(days=prazo_cobranca(con))).isoformat()
        nova = "pendente" if r["situacao"] in ("pendente", "vencido", "recusado", "cancelado", None) else r["situacao"]
        con.execute("UPDATE amigo SET cobranca_em=datetime('now'), cobranca_tipo=?, cobranca_link=?, cobranca_vence=?, situacao=?, atualizado_em=datetime('now') WHERE id=?",
                    (tipo, link, vence, nova, r["id"]))
        _evento(con, r["id"], "cobranca", ator, {"tipo": tipo, "valor": valor_previsto(con, r), "vence": vence, "sem_link": motivo if not link else None})
        if nova != r["situacao"]:
            _marcar_pendente(con, r["id"], {"situacao": PARA_SITE[nova]})
        con.commit()
        out["na_fila"] += enfileirar(con, [r["id"]], "cobranca", "", "", ator)
        out[tipo] += 1
    return out


_FILA_LOCK = threading.Lock()


def _fila_em_segundo_plano() -> None:
    def _rodar():
        if not _FILA_LOCK.acquire(blocking=False):
            return
        try:
            processar_fila()
        finally:
            _FILA_LOCK.release()
    threading.Thread(target=_rodar, daemon=True).start()


def lembretes_devidos(con) -> list[dict]:
    """Quem receberia um lembrete automático hoje (e ainda não recebeu aquele lembrete)."""
    h, dias, out = hoje(), lembrete_dias(con), []
    for r in con.execute("SELECT * FROM amigo WHERE tipo='amigo' AND anonimizado=0 AND inativo_em IS NULL AND apagado_em IS NULL AND situacao IN ('pago','vencido') AND validade IS NOT NULL ORDER BY validade, nome"):
        v = _data(r["validade"])
        if not v:
            continue
        falta = (v - h).days
        if r["situacao"] == "pago" and 0 <= falta <= dias[0]:
            marco = min(m for m in dias if falta <= m)
            modelo, chave = "lembrete_renovacao", f"renovacao:{r['id']}:{r['validade']}:{marco}"
        elif r["situacao"] == "vencido" and -60 <= falta < 0:
            marco, modelo, chave = 0, "aviso_vencido", f"vencido:{r['id']}:{r['validade']}"
        else:
            continue
        if con.execute("SELECT 1 FROM amigo_email WHERE chave=?", (chave,)).fetchone():
            continue
        out.append({"id": r["id"], "nome": r["nome"], "tem_email": bool(email_envio.ENDERECO.match(r["email"] or "")), "validade": r["validade"],
                    "dias": falta, "marco": marco, "modelo": modelo, "chave": chave})
    return out


def rodar_lembretes(con, modo: str | None = None) -> dict:
    modo = modo or modo_lembretes(con)
    if modo == "desligado":
        return {"modo": modo, "seriam": [], "enfileirados": 0}
    seriam = lembretes_devidos(con)
    if modo == "simular":
        _estado_set(con, "lembretes_simulacao", json.dumps({"quando": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                                                             "ids": [s["id"] for s in seriam], "n": len(seriam)}))
        con.commit()
        return {"modo": modo, "seriam": seriam, "enfileirados": 0}
    n = 0
    for s in seriam:
        if s["tem_email"]:
            n += enfileirar(con, [s["id"]], s["modelo"], "", "", "painel (automático)", chave=s["chave"])
    return {"modo": modo, "seriam": seriam, "enfileirados": n}


def rodada(force: bool = False) -> dict:
    """A volta do coletor: manda o pendente, busca o site, vence, lembretes (pelo modo) e a fila de e-mails. Nunca levanta."""
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
        tem_site = bool(_cfg(con, "wp.app_password", settings.WP_APP_PASSWORD))   # sem a senha do site: só as regras locais
        out = {"envio": enviar_pendentes(con) if tem_site else None}
        out["coleta"] = coletar(con) if tem_site else None
        out["vencidos"] = vencer(con)
        if out["vencidos"] and tem_site:
            out["envio2"] = enviar_pendentes(con)
        out["lembretes"] = {k: v for k, v in rodar_lembretes(con).items() if k != "seriam"}
        out["fila"] = processar_fila(con)
        return out
    except Exception as e:  # noqa: BLE001
        registrar(logging.WARNING, "amigos_rodada", "Rodada dos Amigos com problema", erro=type(e).__name__)
        return {"erro": type(e).__name__}
    finally:
        con.close()


def anonimizar_por_email(con, email: str) -> int:
    """LGPD (apagar pessoa): tira nome, e-mail, telefone, notas e textos do painel; ficam os valores pagos (receita). Não faz commit."""
    em = (email or "").strip().lower()
    if not em:
        return 0
    ids = [r[0] for r in con.execute("SELECT id FROM amigo WHERE lower(email)=?", (em,))]
    if ids:
        q = ",".join("?" * len(ids))
        con.execute(f"""UPDATE amigo SET nome='(removido)', empresa=NULL, cargo=NULL, email=NULL, telefone=NULL, vinculo=NULL, mensagem=NULL,
                        origem_pagina=NULL, notas=NULL, anonimizado=1 WHERE id IN ({q})""", ids)
        con.execute(f"UPDATE amigo_email SET para=NULL, corpo=NULL, assunto=NULL WHERE amigo_id IN ({q})", ids)
    return len(ids)


# ---------------------------------------------------------------- desativar, reativar e apagar (CAMP-AMIGO-APAGAR, contrato 1.28)
SITE_ANTIGO_ACAO = "o site ainda não desativa nem apaga Amigos: avise quem cuida do site (plugin da CAMP 1.37.0 ou mais novo)"
SITE_ANTIGO_JUNTAR = "o site ainda não junta cadastros de Amigo: avise quem cuida do site (plugin da CAMP 1.38.0 ou mais novo)"
APAGA = ("nome", "e-mail", "telefone", "empresa e cargo", "vínculo", "mensagem", "notas da equipe", "motivo da desativação", "código do Amigo",
         "acesso à área do Amigo", "inscrição na lista de e-mails da CAMP (Sender)", "endereço e texto dos e-mails enviados")
FICA = ("pagamentos: valor, data, meio e referência (Mercado Pago ou painel), para a contabilidade", "categoria e modalidade",
        "número de Amigo Fundador (fica gasto: não volta para a fila)", "histórico sem dados pessoais")


def _bloqueado(r, modelo: str) -> bool:
    """Apagado: nada sai. Inativo: cobrança, lembretes e boas-vindas não saem (recibo e texto livre, sim)."""
    return bool(r["apagado_em"]) or (bool(r["inativo_em"]) and modelo in MODELOS_BLOQUEADOS_INATIVO)


def _chamar_site(con, wp, r, acao: str, corpo: dict) -> tuple[dict | None, str]:
    """POST /painel/apoios/{site_id}/{acao} (contrato 1.28). → (resposta, "") ou (None, motivo). Nunca levanta."""
    if wp is None:
        try:
            wp = _wp()
        except Exception:  # noqa: BLE001
            return None, "o painel não tem a senha do site (Application Password em Configurações)"
    try:
        resp = wp.h.post(f"{ROTA}/{int(r['site_id'])}/{acao}", json=corpo)
    except Exception as e:  # noqa: BLE001
        return None, f"não consegui falar com o site ({type(e).__name__})"
    if resp.status_code == 200:
        try:
            d = resp.json() or {}
        except ValueError:
            d = {}
        return (d, "") if d.get("ok") else (None, "o site não confirmou")
    txt = getattr(resp, "text", "") or ""
    if resp.status_code == 404 and "rest_no_route" in txt:
        return None, SITE_ANTIGO_JUNTAR if acao == "juntar" else SITE_ANTIGO_ACAO
    try:
        msg = str((resp.json() or {}).get("message") or "")[:240]
    except ValueError:
        msg = ""
    return None, msg or f"o site respondeu {resp.status_code}"


def _sem_mudar(prefixo: str, erro: str) -> str:
    """'Não foi desativado: <motivo>.' (o site já diz "Nada foi mudado: …": não repete)."""
    motivo = re.sub(r"^Nada foi (mudado|apagado):\s*", "", erro.strip()).rstrip(". ")
    return f"{prefixo}: {motivo}."


def _assinatura_ativa_provavel(r) -> bool:
    """Sem resposta do site: mensal que renova sozinha = provavelmente há assinatura no Mercado Pago."""
    return r["modalidade"] == "mensal" and bool(r["renova"])


def previa_desativar(con, ids: list[int], wp=None) -> dict:
    """Quem vai ser desativado e de quem a assinatura mensal do Mercado Pago vai ser cancelada (o site simula; nada muda)."""
    itens = []
    for r in _linhas(con, ids):
        if r["tipo"] != "amigo" or r["apagado_em"]:
            continue
        x = {"id": r["id"], "nome": r["nome"], "ja_inativo": bool(r["inativo_em"]), "assinatura": False, "confirmado_no_site": False, "erro": ""}
        if not r["inativo_em"] and r["site_id"]:
            d, motivo = _chamar_site(con, wp, r, "desativar", {"simular": True})
            if d:
                x["assinatura"], x["confirmado_no_site"] = bool((d.get("assinatura") or {}).get("havia")), True
            else:
                x["assinatura"], x["erro"] = _assinatura_ativa_provavel(r), motivo
        itens.append(x)
    return {"itens": itens, "total": sum(1 for x in itens if not x["ja_inativo"]), "assinaturas": [x["nome"] for x in itens if x["assinatura"] and not x["ja_inativo"]],
            "ja_inativos": [x["nome"] for x in itens if x["ja_inativo"]]}


def desativar(con, ids: list[int], motivo: str, ator: str, wp=None) -> dict:
    """Desativa (o site cancela a assinatura mensal e para o código; falhou = esta pessoa não muda). Reversível com reativar()."""
    out = {"desativados": 0, "assinaturas_canceladas": 0, "ja_inativos": 0, "erros": []}
    motivo = _txt(motivo, 500)
    for r in _linhas(con, ids):
        if r["tipo"] != "amigo" or r["apagado_em"]:
            continue
        if r["inativo_em"]:
            out["ja_inativos"] += 1; continue
        cancelada = False
        if r["site_id"]:
            d, erro = _chamar_site(con, wp, r, "desativar", {})
            if not d:
                out["erros"].append({"id": r["id"], "nome": r["nome"], "erro": _sem_mudar("Não foi desativado", erro)}); continue
            cancelada = bool((d.get("assinatura") or {}).get("cancelada"))
        con.execute("UPDATE amigo SET inativo_em=datetime('now'), inativo_motivo=?, inativo_por=?, atualizado_em=datetime('now') WHERE id=?", (motivo or None, ator, r["id"]))
        n_fila = con.execute(f"UPDATE amigo_email SET situacao='falhou', erro='não enviado: o Amigo foi desativado' WHERE amigo_id=? AND situacao='na_fila' "
                             f"AND modelo IN ({','.join('?' * len(MODELOS_BLOQUEADOS_INATIVO))})", (r["id"], *MODELOS_BLOQUEADOS_INATIVO)).rowcount
        _evento(con, r["id"], "desativado", ator, {"motivo": motivo or None, "assinatura_cancelada": cancelada, "so_no_painel": not r["site_id"], "fila_cancelada": n_fila})
        con.commit()
        out["desativados"] += 1
        out["assinaturas_canceladas"] += int(cancelada)
    if out["desativados"]:
        registrar(logging.INFO, "amigos_desativar", "Amigos desativados", n=out["desativados"], assinaturas=out["assinaturas_canceladas"], falhas=len(out["erros"]))
    return out


def reativar(con, ids: list[int], ator: str, wp=None) -> dict:
    out = {"reativados": 0, "erros": []}
    for r in _linhas(con, ids):
        if r["tipo"] != "amigo" or r["apagado_em"] or not r["inativo_em"]:
            continue
        if r["site_id"]:
            d, erro = _chamar_site(con, wp, r, "reativar", {})
            if not d:
                out["erros"].append({"id": r["id"], "nome": r["nome"], "erro": _sem_mudar("Não foi reativado", erro)}); continue
        con.execute("UPDATE amigo SET inativo_em=NULL, inativo_motivo=NULL, inativo_por=NULL, atualizado_em=datetime('now') WHERE id=?", (r["id"],))
        _evento(con, r["id"], "reativado", ator, {"assinatura_volta": False})
        con.commit()
        out["reativados"] += 1
    return out


def _anonimizar_amigo(con, aid: int) -> None:
    """Tira os dados pessoais deste Amigo (painel). Ficam os pagamentos (sem a observação) e o número de Fundador. Não faz commit."""
    con.execute("""UPDATE amigo SET nome='(removido)', empresa=NULL, cargo=NULL, email=NULL, telefone=NULL, vinculo=NULL, mensagem=NULL, origem_pagina=NULL,
                   notas=NULL, inativo_motivo=NULL, codigo=NULL, cobranca_link=NULL, pendente_site=NULL, erro_site=NULL, nome_publico=0, emkt=0,
                   anonimizado=1, apagado_em=COALESCE(apagado_em, datetime('now')), atualizado_em=datetime('now') WHERE id=?""", (aid,))
    con.execute("UPDATE amigo_email SET para=NULL, corpo=NULL, assunto=NULL, variaveis=NULL, situacao=CASE WHEN situacao='na_fila' THEN 'falhou' ELSE situacao END WHERE amigo_id=?", (aid,))
    con.execute("UPDATE amigo_pagamento SET nota=NULL WHERE amigo_id=?", (aid,))
    for e in con.execute("SELECT id, detalhe FROM evento WHERE entidade='amigo' AND codigo=?", (str(aid),)).fetchall():
        try:
            d = json.loads(e["detalhe"] or "{}")
        except ValueError:
            d = {}
        if isinstance(d, dict) and {"motivo", "assunto", "nota", "erro"} & set(d):
            con.execute("UPDATE evento SET detalhe=? WHERE id=?", (json.dumps({k: v for k, v in d.items() if k not in ("motivo", "assunto", "nota", "erro")}, ensure_ascii=False), e["id"]))


def _confere_nome(digitado: str, nome: str) -> bool:
    n = lambda v: re.sub(r"\s+", " ", str(v or "")).strip().casefold()
    return bool(n(digitado)) and (n(digitado) == "apagar" or n(digitado) == n(nome))


def previa_apagar(con, aid: int, wp=None) -> dict:
    r = _um(con, aid)
    if r["tipo"] != "amigo":
        raise HTTPException(400, "Só Amigos da CAMP são apagados por aqui")
    pags = con.execute("SELECT COUNT(*) n, COALESCE(SUM(valor),0) v FROM amigo_pagamento WHERE amigo_id=?", (aid,)).fetchone()
    out = {"id": aid, "nome": r["nome"], "apaga": list(APAGA), "fica": list(FICA), "pagamentos": pags["n"], "pagamentos_valor": float(pags["v"]),
           "fundador": r["fundador"], "emails": con.execute("SELECT COUNT(*) FROM amigo_email WHERE amigo_id=?", (aid,)).fetchone()[0],
           "assinatura": False, "confirmado_no_site": not r["site_id"], "no_site": bool(r["site_id"]), "erro_site": ""}
    if r["site_id"]:
        d, motivo = _chamar_site(con, wp, r, "apagar", {"simular": True})
        if d:
            out["assinatura"], out["confirmado_no_site"] = bool((d.get("assinatura") or {}).get("havia")), True
        else:
            out["assinatura"], out["erro_site"] = _assinatura_ativa_provavel(r), motivo
    return out


def apagar(con, aid: int, confirmacao: str, ator: str, wp=None) -> dict:
    """Irreversível. 1) confere a confirmação (nome ou APAGAR); 2) o site cancela a assinatura mensal e apaga (falhou = NADA é apagado);
    3) aqui: dados pessoais saem, o Amigo some do painel, pagamentos ficam anônimos; lista de e-mails e E-mails enviados sem a pessoa."""
    r = _um(con, aid)
    if r["tipo"] != "amigo":
        raise HTTPException(400, "Só Amigos da CAMP são apagados por aqui")
    if not _confere_nome(confirmacao, r["nome"]):
        raise HTTPException(400, "Para apagar, digite o nome da pessoa ou APAGAR. Nada foi apagado.")
    site = {"assinatura": {}, "sender": {}}
    if r["site_id"]:
        d, erro = _chamar_site(con, wp, r, "apagar", {"simular": False, "confirmar": "APAGAR"})
        if not d:
            raise HTTPException(502, _sem_mudar("Nada foi apagado", erro))
        site = d
    email = (r["email"] or "").strip().lower()
    _anonimizar_amigo(con, aid)
    n_lista = n_env = 0
    if email and not con.execute("SELECT 1 FROM amigo WHERE lower(email)=? AND id<>?", (email, aid)).fetchone():
        from . import contatos_emkt, emails_enviados
        n_lista = contatos_emkt.apagar_por_email(con, email)
        n_env = emails_enviados.apagar_por_email(con, email)
    pags = con.execute("SELECT COUNT(*) FROM amigo_pagamento WHERE amigo_id=?", (aid,)).fetchone()[0]
    cancelada = bool((site.get("assinatura") or {}).get("cancelada"))
    _evento(con, aid, "apagado", ator, {"pagamentos_mantidos": pags, "fundador": r["fundador"], "assinatura_cancelada": cancelada, "no_site": bool(r["site_id"]),
                                        "sender": str((site.get("sender") or {}).get("status") or "")[:20] or None, "lista_email": n_lista, "emails_enviados": n_env})
    con.commit()
    registrar(logging.INFO, "amigos_apagar", "Amigo apagado (dados pessoais removidos; pagamentos mantidos)", amigo=aid, pagamentos=pags)
    return {"ok": True, "pagamentos_mantidos": pags, "assinatura_cancelada": cancelada, "sender": (site.get("sender") or {}).get("status"),
            "sender_erro": (site.get("sender") or {}).get("erro") or ""}


# ---------------------------------------------------------------- CAMP-AMIGO-DUP: e-mail repetido e "Juntar cadastros"
def normaliza_email(e) -> str:
    """O mesmo do site (Camp_AAP_Amigo::normaliza_email): minúsculas, sem espaços; no Gmail sem pontos e sem o "+sufixo"."""
    e = str(e or "").strip().lower()
    if "@" not in e:
        return e
    u, dom = e.split("@", 1)
    if dom in ("gmail.com", "googlemail.com"):
        u, dom = u.split("+", 1)[0].replace(".", ""), "gmail.com"
    return f"{u}@{dom}"


def repetidos(con) -> dict[int, list[int]]:
    """id do Amigo → ids dos OUTROS cadastros de Amigo (não apagados, inativos inclusive) com o mesmo e-mail normalizado."""
    grupos: dict[str, list[int]] = {}
    for r in con.execute("SELECT id, email FROM amigo WHERE tipo='amigo' AND apagado_em IS NULL AND email IS NOT NULL AND trim(email)<>'' ORDER BY id"):
        grupos.setdefault(normaliza_email(r["email"]), []).append(r["id"])
    return {i: [j for j in ids if j != i] for ids in grupos.values() if len(ids) > 1 for i in ids}


def _ativo(r) -> bool:
    return r["situacao"] in ("pago", "isento") and not r["inativo_em"]


def _quem_fica(a, b):
    """Padrão: o ativo; senão o do pagamento mais recente; senão o da adesão mais recente. → (fica, sai)."""
    nota = lambda r: (1 if _ativo(r) else 0, r["pago_em"] or "", r["criado_no_site"] or r["importado_em"] or "", r["id"])
    return (a, b) if nota(a) >= nota(b) else (b, a)


def _par_juntar(con, aid: int, outro: int, fica: int | None = None):
    a, b = _um(con, aid), _um(con, outro)
    if a["id"] == b["id"] or a["tipo"] != "amigo" or b["tipo"] != "amigo":
        raise HTTPException(400, "Escolha dois cadastros diferentes de Amigo da CAMP. Nada foi mudado.")
    if not normaliza_email(a["email"]) or normaliza_email(a["email"]) != normaliza_email(b["email"]):
        raise HTTPException(400, "Só dá para juntar cadastros com o mesmo e-mail. Nada foi mudado.")
    if not a["site_id"] or not b["site_id"]:
        raise HTTPException(400, "Só dá para juntar cadastros que existem no site (o Amigo registrado só no painel ainda não foi ao site). Nada foi mudado.")
    rec, _ = _quem_fica(a, b)
    if fica in (a["id"], b["id"]):
        f, s = (a, b) if fica == a["id"] else (b, a)
    else:
        f, s = _quem_fica(a, b)
    return f, s, rec["id"]


def _resumo_juntar(con, r) -> dict:
    n = lambda q: con.execute(q, (r["id"],) if "amigo_id" in q else (str(r["id"]),)).fetchone()[0]
    return {"id": r["id"], "nome": r["nome"], "email": r["email"], "protocolo": r["protocolo"], "situacao": r["situacao"], "inativo": bool(r["inativo_em"]),
            "categoria_nome": nome_categoria(con, r["categoria"]), "modalidade": r["modalidade"], "validade": r["validade"], "pago_em": r["pago_em"],
            "criado_no_site": r["criado_no_site"], "pagamentos": n("SELECT COUNT(*) FROM amigo_pagamento WHERE amigo_id=?"),
            "emails": n("SELECT COUNT(*) FROM amigo_email WHERE amigo_id=?"), "historico": n("SELECT COUNT(*) FROM evento WHERE entidade='amigo' AND codigo=?"),
            "notas": bool((r["notas"] or "").strip()), "fundador": r["fundador"]}


def previa_juntar(con, aid: int, outro: int, fica: int | None = None, wp=None) -> dict:
    """Prévia (nada muda): qual fica (padrão: o ativo, ou o do pagamento/adesão mais recente), qual sai (é apagado), o que passa para o que fica
    e se o site vai cancelar uma assinatura mensal do que sai (o site simula)."""
    f, s, rec = _par_juntar(con, aid, outro, fica)
    rs = _resumo_juntar(con, s)
    out = {"fica": _resumo_juntar(con, f), "sai": rs, "recomendado": rec,
           "move": {"pagamentos": rs["pagamentos"], "emails": rs["emails"], "historico": rs["historico"], "notas": rs["notas"], "fundador": rs["fundador"] if not f["fundador"] else None},
           "assinatura": False, "confirmado_no_site": False, "erro_site": "", "site": {}}
    d, motivo = _chamar_site(con, wp, f, "juntar", {"outro_id": int(s["site_id"]), "simular": True})
    if d:
        out["assinatura"], out["confirmado_no_site"], out["site"] = bool((d.get("assinatura") or {}).get("havia")), True, d.get("move") or {}
    else:
        out["assinatura"], out["erro_site"] = _assinatura_ativa_provavel(s), motivo
    return out


def juntar(con, aid: int, outro: int, fica: int | None, confirmacao: str, ator: str, wp=None) -> dict:
    """Junta dois cadastros do mesmo e-mail. 1) confirmação JUNTAR; 2) o SITE junta primeiro (fonte dos Amigos: cancela a assinatura mensal do que sai,
    passa pagamentos e histórico e apaga o que sai; falhou = NADA muda aqui); 3) aqui: pagamentos, e-mails e histórico passam para o que fica,
    as notas vão juntas e o que sai é apagado (dados pessoais), sem tirar a pessoa da lista de e-mails (ela continua no que fica)."""
    if re.sub(r"\s+", "", str(confirmacao or "")).casefold() != "juntar":
        raise HTTPException(400, "Para juntar, digite JUNTAR. Nada foi mudado.")
    f, s, _ = _par_juntar(con, aid, outro, fica)
    d, erro = _chamar_site(con, wp, f, "juntar", {"outro_id": int(s["site_id"]), "simular": False, "confirmar": "JUNTAR"})
    if not d:
        raise HTTPException(502, _sem_mudar("Nada foi juntado", erro))
    fid, sid = f["id"], s["id"]
    n_pg = con.execute("UPDATE amigo_pagamento SET amigo_id=? WHERE amigo_id=?", (fid, sid)).rowcount
    n_em = con.execute("UPDATE amigo_email SET amigo_id=? WHERE amigo_id=?", (fid, sid)).rowcount
    n_ev = con.execute("UPDATE evento SET codigo=? WHERE entidade='amigo' AND codigo=?", (str(fid), str(sid))).rowcount
    if (s["notas"] or "").strip():
        notas = ((f["notas"] or "").strip() + "\n" if (f["notas"] or "").strip() else "") + f"— do cadastro {s['protocolo'] or '#' + str(sid)}: {s['notas'].strip()}"
        con.execute("UPDATE amigo SET notas=? WHERE id=?", (notas[:4000], fid))
    if not f["fundador"] and s["fundador"]:
        con.execute("UPDATE amigo SET fundador=? WHERE id=?", (s["fundador"], fid))
    if isinstance(d.get("fica"), dict):                  # a situação e a validade do que fica, como o site deixou
        _gravar(con, d["fica"], {"lidos": 0, "novos": 0, "atualizados": 0})
    _anonimizar_amigo(con, sid)
    _recalcular_pagamento(con, fid)
    cancelada = bool((d.get("assinatura") or {}).get("cancelada"))
    _evento(con, fid, "juntado", ator, {"de": sid, "protocolo_saiu": s["protocolo"], "pagamentos": n_pg, "emails": n_em, "historico": n_ev, "assinatura_cancelada": cancelada})
    _evento(con, sid, "juntado_a", ator, {"ficou": fid, "protocolo_ficou": f["protocolo"]})
    con.commit()
    registrar(logging.INFO, "amigos_juntar", "Cadastros de Amigo juntados", ficou=fid, saiu=sid, pagamentos=n_pg)
    return {"ok": True, "ficou": fid, "saiu": sid, "pagamentos": n_pg, "emails": n_em, "historico": n_ev, "assinatura_cancelada": cancelada}


# ---------------------------------------------------------------- telas
def _linha(con, r, rep: dict | None = None) -> dict:
    d = dict(r)
    d.pop("pendente_site", None)
    d["pendente_site"] = bool(r["pendente_site"])
    d["categoria_nome"] = nome_categoria(con, r["categoria"])
    d["valor_previsto"] = valor_previsto(con, r) if r["tipo"] == "amigo" else None
    d["ano"] = int((r["pago_em"] or r["criado_no_site"] or r["importado_em"] or "0")[:4] or 0)
    v = _data(r["validade"])
    d["vence_em_dias"] = (v - hoje()).days if v else None
    d["origem_txt"] = "manual" if r["origem_pagamento"] == "manual" else ("site" if r["origem"] == "site" else "painel")
    if rep is not None:                                   # CAMP-AMIGO-DUP: etiqueta "e-mail repetido"
        d["email_repetido"], d["repetidos"] = r["id"] in rep, rep.get(r["id"], [])
    return d


def _com_emkt(con, linhas: list[dict], emkt: str | None) -> list[dict]:
    """18/11/2026 (CAMP-SENDER): "aceita e-mails" (sim | cancelou | nao) pela lista de e-mails da CAMP; filtro sim/nao."""
    from . import contatos_emkt
    m = contatos_emkt.mapa_aceite(con)
    for d in linhas:
        d["aceita_emails"] = m.get((d.get("email") or "").strip().lower(), "nao") if d.get("email") else "nao"
    if emkt in ("sim", "nao", "cancelou"):
        linhas = [d for d in linhas if d["aceita_emails"] == emkt]
    return linhas


def _filtro(aba: str, situacao, categoria, ano, vencendo, q) -> tuple[str, list]:
    onde, vals = (["tipo='amigo'"] if aba == "amigos" else ["tipo IN ('projeto','arquiteto')"]), []
    onde.append("apagado_em IS NULL")                    # apagado (CAMP-AMIGO-APAGAR) some do painel; os pagamentos ficam na receita
    if aba == "amigos" and situacao != REPETIDOS:        # inativo só aparece no filtro "Inativos" (e em "Repetidos": o mesmo e-mail num cadastro inativo)
        onde.append("inativo_em IS NOT NULL" if situacao == INATIVOS else "inativo_em IS NULL")
    if situacao and situacao not in ("todos", "todas", INATIVOS, REPETIDOS):
        if aba == "amigos":
            if situacao not in SITUACOES:
                raise HTTPException(400, "Situação inválida")
            onde.append("situacao=?")
        else:
            if situacao not in STATUS_PEDIDO:
                raise HTTPException(400, "Situação inválida")
            onde.append("status_pedido=?")
        vals.append(situacao)
    if categoria and categoria != "todas":
        onde.append("categoria=?"); vals.append(categoria)
    if ano:
        onde.append("substr(COALESCE(pago_em, criado_no_site, importado_em),1,4)=?"); vals.append(str(int(ano)))
    if vencendo:
        onde.append("situacao='pago' AND validade BETWEEN ? AND ?"); vals += [hoje().isoformat(), (hoje() + timedelta(days=30)).isoformat()]
    prot = protocolo.ler(q) if q else None
    if prot and prot["tipo"] == "site":
        onde.append("site_id=?"); vals.append(prot["id"])
    elif q and q.strip():
        like = f"%{q.strip()}%"
        onde.append("(nome LIKE ? OR email LIKE ? OR empresa LIKE ? OR codigo LIKE ? OR protocolo LIKE ?)"); vals += [like] * 5
    return " AND ".join(onde), vals


def numeros(con) -> dict:
    h = hoje()
    ano = str(h.year)
    receita = con.execute(f"""SELECT COALESCE(SUM(p.valor),0) FROM amigo_pagamento p JOIN amigo a ON a.id=p.amigo_id
                             WHERE substr(p.data,1,4)=? AND p.status IN ({','.join('?' * len(APROVADO))})""", (ano, *APROVADO)).fetchone()[0]
    ativos = con.execute("SELECT COUNT(*) FROM amigo WHERE tipo='amigo' AND inativo_em IS NULL AND apagado_em IS NULL AND (situacao='pago' OR (situacao='isento' AND (validade IS NULL OR validade>=?)))", (h.isoformat(),)).fetchone()[0]
    pend = con.execute("SELECT * FROM amigo WHERE tipo='amigo' AND inativo_em IS NULL AND apagado_em IS NULL AND situacao='pendente'").fetchall()
    venc = con.execute("SELECT COUNT(*) FROM amigo WHERE tipo='amigo' AND inativo_em IS NULL AND apagado_em IS NULL AND situacao='pago' AND validade BETWEEN ? AND ?",
                       (h.isoformat(), (h + timedelta(days=30)).isoformat())).fetchone()[0]
    return {"ativos": ativos, "receita_ano": float(receita), "ano": h.year, "pendentes": len(pend),
            "pendente_valor": float(sum(valor_previsto(con, r) or 0 for r in pend)), "vencendo_30": venc}


@router.get("")
def listar(aba: str = "amigos", situacao: str | None = None, categoria: str | None = None, ano: int | None = None, vencendo: int = 0,
           q: str | None = None, emkt: str | None = None, u: dict = Depends(auth.exige("admin"))) -> dict:
    if aba not in ("amigos", "adocoes"):
        raise HTTPException(400, "Aba inválida")
    con = connect()
    try:
        vencer(con, "painel (automático)")
        w, vals = _filtro(aba, None, categoria, ano, vencendo, q)
        campo = "situacao" if aba == "amigos" else "status_pedido"
        resumo = {s: 0 for s in (SITUACOES if aba == "amigos" else STATUS_PEDIDO)}
        for r in con.execute(f"SELECT {campo} s, COUNT(*) n FROM amigo WHERE {w} GROUP BY {campo}", vals):
            if r["s"] in resumo:
                resumo[r["s"]] = r["n"]
        rep = repetidos(con) if aba == "amigos" else {}
        if aba == "amigos":
            w_i, vals_i = _filtro(aba, INATIVOS, categoria, ano, vencendo, q)
            resumo[INATIVOS] = con.execute(f"SELECT COUNT(*) FROM amigo WHERE {w_i}", vals_i).fetchone()[0]
            resumo[REPETIDOS] = len(rep)
        w2, vals2 = _filtro(aba, situacao, categoria, ano, vencendo, q)
        if aba == "amigos" and situacao == REPETIDOS:
            w2 += f" AND id IN ({','.join('?' * len(rep))})" if rep else " AND 0"
            vals2 = [*vals2, *rep]
        rows = con.execute(f"SELECT * FROM amigo WHERE {w2} ORDER BY {'lower(email), ' if situacao == REPETIDOS else ''}COALESCE(criado_no_site, importado_em) DESC, id DESC", vals2).fetchall()
        anos = [r[0] for r in con.execute("SELECT DISTINCT substr(COALESCE(pago_em, criado_no_site, importado_em),1,4) a FROM amigo WHERE a<>'' ORDER BY a DESC")]
        ult = con.execute("SELECT quando, lidos, novos, erro FROM amigo_coleta ORDER BY id DESC LIMIT 1").fetchone()
        tot = {k: con.execute(q_, ()).fetchone()[0] for k, q_ in (("amigos", "SELECT COUNT(*) FROM amigo WHERE tipo='amigo' AND apagado_em IS NULL AND inativo_em IS NULL"),
                                                                ("adocoes", "SELECT COUNT(*) FROM amigo WHERE tipo<>'amigo' AND apagado_em IS NULL"),
                                                                ("adocoes_novas", "SELECT COUNT(*) FROM amigo WHERE tipo<>'amigo' AND status_pedido='novo'"))}
        cats = _tabela_do_ano(con, hoje().year)
        return {"itens": _com_emkt(con, [_linha(con, r, rep) for r in rows], emkt), "resumo": resumo, "numeros": numeros(con), "anos": anos, "totais": tot,
                "categorias": [{"categoria": k, "nome": v["nome"]} for k, v in cats.items()],
                "ultima_busca": dict(ult) if ult else None, "minutos": coleta_min(con), "lembretes": modo_lembretes(con)}
    finally:
        con.close()


@router.get("/exportar.csv")
def exportar(aba: str = "amigos", situacao: str | None = None, categoria: str | None = None, ano: int | None = None, vencendo: int = 0,
             q: str | None = None, ids: str | None = None, emkt: str | None = None, u: dict = Depends(auth.exige("admin"))):
    """Exporta TUDO do filtro (ou só os selecionados, `ids=1,2,3`). Sem log de dados pessoais."""
    con = connect()
    try:
        if ids:
            lst = [int(x) for x in re.findall(r"\d+", ids)][:5000]
            rows = [r for r in _linhas(con, lst) if not r["apagado_em"]]
        else:
            w, vals = _filtro(aba, situacao, categoria, ano, vencendo, q)
            rows = con.execute(f"SELECT * FROM amigo WHERE {w} ORDER BY nome", vals).fetchall()
        buf = io.StringIO()
        wr = csv.writer(buf, delimiter=";")
        wr.writerow(["protocolo", "tipo", "nome", "empresa", "email", "telefone", "categoria", "modalidade", "situacao", "valor", "pago_em", "valor_pago", "validade", "codigo", "origem", "aceita_emails"])
        for d in _com_emkt(con, [_linha(con, r) for r in rows], None if ids else emkt):
            r = d
            wr.writerow([r["protocolo"] or "", r["tipo"], r["nome"], r["empresa"] or "", r["email"] or "", r["telefone"] or "", d["categoria_nome"], r["modalidade"] or "",
                         r["situacao"] or r["status_pedido"], f"{d['valor_previsto']:.2f}".replace(".", ",") if d["valor_previsto"] else "",
                         r["pago_em"] or "", f"{r['ultimo_valor']:.2f}".replace(".", ",") if r["ultimo_valor"] else "", r["validade"] or "", r["codigo"] or "", d["origem_txt"], d["aceita_emails"]])
    finally:
        con.close()
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="amigos-da-camp-{hoje().isoformat()}.csv"', "Cache-Control": "no-store",
                             "X-Content-Type-Options": "nosniff"})


class Regras(BaseModel):
    cobranca_pix: str | None = None
    cobranca_prazo_dias: int | None = None
    validade_regra: str | None = None
    lembretes_auto: str | None = None
    lembrete_dias: str | None = None
    responder_para: str | None = None


@router.get("/valores")
def ver_valores(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        p = precos(con)
        try:
            fund = json.loads(_estado(con, "fundadores_site") or "null")
        except ValueError:
            fund = None
        return {"anos": {str(a): list(v.values()) for a, v in sorted(p.items())}, "ano_atual": hoje().year, "site": categorias_do_site(con),
                "fundadores": fund, "regras": {"validade_regra": _cfg(con, "amigos.validade_regra", "12_meses"), "lembretes_auto": modo_lembretes(con),
                                               "lembrete_dias": ",".join(str(d) for d in lembrete_dias(con)), "responder_para": _cfg(con, "amigos.responder_para"),
                                               "coleta_min": coleta_min(con), "cobranca_pix": _cfg(con, "amigos.cobranca_pix"),
                                               "cobranca_prazo_dias": prazo_cobranca(con)},
                "canal": canal(con), "rotulo_canal": ROTULO_CANAL.get(canal(con), "")}
    finally:
        con.close()


class PrecoCategoria(BaseModel):
    categoria: str
    nome: str
    anual: float
    mensal: float


@router.put("/valores/{ano}")
def gravar_valores(ano: int, d: list[PrecoCategoria], u: dict = Depends(auth.exige("admin"))) -> dict:
    if not 2020 <= ano <= 2100:
        raise HTTPException(400, "Ano inválido")
    if not d or len(d) > 20:
        raise HTTPException(400, "Informe as categorias")
    con = connect()
    try:
        for c in d:
            cat = re.sub(r"[^a-z0-9_-]", "", c.categoria.lower())[:40]
            if not cat or not c.nome.strip() or c.anual < 0 or c.mensal < 0:
                raise HTTPException(400, "Categoria, nome e valores são obrigatórios")
            con.execute("INSERT INTO amigo_preco (ano, categoria, nome, anual, mensal) VALUES (?,?,?,?,?) ON CONFLICT(ano, categoria) DO UPDATE SET nome=excluded.nome, anual=excluded.anual, mensal=excluded.mensal",
                        (ano, cat, c.nome.strip()[:80], c.anual, c.mensal))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('amigos_valores',?,'editado',?,?)",
                    (str(ano), u["email"], json.dumps([c.model_dump() for c in d], ensure_ascii=False)))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


@router.post("/valores/{ano}/copiar")
def copiar_valores(ano: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Abre um ano novo com os valores do ano anterior (ou os do site)."""
    if not 2020 <= ano <= 2100:
        raise HTTPException(400, "Ano inválido")
    con = connect()
    try:
        if con.execute("SELECT 1 FROM amigo_preco WHERE ano=?", (ano,)).fetchone():
            raise HTTPException(409, f"{ano} já tem valores")
        for c in _tabela_do_ano(con, ano - 1).values():
            con.execute("INSERT OR IGNORE INTO amigo_preco (ano, categoria, nome, anual, mensal) VALUES (?,?,?,?,?)", (ano, c["categoria"], c["nome"], c["anual"], c["mensal"]))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('amigos_valores',?,'criado',?,'{}')", (str(ano), u["email"]))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


@router.put("/regras")
def gravar_regras(d: Regras, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        mud = {}
        if d.validade_regra is not None:
            if d.validade_regra not in ("12_meses", "fim_do_ano"):
                raise HTTPException(400, "Regra de validade inválida")
            mud["amigos.validade_regra"] = d.validade_regra
        if d.lembretes_auto is not None:
            if d.lembretes_auto not in ("desligado", "simular", "ligado"):
                raise HTTPException(400, "Modo dos lembretes inválido")
            mud["amigos.lembretes_auto"] = d.lembretes_auto
        if d.lembrete_dias is not None:
            dias = [int(x) for x in re.findall(r"\d+", d.lembrete_dias) if 0 < int(x) <= 120]
            if not dias:
                raise HTTPException(400, "Informe os dias (ex.: 30,7)")
            mud["amigos.lembrete_dias"] = ",".join(str(x) for x in sorted(set(dias), reverse=True))
        if d.responder_para is not None:
            r = d.responder_para.strip()
            if r and not email_envio.ENDERECO.match(r):
                raise HTTPException(400, "Endereço de resposta inválido")
            mud["amigos.responder_para"] = r
        if d.cobranca_pix is not None:
            mud["amigos.cobranca_pix"] = d.cobranca_pix.strip()[:2000]
        if d.cobranca_prazo_dias is not None:
            if not 1 <= d.cobranca_prazo_dias <= 90:
                raise HTTPException(400, "Prazo da cobrança entre 1 e 90 dias")
            mud["amigos.cobranca_prazo_dias"] = str(d.cobranca_prazo_dias)
        for k, v in mud.items():
            con.execute("UPDATE configuracao SET valor=?, atualizado_em=datetime('now'), atualizado_por=? WHERE chave=?", (v, u["email"], k))
        if mud:
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('configuracao','amigos','editado',?,?)", (u["email"], json.dumps(mud, ensure_ascii=False)))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


@router.get("/lembretes")
def ver_lembretes(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Quem receberia os lembretes automáticos hoje (vale em qualquer modo: é a simulação)."""
    con = connect()
    try:
        vencer(con)
        try:
            ult = json.loads(_estado(con, "lembretes_simulacao") or "null")
        except ValueError:
            ult = None
        return {"modo": modo_lembretes(con), "dias": lembrete_dias(con), "seriam": lembretes_devidos(con), "ultima_simulacao": ult, "canal": canal(con)}
    finally:
        con.close()


@router.post("/sincronizar")
def sincronizar(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        env = enviar_pendentes(con)
        col = coletar(con)
        venc = vencer(con)
        if venc:
            enviar_pendentes(con)
        return {**col, "enviados": env["enviados"], "falhas_envio": env["falhas"], "vencidos": venc}
    finally:
        con.close()


class EmailPedido(BaseModel):
    ids: list[int]
    modelo: str
    assunto: str | None = None
    texto: str | None = None


@router.post("/email/previa")
def email_previa(d: EmailPedido, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return previa(con, d.ids, d.modelo, d.assunto or "", d.texto or "")
    finally:
        con.close()


@router.post("/email/enviar")
def email_enviar(d: EmailPedido, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        if not canal(con):
            raise HTTPException(409, "Os e-mails dos Amigos saem pelo Sender do site: preencha a senha do site (Application Password) em Configurações.")
        n = enfileirar(con, d.ids, d.modelo, d.assunto or "", d.texto or "", u["email"])
    finally:
        con.close()
    if n:
        _fila_em_segundo_plano()
    return {"ok": True, "na_fila": n}


class CobrancaPedido(BaseModel):
    ids: list[int]
    forcar: bool = False


@router.post("/cobranca/previa")
def cobranca_previa(d: CobrancaPedido, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return previa_cobranca(con, d.ids)
    finally:
        con.close()


@router.post("/cobranca/enviar")
def cobranca_enviar(d: CobrancaPedido, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        res = cobrar(con, d.ids, u["email"], forcar=d.forcar)
    finally:
        con.close()
    if res["na_fila"]:
        _fila_em_segundo_plano()
        for i in d.ids[:50]:
            _disparar_envio(int(i))
    return res


class NovoAmigo(BaseModel):
    nome: str
    email: str | None = None
    telefone: str | None = None
    categoria: str
    modalidade: str = "anual"
    notas: str | None = None


@router.post("")
def criar(d: NovoAmigo, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Amigo que entrou fora do site (ex.: pagou por Pix na CAMP). Fica só no painel (o site não tem rota para criar)."""
    nome = _txt(d.nome, 160)
    if len(nome) < 2:
        raise HTTPException(400, "Informe o nome")
    em = _txt(d.email, 200)
    if em and not email_envio.ENDERECO.match(em):
        raise HTTPException(400, "E-mail inválido")
    con = connect()
    try:
        if d.categoria not in _tabela_do_ano(con, hoje().year):
            raise HTTPException(400, "Categoria inválida")
        cur = con.execute("""INSERT INTO amigo (tipo, origem, categoria, modalidade, nome, email, telefone, notas, situacao, criado_no_site)
                             VALUES ('amigo','painel',?,?,?,?,?,?, 'pendente', datetime('now'))""",
                          (d.categoria, "mensal" if d.modalidade == "mensal" else "anual", nome, em or None, _txt(d.telefone, 40) or None, _txt(d.notas, 4000) or None))
        _evento(con, cur.lastrowid, "criado", u["email"], {"origem": "painel", "categoria": d.categoria})
        con.commit()
        return {"ok": True, "id": cur.lastrowid}
    finally:
        con.close()


class IdsPedido(BaseModel):
    ids: list[int]
    motivo: str | None = None


@router.post("/desativar/previa")
def desativar_previa(d: IdsPedido, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return previa_desativar(con, d.ids)
    finally:
        con.close()


@router.post("/desativar")
def desativar_rota(d: IdsPedido, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return desativar(con, d.ids, d.motivo or "", u["email"])
    finally:
        con.close()


@router.post("/reativar")
def reativar_rota(d: IdsPedido, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return reativar(con, d.ids, u["email"])
    finally:
        con.close()


@router.get("/{aid}/apagar/previa")
def apagar_previa(aid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return previa_apagar(con, aid)
    finally:
        con.close()


class Apagar(BaseModel):
    confirmacao: str = ""


@router.post("/{aid}/apagar")
def apagar_rota(aid: int, d: Apagar, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return apagar(con, aid, d.confirmacao, u["email"])
    finally:
        con.close()


@router.get("/{aid}/juntar/previa")
def juntar_previa(aid: int, outro: int, fica: int | None = None, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return previa_juntar(con, aid, outro, fica)
    finally:
        con.close()


class Juntar(BaseModel):
    outro_id: int
    fica_id: int | None = None
    confirmacao: str = ""


@router.post("/{aid}/juntar")
def juntar_rota(aid: int, d: Juntar, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return juntar(con, aid, d.outro_id, d.fica_id, d.confirmacao, u["email"])
    finally:
        con.close()


@router.get("/{aid}")
def detalhe(aid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = _um(con, aid)
        rep = repetidos(con)
        d = _linha(con, r, rep)
        d["repetidos"] = [{"id": o["id"], "nome": o["nome"], "protocolo": o["protocolo"], "situacao": o["situacao"], "inativo": bool(o["inativo_em"]), "pago_em": o["pago_em"],
                           "criado_no_site": o["criado_no_site"]} for o in _linhas(con, rep.get(aid, []))]
        d["erro_site"] = r["erro_site"]
        d["pagamentos"] = [dict(p) for p in con.execute("SELECT id, chave, data, valor, meio, nota, origem, status, criado_por FROM amigo_pagamento WHERE amigo_id=? ORDER BY data DESC, id DESC", (aid,))]
        d["emails"] = [dict(e) for e in con.execute("SELECT id, modelo, assunto, situacao, canal, erro, criado_por, criado_em, enviado_em, modelo_site, sender_id FROM amigo_email WHERE amigo_id=? ORDER BY id DESC LIMIT 50", (aid,))]
        for e in d["emails"]:
            e["template"] = TEMPLATES_SITE.get(e.pop("modelo_site") or "", ("",))[0]
        d["historico"] = [dict(e) for e in con.execute("SELECT tipo, ator, detalhe, quando FROM evento WHERE entidade='amigo' AND codigo=? ORDER BY id DESC LIMIT 100", (str(aid),))]
        return d
    finally:
        con.close()


class Mudanca(BaseModel):
    categoria: str | None = None
    modalidade: str | None = None
    situacao: str | None = None
    status_pedido: str | None = None
    validade: str | None = None
    notas: str | None = None


@router.patch("/{aid}")
def editar(aid: int, d: Mudanca, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        res = mudar(con, aid, d.model_dump(), u["email"])
    finally:
        con.close()
    if res.get("mudou"):
        _disparar_envio(aid)
    return res


class Pagamento(BaseModel):
    data: str
    valor: float
    meio: str
    nota: str | None = None


@router.post("/{aid}/pagamento")
def pagamento(aid: int, d: Pagamento, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        res = registrar_pagamento(con, aid, d.data, d.valor, d.meio, d.nota or "", u["email"])
    finally:
        con.close()
    _disparar_envio(aid)
    return res
