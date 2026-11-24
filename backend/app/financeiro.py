"""Financeiro: relatório de receitas para o contador (CAMP-FIN, 24/11/2026). Rafael: "Estamos recebendo bastante doação pelo Mercado
Pago", "relatório de receitas para o contador" e "Temos como interligar com o Mercado Pago?".

A norma contábil das entidades sem fins lucrativos (ITG 2002 (R1)) pede que doações e patrocínios apareçam separados das outras receitas,
com notas explicativas. O painel ajuda: junta num livro só cada pagamento confirmado e sugere a natureza. **A classificação final é do
contador.**

- Fontes (todas cópias que o painel já guarda; nada novo é pedido às pessoas):
  · Amigos da CAMP (`amigo_pagamento`: Mercado Pago `mp-<id>` e os registrados à mão `painel-…`; tipo amigo = anuidade/mensalidade,
    tipo projeto/arquiteto = adoção);
  · cobranças avulsas (`cobranca_avulsa`, CAMP-COB-n), separadas pela finalidade: doação, doação de acervo, patrocínio (à vista),
    serviço, outro;
  · patrocínio de empresas em 12 meses (`patrocinio.dados.pagamentos`, CAMP-PAT-n);
  · ingressos da visita guiada (`ingresso.pagamentos`, CAMP-INGRESSO-…);
  · a CONTA do Mercado Pago inteira (`mp_pagamento`, contrato 1.33): o site lê `/v1/payments/search` com a chave que só ele tem e o painel
    guarda uma cópia, única pelo id do pagamento. Dela vêm a tarifa e o líquido exatos e os estornos com data. Pagamento sem referência
    nossa (link, QR code ou Pix direto na conta) vira "Recebido direto no Mercado Pago", Doações por padrão, com "Classificar como…".
- Um pagamento conta UMA vez (único pelo id do Mercado Pago, na ordem cobrança → patrocínio → ingresso → Amigos → conta do Mercado Pago).
- Estorno e contestação (chargeback) = linha negativa na data do estorno (sem a data: a do pagamento, com "data do estorno a conferir").
- Sem a tarifa (pagamento que a busca do Mercado Pago ainda não trouxe): "a conferir no extrato". Registrado à mão (Pix na conta do
  banco, dinheiro): fora do Mercado Pago, sem tarifa.
- Entrada ou saída (CAMP-FIN, Rafael: "isso é despesa… presta atenção"): a busca do Mercado Pago traz também os pagamentos FEITOS pela CAMP
  (compra com o saldo, ex.: "Anthropic* claude sub"). O site 1.44.0 (contrato 1.35) manda `direcao` ("entrada": a CAMP recebeu; "saida": a
  CAMP pagou), `contraparte` e `valor_debitado`. Saída NUNCA é receita: vira despesa da conta do Mercado Pago (fila Precisa justificar), sem
  duplicar com o relatório de liberações nem com o Extrato importado (mesmo id do pagamento ou referência). Site antigo, sem `direcao`:
  líquido maior que o bruto, pago com o saldo e sem referência da CAMP = saída provável ("confira: parece pagamento feito pela CAMP").
  Contrato 1.36 (site 1.45.0; Rafael: "vc ta colocando despesa como receita"): o Pix pago a uma empresa ("DSC - MATERIAIS PARA CONSTRUCAO
  LTDA", líquido = bruto) e o "Pix enviado" vinham SEM direção e entravam como receita. O site agora diz "saida" sempre que o recebedor é
  outra conta; sem direção, também é saída provável o líquido > bruto em qualquer meio e a descrição de saída (Pix enviado, Pagamento com
  Pix, boleto, compra, saque, nome de empresa, descritor de cartão "Loja* …"); referência CAMP-… é sempre recebido. As linhas já guardadas
  como receita viram despesa a justificar na leitura (o mesmo refazer, idempotente).
  Linhas já sincronizadas são refeitas na leitura (idempotente): a nota fica, a classificação manual cai (com registro no histórico).
  "Isto é uma saída (despesa)" (receita) e "Isto é uma entrada" (despesa) ficam lembrados (`financeiro_direcao`) e vencem o site.
- Mapa origem → natureza em `financeiro.naturezas` (JSON; o admin muda na tela). Nenhum CPF/CNPJ no relatório, salvo `documento=1`
  (só admin, desligado por padrão).
- Só admin e master. A busca na conta do Mercado Pago roda em segundo plano (`financeiro.mp_coleta_min`, 60; 0 desliga) e no botão
  "Sincronizar com o Mercado Pago agora" (também em segundo plano: nunca dentro da requisição).
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import threading
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import auth
from .config import settings
from .db import connect
from .log_tecnico import registrar

router = APIRouter(prefix="/api/financeiro", tags=["financeiro"])

FUSO = ZoneInfo("America/Sao_Paulo")
ROTA_MP = "/wp-json/camp/v1/painel/mp/pagamentos"
VERSAO_SITE = "1.46.0"   # contrato 1.37: + o que a CAMP pagou (busca payer.id); 1.35: direção (entrada/saída) de cada pagamento
NATUREZAS = {      # ordem do relatório (ITG 2002: doações e patrocínios separados das outras receitas)
    "doacoes": "Doações (sem restrição)",
    "doacoes_restricao": "Doações com restrição (vinculadas)",
    "contribuicoes": "Contribuições de associados (Amigos da CAMP)",
    "patrocinios": "Patrocínios",
    "servicos": "Receitas de serviços e venda de ingressos",
    "outras": "Outras receitas",
    "servicos_projeto": "Serviços prestados ao projeto incentivado",   # CAMP-ROUANET: notas da CAMP pagas pelo projeto (transferência interna no Consolidado)
}
ABA_XLSX = {"doacoes": "Doações", "doacoes_restricao": "Doações com restrição", "contribuicoes": "Contribuições (Amigos)",
            "patrocinios": "Patrocínios", "servicos": "Serviços e ingressos", "outras": "Outras receitas"}
ORIGENS = {
    "doacao": "Doação (cobrança avulsa)",
    "direto_mp": "Recebido direto no Mercado Pago",
    "doacao_acervo": "Doação de acervo (contribuição)",
    "adocao": "Adoção (Adote um projeto ou um arquiteto)",
    "amigos_anual": "Amigos da CAMP (anuidade)",
    "amigos_mensal": "Amigos da CAMP (mensalidade)",
    "patrocinio": "Patrocínio",
    "ingresso": "Ingresso (visita guiada)",
    "servico": "Cobrança avulsa (serviço)",
    "cobranca": "Cobrança avulsa (outra finalidade)",
    "nota_projeto": "Nota da CAMP para o projeto incentivado",
}
MAPA_PADRAO = {"doacao": "doacoes", "direto_mp": "doacoes", "doacao_acervo": "doacoes_restricao", "adocao": "doacoes_restricao",
               "amigos_anual": "contribuicoes", "amigos_mensal": "contribuicoes", "patrocinio": "patrocinios", "ingresso": "servicos",
               "servico": "servicos", "cobranca": "outras", "nota_projeto": "servicos_projeto"}
EXPLICA_NATUREZA = {
    "doacoes": "Dinheiro dado sem destino definido: doações pela cobrança avulsa e o que chega direto na conta do Mercado Pago sem referência nossa.",
    "doacoes_restricao": "Dinheiro dado para um fim definido: a contribuição da doação de acervo (preservação do acervo) e as adoções de projeto ou arquiteto.",
    "contribuicoes": "Anuidades e mensalidades do Amigos da CAMP. O contador decide se entram como contribuições de associados ou como doações.",
    "patrocinios": "Cotas de patrocínio de empresas (à vista ou em 12 meses), com contrapartidas.",
    "servicos": "Ingressos da visita guiada e cobranças de serviço.",
    "outras": "Cobranças avulsas de outra finalidade.",
    "servicos_projeto": "Notas que a CAMP emite ao projeto incentivado (Rouanet), pagas pela conta do projeto. No Consolidado são transferência interna.",
}
CONTA = ("approved", "accredited", "authorized", "refunded", "charged_back", "in_mediation")
ESTORNO = ("refunded", "charged_back")
MEIO = {"credit_card": "cartão de crédito", "debit_card": "cartão de débito", "prepaid_card": "cartão pré-pago", "bank_transfer": "Pix",
        "pix": "Pix", "ticket": "boleto", "account_money": "saldo do Mercado Pago", "transferencia": "transferência", "dinheiro": "dinheiro",
        "cartao": "cartão", "outro": "outro meio", "atm": "boleto"}
PREFIXOS = (("CAMP-AMIGO-", "amigos_anual"), ("CAMP-COB-", "cobranca"), ("CAMP-INGRESSO-", "ingresso"), ("CAMP-PAT-", "patrocinio"))
COLUNAS = ["Data", "Conta", "Natureza", "Origem", "Descrição", "Pagador", "Bruto (R$)", "Tarifa Mercado Pago (R$)", "Líquido (R$)", "Meio",
           "external_reference", "Pagamento no Mercado Pago", "Situação", "Observação"]
_HOJE: date | None = None          # testes fixam o dia


def hoje() -> date:
    return _HOJE or datetime.now(FUSO).date()


# ---------------------------------------------------------------- utilidades
def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _estado(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM financeiro_estado WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _estado_set(con, chave: str, valor: str) -> None:
    con.execute("INSERT INTO financeiro_estado (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, valor))


def _num(v) -> float | None:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _txt(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:n]


def _json(s, padrao):
    try:
        v = json.loads(s) if s else padrao
    except (TypeError, ValueError):
        return padrao
    return v if isinstance(v, type(padrao)) else padrao


def _utc(v) -> str:
    """ISO com fuso (ou sem: já UTC) → 'AAAA-MM-DD HH:MM:SS' UTC; vazio se não der."""
    s = str(v or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s + " 12:00:00"
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if d.tzinfo:
        d = d.astimezone(timezone.utc).replace(tzinfo=None)
    return d.strftime("%Y-%m-%d %H:%M:%S")


def dia_sp(v) -> str:
    """Data do pagamento em São Paulo (AAAA-MM-DD). Só a data: fica como está; sem fuso: UTC."""
    s = str(v or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s[:10] if re.match(r"\d{4}-\d{2}-\d{2}", s) else ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(FUSO).date().isoformat()


def brl(v) -> str:
    s = f"{float(v or 0):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _dbr(d: str) -> str:
    return f"{d[8:10]}/{d[5:7]}/{d[:4]}" if d and len(d) >= 10 else (d or "")


def _wp():
    """Cliente do site (os testes trocam por um falso)."""
    return __import__("app.wp", fromlist=["WP"]).WP()


def _tem_site(con) -> bool:
    return bool(_cfg(con, "wp.app_password", settings.WP_APP_PASSWORD))


CONTA_MP = 1                         # a conta do Mercado Pago (migração 249); toda receita de hoje entra nela
AVISO_PROVAVEL = "confira: parece pagamento feito pela CAMP"
MOTIVO_ENTRADA = "Isto é uma entrada (receita), não despesa"
MEIO_DE_ROTULO = {v: k for k, v in reversed(list(MEIO.items()))}
TIPOS_CONTA = {"operacional": "Operacional", "projeto_incentivado": "Projeto incentivado"}


def contas(con) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT id, nome, banco, tipo, restrito, ativa, projeto FROM financeiro_conta ORDER BY id")]


def mapa(con) -> dict[str, str]:
    m = dict(MAPA_PADRAO)
    for k, v in _json(_cfg(con, "financeiro.naturezas", ""), {}).items():
        if k in ORIGENS and v in NATUREZAS:
            m[k] = v
    return m


def periodo(de: str = "", ate: str = "", mes: str = "", ano: str = "", tri: str = "") -> tuple[str, str]:
    """Mês (AAAA-MM), trimestre (AAAA-Tn), ano (AAAA) ou de/até (AAAA-MM-DD). Sem nada: o mês corrente (São Paulo)."""
    if tri:
        from .despesas import _periodo as _p
        return _p("", "", "", "", tri)
    try:
        if mes:
            a, m = (int(x) for x in mes.split("-"))
            ini = date(a, m, 1)
            fim = (date(a + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
            return ini.isoformat(), fim.isoformat()
        if ano:
            a = int(ano)
            return date(a, 1, 1).isoformat(), date(a, 12, 31).isoformat()
        if de or ate:
            d1 = date.fromisoformat(de) if de else date(2000, 1, 1)
            d2 = date.fromisoformat(ate) if ate else hoje()
            if d2 < d1:
                raise ValueError
            return d1.isoformat(), d2.isoformat()
    except (ValueError, TypeError):
        raise HTTPException(400, "Período inválido: use mês (AAAA-MM), ano (AAAA) ou de/até (AAAA-MM-DD)")
    h = hoje()
    return periodo(mes=f"{h.year}-{h.month:02d}")


# ---------------------------------------------------------------- pagamentos de cada fonte
def _pg(mp_id, data, valor, status, meio, origem, descricao, pagador, ref, *, tarifa=None, liquido=None, fonte="painel", registro=None,
        documento="", fora_mp=False, estornos=None) -> dict:
    return {"mp_id": str(mp_id or "").strip() or None, "data": data, "valor": _num(valor) or 0.0, "status": (status or "approved").lower(),
            "meio": meio or "", "origem": origem, "descricao": descricao, "pagador": pagador or "", "ref": ref or "", "tarifa": tarifa,
            "liquido": liquido, "fonte": fonte, "registro": registro, "documento": documento or "", "fora_mp": fora_mp, "estornos": estornos}


def _de_cobrancas(con, docs: bool) -> tuple[list[dict], list[dict]]:
    pat_cob = {}
    doa_cob = {}
    for r in con.execute("SELECT site_id, empresa, cnpj, dados FROM patrocinio"):
        c = (_json(r["dados"], {}).get("cobranca") or {})
        if isinstance(c, dict) and c.get("id"):
            pat_cob[int(c["id"])] = r
    for r in con.execute("SELECT site_id, protocolo, dados FROM doacao_acervo"):
        d = _json(r["dados"], {})
        c = d.get("cobranca") if isinstance(d.get("cobranca"), dict) else {}
        if c.get("id"):
            doa_cob[int(c["id"])] = (r, d)
    out, sem = [], []
    fin_origem = {"doacao": "doacao", "doacao_acervo": "doacao_acervo", "patrocinio": "patrocinio", "servico": "servico"}
    for r in con.execute("SELECT * FROM cobranca_avulsa WHERE situacao IN ('paga','estornada') OR mp_pagamento_id IS NOT NULL ORDER BY id"):
        origem = fin_origem.get(r["finalidade"], "cobranca")
        pagador, documento, desc = r["nome"] or "", "", r["mp_titulo"] or f"Cobrança avulsa · {r['descricao'][:80]}"
        pat = pat_cob.get(r["site_id"] or -1)
        if pat:
            pagador, documento = pat["empresa"] or pagador, (pat["cnpj"] or "") if docs else ""
        doa = doa_cob.get(r["site_id"] or -1)
        if doa:
            desc = f"{desc} · doação {doa[0]['protocolo'] or ''}".strip()
            documento = (doa[1].get("documento") or "") if docs else documento
        pgs = [p for p in _json(r["pagamentos"], []) if isinstance(p, dict) and str(p.get("status") or "").lower() in CONTA]
        if not pgs and r["mp_pagamento_id"]:
            pgs = [{"id": r["mp_pagamento_id"], "status": "refunded" if r["situacao"] == "estornada" else "approved", "valor": r["valor_pago"],
                    "liquido": r["valor_liquido"], "tarifa": r["tarifa"], "meio": r["meio"], "pago_em": r["pago_em"]}]
        if not pgs and r["situacao"] == "paga":
            sem.append({"origem": origem, "registro": f"cobrança {r['external_reference'] or r['id']}", "motivo": "marcada como paga sem o pagamento do Mercado Pago"})
        for p in pgs:
            out.append(_pg(p.get("id"), dia_sp(p.get("pago_em") or p.get("criado") or r["pago_em"]), p.get("valor") or r["valor_pago"] or r["valor"],
                           p.get("status"), p.get("meio") or r["meio"], origem, desc, pagador, r["external_reference"], tarifa=_num(p.get("tarifa")),
                           liquido=_num(p.get("liquido")), registro={"tela": "cobrancas", "id": r["id"]}, documento=documento))
    return out, sem


def _de_patrocinios(con, docs: bool) -> tuple[list[dict], list[dict]]:
    out, sem = [], []
    for r in con.execute("SELECT * FROM patrocinio ORDER BY site_id"):
        d = _json(r["dados"], {})
        pgs = [p for p in (d.get("pagamentos") or []) if isinstance(p, dict) and str(p.get("status") or "").lower() in CONTA]
        if not pgs and r["etapa"] == "pago" and (r["valor_pago"] or 0) > 0 and not d.get("cobranca"):
            sem.append({"origem": "patrocinio", "registro": f"patrocínio {r['protocolo'] or r['site_id']}", "motivo": "pago sem os pagamentos do Mercado Pago"})
        for p in pgs:
            out.append(_pg(p.get("id"), dia_sp(p.get("pago_em") or p.get("data")), p.get("valor"), p.get("status"), p.get("meio"), "patrocinio",
                           f"Patrocínio · cota {d.get('cota_nome') or r['cota'] or ''} · mensalidade", r["empresa"] or d.get("nome_marca") or "",
                           f"CAMP-PAT-{r['site_id']}", registro={"tela": "patrocinios", "id": r["site_id"]}, documento=(r["cnpj"] or "") if docs else ""))
    return out, sem


def _de_ingressos(con) -> tuple[list[dict], list[dict]]:
    out, sem = [], []
    for r in con.execute("SELECT * FROM ingresso WHERE pagamentos IS NOT NULL OR situacao='pago' ORDER BY site_id"):
        pgs = [p for p in _json(r["pagamentos"], []) if isinstance(p, dict)]
        if not pgs and r["situacao"] == "pago" and (r["total"] or 0) > 0:
            sem.append({"origem": "ingresso", "registro": f"ingresso {r['ref'] or r['site_id']}", "motivo": "pago sem o pagamento do Mercado Pago"})
        for p in pgs:
            st = str(p.get("status") or "approved").lower()
            if st not in CONTA:
                continue
            out.append(_pg(p.get("id"), dia_sp(p.get("data")), p.get("valor"), st, p.get("meio"), "ingresso",
                           f"Ingresso · {r['visita'] or 'visita guiada'} · {_dbr(r['data'] or '')} {r['hora'] or ''} · {r['pessoas']} pessoa(s)",
                           r["nome"] or "", r["ref"], tarifa=_num(p.get("tarifa")), liquido=_num(p.get("liquido")), registro={"tela": "ingressos", "id": r["site_id"]}))
    return out, sem


def _de_amigos(con) -> list[dict]:
    out = []
    for r in con.execute(f"""SELECT p.*, a.site_id, a.tipo, a.modalidade, a.nome, a.categoria FROM amigo_pagamento p JOIN amigo a ON a.id=p.amigo_id
                             WHERE lower(p.status) IN ({','.join('?' * len(CONTA))}) ORDER BY p.id""", CONTA):
        manual = not str(r["chave"]).startswith("mp-")
        origem = "adocao" if r["tipo"] in ("projeto", "arquiteto") else ("amigos_mensal" if r["modalidade"] == "mensal" else "amigos_anual")
        desc = ("Adoção · " + ("Adote um projeto" if r["tipo"] == "projeto" else "Adote um arquiteto")) if origem == "adocao" else \
            f"Amigos da CAMP · {r['categoria'] or ''} · {'mensalidade' if origem == 'amigos_mensal' else 'anuidade'}"
        if manual:
            desc += " · registrado no painel" + (f" ({r['nota']})" if r["nota"] else "")
        out.append(_pg(None if manual else str(r["chave"])[3:], r["data"], r["valor"], r["status"], r["meio"], origem, desc, r["nome"] or "",
                       f"CAMP-AMIGO-{r['site_id']}" if r["site_id"] else "", tarifa=0.0 if manual else None, liquido=_num(r["valor"]) if manual else None,
                       registro={"tela": "amigos", "id": r["amigo_id"]}, fora_mp=manual))
    return out


def _mp_rows(con) -> dict[str, dict]:
    return {str(r["mp_id"]): dict(r) for r in con.execute("SELECT * FROM mp_pagamento")}


def _origem_da_ref(ref: str) -> str:
    for p, o in PREFIXOS:
        if (ref or "").upper().startswith(p):
            return o
    return "direto_mp"


# ---------------------------------------------------------------- entrada ou saída (contrato 1.35)
def _direcoes(con) -> dict[str, dict]:
    """Escolhas manuais "Isto é uma saída (despesa)" / "Isto é uma entrada" (migração 255; banco sem ela: nenhuma)."""
    try:
        return {str(r["mp_id"]): dict(r) for r in con.execute("SELECT * FROM financeiro_direcao")}
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------- o livro da conta (migração 258)
# Rafael: "a direção tem de vir do sistema, de forma confiável, pela documentação do Mercado Pago". Relatório de liberações: NET_CREDIT_AMOUNT
# = creditado no saldo (entrada), NET_DEBIT_AMOUNT = debitado (saída). Extrato: valor positivo = entrada, negativo = saída. Tarifas e impostos
# do mesmo pagamento não contam para a direção (são do recebedor e viriam com sinal contrário ao da venda).
_RE_MOV_ACESSORIO = re.compile(r"tarifa|imposto|^tax|fee|shipping|reserve|chargeback|dispute|mediation|refund|estorno|devolu", re.I)


def gravar_movimento(con, fonte: str, ref: str, data: str, credito: float, debito: float, descricao: str = "") -> int:
    """Um movimento do saldo com o sinal do Mercado Pago (único pela chave). 0 se já estava ou sem referência."""
    ref = _txt(ref, 100)
    if not ref or fonte not in ("relatorio", "extrato"):
        return 0
    cr, db = round(abs(_num(credito) or 0.0), 2), round(abs(_num(debito) or 0.0), 2)
    if not cr and not db:
        return 0
    desc = _txt(descricao, 120)
    try:
        return con.execute("INSERT OR IGNORE INTO mp_movimento (fonte, ref, data, credito, debito, descricao, chave) VALUES (?,?,?,?,?,?,?)",
                           (fonte, ref, data or None, cr, db, desc or None, f"{fonte}:{ref}:{data or ''}:{cr:.2f}:{db:.2f}:{desc.lower()[:60]}")).rowcount
    except Exception:  # noqa: BLE001 (banco sem a migração 258)
        return 0


def movimentos(con) -> dict[str, dict]:
    """ref → {credito, debito, fonte, direcao}: a soma dos movimentos principais (sem tarifa/imposto/estorno) de cada operação. direcao só quando
    o sinal é inequívoco (só crédito = entrada; só débito = saída); crédito E débito (venda e estorno, por exemplo) = '' (não decide)."""
    out: dict[str, dict] = {}
    try:
        rows = con.execute("SELECT fonte, ref, credito, debito, descricao FROM mp_movimento").fetchall()
    except Exception:  # noqa: BLE001
        return out
    for r in rows:
        if r["descricao"] and _RE_MOV_ACESSORIO.search(r["descricao"]):
            continue
        x = out.setdefault(r["ref"], {"credito": 0.0, "debito": 0.0, "fontes": set()})
        x["fontes"].add(r["fonte"])
        # a mesma operação no relatório E no Extrato: não soma duas vezes (fica o maior de cada lado por fonte)
        x.setdefault("_por_fonte", {}).setdefault(r["fonte"], [0.0, 0.0])
        x["_por_fonte"][r["fonte"]][0] += r["credito"] or 0.0
        x["_por_fonte"][r["fonte"]][1] += r["debito"] or 0.0
    for ref, x in out.items():
        pf = x.pop("_por_fonte")
        x["credito"] = round(max(v[0] for v in pf.values()), 2)
        x["debito"] = round(max(v[1] for v in pf.values()), 2)
        x["fonte"] = "relatorio" if "relatorio" in x["fontes"] else "extrato"
        x["fontes"] = sorted(x["fontes"])
        x["direcao"] = "saida" if x["debito"] > 0 and not x["credito"] else ("entrada" if x["credito"] > 0 and not x["debito"] else "")
    return out


def _mov_de(mov: dict[str, dict] | None, mid: str, r: dict) -> dict | None:
    if not mov:
        return None
    ext = str(r.get("external_reference") or "")
    return mov.get(str(mid)) or (mov.get(ext) if ext and not ext.upper().startswith("CAMP-") else None)


def direcao_mp(r: dict, manual: str | None = None, mov: dict | None = None) -> tuple[str, str]:
    """('entrada'|'saida', motivo): motivo 'manual' (escolha da equipe), 'site' (o site disse: só é entrada o que a CAMP recebeu,
    contrato 1.36), 'provavel' (sem direção e sem referência da CAMP: líquido maior que o bruto — a tarifa foi SOMADA, o dinheiro saiu —, ou
    a descrição é de saída: "Pix enviado", "Pagamento com Pix", boleto, compra, nome de empresa (LTDA…), descritor de cartão "Loja* …") ou ''
    (entrada, como antes)."""
    if manual in ("entrada", "saida"):
        return manual, "manual"
    if mov and mov.get("direcao") in ("entrada", "saida"):
        return mov["direcao"], "livro"   # o sinal do Mercado Pago (relatório de liberações ou Extrato): vence o site e a heurística
    d = str(r.get("direcao") or "").lower()
    if d in ("entrada", "saida"):
        return d, "site"
    if str(r.get("external_reference") or "").upper().startswith("CAMP-"):
        return "entrada", ""        # cobrança, Amigos, ingresso, patrocínio: gerados pelo site da CAMP = recebidos
    v, liq = _num(r.get("valor")), _num(r.get("liquido"))
    if v is not None and liq is not None and liq > v + 0.005:
        return "saida", "provavel"  # a tarifa foi SOMADA ao que saiu da conta
    if _parece_saida(str(r.get("descricao") or "")):
        return "saida", "provavel"
    return "entrada", ""


# Sem `direcao` (site até 1.44.0 deixava sem direção o Pix pago a uma empresa sem payer.id; linhas antigas): o que a descrição do Mercado
# Pago diz. Só a DESCRIÇÃO (o pagador pode ser uma empresa que doou). Rafael: "vc ta colocando despesa como receita, e eh saida de dinheiro".
_RE_SAIDA_ROTULO = re.compile(r"\b(pix enviado|transfer[eê]ncia (pix )?enviada|pagamento com pix|pagamento (de|do) boleto|boleto pago|pagamento de conta"
                              r"|compra (com|no|de)|saque)\b", re.I)
_RE_EMPRESA = re.compile(r"\b(ltda|eireli|s\.?\s?a\.?|s/a|me|mei|epp)\s*\.?\s*$|\bltda\b", re.I)
_RE_DESCRITOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .&-]{1,24}\*\s?\S")   # "Anthropic* claude sub": descritor de fatura de cartão de um vendedor


def _parece_saida(desc: str) -> bool:
    d = " ".join(desc.split())
    return bool(d) and bool(_RE_SAIDA_ROTULO.search(d) or _RE_EMPRESA.search(d) or _RE_DESCRITOR.match(d))


def saidas_mp(con, mp: dict[str, dict] | None = None, dman: dict[str, dict] | None = None) -> dict[str, tuple[dict, str]]:
    """mp_id → (dados do pagamento, motivo) de cada pagamento que é SAÍDA (feito pela CAMP)."""
    mp = _mp_rows(con) if mp is None else mp
    dman = _direcoes(con) if dman is None else dman
    mov = movimentos(con)
    out: dict[str, tuple[dict, str]] = {}
    for mid, r in mp.items():
        d, motivo = direcao_mp(r, (dman.get(mid) or {}).get("direcao"), _mov_de(mov, mid, r))
        if d == "saida" and (r.get("status") or "").lower() in CONTA:
            out[mid] = (r, motivo)
    for mid, x in dman.items():
        if x.get("direcao") == "saida" and mid not in out:
            out[mid] = (_json(x.get("dados"), {}), "manual")
    return out


def _debitado(r: dict, mov: dict | None = None) -> float:
    """O que saiu da conta: o débito do livro (relatório de liberações/Extrato: o valor exato do Mercado Pago); senão o valor que o site mandou
    (total pago); senão o líquido quando é maior que o bruto (site antigo); senão o bruto. As tarifas (fee_details) são do RECEBEDOR: somá-las
    dava −R$ 482,24 numa compra que o Extrato mostra −R$ 472,24."""
    if mov and (mov.get("debito") or 0) > 0 and not mov.get("credito"):
        return round(mov["debito"], 2)
    deb, v, liq = _num(r.get("debitado")), _num(r.get("valor")) or 0.0, _num(r.get("liquido"))
    if deb and deb > 0:
        return deb
    if liq is not None and liq > v:
        return liq
    return round(v, 2)


def _ev_mp(con, mid: str, tipo: str, ator: str, detalhe: dict) -> None:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('mp_pagamento',?,?,?,?)", (mid, tipo, ator, json.dumps(detalhe, ensure_ascii=False)))


def rotulo_generico(txt: str) -> bool:
    """Texto que é rótulo do painel ou do Mercado Pago, não o nome de quem recebeu ("Recebido direto no Mercado Pago", "Pagamento com o saldo do
    Mercado Pago"…). Rafael viu uma despesa com o título "Recebido direto no Mercado Pago": o "Isto é uma saída" levava o rótulo da receita como
    quem recebeu."""
    from . import despesas
    t = " ".join(str(txt or "").split()).lower()
    if not t:
        return True
    rot = {v.lower() for v in ORIGENS.values()} | {"pagamento do mercado pago"}
    rot |= {str(x).lower() for x in getattr(despesas, "ROTULOS_MP", ())}
    return t in rot or t.startswith("pagamento com o saldo do mercado pago") or t.startswith("recebido direto no mercado pago")


def reprocessar_saidas_mp(con, ator: str = "painel") -> dict:
    """Cada pagamento de SAÍDA vira (uma vez) despesa da conta do Mercado Pago, na fila Precisa justificar. Idempotente; roda depois de cada
    busca e na leitura do Financeiro/Despesas/DRE (refaz as linhas antigas que entraram como receita). Não duplica: se o relatório de
    liberações ou o Extrato já trouxe o movimento (mesmo id do pagamento ou referência), só completa quem recebeu. A nota da equipe vira a
    justificativa; a classificação manual (natureza de receita) cai, com registro no histórico. Saída que voltou a ser entrada sai das despesas."""
    from . import despesas
    out = {"criadas": 0, "ja_existiam": 0, "reativadas": 0, "retiradas": 0, "classificacoes_descartadas": 0}
    try:
        mp, dman = _mp_rows(con), _direcoes(con)
        alvos = saidas_mp(con, mp, dman)
        mov = movimentos(con)
        for d in con.execute("SELECT id, contraparte FROM despesa WHERE origem='mp' AND COALESCE(contraparte,'')<>''").fetchall():
            if rotulo_generico(d["contraparte"]):    # linha antiga com o rótulo da receita no lugar de quem recebeu: limpa (o nome real entra a seguir)
                con.execute("UPDATE despesa SET contraparte=NULL WHERE id=?", (d["id"],))
        sem_tarifa = "COALESCE(categoria,'') NOT IN ('tarifas','impostos')"
        for mid, (r, motivo) in sorted(alvos.items()):
            row = mp.get(mid) or {}
            if row.get("classificar"):
                con.execute("UPDATE mp_pagamento SET classificar=NULL, classificado_por=NULL, alterado_em=datetime('now') WHERE mp_id=? AND classificar IS NOT NULL", (mid,))
                _ev_mp(con, mid, "classificacao_descartada", ator, {"de": row["classificar"], "motivo": "é saída (pagamento feito pela CAMP): virou despesa"})
                out["classificacoes_descartadas"] += 1
            ext = _txt(r.get("external_reference"), 80)
            refs = [mid] + ([ext] if ext and ext != mid else [])
            ph = ",".join("?" * len(refs))
            achou = con.execute(f"SELECT id, apagado_em, apagado_motivo FROM despesa WHERE (mp_ref IN ({ph}) OR chave=?) AND {sem_tarifa} ORDER BY apagado_em IS NOT NULL, id",
                                (*refs, f"mpp:{mid}")).fetchall()
            ativa = next((a for a in achou if not a["apagado_em"]), None)
            man = _json((dman.get(mid) or {}).get("dados"), {})     # "Isto é uma saída" numa receita: quem estava na linha (o pagador)
            quem = next((q for q in (_txt(v, 160) for v in (r.get("contraparte"), man.get("contraparte"), r.get("descricao"))) if q and not rotulo_generico(q)), "")
            if ativa:
                if quem:
                    con.execute("UPDATE despesa SET contraparte=COALESCE(NULLIF(contraparte,''), ?) WHERE id=?", (quem, ativa["id"]))
                certo = _debitado(r, _mov_de(mov, mid, r))
                va = con.execute("SELECT valor, chave FROM despesa WHERE id=?", (ativa["id"],)).fetchone()
                if va and va["chave"].startswith("mpp:") and certo > 0 and abs((va["valor"] or 0) - certo) > 0.005:   # o valor exato do Mercado Pago
                    con.execute("UPDATE despesa SET valor=?, alterado_por=?, alterado_em=datetime('now') WHERE id=?", (certo, ator, ativa["id"]))
                    despesas._ev(con, ativa["id"], "valor_corrigido", ator, {"de": va["valor"], "para": certo, "mp_id": mid})
                    out["valores_corrigidos"] = out.get("valores_corrigidos", 0) + 1
                out["ja_existiam"] += 1
                continue
            volta = next((a for a in achou if a["apagado_motivo"] == MOTIVO_ENTRADA), None)
            if volta:
                con.execute("UPDATE despesa SET apagado_em=NULL, apagado_por=NULL, apagado_motivo=NULL, alterado_por=?, alterado_em=datetime('now') WHERE id=?", (ator, volta["id"]))
                despesas._ev(con, volta["id"], "reativada", ator, {"motivo": "é saída de novo", "mp_id": mid})
                out["reativadas"] += 1
                continue
            if achou:                       # a equipe apagou de propósito (com motivo): não volta
                out["ja_existiam"] += 1
                continue
            _, meio, _, rotulo = despesas._classificar_mp("payment", str(r.get("meio") or ""), str(r.get("metodo") or ""))
            desc = rotulo + (f" · {AVISO_PROVAVEL}" if motivo == "provavel" else "")
            dia = dia_sp(r.get("aprovado_em") or r.get("data")) or hoje().isoformat()
            did = con.execute("""INSERT OR IGNORE INTO despesa (conta_id, data, valor, meio, contraparte, descricao, origem, chave, tipo, justificativa, mp_ref, criado_por)
                                 VALUES (?,?,?,?,?,?, 'mp', ?, 'despesa', ?, ?, 'Mercado Pago')""",
                              (CONTA_MP, dia, _debitado(r, _mov_de(mov, mid, r)), meio, quem or None, desc, f"mpp:{mid}", _txt(row.get("nota"), 500) or None, mid)).lastrowid
            if did:
                despesas._ev(con, did, "importada", ator, {"origem": "pagamentos do Mercado Pago (saída)", "mp_id": mid, "motivo": motivo})
                out["criadas"] += 1
        # saída que deixou de ser (a equipe disse "Isto é uma entrada", ou o site corrigiu): some das despesas (fica no histórico)
        entradas = {mid for mid, x in dman.items() if x.get("direcao") == "entrada"}
        for d in con.execute(f"SELECT id, chave, mp_ref FROM despesa WHERE apagado_em IS NULL AND origem='mp' AND mp_ref IS NOT NULL AND {sem_tarifa}").fetchall():
            fora = (d["chave"].startswith("mpp:") and d["chave"][4:] not in alvos) or d["mp_ref"] in entradas
            if fora:
                con.execute("UPDATE despesa SET apagado_em=datetime('now'), apagado_por=?, apagado_motivo=? WHERE id=?", (ator, MOTIVO_ENTRADA, d["id"]))
                despesas._ev(con, d["id"], "apagada", ator, {"motivo": MOTIVO_ENTRADA, "mp_id": d["mp_ref"]})
                out["retiradas"] += 1
        con.commit()
    except Exception as e:  # noqa: BLE001 (nunca derruba a tela)
        registrar(logging.WARNING, "financeiro_saidas", "Saídas do Mercado Pago (pagamentos feitos pela CAMP) com problema", erro=type(e).__name__)
        out["erro"] = type(e).__name__
    return out


# ---------------------------------------------------------------- o livro
def livro(con, de: str, ate: str, docs: bool = False) -> dict:
    """Todas as linhas do período (São Paulo) + a conferência. Puro sobre o banco (os testes chamam direto)."""
    m = mapa(con)
    mp = _mp_rows(con)
    r0 = con.execute("SELECT nome FROM financeiro_conta WHERE id=?", (CONTA_MP,)).fetchone()
    nome_mp = r0[0] if r0 else "Mercado Pago"
    saidas = saidas_mp(con, mp)            # pagamentos FEITOS pela CAMP: nunca receita (viram despesa em reprocessar_saidas_mp)
    cob, sem1 = _de_cobrancas(con, docs)
    pat, sem2 = _de_patrocinios(con, docs)
    ing, sem3 = _de_ingressos(con)
    ami = _de_amigos(con)
    vistos: set[str] = set()
    dup: list[str] = []
    linhas: list[dict] = []
    sem_no_mp: list[dict] = []
    cobre_de, cobre_ate = _estado(con, "mp_de"), _estado(con, "mp_ate")

    def natureza(origem, mprow):
        n = (mprow or {}).get("classificar")
        return n if n in NATUREZAS else m.get(origem, "outras")

    def emitir(p: dict, mprow: dict | None, sem_par: bool = False):
        origem = p["origem"]
        nat = natureza(origem, mprow)
        st = p["status"]
        data = p["data"]
        valor, tarifa, liquido, meio = p["valor"], p["tarifa"], p["liquido"], p["meio"]
        estornos = p.get("estornos") or []
        if mprow:
            st = (mprow.get("status") or st).lower()
            data = dia_sp(mprow.get("aprovado_em")) or data
            valor = _num(mprow.get("valor")) if mprow.get("valor") is not None else valor
            tarifa = _num(mprow.get("tarifa")) if mprow.get("tarifa") is not None else tarifa
            liquido = _num(mprow.get("liquido")) if mprow.get("liquido") is not None else liquido
            meio = mprow.get("meio") or meio
            estornos = _json(mprow.get("estornos"), [])
        conferir = tarifa is None
        if st in ESTORNO and tarifa is not None:
            liquido = None          # depois do estorno o Mercado Pago dá líquido 0; aqui a linha positiva fica bruto − tarifa e o estorno vem na linha negativa
        if tarifa is not None and liquido is None:
            liquido = round(valor - tarifa, 2)
        base = {"conta_id": CONTA_MP, "conta_nome": nome_mp, "natureza": nat, "natureza_nome": NATUREZAS[nat], "origem": origem, "origem_nome": ORIGENS[origem], "descricao": p["descricao"],
                "pagador": p["pagador"], "meio": MEIO.get(meio, meio or ""), "external_reference": p["ref"], "mp_id": p["mp_id"] or "",
                "fonte": p["fonte"], "registro": p["registro"], "fora_mp": p["fora_mp"], "sem_par_painel": sem_par,
                "classificavel": bool(mprow), "classificado": bool((mprow or {}).get("classificar")), "nota": (mprow or {}).get("nota") or "",
                "pode_ser_saida": bool(p["mp_id"]) and not p["fora_mp"]}
        if docs:
            base["documento"] = p.get("documento") or ""
        obs = []
        if p["fora_mp"]:
            obs.append("fora do Mercado Pago (registrado no painel)")
        if conferir:
            obs.append("tarifa a conferir no extrato")
        if sem_par:
            obs.append("referência da CAMP sem registro no painel")
        linhas.append(dict(base, id=f"{p['fonte']}:{p['mp_id'] or id(p)}", data=data, bruto=valor, tarifa=tarifa, liquido=liquido,
                           tarifa_conferir=conferir, situacao="estornado depois" if st in ESTORNO else ("em disputa" if st == "in_mediation" else "confirmado"),
                           estorno=False, observacao="; ".join(obs)))
        if st in ESTORNO or (mprow and (mprow.get("estornado") or 0) > 0):
            lista = [e for e in estornos if isinstance(e, dict) and _num(e.get("valor"))]
            if not lista:
                tot = _num((mprow or {}).get("estornado")) or valor
                lista = [{"valor": tot, "em": ""}]
            for i, e in enumerate(lista):
                quando = dia_sp(e.get("em"))
                linhas.append(dict(base, id=f"{p['fonte']}:{p['mp_id'] or id(p)}:estorno{i}", data=quando or data, bruto=-abs(_num(e["valor"])),
                                   tarifa=None, liquido=-abs(_num(e["valor"])), tarifa_conferir=True,
                                   situacao="contestação (chargeback)" if st == "charged_back" else "estorno", estorno=True,
                                   observacao="estorno" + ("" if quando else "; data do estorno a conferir no extrato") + "; tarifa a conferir no extrato"))

    for p in cob + pat + ing + ami:
        if p["mp_id"] and p["mp_id"] in saidas:
            vistos.add(p["mp_id"])
            continue
        if p["mp_id"]:
            if p["mp_id"] in vistos:
                dup.append(p["mp_id"])
                continue
            vistos.add(p["mp_id"])
        mprow = mp.get(p["mp_id"]) if p["mp_id"] else None
        emitir(p, mprow)
        if p["mp_id"] and not mprow and cobre_de and cobre_de <= p["data"] <= cobre_ate and de <= p["data"] <= ate:
            sem_no_mp.append({"mp_id": p["mp_id"], "data": p["data"], "origem": ORIGENS[p["origem"]], "external_reference": p["ref"], "valor": p["valor"]})
    try:                                     # CAMP-ROUANET: notas da CAMP pagas pelo projeto = receita da conta da CAMP (o crédito no Mercado Pago não vira doação)
        from . import rouanet
        mp_int, lin_int = rouanet.receitas_livro(con)
        vistos |= mp_int
        linhas += lin_int
    except ImportError:
        pass
    mp_sem_par, diretos = [], 0
    for mid, r in mp.items():
        if mid in vistos or mid in saidas or (r.get("status") or "").lower() not in CONTA:
            continue
        vistos.add(mid)
        ref = r.get("external_reference") or ""
        origem = _origem_da_ref(ref)
        sem_par = origem != "direto_mp"
        desc = _txt(r.get("descricao"), 160) or ("Recebido direto no Mercado Pago" if not sem_par else "Pagamento do Mercado Pago")
        p = _pg(mid, dia_sp(r.get("aprovado_em")), r.get("valor"), r.get("status"), r.get("meio"), origem, desc, r.get("pagador") or "", ref, fonte="mp")
        emitir(p, r, sem_par=sem_par)
        d = dia_sp(r.get("aprovado_em"))
        if de <= d <= ate:
            if sem_par:
                mp_sem_par.append({"mp_id": mid, "data": d, "external_reference": ref, "valor": _num(r.get("valor"))})
            else:
                diretos += 1
    no_periodo = [x for x in linhas if de <= x["data"] <= ate]
    no_periodo.sort(key=lambda x: (x["data"], x["origem"], x["id"]))
    conf = {
        "linhas": len(no_periodo),
        "com_mp": sum(1 for x in no_periodo if x["mp_id"] and not x["estorno"]),
        "confirmados_no_mp": sum(1 for x in no_periodo if x["mp_id"] and not x["estorno"] and x["mp_id"] in mp),
        "fora_mp": sum(1 for x in no_periodo if x["fora_mp"]),
        "diretos_mp": diretos,
        "duplicados_ignorados": sorted(set(dup)),
        "painel_sem_mp": sem_no_mp,
        "mp_sem_painel": mp_sem_par,
        "sem_confirmacao": sem1 + sem2 + sem3,
        "mp_cobre": {"de": cobre_de, "ate": cobre_ate},
        "saidas_mp": [{"mp_id": mid, "data": dia_sp(r.get("aprovado_em") or r.get("data")), "valor": _debitado(r), "contraparte": _txt(r.get("contraparte") or r.get("descricao"), 160),
                       "motivo": motivo, "aviso": AVISO_PROVAVEL if motivo == "provavel" else ""}
                      for mid, (r, motivo) in sorted(saidas.items()) if de <= dia_sp(r.get("aprovado_em") or r.get("data")) <= ate],
    }
    return {"linhas": no_periodo, "conferencia": conf}


def _soma(ls: list[dict]) -> dict:
    return {"bruto": round(sum(x["bruto"] for x in ls), 2), "tarifa": round(sum(x["tarifa"] or 0 for x in ls), 2),
            "liquido": round(sum((x["liquido"] if x["liquido"] is not None else x["bruto"]) for x in ls), 2), "n": sum(1 for x in ls if not x["estorno"]),
            "tarifa_conferir": sum(1 for x in ls if x["tarifa_conferir"] and not x["estorno"])}


def totais(linhas: list[dict], ctas: list[dict] | None = None) -> dict:
    por_nat = {k: dict(_soma([x for x in linhas if x["natureza"] == k]), natureza=k, nome=v) for k, v in NATUREZAS.items()
               if k != "servicos_projeto" or any(x["natureza"] == k for x in linhas)}   # CAMP-ROUANET: só aparece quando houver nota da CAMP paga
    meses = sorted({x["data"][:7] for x in linhas})
    por_mes = [dict(_soma([x for x in linhas if x["data"][:7] == mm]), mes=mm) for mm in meses]
    doa = [x for x in linhas if x["natureza"] in ("doacoes", "doacoes_restricao")]
    so_doa = [x for x in linhas if x["natureza"] == "doacoes"]
    est = [x for x in linhas if x["estorno"]]
    por_conta = [dict(_soma([x for x in linhas if x.get("conta_id") == c["id"]]), conta_id=c["id"], nome=c["nome"], restrito=bool(c["restrito"]),
                      tipo=c["tipo"]) for c in (ctas or [])]
    return {"geral": _soma(linhas), "por_conta": por_conta, "por_natureza": list(por_nat.values()), "por_mes": por_mes,
            "doacoes": dict(_soma(doa), sem_restricao=_soma(so_doa)["bruto"], com_restricao=round(_soma(doa)["bruto"] - _soma(so_doa)["bruto"], 2)),
            "estornos": {"valor": round(sum(x["bruto"] for x in est), 2), "n": len(est)}}


def rascunho(de: str, ate: str, tot: dict, linhas: list[dict], extra: list[str] | None = None) -> str:
    """Parágrafo factual para as notas explicativas (o contador revisa)."""
    g = tot["geral"]
    partes = [f"No período de {_dbr(de)} a {_dbr(ate)}, o painel da CAMP registrou receitas brutas de {brl(g['bruto'])} "
              f"({g['n']} recebimentos), com tarifas do Mercado Pago de {brl(g['tarifa'])} e valor líquido de {brl(g['liquido'])}."]
    nat = [f"{n['nome']}: {brl(n['bruto'])} ({n['n']})" for n in tot["por_natureza"] if n["n"] or n["bruto"]]
    if nat:
        partes.append("Por natureza: " + "; ".join(nat) + ".")
    origens = sorted({x["origem_nome"] for x in linhas})
    if origens:
        partes.append("Origens: " + ", ".join(origens) + ".")
    if tot["estornos"]["n"]:
        partes.append(f"Estornos e contestações no período: {brl(tot['estornos']['valor'])} ({tot['estornos']['n']}).")
    conf = sum(1 for x in linhas if x["tarifa_conferir"] and not x["estorno"])
    if conf:
        partes.append(f"Em {conf} recebimento(s) a tarifa do Mercado Pago ainda não foi lida e deve ser conferida no extrato.")
    partes += extra or []
    partes.append("A classificação por natureza foi sugerida pelo painel e deve ser confirmada pelo contador.")
    return " ".join(partes)


def filtrar(linhas: list[dict], natureza: str = "", origem: str = "", conta: int = 0) -> list[dict]:
    return [x for x in linhas if (not natureza or x["natureza"] == natureza) and (not origem or x["origem"] == origem)
            and (not conta or x.get("conta_id") == conta)]


# ---------------------------------------------------------------- conta do Mercado Pago (pelo site)
def mp_coleta_min(con) -> int:
    try:
        return max(0, int(_cfg(con, "financeiro.mp_coleta_min", "60")))
    except ValueError:
        return 60


def _gravar_mp(con, x: dict) -> int:
    mid = _txt(x.get("id"), 40)
    if not mid or not re.fullmatch(r"[0-9A-Za-z_-]+", mid):
        return 0
    est = []
    for e in x.get("estornos") or x.get("refunds") or []:
        if isinstance(e, dict) and _num(e.get("valor", e.get("amount"))):
            est.append({"valor": _num(e.get("valor", e.get("amount"))), "em": _utc(e.get("em") or e.get("date_created"))})
    tarifa = x.get("tarifa")
    if tarifa is None and isinstance(x.get("fee_details"), list):
        tarifa = sum(float(f.get("amount") or 0) for f in x["fee_details"] if isinstance(f, dict))
    v = {"aprovado_em": _utc(x.get("date_approved") or x.get("aprovado_em")) or None, "status": _txt(x.get("status"), 30).lower() or None,
         "valor": _num(x.get("transaction_amount", x.get("valor"))), "tarifa": _num(tarifa),
         "liquido": _num(x.get("net_received_amount", x.get("liquido"))), "estornado": _num(x.get("transaction_amount_refunded", x.get("estornado"))) or 0.0,
         "estornos": json.dumps(est) if est else None, "meio": _txt(x.get("payment_type_id") or x.get("meio"), 30) or None,
         "metodo": _txt(x.get("payment_method_id") or x.get("metodo"), 30) or None, "external_reference": _txt(x.get("external_reference"), 80) or None,
         "descricao": _txt(x.get("description") or x.get("descricao"), 200) or None, "pagador": _txt(x.get("pagador") or x.get("payer_name"), 160) or None}
    if _tem_coluna(con, "mp_pagamento", "direcao"):     # contrato 1.35 (OPCIONAL): site antigo não manda = NULL (heurística na leitura)
        d = _txt(x.get("direcao"), 10).lower()
        v.update({"direcao": d if d in ("entrada", "saida") else None, "contraparte": _txt(x.get("contraparte"), 160) or None,
                  "debitado": _num(x.get("valor_debitado"))})
    ja = con.execute("SELECT 1 FROM mp_pagamento WHERE mp_id=?", (mid,)).fetchone()
    if ja:
        con.execute(f"UPDATE mp_pagamento SET {', '.join(k + '=?' for k in v)}, alterado_em=datetime('now') WHERE mp_id=?", (*v.values(), mid))
        return 0
    con.execute(f"INSERT INTO mp_pagamento (mp_id, {', '.join(v)}) VALUES (?{',?' * len(v)})", (mid, *v.values()))
    return 1


def _tem_coluna(con, tabela: str, coluna: str) -> bool:
    return any(r[1] == coluna for r in con.execute(f"PRAGMA table_info({tabela})"))


def coletar_mp(con=None, wp=None, de: str | None = None, ate: str | None = None) -> dict:
    """Uma volta na conta do Mercado Pago (pelo site; a chave fica lá). 1ª vez: desde financeiro.mp_inicio; depois os últimos 40 dias
    (pega estornos). Paginado; nunca levanta; nada de chave, nome ou valor no log técnico."""
    fechar = con is None
    con = con or connect()
    out = {"lidos": 0, "novos": 0, "paginas": 0, "sem_rota": False, "desligado": False, "erro": None}
    try:
        wp = wp or _wp()
        ate = ate or hoje().isoformat()
        if not de:
            ult = _estado(con, "mp_ate")
            de = (date.fromisoformat(ult) - timedelta(days=40)).isoformat() if ult else _cfg(con, "financeiro.mp_inicio", "2026-01-01")
        pagina = 1
        while pagina <= 200:
            r = wp.h.get(ROTA_MP, params={"desde": de, "ate": ate, "pagina": pagina})
            if r.status_code == 404:
                out["sem_rota"] = True
                _estado_set(con, "sem_rota", "1")
                con.commit()
                return out
            if r.status_code == 409:
                out["desligado"] = True
                _estado_set(con, "desligado", "1")
                con.commit()
                return out
            if r.status_code >= 400:
                raise RuntimeError(f"O site respondeu {r.status_code} ao buscar os pagamentos do Mercado Pago")
            d = r.json()
            if not isinstance(d, dict):
                raise RuntimeError("O site devolveu formato inválido para os pagamentos do Mercado Pago")
            out["paginas"] += 1
            bp = str(d.get("busca_pagos") or "")      # contrato 1.37 (site 1.46.0): a busca do que a CAMP pagou (payer.id)
            if bp and out.get("busca_pagos") != "falhou":
                out["busca_pagos"] = bp
            out["pagos"] = out.get("pagos", 0) + int(d.get("pagos") or 0)
            for x in d.get("itens") or []:
                if isinstance(x, dict):
                    out["lidos"] += 1
                    out["novos"] += _gravar_mp(con, x)
            con.commit()
            if not d.get("mais"):
                break
            pagina += 1
        antes = _estado(con, "mp_de")
        _estado_set(con, "mp_de", min(antes, de) if antes else de)
        _estado_set(con, "mp_ate", max(_estado(con, "mp_ate") or ate, ate))
        for k in ("sem_rota", "desligado", "ultimo_erro"):
            _estado_set(con, k, "")
        _estado_set(con, "busca_pagos", out.get("busca_pagos") or "site_antigo")
        _estado_set(con, "ultimo_periodo", f"{de}|{ate}")
        con.commit()
        out["saidas"] = reprocessar_saidas_mp(con, "Mercado Pago")
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)[:200]
        _estado_set(con, "ultimo_erro", out["erro"])
        registrar(logging.WARNING, "financeiro_mp", "Busca dos pagamentos do Mercado Pago com problema", erro=type(e).__name__)
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
    """A volta automática (financeiro.mp_coleta_min; 0 desliga). Sem a senha do site: nada. Nunca levanta."""
    con = connect()
    try:
        m = mp_coleta_min(con)
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
        out = coletar_mp(con)
        try:
            from . import despesas
            out["despesas"] = despesas.rodada_mp(con)
        except ImportError:
            pass
        return out
    except Exception as e:  # noqa: BLE001
        registrar(logging.WARNING, "financeiro_rodada", "Rodada do Financeiro com problema", erro=type(e).__name__)
        return {"erro": type(e).__name__}
    finally:
        con.close()


def estado_mp(con) -> dict:
    return {"ultima_busca": _estado(con, "ultima_busca"), "ultimo_erro": _estado(con, "ultimo_erro"), "sem_rota": bool(_estado(con, "sem_rota")),
            "desligado": bool(_estado(con, "desligado")), "de": _estado(con, "mp_de"), "ate": _estado(con, "mp_ate"),
            "em_andamento": bool(_SINC.locked()), "pagamentos": con.execute("SELECT COUNT(*) FROM mp_pagamento").fetchone()[0],
            "tem_site": _tem_site(con), "versao_site": VERSAO_SITE, "busca_pagos": _estado(con, "busca_pagos") or None,
            "ultimo_periodo": _estado(con, "ultimo_periodo") or None}


_SINC = threading.Lock()


def _sincronizar_fundo(de: str | None = None, ate: str | None = None) -> None:
    if not _SINC.acquire(blocking=False):
        return
    try:
        con = connect()
        try:
            coletar_mp(con, de=de, ate=ate)
            try:
                from . import despesas
                despesas.rodada_mp(con, force=True)
            except ImportError:
                pass
        finally:
            con.close()
    finally:
        _SINC.release()


# ---------------------------------------------------------------- relatório completo
def relatorio(con, de: str, ate: str, natureza: str = "", origem: str = "", docs: bool = False, conta: int = 0) -> dict:
    """Totais por conta separados; com `conta`, o resto do relatório (totais, linhas) fica só naquela conta."""
    reprocessar_saidas_mp(con)                # linhas antigas que entraram como receita viram despesa (idempotente)
    lv = livro(con, de, ate, docs)
    ctas = contas(con)
    por_conta = totais(lv["linhas"], ctas)["por_conta"]
    base = filtrar(lv["linhas"], conta=conta)
    tot = totais(base, ctas)
    tot["por_conta"] = por_conta
    extra: list[str] = []
    desp = None
    try:
        from . import despesas
        desp = despesas.resumo_periodo(con, de, ate, conta, tot)
        extra = despesas.frases_rascunho(desp, tot)
    except ImportError:
        pass
    serie, anterior = _serie_e_anterior(con, de, ate, conta)
    nota = con.execute("SELECT texto, atualizado_por, atualizado_em FROM financeiro_nota WHERE periodo=?", (f"{de}|{ate}",)).fetchone()
    m = mapa(con)
    return {"periodo": {"de": de, "ate": ate}, "gerado_em": datetime.now(FUSO).strftime("%Y-%m-%d %H:%M"),
            "naturezas": [{"chave": k, "nome": v, "explica": EXPLICA_NATUREZA[k]} for k, v in NATUREZAS.items() if k != "servicos_projeto"],   # vem só das notas da CAMP
            "origens": [{"chave": k, "nome": v, "natureza": m[k]} for k, v in ORIGENS.items() if k != "nota_projeto"], "mapa": m, "totais": tot,
            "linhas": filtrar(base, natureza, origem), "n_total": len(base), "conferencia": lv["conferencia"],
            "nota": dict(nota) if nota else {"texto": "", "atualizado_por": "", "atualizado_em": ""},
            "rascunho": rascunho(de, ate, tot, base, extra), "contas": ctas, "conta": conta,
            "tipos_conta": TIPOS_CONTA, "serie": serie, "anterior": anterior, "mp": estado_mp(con), "despesas": desp, "documento": docs}


def _serie_e_anterior(con, de: str, ate: str, conta: int = 0) -> tuple[list[dict], dict]:
    """12 meses até o fim do período (receitas brutas e líquidas, despesas, resultado) e os números do período anterior do mesmo tamanho."""
    try:
        from . import despesas, dre
    except ImportError:
        return [], {}
    fim = date.fromisoformat(ate)
    a, m = fim.year, fim.month - 11
    while m < 1:
        a, m = a - 1, m + 12
    ini = date(a, m, 1).isoformat()
    rec = filtrar(livro(con, ini, ate)["linhas"], conta=conta)
    ds = despesas.listar(con, ini, ate, conta)
    serie = []
    for i in range(12):
        mm = f"{a + (m - 1 + i) // 12}-{(m - 1 + i) % 12 + 1:02d}"
        r_ = [x for x in rec if x["data"][:7] == mm]
        b = round(sum(x["bruto"] for x in r_), 2)
        lq = round(sum((x["liquido"] if x["liquido"] is not None else x["bruto"]) for x in r_), 2)
        dv = round(sum(x["valor"] for x in ds if x["data"][:7] == mm), 2)
        serie.append({"mes": mm, "receitas": b, "receitas_liquidas": lq, "despesas": dv, "resultado": round(lq - dv, 2)})
    a1, a2 = dre.periodo_anterior(de, ate)
    ra = filtrar(livro(con, a1, a2)["linhas"], conta=conta)
    da = despesas.listar(con, a1, a2, conta)
    ta = totais(ra)
    dt = round(sum(x["valor"] for x in da), 2)
    return serie, {"periodo": {"de": a1, "ate": a2}, "receitas": ta["geral"]["bruto"], "despesas": dt, "resultado": round(ta["geral"]["liquido"] - dt, 2),
                   "doacoes": ta["doacoes"]["bruto"], "doacoes_n": ta["doacoes"]["n"], "comparavel": bool(ra or da)}


def _seguro(v):
    """Texto que começa com = + - @ vira texto (planilha não executa fórmula)."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def _linha_csv(x: dict, docs: bool) -> list:
    base = [_dbr(x["data"]), x.get("conta_nome") or "", x["natureza_nome"], x["origem_nome"], x["descricao"], x["pagador"], x["bruto"],
            "a conferir no extrato" if x["tarifa"] is None else x["tarifa"], x["liquido"] if x["liquido"] is not None else "a conferir no extrato",
            x["meio"], x["external_reference"], x["mp_id"], x["situacao"], "; ".join(t for t in (x["observacao"], x.get("nota") or "") if t)]
    return base + ([x.get("documento") or ""] if docs else [])


def exportar_csv(rel: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    p = rel["periodo"]
    w.writerow(["CAMP — Relatório de receitas para o contador"])
    w.writerow([f"Período: {_dbr(p['de'])} a {_dbr(p['ate'])}"])
    w.writerow([f"Gerado em: {rel['gerado_em']} (horário de São Paulo)"])
    w.writerow(["A classificação por natureza foi sugerida pelo painel; a classificação final é do contador."])
    w.writerow([])
    w.writerow(COLUNAS + (["CPF/CNPJ"] if rel["documento"] else []))
    num = lambda v: f"{v:.2f}".replace(".", ",") if isinstance(v, (int, float)) else v   # noqa: E731
    for x in rel["linhas"]:
        w.writerow([num(_seguro(v)) for v in _linha_csv(x, rel["documento"])])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def exportar_xlsx(rel: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    p = rel["periodo"]
    cab = [f"CAMP — Relatório de receitas para o contador", f"Período: {_dbr(p['de'])} a {_dbr(p['ate'])}",
           f"Gerado em: {rel['gerado_em']} (horário de São Paulo)"]
    ws = wb.active
    ws.title = "Resumo"
    for t in cab:
        ws.append([t])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["A classificação por natureza foi sugerida pelo painel; a classificação final é do contador."])
    ws.append([])
    d = rel["totais"]["doacoes"]
    ws.append([f"Doações recebidas no período: {brl(d['bruto'])} ({d['n']} doações)"])
    ws.append([])
    ws.append(["Natureza", "Bruto (R$)", "Tarifa Mercado Pago (R$)", "Líquido (R$)", "Recebimentos", "Tarifa a conferir"])
    for n in rel["totais"]["por_natureza"]:
        ws.append([n["nome"], n["bruto"], n["tarifa"], n["liquido"], n["n"], n["tarifa_conferir"]])
    g = rel["totais"]["geral"]
    ws.append(["Total", g["bruto"], g["tarifa"], g["liquido"], g["n"], g["tarifa_conferir"]])
    ws.append([])
    ws.append(["Conta (recursos com restrição sempre separados)", "Bruto (R$)", "Tarifa Mercado Pago (R$)", "Líquido (R$)", "Recebimentos"])
    for c in rel["totais"]["por_conta"]:
        ws.append([c["nome"] + (" · com restrição" if c["restrito"] else ""), c["bruto"], c["tarifa"], c["liquido"], c["n"]])
    ws.append([])
    ws.append(["Mês", "Bruto (R$)", "Tarifa Mercado Pago (R$)", "Líquido (R$)", "Recebimentos"])
    for mm in rel["totais"]["por_mes"]:
        ws.append([f"{mm['mes'][5:7]}/{mm['mes'][:4]}", mm["bruto"], mm["tarifa"], mm["liquido"], mm["n"]])
    ws.append([])
    ws.append(["Rascunho das notas explicativas"])
    ws.append([rel["rascunho"]])
    if rel["nota"]["texto"]:
        ws.append(["Notas para o contador"])
        ws.append([_seguro(rel["nota"]["texto"])])
    cols = COLUNAS + (["CPF/CNPJ"] if rel["documento"] else [])
    for k, nome in ABA_XLSX.items():
        sh = wb.create_sheet(nome)
        sh.append([f"{NATUREZAS[k]} · {_dbr(p['de'])} a {_dbr(p['ate'])} · gerado em {rel['gerado_em']}"])
        sh.append(cols)
        for x in rel["linhas"]:
            if x["natureza"] == k:
                sh.append([_seguro(v) for v in _linha_csv(x, rel["documento"])])
    if any(x["natureza"] == "servicos_projeto" for x in rel["linhas"]):   # CAMP-ROUANET: só quando houver
        sh = wb.create_sheet("Serviços ao projeto")
        sh.append([f"{NATUREZAS['servicos_projeto']} · {_dbr(p['de'])} a {_dbr(p['ate'])} · transferência interna no Consolidado"])
        sh.append(cols)
        for x in rel["linhas"]:
            if x["natureza"] == "servicos_projeto":
                sh.append([_seguro(v) for v in _linha_csv(x, rel["documento"])])
    try:
        from . import despesas
        despesas.abas_xlsx(wb, rel)
    except ImportError:
        pass
    for sh in wb.worksheets:
        for row in sh.iter_rows():
            for c in row:
                if isinstance(c.value, float):
                    c.number_format = "#,##0.00"
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


# ---------------------------------------------------------------- rotas (só admin e master)
@router.get("")
def ver(de: str = "", ate: str = "", mes: str = "", ano: str = "", natureza: str = "", origem: str = "", documento: int = 0,
        conta: int = 0, tri: str = "", u: dict = Depends(auth.exige("admin"))) -> dict:
    d1, d2 = periodo(de, ate, mes, ano, tri)
    con = connect()
    try:
        return relatorio(con, d1, d2, natureza, origem, bool(documento), conta)
    finally:
        con.close()


def _nome_arq(d1: str, d2: str, ext: str) -> str:
    return f"camp-receitas-{d1}-a-{d2}.{ext}"


@router.get("/exportar.csv")
def exportar_csv_rota(de: str = "", ate: str = "", mes: str = "", ano: str = "", natureza: str = "", origem: str = "", documento: int = 0,
                      conta: int = 0, tri: str = "", u: dict = Depends(auth.exige("admin"))):
    d1, d2 = periodo(de, ate, mes, ano, tri)
    con = connect()
    try:
        rel = relatorio(con, d1, d2, natureza, origem, bool(documento), conta)
    finally:
        con.close()
    return Response(exportar_csv(rel), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{_nome_arq(d1, d2, "csv")}"'})


@router.get("/exportar.xlsx")
def exportar_xlsx_rota(de: str = "", ate: str = "", mes: str = "", ano: str = "", documento: int = 0, conta: int = 0, tri: str = "",
                       agrupar_pessoal: int = 1, u: dict = Depends(auth.exige("admin"))):
    d1, d2 = periodo(de, ate, mes, ano, tri)
    con = connect()
    try:
        rel = relatorio(con, d1, d2, "", "", bool(documento), conta)
        rel["agrupar_pessoal"] = bool(agrupar_pessoal)   # CAMP-FIN contas fixas: pessoal numa linha por categoria, sem nomes (padrão)
    finally:
        con.close()
    return Response(exportar_xlsx(rel), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{_nome_arq(d1, d2, "xlsx")}"'})


class Mapa(BaseModel):
    mapa: dict[str, str]


@router.put("/mapa")
def gravar_mapa(b: Mapa, u: dict = Depends(auth.exige("admin"))) -> dict:
    ruins = [k for k, v in b.mapa.items() if k not in ORIGENS or v not in NATUREZAS or (v == "servicos_projeto") != (k == "nota_projeto")]
    if ruins:
        raise HTTPException(400, "Origem ou natureza desconhecida: " + ", ".join(ruins[:5]))
    con = connect()
    try:
        novo = dict(mapa(con), **b.mapa)
        con.execute("INSERT INTO configuracao (chave, valor, descricao, sensivel) VALUES ('financeiro.naturezas', ?, 'Financeiro: natureza de cada origem', 0) "
                    "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (json.dumps(novo, ensure_ascii=False),))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('financeiro','mapa','mapa_naturezas',?,?)",
                    (u.get("email") or "painel", json.dumps(b.mapa, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "mapa": novo}
    finally:
        con.close()


class Nota(BaseModel):
    de: str
    ate: str
    texto: str = ""


@router.put("/nota")
def gravar_nota(b: Nota, u: dict = Depends(auth.exige("admin"))) -> dict:
    d1, d2 = periodo(b.de, b.ate)
    con = connect()
    try:
        con.execute("INSERT INTO financeiro_nota (periodo, texto, atualizado_por, atualizado_em) VALUES (?,?,?,datetime('now')) "
                    "ON CONFLICT(periodo) DO UPDATE SET texto=excluded.texto, atualizado_por=excluded.atualizado_por, atualizado_em=excluded.atualizado_em",
                    (f"{d1}|{d2}", b.texto[:20000], u.get("email") or "painel"))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


class Classificar(BaseModel):
    natureza: str = ""          # vazio = volta para a do mapa
    nota: str | None = None


@router.post("/mp/{mp_id}/classificar")
def classificar(mp_id: str, b: Classificar, u: dict = Depends(auth.exige("admin"))) -> dict:
    if b.natureza and (b.natureza not in NATUREZAS or b.natureza == "servicos_projeto"):   # CAMP-ROUANET: essa natureza vem só das notas da CAMP
        raise HTTPException(400, "Natureza desconhecida")
    con = connect()
    try:
        r = con.execute("SELECT classificar, nota FROM mp_pagamento WHERE mp_id=?", (mp_id,)).fetchone()
        if not r:
            raise HTTPException(404, "Pagamento do Mercado Pago não encontrado (sincronize antes)")
        nota = r["nota"] if b.nota is None else (_txt(b.nota, 500) or None)
        con.execute("UPDATE mp_pagamento SET classificar=?, nota=?, classificado_por=?, alterado_em=datetime('now') WHERE mp_id=?",
                    (b.natureza or None, nota, u.get("email") or "painel", mp_id))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('mp_pagamento',?,'classificado',?,?)",
                    (mp_id, u.get("email") or "painel", json.dumps({"de": r["classificar"], "para": b.natureza or None}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "natureza": b.natureza or None, "nota": nota or ""}
    finally:
        con.close()


class Direcao(BaseModel):
    motivo: str = ""


def gravar_direcao(con, mid: str, direcao: str, dados: dict | None, ator: str, extra: dict | None = None) -> None:
    """Lembra a escolha manual (vence o site e a heurística) e registra no histórico do pagamento."""
    antes = (_direcoes(con).get(mid) or {}).get("direcao")
    con.execute("INSERT INTO financeiro_direcao (mp_id, direcao, dados, por, em) VALUES (?,?,?,?,datetime('now')) ON CONFLICT(mp_id) DO UPDATE SET "
                "direcao=excluded.direcao, dados=COALESCE(excluded.dados, financeiro_direcao.dados), por=excluded.por, em=excluded.em",
                (mid, direcao, json.dumps(dados, ensure_ascii=False) if dados else None, ator))
    _ev_mp(con, mid, "direcao_manual", ator, dict({"de": antes or "automática", "para": direcao}, **(extra or {})))


@router.post("/mp/{mp_id}/saida")
def marcar_saida(mp_id: str, b: Direcao, u: dict = Depends(auth.exige("admin"))) -> dict:
    """"Isto é uma saída (despesa)" numa linha de receita: sai das receitas, vira despesa (Precisa justificar). Lembrado."""
    mid = _txt(mp_id, 40)
    ator = u.get("email") or "painel"
    con = connect()
    try:
        linha = next((x for x in livro(con, "2000-01-01", "2100-12-31")["linhas"] if x["mp_id"] == mid and not x["estorno"]), None)
        mpr = con.execute("SELECT 1 FROM mp_pagamento WHERE mp_id=?", (mid,)).fetchone()
        if not mid or (not linha and not mpr):
            raise HTTPException(404, "Pagamento do Mercado Pago não encontrado (sincronize antes)")
        dados = None
        if linha:
            dados = {"data": linha["data"], "valor": linha["bruto"], "tarifa": linha["tarifa"], "liquido": linha["liquido"], "status": "approved",
                     "meio": MEIO_DE_ROTULO.get(linha["meio"], linha["meio"]), "descricao": linha["descricao"], "contraparte": linha["pagador"] or linha["descricao"],
                     "external_reference": linha["external_reference"]}
        gravar_direcao(con, mid, "saida", dados, ator, {"motivo": _txt(b.motivo, 300)} if b.motivo else None)
        con.commit()
        reprocessar_saidas_mp(con, ator)
        d = con.execute("SELECT id FROM despesa WHERE apagado_em IS NULL AND (mp_ref=? OR chave=?) ORDER BY id", (mid, f"mpp:{mid}")).fetchone()
        return {"ok": True, "direcao": "saida", "despesa_id": d[0] if d else None}
    finally:
        con.close()


@router.get("/mp/estado")
def mp_estado(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return estado_mp(con)
    finally:
        con.close()


class Periodo(BaseModel):
    de: str = ""
    ate: str = ""


def periodo_valido(de: str, ate: str) -> tuple[str, str] | tuple[None, None]:
    """("AAAA-MM-DD", "AAAA-MM-DD") de um período escolhido pela equipe (Buscar período), ou (None, None) sem período. 400 se inválido:
    datas reais, de <= até, até no máximo hoje, no máximo 366 dias de uma vez, nada antes de 2020."""
    de, ate = (de or "").strip(), (ate or "").strip()
    if not de and not ate:
        return None, None
    try:
        d0, d1 = date.fromisoformat(de), date.fromisoformat(ate or hoje().isoformat())
    except ValueError as e:
        raise HTTPException(400, "Período inválido: use datas no formato AAAA-MM-DD") from e
    d1 = min(d1, hoje())
    if d0 > d1 or d0.year < 2020:
        raise HTTPException(400, "Período inválido: a data inicial tem de ser antes da final (e de 2020 em diante)")
    if (d1 - d0).days > 366:
        raise HTTPException(400, "Período longo demais: busque até 12 meses de cada vez")
    return d0.isoformat(), d1.isoformat()


@router.post("/mp/sincronizar")
def mp_sincronizar(b: Periodo | None = None, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Sem corpo: a volta de sempre (últimos 40 dias). Com {de, ate} (CAMP-FIN, "Buscar período"): relê esse período no Mercado Pago, para
    compras e recebimentos mais antigos que a janela automática (Rafael: "paguei uma compra de mais de 1700 reais e não está lá")."""
    de, ate = periodo_valido(b.de, b.ate) if b else (None, None)
    con = connect()
    try:
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações: sem ela o painel não lê a conta do Mercado Pago")
    finally:
        con.close()
    if _SINC.locked():
        return {"ok": True, "iniciado": False, "mensagem": "Já está sincronizando."}
    threading.Thread(target=_sincronizar_fundo, args=(de, ate), daemon=True).start()
    return {"ok": True, "iniciado": True, "de": de, "ate": ate,
            "mensagem": "Sincronizando com o Mercado Pago em segundo plano. Atualize a tela em alguns minutos."}


class Conta(BaseModel):
    nome: str
    banco: str = ""
    tipo: str = "operacional"
    restrito: bool = False
    ativa: bool = True
    projeto: str = ""          # rótulo de projeto/rubrica sugerido nas despesas desta conta (texto livre)


def _validar_conta(b: Conta) -> tuple:
    nome = _txt(b.nome, 80)
    if not nome:
        raise HTTPException(400, "Dê um nome à conta")
    if b.tipo not in TIPOS_CONTA:
        raise HTTPException(400, "Tipo de conta inválido")
    return (nome, _txt(b.banco, 80) or None, b.tipo, 1 if (b.restrito or b.tipo == "projeto_incentivado") else 0, 1 if b.ativa else 0,
            _txt(b.projeto, 120) or None)


@router.get("/contas")
def ver_contas(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return {"contas": contas(con), "tipos": TIPOS_CONTA}
    finally:
        con.close()


@router.post("/contas")
def criar_conta(b: Conta, u: dict = Depends(auth.exige("admin"))) -> dict:
    v = _validar_conta(b)
    con = connect()
    try:
        if con.execute("SELECT 1 FROM financeiro_conta WHERE lower(nome)=lower(?)", (v[0],)).fetchone():
            raise HTTPException(409, "Já existe uma conta com esse nome")
        cid = con.execute("INSERT INTO financeiro_conta (nome, banco, tipo, restrito, ativa, projeto) VALUES (?,?,?,?,?,?)", v).lastrowid
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('financeiro_conta',?,'criada',?,?)",
                    (str(cid), u.get("email") or "painel", json.dumps({"nome": v[0], "tipo": v[2], "restrito": v[3]}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "id": cid}
    finally:
        con.close()


@router.put("/contas/{cid}")
def mudar_conta(cid: int, b: Conta, u: dict = Depends(auth.exige("admin"))) -> dict:
    v = _validar_conta(b)
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM financeiro_conta WHERE id=?", (cid,)).fetchone():
            raise HTTPException(404, "Conta não encontrada")
        if cid == CONTA_MP and (v[3] or not v[4]):
            raise HTTPException(400, "A conta do Mercado Pago é a operacional: não pode ser marcada com restrição nem desativada")
        con.execute("UPDATE financeiro_conta SET nome=?, banco=?, tipo=?, restrito=?, ativa=?, projeto=? WHERE id=?", (*v, cid))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('financeiro_conta',?,'alterada',?,?)",
                    (str(cid), u.get("email") or "painel", json.dumps({"nome": v[0], "tipo": v[2], "restrito": v[3], "ativa": v[4]}, ensure_ascii=False)))
        con.commit()
        return {"ok": True}
    finally:
        con.close()
