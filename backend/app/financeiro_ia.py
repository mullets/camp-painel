"""Financeiro · inteligência (CAMP-FIN, 24/11/2026). Rafael: "Capriche na inteligência do sistema, UI e UX exemplares".

Tudo explicável e reversível: cada sugestão diz POR QUÊ e nada é aplicado sozinho (a fila "Precisa justificar" pré-preenche, a pessoa confirma).
- Categoria/natureza sugerida: regra da equipe → o que a equipe escolheu antes para a mesma contraparte (nome normalizado ou CNPJ) → palavras
  da descrição ("correios", "kalunga", "papel neutro"…). Confiança de 0 a 1 e o motivo ("igual às 4 últimas compras em Kalunga").
- Regras "Sempre classificar X como Y" (tabela financeiro_regra, com histórico); sugeridas quando a mesma escolha se repete 3 vezes.
- Justificativa sugerida: a das despesas parecidas e a das tarefas de doação de acervo com valor e data perto (ex.: "Cotar frete · doação Cassol").
- Comprovante: casar valor e data digitados (± R$ 0,05, ± 3 dias) com as saídas do Mercado Pago. Leitura automática da foto/PDF por um leitor
  plugável, DESLIGADA por padrão (`financeiro.leitura_comprovante` = 0): o painel não tem cliente de IA hoje; com um leitor registrado e a
  chave ligada, o arquivo vai para ele (a tela avisa). Nenhuma chave em log.
- Alertas: cobrança repetida, valor fora do usual, cobrança recorrente (com a próxima data), sem comprovante há N dias, doadores (primeira vez,
  recorrentes, maior doação) e orçamento de conta de projeto (gancho para o orçamento da Rouanet).
- Projeção de 3 meses (ESTIMATIVA): mensalidades dos Amigos, renovações anuais que vencem, patrocínio em 12 meses, menos as despesas recorrentes.
- Busca natural: "frete outubro", "doações acima de 500", "sem nota", "Kalunga 2026" → filtros.
"""
from __future__ import annotations

import json
import re
import statistics
import unicodedata
from datetime import date, timedelta
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect

router = APIRouter(prefix="/api/financeiro/ia", tags=["financeiro_ia"])

MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
SUFIXOS = {"ltda", "me", "mei", "epp", "eireli", "sa", "s/a", "s.a.", "cia", "comercio", "com", "de", "da", "do", "e", "servicos"}
PALAVRAS = [   # (trecho normalizado, categoria): na ordem; o primeiro que aparecer vale
    # CAMP-FIN contas fixas: aluguel, consumo e pessoal (antes de "eletric", que é manutenção)
    ("aluguel", "aluguel"), ("condominio", "aluguel"), ("imobiliaria", "aluguel"), ("energia", "consumo"), ("enel", "consumo"), ("sabesp", "consumo"),
    ("conta de agua", "consumo"), ("internet", "consumo"), ("telefon", "consumo"), ("vivo", "consumo"), ("claro", "consumo"), ("comgas", "consumo"),
    ("salario", "salarios"), ("folha de pagamento", "salarios"), ("inss", "encargos"), ("fgts", "encargos"), ("ferias", "encargos"),
    ("decimo terceiro", "encargos"), ("rpa", "autonomos"), ("autonomo", "autonomos"), ("estagi", "bolsas"), ("bolsa", "bolsas"),
    ("correios", "frete"), ("sedex", "frete"), ("frete", "frete"), ("transport", "frete"), ("mudanca", "frete"), ("uber", "frete"),
    ("kalunga", "materiais"), ("tyvek", "materiais"), ("papel neutro", "materiais"), ("papel alcalino", "materiais"), ("caixa arquivo", "materiais"),
    ("poliester", "materiais"), ("mylar", "materiais"), ("acondicion", "materiais"), ("conserva", "materiais"), ("papelaria", "materiais"),
    ("hospedagem", "tecnologia"), ("dominio", "tecnologia"), ("google", "tecnologia"), ("adobe", "tecnologia"), ("microsoft", "tecnologia"),
    ("software", "tecnologia"), ("aws", "tecnologia"), ("tarifa", "tarifas"), ("iof", "tarifas"), ("eletric", "manutencao"), ("encanad", "manutencao"),
    ("pintura", "manutencao"), ("manutenc", "manutencao"), ("darf", "impostos"), ("imposto", "impostos"), ("estagi", "pessoal"), ("bolsa", "pessoal"),
    ("buffet", "eventos"), ("cafe", "eventos"), ("evento", "eventos"),
]
RE_CNPJ = re.compile(r"\b(\d{2})\.?(\d{3})\.?(\d{3})/?(\d{4})-?(\d{2})\b")
AVISO_PROJECAO = "Estimativa simples, só com o que se repete (mensalidades, renovações, contas fixas e despesas recorrentes). Não é previsão garantida."


def _fin():
    from . import financeiro
    return financeiro


def _desp():
    from . import despesas
    return despesas


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "").lower()) if unicodedata.category(c) != "Mn")


def cnpj(texto: str) -> str:
    m = RE_CNPJ.search(str(texto or ""))
    return "".join(m.groups()) if m else ""


def normalizar(nome: str) -> str:
    """'KALUNGA COMÉRCIO E INDÚSTRIA GRÁFICA LTDA' → 'kalunga industria grafica' (sem acento, sem sufixo de empresa, sem pontuação)."""
    s = RE_CNPJ.sub(" ", sem_acento(nome))
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    ps = [p for p in s.split() if p not in SUFIXOS and not p.isdigit()]
    return " ".join(ps[:4])


def _chave(d: dict) -> str:
    return cnpj((d.get("contraparte") or "") + " " + (d.get("descricao") or "")) or normalizar(d.get("contraparte") or "")


def _nome(d: dict) -> str:
    return (d.get("contraparte") or d.get("descricao") or "").strip() or "sem nome"


def _reais(v) -> str:
    return _fin().brl(v)


# ---------------------------------------------------------------- categoria sugerida
def _historico(con, excluir: int | None = None) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT id, data, valor, contraparte, descricao, categoria, justificativa, conta_id, tipo FROM despesa "
                                         "WHERE apagado_em IS NULL AND tipo='despesa' AND id IS NOT ? ORDER BY data, id", (excluir,))]


def regras(con, tipo: str | None = None) -> list[dict]:
    sql, a = "SELECT * FROM financeiro_regra WHERE ativa=1", []
    if tipo:
        sql += " AND tipo=?"
        a.append(tipo)
    return [dict(r) for r in con.execute(sql + " ORDER BY id", a)]


def sugerir_categoria(con, d: dict, hist: list[dict] | None = None) -> dict | None:
    """{categoria, confianca, motivo, fonte, alta} ou None. Nada é gravado."""
    cats = _desp().categorias(con)
    ch, nm = _chave(d), _nome(d)
    for r in regras(con, "despesa"):
        if r["alvo"] in cats and ((r["campo"] == "cnpj" and r["padrao"] == cnpj((d.get("contraparte") or "") + " " + (d.get("descricao") or "")))
                                  or (r["campo"] == "contraparte" and r["padrao"] == normalizar(d.get("contraparte") or ""))
                                  or (r["campo"] == "palavra" and r["padrao"] in sem_acento((d.get("contraparte") or "") + " " + (d.get("descricao") or "")))):
            return {"categoria": r["alvo"], "nome": cats[r["alvo"]], "confianca": 0.97, "alta": True, "fonte": "regra", "regra_id": r["id"],
                    "motivo": f"regra da equipe: sempre classificar {r['padrao']} como {cats[r['alvo']]}"}
    hist = hist if hist is not None else _historico(con, d.get("id"))
    if ch:
        iguais = [h for h in hist if h["categoria"] and h["id"] != d.get("id") and _chave(h) == ch]
        if iguais:
            cont: dict[str, int] = {}
            for h in iguais:
                cont[h["categoria"]] = cont.get(h["categoria"], 0) + 1
            cat, n = max(cont.items(), key=lambda kv: kv[1])
            share = n / len(iguais)
            conf = 0.5 + 0.45 * share * min(n, 4) / 4
            ultimas = iguais[-n:]
            motivo = f"igual {'à última compra' if n == 1 else f'às {n} últimas compras'} em {nm}"
            if d.get("valor") and any(abs(h["valor"] - d["valor"]) <= max(0.05, 0.05 * d["valor"]) for h in ultimas):
                conf += 0.05
                motivo += ", com o mesmo valor"
            if cat in cats:
                conf = round(min(conf, 0.95), 2)
                return {"categoria": cat, "nome": cats[cat], "confianca": conf, "alta": conf >= 0.8, "fonte": "historico", "motivo": motivo}
    txt = sem_acento((d.get("contraparte") or "") + " " + (d.get("descricao") or "") + " " + (d.get("justificativa") or ""))
    for p, cat in PALAVRAS:
        if p in txt and cat in cats:
            return {"categoria": cat, "nome": cats[cat], "confianca": 0.6, "alta": False, "fonte": "palavra", "motivo": f"a descrição tem “{p}”"}
    return None


def sugerir_justificativa(con, d: dict, hist: list[dict] | None = None) -> list[dict]:
    """Textos prontos, com o motivo: despesas parecidas (mesma contraparte) e tarefas de doação com valor e data perto."""
    out = []
    hist = hist if hist is not None else _historico(con, d.get("id"))
    ch = _chave(d)
    vistos = set()
    for h in reversed(hist):
        if ch and h["justificativa"] and _chave(h) == ch and h["justificativa"] not in vistos:
            vistos.add(h["justificativa"])
            out.append({"texto": h["justificativa"], "categoria": h["categoria"] or "", "motivo": f"usada em {_nome(h)} em {_fin()._dbr(h['data'])}"})
        if len(out) >= 3:
            break
    try:
        dd = date.fromisoformat(d["data"])
    except (KeyError, TypeError, ValueError):
        return out
    v = float(d.get("valor") or 0)
    for t in con.execute("""SELECT t.id, t.titulo, t.valor, t.prazo, t.criado_em, t.site_id, a.autor, a.protocolo FROM doacao_tarefa t
                            JOIN doacao_acervo a ON a.site_id=t.site_id WHERE t.situacao != 'nao_se_aplica'"""):
        ref = t["prazo"] or (t["criado_em"] or "")[:10]
        try:
            dist = abs((date.fromisoformat(ref) - dd).days)
        except ValueError:
            continue
        perto_valor = t["valor"] and abs(t["valor"] - v) <= max(5.0, 0.1 * v)
        palavra = any(k in sem_acento(t["titulo"]) for k in ("frete", "embal", "transport", "caixa", "insumo")) and \
            any(k in sem_acento((d.get("contraparte") or "") + " " + (d.get("descricao") or "")) for k in ("frete", "transport", "correio", "embal", "papel"))
        if dist <= 30 and (perto_valor or palavra):
            autor = (t["autor"] or t["protocolo"] or "").strip()
            out.append({"texto": f"{t['titulo']} · doação {autor}".strip(), "categoria": "frete" if "frete" in sem_acento(t["titulo"]) else "",
                        "vinculo": {"tipo": "doacao", "ref": str(t["site_id"]), "tarefa_id": t["id"]},
                        "motivo": (f"valor perto da tarefa “{t['titulo']}” da doação {autor} ({_reais(t['valor'])})" if perto_valor
                                   else f"parece com a tarefa “{t['titulo']}” da doação {autor}") + f", {dist} dia(s) de distância"})
    return out


def regras_sugeridas(con) -> list[dict]:
    """Mesma escolha 3 vezes para a mesma contraparte (despesa) ou o mesmo pagador (receita direta) e ainda sem regra."""
    cats = _desp().categorias(con)
    nat = _fin().NATUREZAS
    ja = {(r["tipo"], r["campo"], r["padrao"]) for r in regras(con)}
    out = []
    grupos: dict[tuple, list] = {}
    for h in _historico(con):
        if h["categoria"] and normalizar(h["contraparte"] or ""):
            grupos.setdefault((normalizar(h["contraparte"]), h["categoria"]), []).append(h)
    for (pad, cat), hs in grupos.items():
        if len(hs) >= 3 and ("despesa", "contraparte", pad) not in ja and cat in cats:
            out.append({"tipo": "despesa", "campo": "contraparte", "padrao": pad, "alvo": cat, "alvo_nome": cats[cat], "n": len(hs),
                        "motivo": f"{len(hs)} vezes {_nome(hs[-1])} foi classificada como {cats[cat]}"})
    gr: dict[tuple, int] = {}
    for r in con.execute("SELECT pagador, classificar FROM mp_pagamento WHERE classificar IS NOT NULL AND pagador IS NOT NULL"):
        k = (normalizar(r["pagador"]), r["classificar"])
        if k[0]:
            gr[k] = gr.get(k, 0) + 1
    for (pad, n_), n in gr.items():
        if n >= 3 and ("receita", "contraparte", pad) not in ja and n_ in nat:
            out.append({"tipo": "receita", "campo": "contraparte", "padrao": pad, "alvo": n_, "alvo_nome": nat[n_], "n": n,
                        "motivo": f"{n} vezes {pad} foi classificado como {nat[n_]}"})
    return out


def natureza_por_regra(con, pagador: str) -> dict | None:
    pad = normalizar(pagador or "")
    for r in regras(con, "receita"):
        if r["campo"] == "contraparte" and r["padrao"] == pad and r["alvo"] in _fin().NATUREZAS:
            return {"natureza": r["alvo"], "motivo": f"regra da equipe: sempre classificar {pad} como {_fin().NATUREZAS[r['alvo']]}", "confianca": 0.97}
    return None


# ---------------------------------------------------------------- comprovante: casar e ler
def casar(con, valor: float, data: str, excluir: int | None = None) -> list[dict]:
    """Saídas com o mesmo valor (± R$ 0,05) e data perto (± 3 dias): o comprovante digitado é desta despesa?"""
    try:
        d0 = date.fromisoformat(data)
    except ValueError:
        raise HTTPException(400, "Data inválida (AAAA-MM-DD)")
    out = []
    for r in con.execute("SELECT id, data, valor, contraparte, descricao, origem FROM despesa WHERE apagado_em IS NULL AND tipo='despesa' AND abs(valor-?)<=0.05 AND id IS NOT ?",
                         (float(valor), excluir)):
        dist = abs((date.fromisoformat(r["data"]) - d0).days)
        if dist <= 3:
            out.append({"id": r["id"], "data": r["data"], "valor": r["valor"], "contraparte": r["contraparte"] or "", "origem": r["origem"], "dias": dist,
                        "motivo": f"mesmo valor ({_reais(r['valor'])}) e {('mesmo dia' if not dist else f'{dist} dia(s) de diferença')}"})
    return sorted(out, key=lambda x: (x["dias"], x["id"]))


LEITORES: dict[str, Callable[[bytes, str], dict]] = {}     # nome → função (bytes, mime) → {cnpj, emissor, data, total, itens}; os testes registram um falso


def leitura_ligada(con) -> bool:
    return _cfg(con, "financeiro.leitura_comprovante", "0") == "1"


def ler_comprovante(con, despesa_id: int, anexo_id: int) -> dict:
    if not leitura_ligada(con):
        raise HTTPException(409, "A leitura automática de comprovantes está desligada (Configurações → financeiro.leitura_comprovante). Nada foi enviado.")
    nome = _cfg(con, "financeiro.leitor", "")
    fn = LEITORES.get(nome)
    if not fn:
        raise HTTPException(409, "Nenhum leitor de comprovantes configurado no painel. É preciso um leitor (cliente de visão) e o nome dele em financeiro.leitor. Nada foi enviado.")
    r = con.execute("SELECT arquivo, mime FROM despesa_anexo WHERE id=? AND despesa_id=?", (anexo_id, despesa_id)).fetchone()
    if not r:
        raise HTTPException(404, "Comprovante não encontrado")
    f = (_desp().pasta() / r["arquivo"]).resolve()
    if _desp().pasta().resolve() not in f.parents or not f.is_file():
        raise HTTPException(404, "Arquivo do comprovante não encontrado")
    lido = fn(f.read_bytes(), r["mime"] or "") or {}
    out = {k: lido.get(k) for k in ("cnpj", "emissor", "data", "total", "itens")}
    out["casa_com"] = casar(con, float(out["total"]), str(out["data"])) if out.get("total") and out.get("data") else []
    return out


# ---------------------------------------------------------------- alertas e destaques
def _mais_um_mes(d: date) -> date:
    a, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    for dia in (d.day, 30, 29, 28):
        try:
            return date(a, m, dia)
        except ValueError:
            continue
    return date(a, m, 28)


def recorrentes(con, hist: list[dict] | None = None) -> list[dict]:
    """Mesma contraparte em 3 meses seguidos (ou mais) com valor parecido (± 15% da mediana) → assinatura mensal, com a próxima data."""
    hist = hist if hist is not None else _historico(con)
    g: dict[str, list] = {}
    for h in hist:
        k = _chave(h)
        if k:
            g.setdefault(k, []).append(h)
    out = []
    for k, hs in g.items():
        meses = sorted({h["data"][:7] for h in hs})
        if len(meses) < 3:
            continue
        md = statistics.median(h["valor"] for h in hs)
        parecidos = [h for h in hs if abs(h["valor"] - md) <= 0.15 * md]
        ms = sorted({h["data"][:7] for h in parecidos})
        seguidos, melhor = 1, 1
        for a, b in zip(ms, ms[1:]):
            ya, ma = int(a[:4]), int(a[5:7])
            seguidos = seguidos + 1 if (int(b[:4]) * 12 + int(b[5:7])) - (ya * 12 + ma) == 1 else 1
            melhor = max(melhor, seguidos)
        if melhor >= 3:
            ult = max(parecidos, key=lambda h: h["data"])
            prox = _mais_um_mes(date.fromisoformat(ult["data"]))
            out.append({"chave": k, "nome": _nome(ult), "valor": round(md, 2), "meses": melhor, "ultima": ult["data"], "proxima": prox.isoformat(),
                        "categoria": ult["categoria"] or "", "texto": f"assinatura mensal de ~{_reais(md)} em {_nome(ult)}",
                        "motivo": f"{melhor} meses seguidos com valor parecido; a próxima deve vir por volta de {_fin()._dbr(prox.isoformat())}"})
    return out


def alertas(con, de: str, ate: str) -> list[dict]:
    hist = _historico(con)
    no = [h for h in hist if de <= h["data"] <= ate]
    out: list[dict] = []
    # cobrança repetida: mesma contraparte e valor em até 3 dias
    for i, a in enumerate(no):
        for b in no[i + 1:]:
            if _chave(a) and _chave(a) == _chave(b) and abs(a["valor"] - b["valor"]) < 0.01 and abs((date.fromisoformat(b["data"]) - date.fromisoformat(a["data"])).days) <= 3:
                out.append({"tipo": "duplicada", "nivel": "a", "titulo": f"Possível cobrança repetida: {_nome(a)}, {_reais(a['valor'])}",
                            "motivo": f"o mesmo valor em {_fin()._dbr(a['data'])} e {_fin()._dbr(b['data'])}", "ids": [a["id"], b["id"]]})
    # fora do usual: > 2× a mediana da contraparte (com 3 anteriores ou mais) e pelo menos R$ 50 acima
    for h in no:
        ant = [x for x in hist if _chave(x) and _chave(x) == _chave(h) and x["data"] < h["data"]]
        if len(ant) >= 3:
            md = statistics.median(x["valor"] for x in ant)
            if h["valor"] > 2 * md and h["valor"] - md >= 50:
                out.append({"tipo": "fora_do_usual", "nivel": "a", "titulo": f"Valor acima do usual: {_nome(h)}, {_reais(h['valor'])}",
                            "motivo": f"o normal nessa contraparte é ~{_reais(md)} (mediana de {len(ant)} anteriores)", "ids": [h["id"]]})
    for r in recorrentes(con, hist):
        out.append({"tipo": "recorrente", "nivel": "b", "titulo": r["texto"][:1].upper() + r["texto"][1:], "motivo": r["motivo"], "proxima": r["proxima"], "valor": r["valor"]})
    try:
        n_dias = int(_cfg(con, "financeiro.alerta_sem_comprovante_dias", "15"))
    except ValueError:
        n_dias = 15
    lim = (_fin().hoje() - timedelta(days=n_dias)).isoformat()
    velhas = [x for x in _desp().listar(con, "2000-01-01", lim) if "comprovante" in x["falta"]]
    if velhas:
        out.append({"tipo": "sem_comprovante", "nivel": "b", "titulo": f"{len(velhas)} {'despesa' if len(velhas) == 1 else 'despesas'} sem comprovante há mais de {n_dias} dias",
                    "motivo": f"a mais antiga é de {_fin()._dbr(min(x['data'] for x in velhas))}", "ids": [x["id"] for x in velhas]})
    # doadores
    todas = [x for x in _fin().livro(con, "2000-01-01", ate)["linhas"] if x["natureza"] in ("doacoes", "doacoes_restricao") and not x["estorno"]]
    per = [x for x in todas if x["data"] >= de]
    if per:
        maior = max(per, key=lambda x: x["bruto"])
        out.append({"tipo": "maior_doacao", "nivel": "b", "titulo": f"Maior doação do período: {_reais(maior['bruto'])}", "motivo": f"{maior['pagador'] or maior['origem_nome']}, em {_fin()._dbr(maior['data'])}"})
        antes = {normalizar(x["pagador"]) for x in todas if x["data"] < de and normalizar(x["pagador"])}
        novos = sorted({x["pagador"] for x in per if normalizar(x["pagador"]) and normalizar(x["pagador"]) not in antes})
        if novos:
            out.append({"tipo": "doadores_novos", "nivel": "b", "titulo": f"{len(novos)} {'pessoa doou' if len(novos) == 1 else 'pessoas doaram'} pela primeira vez", "motivo": ", ".join(novos[:5])})
        meses_por: dict[str, set] = {}
        for x in todas:
            if normalizar(x["pagador"]):
                meses_por.setdefault(normalizar(x["pagador"]), set()).add(x["data"][:7])
        rec = sorted({x["pagador"] for x in per if len(meses_por.get(normalizar(x["pagador"]), ())) >= 3})
        if rec:
            out.append({"tipo": "doadores_recorrentes", "nivel": "b", "titulo": f"{len(rec)} {'doador recorrente' if len(rec) == 1 else 'doadores recorrentes'}", "motivo": "doaram em 3 meses ou mais: " + ", ".join(rec[:5])})
    out += orcamento_projetos(con, ate)
    return out


def orcamento_projetos(con, ate: str) -> list[dict]:
    """Gancho do orçamento da conta de projeto (Rouanet): {conta_id: {rubrica: valor}} em financeiro.orcamento_projetos. Sem orçamento: nada."""
    try:
        orc = json.loads(_cfg(con, "financeiro.orcamento_projetos", "{}")) or {}
    except ValueError:
        orc = {}
    out = []
    try:                         # CAMP-ROUANET: orçamento do projeto por item (90% âmbar, acima do orçado vermelho, total usado)
        from . import rouanet
        out += rouanet.alertas(con)
    except ImportError:
        pass
    for cid, itens in (orc.items() if isinstance(orc, dict) else []):
        try:
            cid_i = int(cid)
        except ValueError:
            continue
        gasto: dict[str, float] = {}
        for x in _desp().listar(con, "2000-01-01", ate, cid_i):
            k = x["projeto"] or x["categoria"] or ""
            gasto[k] = gasto.get(k, 0.0) + x["valor"]
        for rub, teto in (itens or {}).items():
            g = sum(v for k, v in gasto.items() if k == rub or k.endswith(rub))
            if teto and g >= 0.9 * float(teto):
                out.append({"tipo": "orcamento", "nivel": "a" if g > float(teto) else "b",
                            "titulo": f"{'Acima' if g > float(teto) else 'Perto'} do orçamento: {rub} ({_reais(g)} de {_reais(teto)})", "motivo": f"conta {cid_i}"})
    return out


# ---------------------------------------------------------------- projeção (estimativa)
def projecao(con, ate: str, meses: int = 3) -> dict:
    fim = date.fromisoformat(ate)
    base = date(fim.year, fim.month, 1)
    futuros = []
    d = base
    for _ in range(meses):
        d = _mais_um_mes(d).replace(day=1)
        futuros.append(d.strftime("%Y-%m"))
    out = {m: {"mes": m, "receitas": 0.0, "despesas": 0.0, "explica": []} for m in futuros}
    mens = con.execute("SELECT COUNT(*), COALESCE(SUM(COALESCE(ultimo_valor, valor_cobrado, 0)),0) FROM amigo WHERE tipo='amigo' AND modalidade='mensal' AND situacao='pago' "
                       "AND inativo_em IS NULL AND apagado_em IS NULL").fetchone()
    for m in futuros:
        if mens[0]:
            out[m]["receitas"] += mens[1]
            out[m]["explica"].append(f"{mens[0]} Amigo(s) com mensalidade: {_reais(mens[1])}")
    for r in con.execute("SELECT validade, COALESCE(ultimo_valor, valor_cobrado, 0) v FROM amigo WHERE tipo='amigo' AND modalidade!='mensal' AND situacao='pago' "
                         "AND inativo_em IS NULL AND apagado_em IS NULL AND validade IS NOT NULL"):
        m = (r["validade"] or "")[:7]
        if m in out and r["v"]:
            out[m]["receitas"] += r["v"]
            out[m]["explica"].append(f"renovação anual que vence: {_reais(r['v'])}")
    for r in con.execute("SELECT valor_anual, meses_pagos FROM patrocinio WHERE modalidade='mensal' AND etapa NOT IN ('cancelada','encerrada') AND meses_pagos BETWEEN 1 AND 11"):
        falta = 12 - (r["meses_pagos"] or 0)
        for i, m in enumerate(futuros):
            if i < falta and r["valor_anual"]:
                out[m]["receitas"] += r["valor_anual"] / 12
                out[m]["explica"].append(f"patrocínio em 12 meses: {_reais(r['valor_anual'] / 12)}")
    from . import contas_fixas as cfx   # CAMP-FIN contas fixas: o que está combinado vale mais que o que só se repetiu
    todas_cf = cfx.contas(con, com_inativas=False)
    for m in futuros:
        v, ex, _ = cfx.previsao(con, m)
        out[m]["despesas"] += v
        out[m]["explica"] += ex
    for r in recorrentes(con):
        if any(cfx._cobre(cf, r) for cf in todas_cf):
            continue
        for m in futuros:
            out[m]["despesas"] += r["valor"]
            out[m]["explica"].append(f"despesa recorrente ({r['nome']}): {_reais(r['valor'])}")
    lst = []
    for m in futuros:
        x = out[m]
        x["receitas"], x["despesas"] = round(x["receitas"], 2), round(x["despesas"], 2)
        x["resultado"] = round(x["receitas"] - x["despesas"], 2)
        lst.append(x)
    return {"meses": lst, "aviso": AVISO_PROJECAO}


# ---------------------------------------------------------------- busca natural
def interpretar(q: str, categorias: dict[str, str] | None = None) -> dict:
    """'frete outubro' → {categoria: frete, mes: 10}; 'doações acima de 500' → {natureza: doacoes, valor_min: 500}; 'sem nota'; 'Kalunga 2026'."""
    s = " " + sem_acento(q).strip() + " "
    out: dict = {"texto": "", "chips": []}
    cats = categorias or {}

    def tira(padrao: str) -> re.Match | None:
        nonlocal s
        m = re.search(padrao, s)
        if m:
            s = s[:m.start()] + " " + s[m.end():]
        return m

    num = r"(?:r\$\s*)?(\d+(?:[.,]\d+)?)"
    for pad, campo, rot in ((rf"\b(?:acima de|maior que|mais de|a partir de)\s+{num}", "valor_min", "acima de"), (rf">\s*{num}", "valor_min", "acima de"),
                            (rf"\b(?:abaixo de|menor que|menos de|ate)\s+{num}", "valor_max", "abaixo de"), (rf"<\s*{num}", "valor_max", "abaixo de")):
        m = tira(pad)
        if m:
            v = float(m.group(1).replace(".", "").replace(",", ".") if "," in m.group(1) else m.group(1))
            out[campo] = v
            out["chips"].append({"campo": campo, "rotulo": f"{rot} {_reais(v)}"})
    if tira(r"\bsem (?:nota|comprovante|recibo)\b"):
        out["sem_nota"] = True
        out["chips"].append({"campo": "sem_nota", "rotulo": "sem comprovante"})
    if tira(r"\bsem categoria\b"):
        out["sem_categoria"] = True
        out["chips"].append({"campo": "sem_categoria", "rotulo": "sem categoria"})
    m = tira(r"\b(20\d\d)\b")
    if m:
        out["ano"] = int(m.group(1))
        out["chips"].append({"campo": "ano", "rotulo": m.group(1)})
    for i, nome in enumerate(MESES):
        m = tira(rf"\b(?:{nome}|{nome[:3]})\b")
        if m:
            out["mes"] = i + 1
            out["chips"].append({"campo": "mes", "rotulo": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"][i]})
            break
    for pad, nat, rot in ((r"\bdoac(?:ao|oes)\b", "doacoes", "Doações"), (r"\bpatrocinios?\b", "patrocinios", "Patrocínios"), (r"\bingressos?\b", "servicos", "Ingressos e serviços"),
                          (r"\bamigos?\b", "contribuicoes", "Contribuições (Amigos)")):
        if tira(pad):
            out["natureza"] = nat
            out["chips"].append({"campo": "natureza", "rotulo": rot})
            break
    sinon = {"frete": "frete", "fretes": "frete", "material": "materiais", "materiais": "materiais", "tecnologia": "tecnologia", "software": "tecnologia",
             "pessoal": "pessoal", "estagio": "pessoal", "tarifa": "tarifas", "tarifas": "tarifas", "eventos": "eventos", "evento": "eventos",
             "manutencao": "manutencao", "impostos": "impostos", "imposto": "impostos", "servicos": "servicos",
             "aluguel": "aluguel", "condominio": "aluguel", "salario": "salarios", "salarios": "salarios", "inss": "encargos", "fgts": "encargos",
             "encargos": "encargos", "internet": "consumo", "luz": "consumo", "agua": "consumo", "bolsas": "bolsas", "rpa": "autonomos"}
    for k, nome in cats.items():
        sinon.setdefault(sem_acento(nome).split()[0], k)
    for pal, cat in sinon.items():
        if cat in cats and tira(rf"\b{pal}\b"):
            out["categoria"] = cat
            out["chips"].append({"campo": "categoria", "rotulo": cats[cat]})
            break
    out["texto"] = re.sub(r"\s+", " ", s).strip()
    if out["texto"]:
        out["chips"].append({"campo": "texto", "rotulo": f"“{out['texto']}”"})
    return out


# ---------------------------------------------------------------- rotas (só admin e master)
@router.get("/despesa/{did}")
def ver_sugestoes(did: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT * FROM despesa WHERE id=? AND apagado_em IS NULL", (did,)).fetchone()
        if not r:
            raise HTTPException(404, "Despesa não encontrada")
        d = dict(r)
        hist = _historico(con, did)
        from . import contas_fixas as cfx
        from . import rouanet
        return {"categoria": sugerir_categoria(con, d, hist), "justificativas": sugerir_justificativa(con, d, hist), "conta_fixa": cfx.sugestao_para(con, d),
                "item": rouanet.sugerir_item(con, d),
                "leitura_ligada": leitura_ligada(con), "leitor": bool(LEITORES.get(_cfg(con, "financeiro.leitor", "")))}
    finally:
        con.close()


@router.get("/regras")
def ver_regras(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return {"regras": regras(con), "sugeridas": regras_sugeridas(con)}
    finally:
        con.close()


class Regra(BaseModel):
    tipo: str
    padrao: str
    alvo: str
    campo: str = "contraparte"


@router.post("/regras")
def criar_regra(b: Regra, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        if b.tipo not in ("despesa", "receita") or b.campo not in ("contraparte", "cnpj", "palavra"):
            raise HTTPException(400, "Regra inválida")
        if (b.tipo == "despesa" and b.alvo not in _desp().categorias(con)) or (b.tipo == "receita" and b.alvo not in _fin().NATUREZAS):
            raise HTTPException(400, "Categoria ou natureza desconhecida")
        pad = normalizar(b.padrao) if b.campo == "contraparte" else (re.sub(r"\D", "", b.padrao) if b.campo == "cnpj" else sem_acento(b.padrao).strip())
        if not pad:
            raise HTTPException(400, "Diga o nome ou a palavra da regra")
        con.execute("INSERT INTO financeiro_regra (tipo, campo, padrao, alvo, criado_por) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(tipo, campo, padrao) DO UPDATE SET alvo=excluded.alvo, ativa=1", (b.tipo, b.campo, pad, b.alvo, u.get("email") or "painel"))
        rid = con.execute("SELECT id FROM financeiro_regra WHERE tipo=? AND campo=? AND padrao=?", (b.tipo, b.campo, pad)).fetchone()[0]
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('financeiro_regra',?,'criada',?,?)",
                    (str(rid), u.get("email") or "painel", json.dumps({"tipo": b.tipo, "campo": b.campo, "padrao": pad, "alvo": b.alvo}, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "id": rid, "padrao": pad}
    finally:
        con.close()


@router.delete("/regras/{rid}")
def apagar_regra(rid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        r = con.execute("SELECT * FROM financeiro_regra WHERE id=?", (rid,)).fetchone()
        if not r:
            raise HTTPException(404, "Regra não encontrada")
        con.execute("UPDATE financeiro_regra SET ativa=0 WHERE id=?", (rid,))
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('financeiro_regra',?,'desligada',?,?)",
                    (str(rid), u.get("email") or "painel", json.dumps({"padrao": r["padrao"], "alvo": r["alvo"]}, ensure_ascii=False)))
        con.commit()
        return {"ok": True}
    finally:
        con.close()


@router.get("/casar")
def casar_rota(valor: float, data: str, excluir: int | None = None, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return {"candidatos": casar(con, valor, data, excluir)}
    finally:
        con.close()


@router.post("/despesa/{did}/comprovante/{aid}/ler")
def ler(did: int, aid: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return ler_comprovante(con, did, aid)
    finally:
        con.close()


@router.get("/busca")
def busca(q: str = "", u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        return interpretar(q, _desp().categorias(con))
    finally:
        con.close()


@router.get("/painel")
def painel_ia(de: str = "", ate: str = "", mes: str = "", ano: str = "", tri: str = "", u: dict = Depends(auth.exige("admin"))) -> dict:
    d1, d2 = _fin().periodo(de, ate, mes, ano, tri)
    con = connect()
    try:
        return {"alertas": alertas(con, d1, d2), "projecao": projecao(con, d2), "regras_sugeridas": regras_sugeridas(con), "recorrentes": recorrentes(con),
                "regras": regras(con), "leitura_ligada": leitura_ligada(con)}
    finally:
        con.close()
