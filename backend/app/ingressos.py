"""Ingressos da visita guiada à Residência João Marino (CAMP-INGRESSOS, 19/11/2026). Rafael: "Não esquece de preparar nosso painel adm".

A venda acontece no site (plugin 1.28.0+: compra, Mercado Pago, desconto de Amigo, QR code e entrada pela equipe). O painel é o lugar de
acompanhar e fazer as contas:
- Busca (contrato 1.18, docs/CONTRATO_UNICO.md §6): GET /wp-json/camp/v1/painel/ingressos?desde=…&todas=1 (só leitura, incremental) →
  `ingresso` (chave site_id) e as turmas com vagas em `ingresso_turma`. Site sem a rota (404): silêncio e aviso na tela. Roda no coletor,
  a cada `ingressos.coleta_min` (padrão 10; 0 desliga), e em "Sincronizar agora".
- Tela Ingressos (só admin e master: nome, e-mail e telefone): turmas do mês com vagas, pessoas, entradas e valores; lista por turma
  (serve de lista da porta); filtro por mês e situação; planilha CSV para o Excel; reenviar o ingresso (POST …/{id}/reenviar no site).
- A referência é a mesma do Mercado Pago (CAMP-INGRESSO-JM-AAAAMMDD-HHMM-n): no relatório de lá, a busca por
  CAMP-INGRESSO-JM-AAAAMM acha o mês.
- LGPD: apagar pessoa anonimiza (os valores ficam para a receita). Nada de nome ou e-mail no log técnico.
- Detalhe (20/11/2026, Rafael: "saber quem pagou meia, quem é Amigo etc. E abrir a data para listar as pessoas, e se precisar reenviar
  o ingresso ou a cobrança"; contrato 1.21 `meias` e 1.22 `tipos`/`link_pagamento`/`historico`, tudo OPCIONAL): tipo de cada ingresso
  (inteira, meia-entrada, Amigo com desconto, gratuidade), Amigo da CAMP pelo e-mail (cadastro de Amigos do painel, adesão em dia),
  datas com contas por tipo e situação, lista de presença de cada data/turma (filtros, impressão, CSV), "Reenviar ingresso" (TR23) e
  "Reenviar cobrança" (TR29, link novo do Mercado Pago se o antigo venceu) SÓ pelo Sender, um a um ou em lote; tudo no histórico
  (tabela evento, entidade 'ingresso'). Site antigo: os tipos saem de pessoas/meias/desconto; a cobrança diz "atualize o site".
- Um ingresso por pessoa (20/11/2026, Rafael: "Nome e e-mail para enviar o ingresso dessa pessoa. E envia todos os ingressos separados para
  quem comprou também"; contrato 1.24 `ingressos`, OPCIONAL, site 1.33.0, migração 234 `ingresso_pessoa`): a lista de presença tem uma linha
  POR PESSOA (nome, e-mail, tipo, motivo da meia, código do ingresso, pedido/comprador, pago, Amigo); compra antiga = uma linha "comprador + N".
  "Reenviar ingresso (a esta pessoa)" e "Reenviar todos ao comprador" (um e-mail por ingresso), SÓ pelo Sender (TR23). LGPD cobre as pessoas.
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

router = APIRouter(prefix="/api/ingressos", tags=["ingressos"])

FUSO = ZoneInfo("America/Sao_Paulo")
ROTA = "/wp-json/camp/v1/painel/ingressos"
REMOVIDO = "(removido)"
SITUACOES = {"pago": "Pago", "gratuito": "Gratuito (Amigo)", "reservado": "Aguardando pagamento", "processando": "Pagamento em análise",
             "recusado": "Recusado", "cancelado": "Cancelado"}
VALEM = ("pago", "gratuito")          # contam nas vagas, nas pessoas e na receita
CATEGORIAS = {"estudante": "Estudante / Professor", "amigo": "Amigo", "guardiao": "Guardião", "patrono": "Patrono"}
VERSAO_SITE = "1.31.0"                # plugin do site com o contrato 1.22 (cobrança e reenvio só pelo Sender)
MOTIVOS = {"estudante": "Estudante", "professor": "Professor(a)", "idoso": "Pessoa com 60 anos ou mais", "pcd": "Pessoa com deficiência (ou acompanhante)",
           "id_jovem": "Jovem de baixa renda (ID Jovem)", "outro": "Outro direito previsto em lei"}
TIPOS = {"inteira": "Inteira", "meia": "Meia-entrada", "amigo": "Amigo da CAMP (desconto)", "gratuidade": "Gratuidade (Amigo da CAMP)"}
PENDENTES = ("reservado", "processando")
COBRAVEIS = ("reservado", "recusado", "cancelado")     # dá para reenviar a cobrança (o site confere vagas e abre link novo se venceu)
TPL_INGRESSO = ("TR23", "Ingresso da visita")
TPL_COBRANCA = ("TR29", "Cobrança do ingresso")
ONDE_TEMPLATE = "na administração do site, Apoios → Mercado Pago → E-mails pelo Sender (avise quem cuida do site)"
MEIOS = {"credit_card": "Cartão de crédito", "debit_card": "Cartão de débito", "bank_transfer": "Pix", "pix": "Pix", "account_money": "Saldo do Mercado Pago", "ticket": "Boleto"}


# ---------------------------------------------------------------- utilidades
def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _estado(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM ingresso_estado WHERE chave=?", (chave,)).fetchone()
    return (r[0] if r and r[0] is not None else "") or padrao


def _estado_set(con, chave: str, valor: str) -> None:
    con.execute("INSERT INTO ingresso_estado (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, valor))


def coleta_min(con) -> int:
    try:
        return max(0, int(_cfg(con, "ingressos.coleta_min", "10")))
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


def _num(v, padrao=0.0) -> float:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return padrao


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _wp():
    """Cliente do site (os testes trocam por um falso)."""
    return __import__("app.wp", fromlist=["WP"]).WP()


def _tem_site(con) -> bool:
    return bool(_cfg(con, "wp.app_password", settings.WP_APP_PASSWORD))


# ---------------------------------------------------------------- busca no site (site → painel)
def _gravar(con, x: dict) -> int:
    """Grava/atualiza um ingresso vindo do site. Devolve 1 se era novo. Linha anonimizada aqui não recebe os dados pessoais de volta."""
    sid = _int(x.get("id"))
    if sid <= 0:
        return 0
    data = _txt(x.get("data"), 10)
    hora = _txt(x.get("hora"), 5)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data) or not re.fullmatch(r"\d{2}:\d{2}", hora):
        return 0
    dc = x.get("desconto") if isinstance(x.get("desconto"), dict) else None
    pg = [p for p in (x.get("pagamentos") or []) if isinstance(p, dict)]
    sit = str(x.get("situacao") or "")
    vals = {
        "ref": _txt(x.get("ref"), 80), "casa": _txt(x.get("casa"), 8), "visita": _txt(x.get("visita"), 120), "data": data, "hora": hora,
        "nome": _txt(x.get("nome"), 200) or None, "email": _txt(x.get("email"), 200).lower() or None, "telefone": _txt(x.get("telefone"), 40) or None,
        "pessoas": _int(x.get("pessoas")), "entraram": _int(x.get("entraram")), "preco": _num(x.get("preco")), "total": _num(x.get("total")),
        "situacao": sit if sit in SITUACOES else "reservado", "amigo_site_id": _int(x.get("amigo_id")) or None,
        "desconto": json.dumps(dc, ensure_ascii=False) if dc else None, "pagamentos": json.dumps(pg, ensure_ascii=False) if pg else None,
        "codigo": _txt(x.get("codigo"), 12), "link": _txt(x.get("link"), 300), "modo": _txt(x.get("modo"), 10),
        "criado_em": _utc(x.get("criado_em")) or None, "confirmado_em": _utc(x.get("confirmado_em")) or None, "alterado_em": _utc(x.get("alterado_em")) or None,
    }
    # contrato 1.21/1.22 (OPCIONAL): só grava o que o site mandou (site antigo não apaga o que já havia)
    if "meias" in x:
        vals["meias"] = max(0, _int(x.get("meias")))
    if isinstance(x.get("tipos"), list):
        tp = [{"tipo": _txt(t.get("tipo"), 20), "nome": _txt(t.get("nome"), 80), "qtd": max(0, _int(t.get("qtd"))), "valor": _num(t.get("valor")),
               **({"pct": _int(t.get("pct"))} if t.get("pct") is not None else {}), **({"categoria": _txt(t.get("categoria"), 20)} if t.get("categoria") else {})}
              for t in x["tipos"] if isinstance(t, dict) and _txt(t.get("tipo"), 20)]
        vals["tipos"] = json.dumps(tp, ensure_ascii=False)
    if "link_pagamento" in x:
        lp = _txt(x.get("link_pagamento"), 400)
        vals["link_pagamento"] = lp if re.match(r"^https://(www\.|sandbox\.)?mercadopago\.com(\.br)?/", lp) else None
        vals["link_pagamento_ate"] = _utc(x.get("link_pagamento_ate")) or None
    if isinstance(x.get("historico"), list):
        vals["historico"] = json.dumps([_txt(h, 300) for h in x["historico"][-40:]], ensure_ascii=False)
    if isinstance(x.get("aviso_equipe"), list):                # avisos à equipe por wp_mail (o destinatário é a equipe, não o comprador)
        vals["aviso_equipe"] = json.dumps([{"quando": _utc(a.get("quando")), "momento": _txt(a.get("momento"), 20), "para": _txt(a.get("para"), 200),
                                            "ok": bool(a.get("ok")), "erro": _txt(a.get("erro"), 300)} for a in x["aviso_equipe"][-20:] if isinstance(a, dict)], ensure_ascii=False)
    velho = con.execute("SELECT anonimizado FROM ingresso WHERE site_id=?", (sid,)).fetchone()
    if velho and velho["anonimizado"]:
        vals.update(nome=REMOVIDO, email=None, telefone=None)
    cols = list(vals)
    if isinstance(x.get("ingressos"), list):                   # contrato 1.24 (OPCIONAL): um ingresso por pessoa
        _gravar_pessoas(con, sid, x["ingressos"])
    if velho:
        con.execute(f"UPDATE ingresso SET {', '.join(c + '=?' for c in cols)}, visto_em=datetime('now') WHERE site_id=?", (*vals.values(), sid))
        return 0
    con.execute(f"INSERT INTO ingresso (site_id, {', '.join(cols)}) VALUES (?, {', '.join('?' * len(cols))})", (sid, *vals.values()))
    return 1


def _gravar_pessoas(con, sid: int, lista_: list) -> None:
    """Troca as pessoas da compra pelas do site. Pessoa anonimizada aqui (LGPD) não recebe nome nem e-mail de volta."""
    try:
        anon = {r[0] for r in con.execute("SELECT n FROM ingresso_pessoa WHERE site_id=? AND anonimizado=1", (sid,))}
    except Exception:  # noqa: BLE001  (banco sem a migração 234)
        return
    con.execute("DELETE FROM ingresso_pessoa WHERE site_id=?", (sid,))
    for p in lista_:
        if not isinstance(p, dict) or _int(p.get("n")) <= 0:
            continue
        n = _int(p.get("n"))
        tipo = str(p.get("tipo") or "")
        mot = str(p.get("motivo") or "")
        envs = [{"em": _utc(e.get("em")), "para": _txt(e.get("para"), 12), "via": _txt(e.get("via"), 12)} for e in (p.get("envios") or [])[-10:] if isinstance(e, dict)]
        an = n in anon
        con.execute("INSERT OR REPLACE INTO ingresso_pessoa (site_id, n, nome, email, tipo, motivo, codigo, link, entrou, entrou_em, eh_comprador, envios, anonimizado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (sid, n, REMOVIDO if an else (_txt(p.get("nome"), 200) or None), None if an else (_txt(p.get("email"), 200).lower() or None),
                     tipo if tipo in TIPOS else "inteira", mot if tipo == "meia" and mot in MOTIVOS else None, _txt(p.get("codigo"), 12),
                     _txt(p.get("link"), 300), 1 if p.get("entrou") else 0, _utc(p.get("entrou_em")) or None, 1 if p.get("eh_comprador") else 0,
                     json.dumps(envs, ensure_ascii=False) if envs else None, 1 if an else 0))


def pessoas_das_compras(con, sids) -> dict:
    """{site_id: [pessoa…]} (contrato 1.24). Banco sem a migração 234 ou compra antiga: sem chave."""
    ids = sorted({int(i) for i in sids})
    out: dict = {}
    if not ids:
        return out
    try:
        for i in range(0, len(ids), 400):
            parte = ids[i:i + 400]
            for r in con.execute(f"SELECT * FROM ingresso_pessoa WHERE site_id IN ({','.join('?' * len(parte))}) ORDER BY site_id, n", parte):
                out.setdefault(r["site_id"], []).append({"n": r["n"], "nome": r["nome"] or "", "email": r["email"] or "", "tipo": r["tipo"], "tipo_nome": TIPOS.get(r["tipo"], r["tipo"]),
                                                         "motivo": r["motivo"] or "", "motivo_nome": MOTIVOS.get(r["motivo"] or "", ""), "codigo": r["codigo"] or "", "link": r["link"] or "",
                                                         "entrou": bool(r["entrou"]), "eh_comprador": bool(r["eh_comprador"]), "anonimizado": bool(r["anonimizado"]),
                                                         "envios": json.loads(r["envios"]) if r["envios"] else []})
    except Exception:  # noqa: BLE001
        return {}
    return out


def coletar(con=None, wp=None) -> dict:
    """Uma volta da busca no site. Incremental (desde = agora da volta anterior − 2 min). Nunca levanta."""
    fechar = con is None
    con = con or connect()
    out = {"lidos": 0, "novos": 0, "sem_rota": False, "erro": None}
    try:
        wp = wp or _wp()
        params = {"todas": 1}
        desde = _estado(con, "desde")
        if desde:
            params["desde"] = desde
        r = wp.h.get(ROTA, params=params)
        if r.status_code == 404:
            out["sem_rota"] = True                   # site sem o contrato 1.18
            _estado_set(con, "sem_rota", "1")
            con.commit()
            return out
        if r.status_code >= 400:
            raise RuntimeError(f"O site respondeu {r.status_code} ao buscar os ingressos")
        d = r.json()
        if not isinstance(d, dict):
            raise RuntimeError("O site devolveu formato inválido para os ingressos")
        for x in d.get("itens") or []:
            if isinstance(x, dict):
                out["lidos"] += 1
                out["novos"] += _gravar(con, x)
        if isinstance(d.get("turmas"), list):        # as turmas vêm inteiras a cada busca: troca a cópia
            con.execute("DELETE FROM ingresso_turma")
            for t in d["turmas"]:
                if isinstance(t, dict) and re.fullmatch(r"\d{4}-\d{2}-\d{2}\|\d{2}:\d{2}", str(t.get("chave") or "")):
                    con.execute("INSERT OR REPLACE INTO ingresso_turma (chave, data, hora, vagas, ocupadas, livres) VALUES (?,?,?,?,?,?)",
                                (t["chave"], _txt(t.get("data"), 10), _txt(t.get("hora"), 5), _int(t.get("vagas")), _int(t.get("ocupadas")), _int(t.get("livres"))))
        if isinstance(d.get("config"), dict):
            _estado_set(con, "config", json.dumps(d["config"], ensure_ascii=False))
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
        registrar(logging.WARNING, "ingressos_coleta", "Busca dos ingressos no site com problema", erro=out["erro"][:160])
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
    """A volta automática (ingressos.coleta_min; 0 desliga). Sem a senha do site: nada. Nunca levanta."""
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
        registrar(logging.WARNING, "ingressos_rodada", "Rodada dos ingressos com problema", erro=type(e).__name__)
        return {"erro": type(e).__name__}
    finally:
        con.close()


# ---------------------------------------------------------------- contas
def _cols(r) -> set:
    try:
        return set(r.keys())
    except AttributeError:
        return set()


def tipos_da_compra(r) -> list[dict]:
    """Ingressos da compra por tipo. Usa `tipos` do site (contrato 1.22); site antigo: calcula com pessoas, meias (1.21) e desconto.
    Desconto de Amigo vale nas inteiras (não soma com a meia); 100% = gratuidade (Patrono)."""
    ks = _cols(r)
    if "tipos" in ks and r["tipos"]:
        try:
            tp = [t for t in json.loads(r["tipos"]) if isinstance(t, dict) and _int(t.get("qtd")) > 0]
            return [dict(t, nome=TIPOS.get(t.get("tipo"), t.get("nome") or t.get("tipo"))) if t.get("tipo") in ("inteira", "meia", "gratuidade") else t for t in tp]
        except (ValueError, TypeError):
            pass
    dc = json.loads(r["desconto"]) if r["desconto"] else None
    pessoas = _int(r["pessoas"])
    meias = min(pessoas, _int(r["meias"]) if "meias" in ks else 0)
    pct = _int((dc or {}).get("pct"))
    dq = min(max(0, pessoas - meias), _int((dc or {}).get("qtd"))) if dc and pct > 0 else 0
    preco = float(r["preco"] or 0)
    out = [{"tipo": "inteira", "nome": TIPOS["inteira"], "qtd": pessoas - meias - dq, "valor": round(preco, 2)},
           {"tipo": "meia", "nome": TIPOS["meia"], "qtd": meias, "valor": round(preco / 2, 2)}]
    if dq:
        cat = str((dc or {}).get("categoria") or "")
        out.append({"tipo": "gratuidade", "nome": TIPOS["gratuidade"], "qtd": dq, "valor": 0.0, "pct": 100, "categoria": cat} if pct >= 100 else
                   {"tipo": "amigo", "nome": f"Amigo da CAMP ({pct}% de desconto)", "qtd": dq, "valor": _num((dc or {}).get("valor")), "pct": pct, "categoria": cat})
    return [t for t in out if t["qtd"] > 0]


def _tipos_txt(tp: list[dict]) -> str:
    """"2 inteiras · 1 meia-entrada · 1 Amigo (20%)"."""
    nomes = {"inteira": ("inteira", "inteiras"), "meia": ("meia-entrada", "meias-entradas"), "gratuidade": ("gratuidade", "gratuidades")}
    partes = []
    for t in tp:
        q = _int(t.get("qtd"))
        if t.get("tipo") == "amigo":
            partes.append(f"{q} Amigo ({_int(t.get('pct'))}%)")
        else:
            n = nomes.get(t.get("tipo"))
            partes.append(f"{q} {n[0] if q == 1 else n[1]}" if n else f"{q} {t.get('nome') or t.get('tipo')}")
    return " · ".join(partes)


def amigos_por_email(con, emails) -> dict:
    """Cadastro de Amigos da CAMP do painel (tabela amigo) pelo e-mail: {email: {id, categoria, categoria_nome, situacao, validade, ativo}}.
    Ativo = adesão paga e dentro da validade, ou isenta. Banco sem a migração 226: {}."""
    ems = sorted({(e or "").strip().lower() for e in emails if e})
    if not ems:
        return {}
    hoje_ = datetime.now(FUSO).strftime("%Y-%m-%d")
    out: dict = {}
    try:
        for i in range(0, len(ems), 400):
            parte = ems[i:i + 400]
            for a in con.execute(f"SELECT id, lower(email) AS em, categoria, situacao, validade FROM amigo WHERE tipo='amigo' AND anonimizado=0 AND lower(email) IN ({','.join('?' * len(parte))}) ORDER BY id", parte):
                ativo = a["situacao"] == "isento" or (a["situacao"] == "pago" and (not a["validade"] or a["validade"] >= hoje_))
                ja = out.get(a["em"])
                if ja and ja["ativo"] and not ativo:
                    continue
                out[a["em"]] = {"id": a["id"], "categoria": a["categoria"] or "", "categoria_nome": CATEGORIAS.get(a["categoria"] or "", a["categoria"] or ""),
                                "situacao": a["situacao"] or "", "validade": a["validade"] or "", "ativo": bool(ativo)}
    except Exception:  # noqa: BLE001  (banco sem a tabela de Amigos)
        return {}
    return out


def _linha(r, amigos: dict | None = None) -> dict:
    dc = json.loads(r["desconto"]) if r["desconto"] else None
    pg = json.loads(r["pagamentos"]) if r["pagamentos"] else []
    meio = str((pg[-1] if pg else {}).get("meio") or "")
    ks = _cols(r)
    tp = tipos_da_compra(r)
    por = {}
    for t in tp:
        por[t["tipo"]] = por.get(t["tipo"], 0) + _int(t.get("qtd"))
    cad = (amigos or {}).get((r["email"] or "").lower()) if r["email"] else None
    # Descontos separados (21/11/2026, Rafael: "tem algum erro na conta de desconto de amigos?"): a meia-entrada NÃO é desconto de
    # Amigo. Antes, "desconto" = preço cheio × pessoas − pago, e as meias entravam como desconto de Amigo.
    preco = float(r["preco"] or 0)
    d_amigo = round(sum(_int(t.get("qtd")) * max(0.0, preco - float(_num(t.get("valor")) or 0)) for t in tp if t.get("tipo") in ("amigo", "gratuidade")), 2)
    d_meia = round(sum(_int(t.get("qtd")) * max(0.0, preco - float(_num(t.get("valor")) or 0)) for t in tp if t.get("tipo") == "meia"), 2)
    return {"id": r["site_id"], "ref": r["ref"] or "", "data": r["data"], "hora": r["hora"], "turma": f"{r['data']}|{r['hora']}",
            "nome": r["nome"] or "", "email": r["email"] or "", "telefone": r["telefone"] or "", "pessoas": r["pessoas"], "entraram": r["entraram"],
            "bruto": round((r["preco"] or 0) * (r["pessoas"] or 0), 2), "total": r["total"] or 0.0,
            "desconto": d_amigo, "desconto_meia": d_meia,
            "amigo": f"{CATEGORIAS.get((dc or {}).get('categoria', ''), (dc or {}).get('categoria', ''))} ({(dc or {}).get('pct', 0)}%)" if dc else "",
            "meio": "" if r["situacao"] == "gratuito" else MEIOS.get(meio, meio), "situacao": r["situacao"], "situacao_nome": SITUACOES.get(r["situacao"], r["situacao"]),
            "codigo": r["codigo"] or "", "link": r["link"] or "", "modo": r["modo"] or "", "confirmado_em": r["confirmado_em"] or "", "criado_em": r["criado_em"] or "",
            # detalhe (contrato 1.21/1.22; site antigo: calculado)
            "meias": por.get("meia", 0), "tipos": tp, "tipos_txt": _tipos_txt(tp), "por_tipo": por,
            "amigo_cadastro": cad, "eh_amigo": bool(cad and cad["ativo"]) or bool(dc),
            "link_pagamento": (r["link_pagamento"] or "") if "link_pagamento" in ks and r["situacao"] not in VALEM else "",
            "link_pagamento_ate": (r["link_pagamento_ate"] or "") if "link_pagamento_ate" in ks and r["situacao"] not in VALEM else "",
            "pode_reenviar": r["situacao"] in VALEM and bool(r["email"]), "pode_cobrar": r["situacao"] in COBRAVEIS and bool(r["email"])}


def _zerar_tipos() -> dict:
    return {k: 0 for k in TIPOS}


def do_mes(con, mes: str, situacao: str = "valem", q: str = "") -> dict:
    """Ingressos e turmas de um mês (AAAA-MM). situacao: valem (pagos e gratuitos, padrão) | todas | uma das SITUACOES."""
    if not re.fullmatch(r"\d{4}-\d{2}", mes or ""):
        raise HTTPException(400, "Mês inválido (AAAA-MM)")
    rows = con.execute("SELECT * FROM ingresso WHERE data LIKE ? ORDER BY data, hora, nome", (mes + "-%",)).fetchall()
    am = amigos_por_email(con, [r["email"] for r in rows])
    todas_l = [_linha(r, am) for r in rows]
    itens = list(todas_l)
    if situacao == "valem":
        itens = [x for x in itens if x["situacao"] in VALEM]
    elif situacao in SITUACOES:
        itens = [x for x in itens if x["situacao"] == situacao]
    if q:
        qq = q.strip().lower()
        itens = [x for x in itens if qq in f"{x['nome']} {x['email']} {x['ref']} {x['codigo']}".lower()]
    cfg = json.loads(_estado(con, "config") or "{}") or {}
    vagas_padrao = _int(cfg.get("vagas")) or 15
    turmas: dict[str, dict] = {}
    for t in con.execute("SELECT * FROM ingresso_turma WHERE data LIKE ? ORDER BY data, hora", (mes + "-%",)):
        turmas[t["chave"]] = {"chave": t["chave"], "data": t["data"], "hora": t["hora"], "vagas": t["vagas"], "compras": 0, "pessoas": 0, "entraram": 0, "bruto": 0.0, "desconto": 0.0, "desconto_meia": 0.0, "total": 0.0, "amigos": 0, "por_tipo": _zerar_tipos(), "pagos": 0, "gratuitos": 0, "pendentes": 0}
    por_meio: dict[str, float] = {}
    for x in (y for y in todas_l if y["situacao"] in PENDENTES):     # tela: pendentes de cada turma (reserva em pagamento)
        t = turmas.setdefault(x["turma"], {"chave": x["turma"], "data": x["data"], "hora": x["hora"], "vagas": vagas_padrao, "compras": 0, "pessoas": 0, "entraram": 0, "bruto": 0.0, "desconto": 0.0, "desconto_meia": 0.0, "total": 0.0, "amigos": 0, "por_tipo": _zerar_tipos(), "pagos": 0, "gratuitos": 0, "pendentes": 0})
        t["pendentes"] += x["pessoas"]
    for x in (y for y in todas_l if y["situacao"] in VALEM):
        t = turmas.setdefault(x["turma"], {"chave": x["turma"], "data": x["data"], "hora": x["hora"], "vagas": vagas_padrao, "compras": 0, "pessoas": 0, "entraram": 0, "bruto": 0.0, "desconto": 0.0, "desconto_meia": 0.0, "total": 0.0, "amigos": 0, "por_tipo": _zerar_tipos(), "pagos": 0, "gratuitos": 0, "pendentes": 0})
        t["pagos" if x["situacao"] == "pago" else "gratuitos"] += x["pessoas"]
        if x["total"] and x["meio"]:
            por_meio[x["meio"]] = round(por_meio.get(x["meio"], 0.0) + float(x["total"]), 2)
        t["compras"] += 1
        t["pessoas"] += x["pessoas"]
        t["entraram"] += x["entraram"]
        t["bruto"] = round(t["bruto"] + x["bruto"], 2)
        t["desconto"] = round(t["desconto"] + x["desconto"], 2)
        t["desconto_meia"] = round(t["desconto_meia"] + x["desconto_meia"], 2)
        t["total"] = round(t["total"] + x["total"], 2)
        t["amigos"] += 1 if x["desconto"] > 0 else 0
        for k, v in x["por_tipo"].items():
            t["por_tipo"][k] = t["por_tipo"].get(k, 0) + v
    ts = sorted(turmas.values(), key=lambda t: t["chave"])
    for t in ts:
        t["livres"] = max(0, (t["vagas"] or vagas_padrao) - t["pessoas"])
    tot = {k: (round(sum(t[k] for t in ts), 2) if isinstance(ts[0][k], float) else sum(t[k] for t in ts)) if ts else 0
           for k in ("compras", "pessoas", "entraram", "bruto", "desconto", "desconto_meia", "total", "amigos", "livres", "pendentes")}
    tot["vagas"] = sum((t["vagas"] or vagas_padrao) for t in ts)
    tot["por_tipo"] = _zerar_tipos()
    for t in ts:
        for k, v in t["por_tipo"].items():
            tot["por_tipo"][k] = tot["por_tipo"].get(k, 0) + v
    tot["amigos_cadastro"] = sum(1 for x in todas_l if x["situacao"] in VALEM and x["amigo_cadastro"] and x["amigo_cadastro"]["ativo"])
    tot["por_meio"] = por_meio                                   # recebido por meio (Pix, cartão…), para a tela
    return {"mes": mes, "itens": itens, "turmas": ts, "totais": tot, "situacoes": SITUACOES, "tipos": TIPOS, "config": cfg}


def datas(con, mes: str = "") -> dict:
    """Datas de visita (dia → turmas) com contas: vendidos por tipo (pagos e gratuitos), pagos, gratuitos, pendentes (reservas em pagamento),
    entraram, vagas e livres. mes vazio = de hoje em diante (São Paulo); AAAA-MM = aquele mês."""
    if mes and not re.fullmatch(r"\d{4}-\d{2}", mes):
        raise HTTPException(400, "Mês inválido (AAAA-MM)")
    hoje_ = datetime.now(FUSO).strftime("%Y-%m-%d")
    filtro, arg = ("data LIKE ?", mes + "-%") if mes else ("data >= ?", hoje_)
    cfg = json.loads(_estado(con, "config") or "{}") or {}
    vagas_padrao = _int(cfg.get("vagas")) or 15
    tur: dict[str, dict] = {}

    def nova(chave, data, hora, vagas=None, livres_site=None):
        return {"chave": chave, "data": data, "hora": hora, "vagas": vagas or vagas_padrao, "livres_site": livres_site, "compras": 0, "pessoas": 0,
                "pagos": 0, "gratuitos": 0, "pendentes": 0, "entraram": 0, "amigos": 0, "total": 0.0, "por_tipo": _zerar_tipos()}
    for t in con.execute(f"SELECT * FROM ingresso_turma WHERE {filtro}", (arg,)):
        tur[t["chave"]] = nova(t["chave"], t["data"], t["hora"], t["vagas"], t["livres"])
    rows = con.execute(f"SELECT * FROM ingresso WHERE {filtro}", (arg,)).fetchall()
    am = amigos_por_email(con, [r["email"] for r in rows])
    for r in rows:
        x = _linha(r, am)
        t = tur.setdefault(x["turma"], nova(x["turma"], x["data"], x["hora"]))
        if x["situacao"] in VALEM:
            t["compras"] += 1
            t["pessoas"] += x["pessoas"]
            t["entraram"] += x["entraram"]
            t["total"] = round(t["total"] + x["total"], 2)
            t["pagos" if x["situacao"] == "pago" else "gratuitos"] += x["pessoas"]
            t["amigos"] += 1 if x["eh_amigo"] else 0
            for k, v in x["por_tipo"].items():
                t["por_tipo"][k] = t["por_tipo"].get(k, 0) + v
        elif x["situacao"] in PENDENTES:
            t["pendentes"] += x["pessoas"]
    dias: dict[str, dict] = {}
    for t in sorted(tur.values(), key=lambda t: t["chave"]):
        t["livres"] = t["livres_site"] if t["livres_site"] is not None else max(0, t["vagas"] - t["pessoas"])
        d = dias.setdefault(t["data"], {"data": t["data"], "turmas": [], "pessoas": 0, "pagos": 0, "gratuitos": 0, "pendentes": 0, "entraram": 0, "vagas": 0, "livres": 0, "amigos": 0, "total": 0.0, "por_tipo": _zerar_tipos()})
        d["turmas"].append(t)
        for k in ("pessoas", "pagos", "gratuitos", "pendentes", "entraram", "vagas", "livres", "amigos"):
            d[k] += t[k]
        d["total"] = round(d["total"] + t["total"], 2)
        for k, v in t["por_tipo"].items():
            d["por_tipo"][k] = d["por_tipo"].get(k, 0) + v
    return {"mes": mes, "de": "" if mes else hoje_, "dias": list(dias.values()), "tipos": TIPOS}


FILTROS_SITUACAO = {"valem": "Pagos e gratuitos", "pendentes": "Aguardando pagamento", "todas": "Todas as situações"}


def _linhas_pessoa(x: dict, pessoas: list) -> list[dict]:
    """Linhas da lista de presença de uma compra: uma POR PESSOA (contrato 1.24) ou, compra antiga, uma só "comprador + N"."""
    base = {"id": x["id"], "data": x["data"], "hora": x["hora"], "ref": x["ref"], "pedido_codigo": x["codigo"], "comprador": x["nome"], "comprador_email": x["email"],
            "telefone": x["telefone"], "situacao": x["situacao"], "situacao_nome": x["situacao_nome"], "pago": x["situacao"] in VALEM, "total": x["total"], "meio": x["meio"],
            "link_pagamento_ate": x["link_pagamento_ate"], "pode_cobrar": x["pode_cobrar"], "pode_reenviar": x["pode_reenviar"], "amigo_txt": _amigo_txt(x),
            "amigo_compra": x["amigo"], "amigo_cadastro": x["amigo_cadastro"]}
    if not pessoas:
        return [dict(base, legado=True, n=0, nome=x["nome"], email=x["email"], pessoas=x["pessoas"], tipo="", tipo_nome=x["tipos_txt"], motivo="", motivo_nome="",
                     codigo=x["codigo"], entrou=x["entraram"] >= x["pessoas"] > 0, entraram=x["entraram"], eh_comprador=True, por_tipo=x["por_tipo"],
                     eh_amigo=x["eh_amigo"], pode_reenviar_pessoa=False)]
    out = []
    for p in pessoas:
        out.append(dict(base, legado=False, n=p["n"], nome=p["nome"], email=p["email"], pessoas=1, tipo=p["tipo"], tipo_nome=p["tipo_nome"], motivo=p["motivo"],
                        motivo_nome=p["motivo_nome"], codigo=p["codigo"], link=p["link"], entrou=p["entrou"], entraram=1 if p["entrou"] else 0, eh_comprador=p["eh_comprador"],
                        por_tipo={p["tipo"]: 1}, eh_amigo=p["tipo"] in ("amigo", "gratuidade") or (p["eh_comprador"] and bool(x["amigo_cadastro"] and x["amigo_cadastro"]["ativo"])),
                        envios=p["envios"], anonimizado=p["anonimizado"],
                        pode_reenviar_pessoa=x["situacao"] in VALEM and bool(p["email"]) and not p["eh_comprador"]))
    return out


def lista(con, turma: str, situacao: str = "todas", tipo: str = "", amigo: str = "", q: str = "") -> dict:
    """Lista de presença de uma data (AAAA-MM-DD) ou turma (AAAA-MM-DD|HH:MM): uma linha por PESSOA (`linhas`; compra antiga = "comprador + N")
    e as compras (`itens`) com o comprador, tipos, Amigo, pagamento, pedido e entrada. situacao: todas (padrão) | valem | pendentes | uma das
    SITUACOES; tipo: inteira|meia|amigo|gratuidade; amigo=1; q procura no nome/e-mail da pessoa e do comprador, telefone, pedido e códigos."""
    turma = (turma or "").strip()
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:\|(\d{2}:\d{2}))?", turma)
    if not m:
        raise HTTPException(400, "Data ou turma inválida (AAAA-MM-DD ou AAAA-MM-DD|HH:MM)")
    data, hora = m.group(1), m.group(2)
    rows = con.execute("SELECT * FROM ingresso WHERE data=?" + (" AND hora=?" if hora else "") + " ORDER BY hora, nome COLLATE NOCASE", (data, hora) if hora else (data,)).fetchall()
    am = amigos_por_email(con, [r["email"] for r in rows])
    todos = [_linha(r, am) for r in rows]
    itens = todos
    if situacao == "valem":
        itens = [x for x in itens if x["situacao"] in VALEM]
    elif situacao == "pendentes":
        itens = [x for x in itens if x["situacao"] in PENDENTES]
    elif situacao in SITUACOES:
        itens = [x for x in itens if x["situacao"] == situacao]
    pes = pessoas_das_compras(con, [x["id"] for x in itens])
    linhas = [l for x in itens for l in _linhas_pessoa(x, pes.get(x["id"], []))]
    if tipo in TIPOS:
        linhas = [l for l in linhas if l["por_tipo"].get(tipo)]
    if amigo in ("1", "sim"):
        linhas = [l for l in linhas if l["eh_amigo"]]
    if q:
        qq = q.strip().lower()
        linhas = [l for l in linhas if qq in f"{l['nome']} {l['email']} {l['comprador']} {l['comprador_email']} {l['telefone']} {l['ref']} {l['codigo']} {l['pedido_codigo']}".lower()]
    ficam = {l["id"] for l in linhas}
    itens = [x for x in itens if x["id"] in ficam]
    for x in itens:
        x["ingressos"] = pes.get(x["id"], [])
    tot = {"compras": len(itens), "pessoas": sum(x["pessoas"] for x in itens), "entraram": sum(x["entraram"] for x in itens),
           "amigos": sum(1 for x in itens if x["eh_amigo"]), "por_tipo": _zerar_tipos(), "linhas": len(linhas),
           "pagos": sum(x["pessoas"] for x in itens if x["situacao"] == "pago"), "gratuitos": sum(x["pessoas"] for x in itens if x["situacao"] == "gratuito"),
           "pendentes": sum(x["pessoas"] for x in itens if x["situacao"] in PENDENTES)}
    for x in itens:
        for k, v in x["por_tipo"].items():
            tot["por_tipo"][k] = tot["por_tipo"].get(k, 0) + v
    horas = sorted({x["hora"] for x in todos} | {t["hora"] for t in con.execute("SELECT hora FROM ingresso_turma WHERE data=?", (data,))})
    return {"turma": turma, "data": data, "hora": hora or "", "horas": horas, "itens": itens, "linhas": linhas, "totais": tot, "tipos": TIPOS, "motivos": MOTIVOS,
            "situacoes": {**FILTROS_SITUACAO, **SITUACOES}}


def anonimizar_por_email(con, email: str) -> int:
    """LGPD (apagar pessoa): tira nome, e-mail e telefone; ficam turma, pessoas e valores (receita). Não faz commit."""
    em = (email or "").strip().lower()
    if not em:
        return 0
    try:
        return con.execute("UPDATE ingresso SET nome=?, email=NULL, telefone=NULL, anonimizado=1 WHERE lower(email)=?", (REMOVIDO, em)).rowcount
    except Exception:  # noqa: BLE001  (banco sem a migração 230)
        return 0


def anonimizar_pessoas_por_email(con, email: str) -> int:
    """LGPD (apagar pessoa): a pessoa de um ingresso (contrato 1.24) perde nome e e-mail; ficam tipo, código e entrada. Não faz commit."""
    em = (email or "").strip().lower()
    if not em:
        return 0
    try:
        return con.execute("UPDATE ingresso_pessoa SET nome=?, email=NULL, anonimizado=1 WHERE lower(email)=?", (REMOVIDO, em)).rowcount
    except Exception:  # noqa: BLE001  (banco sem a migração 234)
        return 0


# ---------------------------------------------------------------- telas (só admin e master)
def _mes_padrao() -> str:
    return datetime.now(FUSO).strftime("%Y-%m")


@router.get("")
def listar(mes: str | None = None, situacao: str = "valem", q: str = "", u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        d = do_mes(con, mes or _mes_padrao(), situacao, q)
        meses = [r[0] for r in con.execute("SELECT DISTINCT substr(data,1,7) FROM ingresso UNION SELECT DISTINCT substr(data,1,7) FROM ingresso_turma ORDER BY 1")]
        d["meses"] = sorted(set(meses) | {d["mes"]})
        cfg = d.get("config") or {}
        d["avisos"] = {"destino": cfg.get("email_ingressos_destino") or "", "email": cfg.get("email_ingressos") or "", "aviso_recusado": bool(cfg.get("aviso_recusado")),
                       "teste": cfg.get("aviso_teste") if isinstance(cfg.get("aviso_teste"), dict) else None, "site_sabe": "email_ingressos_destino" in cfg}
        d["site"] = {"ultima_busca": _estado(con, "ultima_busca") or None, "erro": _estado(con, "ultimo_erro") or None,
                     "sem_rota": _estado(con, "sem_rota") == "1", "minutos": coleta_min(con), "tem_senha": _tem_site(con)}
        return d
    finally:
        con.close()


def _cel(v):
    s = f"{v:.2f}".replace(".", ",") if isinstance(v, float) else str(v if v is not None else "")
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def _csv(cab: list, linhas: list, nome: str) -> Response:
    buf = io.StringIO()
    wr = csv.writer(buf, delimiter=";")
    wr.writerow(cab)
    for l in linhas:
        wr.writerow([_cel(v) for v in l])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def _amigo_txt(x: dict) -> str:
    c = x.get("amigo_cadastro")
    if c and c.get("ativo"):
        return f"Amigo ({c.get('categoria_nome') or c.get('categoria') or 'sem categoria'})"
    return "desconto de Amigo" if x.get("amigo") else ""


@router.get("/exportar.csv")
def exportar(mes: str | None = None, situacao: str = "valem", u: dict = Depends(auth.exige("admin"))):
    """Planilha do mês para o Excel (separador ;, UTF-8 com BOM, valores com vírgula, sem fórmulas). Sem log de dados pessoais."""
    con = connect()
    try:
        d = do_mes(con, mes or _mes_padrao(), situacao)
    finally:
        con.close()
    cab = ["Data", "Hora", "Nome", "E-mail", "Telefone", "Pessoas", "Entraram", "Bruto (R$)", "Desconto Amigo (R$)", "Pago (R$)", "Amigo (categoria)", "Meio", "Situação", "Referência Mercado Pago",
           "Inteiras", "Meias-entradas", "Amigo com desconto", "Gratuidades", "Amigo da CAMP (cadastro)", "Meia-entrada: abatimento (R$)"]
    return _csv(cab, [("/".join(reversed(x["data"].split("-"))), x["hora"], x["nome"], x["email"], x["telefone"], x["pessoas"], x["entraram"],
                       float(x["bruto"]), float(x["desconto"]), float(x["total"]), x["amigo"], x["meio"], x["situacao_nome"], x["ref"],
                       x["por_tipo"].get("inteira", 0), x["por_tipo"].get("meia", 0), x["por_tipo"].get("amigo", 0), x["por_tipo"].get("gratuidade", 0), _amigo_txt(x), float(x["desconto_meia"]))
                      for x in d["itens"]], f"ingressos-joao-marino-{d['mes']}.csv")


@router.get("/datas")
def ver_datas(mes: str = "", u: dict = Depends(auth.exige("admin"))) -> dict:
    """Datas de visita com contas por tipo e situação (sem mês: de hoje em diante)."""
    con = connect()
    try:
        return datas(con, mes)
    finally:
        con.close()


@router.get("/lista")
def ver_lista(turma: str, situacao: str = "todas", tipo: str = "", amigo: str = "", q: str = "", u: dict = Depends(auth.exige("admin"))) -> dict:
    """Lista de presença de uma data ou turma (pessoas, tipos, Amigo, pagamento, pedido, entrada)."""
    con = connect()
    try:
        return lista(con, turma, situacao, tipo, amigo, q)
    finally:
        con.close()


@router.get("/lista.csv")
def lista_csv(turma: str, situacao: str = "todas", tipo: str = "", amigo: str = "", q: str = "", u: dict = Depends(auth.exige("admin"))):
    """Lista de presença em CSV (Excel), com uma coluna "Presença" em branco para marcar na porta."""
    con = connect()
    try:
        d = lista(con, turma, situacao, tipo, amigo, q)
    finally:
        con.close()
    # uma linha por pessoa (contrato 1.24); compra antiga: uma linha com o comprador e as N pessoas
    cab = ["Data", "Hora", "Nome", "E-mail", "Telefone", "Pessoas", "Inteiras", "Meias-entradas", "Amigo com desconto", "Gratuidades", "Amigo da CAMP",
           "Situação", "Código do ingresso", "Pedido (referência)", "Entraram", "Motivo da meia-entrada", "Comprador", "Presença"]
    nome = "lista-presenca-joao-marino-" + d["data"] + (("-" + d["hora"].replace(":", "h")) if d["hora"] else "") + ".csv"
    return _csv(cab, [("/".join(reversed(l["data"].split("-"))), l["hora"], l["nome"], l["email"], l["telefone"], l["pessoas"],
                       l["por_tipo"].get("inteira", 0), l["por_tipo"].get("meia", 0), l["por_tipo"].get("amigo", 0), l["por_tipo"].get("gratuidade", 0),
                       l["amigo_txt"] if (l["legado"] or l["eh_comprador"]) else ("Amigo (desconto)" if l["eh_amigo"] else ""), l["situacao_nome"], l["codigo"], l["ref"], l["entraram"],
                       l["motivo_nome"], "" if l["legado"] else l["comprador"], "") for l in d["linhas"]], nome)


@router.post("/sincronizar")
def sincronizar(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações: sem ela o painel não busca os ingressos")
        return coletar(con)
    finally:
        con.close()


# ---------------------------------------------------------------- reenvios (só admin; SÓ pelo Sender, pelo site)
def _evento(con, sid: int, tipo: str, ator: str, detalhe: dict | None = None) -> None:
    """Histórico do ingresso no painel (tabela evento; sem nome nem e-mail do comprador)."""
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('ingresso',?,?,?,?)", (str(int(sid)), tipo, ator, json.dumps(detalhe or {}, ensure_ascii=False)))


def _json(r) -> dict:
    try:
        d = r.json() if callable(getattr(r, "json", None)) else {}
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


ACOES = {"ingresso": ("reenviar", TPL_INGRESSO, "ingresso_reenviado"), "cobranca": ("cobranca", TPL_COBRANCA, "cobranca_reenviada")}


def _executar(con, sid: int, acao: str, ator: str, pessoa: int = 0, para: str = "") -> tuple[int, str, dict]:
    """Pede ao site um reenvio. Devolve (status HTTP para a tela, mensagem, extra). Grava o histórico. Nunca levanta (fora 404/409 da checagem).
    Contrato 1.24: pessoa = n reenvia SÓ o ingresso daquela pessoa (para "pessoa", padrão, ou "comprador"); sem pessoa numa compra por pessoa,
    o site manda todos os ingressos a quem comprou, um por e-mail."""
    caminho, tpl, ev_ok = ACOES[acao]
    r = con.execute("SELECT site_id, email, situacao FROM ingresso WHERE site_id=?", (sid,)).fetchone()
    if not r:
        return 404, "Ingresso não encontrado no painel", {}
    para = para if para in ("pessoa", "comprador") else "pessoa"
    corpo = {"so_sender": True} if acao == "ingresso" else {}
    pes = pessoas_das_compras(con, [sid]).get(sid, []) if acao == "ingresso" else []
    if pessoa:
        p = next((x for x in pes if x["n"] == int(pessoa)), None)
        if acao != "ingresso" or not p:
            return 404, "Esta pessoa não está neste pedido no painel", {}
        if para == "pessoa" and not p["email"]:
            return 409, ("não enviado: os dados desta pessoa foram apagados a pedido dela" if p["anonimizado"] else
                         "não enviado: esta pessoa não deixou e-mail. Use Reenviar ao comprador"), {}
        corpo.update(pessoa=int(pessoa), para=para)
    if (not pessoa or para == "comprador") and not r["email"]:
        return 409, "não enviado: este pedido está sem e-mail (dados apagados a pedido da pessoa)", {}
    if not _tem_site(con):
        return 409, "Falta a senha do site (Application Password) em Configurações", {}
    try:
        resp = _wp().h.post(f"{ROTA}/{int(sid)}/{caminho}", json=corpo)
    except Exception as e:  # noqa: BLE001
        registrar(logging.WARNING, "ingressos_reenvio", "Reenvio de ingresso: o site não respondeu", site_id=int(sid), erro=type(e).__name__)
        return 502, "não enviado: o site não respondeu. Tente de novo em instantes", {}
    d = _json(resp)
    cod = str(d.get("code") or "")
    st = resp.status_code
    msg = None
    if st == 404 and cod in ("", "rest_no_route"):
        msg = ("O site ainda não tem o reenvio de ingressos: avise quem cuida do site" if acao == "ingresso"
               else f"não enviado: o site ainda não reenvia cobranças de ingresso. Avise quem cuida do site (plugin da CAMP {VERSAO_SITE} ou mais novo)")
        st = 409
    elif cod == "camp_ing_nao_existe" or st == 404:
        msg, st = "Este ingresso não existe mais no site", 404
    elif cod == "camp_sender_sem_template":
        msg = f"não enviado: falta o template {tpl[0]} ({tpl[1]}) do Sender no site. Crie no Sender e cole o ID {ONDE_TEMPLATE}"
    elif cod == "camp_sender_sem_chave":
        msg = "não enviado: o Sender está desligado no site (sem o token). Avise quem cuida do site"
    elif cod == "camp_sender_falhou":
        msg = "não enviado: o Sender recusou o e-mail. Tente de novo mais tarde"
    elif cod == "camp_ing_email":
        msg = "não enviado: o e-mail de destino é inválido"
    elif cod == "camp_ing_pessoa_sem_email":
        msg = "não enviado: esta pessoa não deixou e-mail no site. Use Reenviar ao comprador"
    elif cod == "camp_ing_pessoa_nao_existe":
        msg, st = "Esta pessoa não existe mais neste pedido no site", 404
    elif cod in ("camp_ing_pago",):
        msg = "não enviado: esta compra já está paga, não há o que cobrar. Use Reenviar ingresso"
    elif cod == "camp_ing_em_analise":
        msg = "não enviado: o pagamento está em análise no Mercado Pago. Espere a resposta antes de cobrar de novo"
    elif cod == "camp_ing_turma_fechada":
        msg = "não enviado: a venda desta turma já fechou"
    elif cod == "camp_ing_sem_vagas":
        msg = "não enviado: a turma não tem mais vagas para esta compra (" + _txt(d.get("message"), 160) + ")"
    elif cod == "camp_mp_desligado":
        msg = "não enviado: o Mercado Pago está desligado no site. Avise quem cuida do site"
    elif cod == "camp_mp_falhou":
        msg = "não enviado: o Mercado Pago não abriu o link novo agora. Tente de novo em instantes"
    elif st == 409:
        msg = "Este ingresso não está pago: não há o que reenviar" if acao == "ingresso" else "não enviado: o site recusou a cobrança"
    elif st >= 400:
        msg, st = f"não enviado: o site respondeu {st}", 502
    quem = {"pessoa": int(pessoa), "para": para} if pessoa else ({"para": "comprador", "todos": len(pes)} if pes else {})
    if msg:
        _evento(con, sid, "reenvio_falhou", ator, {"acao": acao, "template": tpl[0], **quem, "erro": msg[:300]})
        con.commit()
        return (st if st in (404, 409) else 502), msg, {}
    if isinstance(d.get("registro"), dict):
        _gravar(con, d["registro"])
    extra = {"novo_link": bool(d.get("novo_link")), "canal": "sender" if d.get("enviado") else "site"}
    if "enviados" in d:
        extra["enviados"] = _int(d.get("enviados"))
    _evento(con, sid, ev_ok, ator, {"acao": acao, "template": tpl[0], **extra, **quem, "sender_id": str((d.get("sender") or {}).get("id") or "")})
    con.commit()
    registrar(logging.INFO, "ingressos_reenvio", "Reenvio de ingresso pelo painel", site_id=int(sid), acao=acao, pessoa=int(pessoa))
    if acao == "ingresso" and pessoa:
        return 200, f"Ingresso {int(pessoa)} reenviado " + ("à pessoa" if para == "pessoa" else "ao comprador") + " por e-mail", extra
    if acao == "ingresso" and pes:
        n_ = extra.get("enviados") or len(pes)
        return 200, f"{n_} ingressos reenviados ao comprador, um por e-mail" if n_ != 1 else "1 ingresso reenviado ao comprador", extra
    if acao == "ingresso":
        return 200, "Ingresso reenviado por e-mail", extra
    return 200, "Cobrança reenviada por e-mail" + (" com um link novo do Mercado Pago" if extra["novo_link"] else ""), extra


def _uma(site_id: int, acao: str, u: dict, pessoa: int = 0, para: str = "") -> dict:
    con = connect()
    try:
        st, msg, extra = _executar(con, int(site_id), acao, u["email"], pessoa, para)
        if st != 200:
            raise HTTPException(st, msg)
        return {"ok": bool(extra.get("ok", True)), "mensagem": msg, **extra}
    finally:
        con.close()


class Lote(BaseModel):
    acao: str
    ids: list[int]


@router.post("/lote")
def lote(corpo: Lote, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Reenvio em lote (lista de presença): acao ingresso | cobranca, até 60 ingressos. Cada um segue as regras do reenvio de um."""
    if corpo.acao not in ACOES:
        raise HTTPException(400, "Ação inválida (ingresso ou cobranca)")
    ids = list(dict.fromkeys(int(i) for i in corpo.ids))
    if not ids or len(ids) > 60:
        raise HTTPException(400, "Escolha de 1 a 60 ingressos")
    con = connect()
    try:
        res = []
        for sid in ids:
            st, msg, extra = _executar(con, sid, corpo.acao, u["email"])
            res.append({"id": sid, "ok": st == 200, "mensagem": msg, **extra})
            if st == 409 and "senha do site" in msg:
                break
        return {"feitos": sum(1 for x in res if x["ok"]), "falhas": sum(1 for x in res if not x["ok"]), "resultados": res}
    finally:
        con.close()


class AvisosCfg(BaseModel):
    email_ingressos: str | None = None
    aviso_recusado: bool | None = None


def _cfg_site_atualiza(con, nova: dict) -> None:
    cfg = json.loads(_estado(con, "config") or "{}") or {}
    cfg.update({k: v for k, v in (nova or {}).items() if k in ("email_ingressos", "email_ingressos_destino", "aviso_recusado", "aviso_teste")})
    _estado_set(con, "config", json.dumps(cfg, ensure_ascii=False))


@router.post("/avisos")
def avisos_config(corpo: AvisosCfg, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Quem recebe os avisos de ingresso à equipe (wp_mail do site, sem Sender) e se avisa também os recusados. Vazio = padrão do site."""
    con = connect()
    try:
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações")
        b = {}
        if corpo.email_ingressos is not None:
            em = corpo.email_ingressos.strip()
            if em and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", em):
                raise HTTPException(400, "E-mail inválido")
            b["email_ingressos"] = em or "__limpar__"
        if corpo.aviso_recusado is not None:
            b["aviso_recusado"] = corpo.aviso_recusado
        r = _wp().h.post(f"{ROTA}/config", json=b)
        d = _json(r)
        if r.status_code == 404 and str(d.get("code") or "") in ("", "rest_no_route"):
            raise HTTPException(409, f"O site ainda não tem esta configuração: avise quem cuida do site (plugin da CAMP {VERSAO_SITE} ou mais novo)")
        if r.status_code == 400:
            raise HTTPException(400, "O site recusou o e-mail (inválido)")
        if r.status_code >= 400:
            raise HTTPException(502, f"O site respondeu {r.status_code}")
        _cfg_site_atualiza(con, d.get("config") or {})
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('ingresso','config','avisos_config',?,?)", (u["email"], json.dumps(b, ensure_ascii=False)))
        con.commit()
        return {"ok": True, "config": d.get("config") or {}}
    finally:
        con.close()


@router.post("/aviso-teste")
def aviso_teste(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Pede ao site um aviso de TESTE à equipe (o mesmo caminho dos avisos de venda: wp_mail do site, sem Sender).
    ok = o servidor de e-mail do site aceitou (não garante que chegou: se nada chegar, o problema é a conexão de SMTP do site)."""
    con = connect()
    try:
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações")
        r = _wp().h.post(f"{ROTA}/aviso-teste", json={})
        d = _json(r)
        if r.status_code == 404 and str(d.get("code") or "") in ("", "rest_no_route"):
            raise HTTPException(409, f"O site ainda não manda o aviso de teste: avise quem cuida do site (plugin da CAMP {VERSAO_SITE} ou mais novo)")
        if r.status_code >= 400:
            raise HTTPException(502, f"O site respondeu {r.status_code}")
        res = {"ok": bool(d.get("ok")), "para": _txt(d.get("para"), 200), "erro": _txt(d.get("erro"), 300), "em": _txt(d.get("em"), 40)}
        _cfg_site_atualiza(con, {"aviso_teste": res, **({"email_ingressos_destino": res["para"]} if res["para"] else {})})
        con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('ingresso','config','aviso_teste',?,?)",
                    (u["email"], json.dumps({"ok": res["ok"], "erro": res["erro"]}, ensure_ascii=False)))
        con.commit()
        registrar(logging.INFO, "ingressos_aviso_teste", "Aviso de teste dos ingressos pedido pelo painel", ok=res["ok"])
        return res
    finally:
        con.close()


@router.get("/{site_id}")
def detalhe(site_id: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Um pedido: comprador, tipos, Amigo, pagamento, histórico do site e o que o painel fez (reenvios)."""
    con = connect()
    try:
        r = con.execute("SELECT * FROM ingresso WHERE site_id=?", (site_id,)).fetchone()
        if not r:
            raise HTTPException(404, "Ingresso não encontrado no painel")
        x = _linha(r, amigos_por_email(con, [r["email"]]))
        x["historico_site"] = json.loads(r["historico"]) if "historico" in _cols(r) and r["historico"] else []
        x["aviso_equipe"] = json.loads(r["aviso_equipe"]) if "aviso_equipe" in _cols(r) and r["aviso_equipe"] else []
        x["ingressos"] = pessoas_das_compras(con, [site_id]).get(int(site_id), [])   # contrato 1.24: um por pessoa ([] = compra antiga)
        x["eventos"] = [{"quando": e["quando"], "tipo": e["tipo"], "ator": e["ator"], "detalhe": json.loads(e["detalhe"] or "{}")}
                        for e in con.execute("SELECT quando, tipo, ator, detalhe FROM evento WHERE entidade='ingresso' AND codigo=? ORDER BY id DESC LIMIT 50", (str(int(site_id)),))]
        return x
    finally:
        con.close()


class Reenvio(BaseModel):
    pessoa: int = 0          # contrato 1.24: só o ingresso desta pessoa (n)
    para: str = "pessoa"     # pessoa | comprador


@router.post("/{site_id}/reenviar")
def reenviar(site_id: int, corpo: Reenvio | None = None, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Pede ao site para mandar de novo o ingresso (com o QR), SÓ pelo Sender (TR23). Sem template: não sai e a tela diz o que falta.
    Sem corpo: ao comprador (compra por pessoa: todos, um por e-mail). {pessoa: n, para: pessoa|comprador}: só o ingresso daquela pessoa."""
    c = corpo or Reenvio()
    return _uma(site_id, "ingresso", u, max(0, c.pessoa), c.para)


@router.post("/{site_id}/cobranca")
def cobranca(site_id: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Reenvia ao comprador o link de pagamento de uma compra não paga, SÓ pelo Sender (TR29); link vencido: o site abre outro (contrato 1.22)."""
    return _uma(site_id, "cobranca", u)
