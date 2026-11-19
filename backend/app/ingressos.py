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
    velho = con.execute("SELECT anonimizado FROM ingresso WHERE site_id=?", (sid,)).fetchone()
    if velho and velho["anonimizado"]:
        vals.update(nome=REMOVIDO, email=None, telefone=None)
    cols = list(vals)
    if velho:
        con.execute(f"UPDATE ingresso SET {', '.join(c + '=?' for c in cols)}, visto_em=datetime('now') WHERE site_id=?", (*vals.values(), sid))
        return 0
    con.execute(f"INSERT INTO ingresso (site_id, {', '.join(cols)}) VALUES (?, {', '.join('?' * len(cols))})", (sid, *vals.values()))
    return 1


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
def _linha(r) -> dict:
    dc = json.loads(r["desconto"]) if r["desconto"] else None
    pg = json.loads(r["pagamentos"]) if r["pagamentos"] else []
    meio = str((pg[-1] if pg else {}).get("meio") or "")
    return {"id": r["site_id"], "ref": r["ref"] or "", "data": r["data"], "hora": r["hora"], "turma": f"{r['data']}|{r['hora']}",
            "nome": r["nome"] or "", "email": r["email"] or "", "telefone": r["telefone"] or "", "pessoas": r["pessoas"], "entraram": r["entraram"],
            "bruto": round((r["preco"] or 0) * (r["pessoas"] or 0), 2), "total": r["total"] or 0.0,
            "desconto": round((r["preco"] or 0) * (r["pessoas"] or 0) - (r["total"] or 0), 2),
            "amigo": f"{CATEGORIAS.get((dc or {}).get('categoria', ''), (dc or {}).get('categoria', ''))} ({(dc or {}).get('pct', 0)}%)" if dc else "",
            "meio": "" if r["situacao"] == "gratuito" else MEIOS.get(meio, meio), "situacao": r["situacao"], "situacao_nome": SITUACOES.get(r["situacao"], r["situacao"]),
            "codigo": r["codigo"] or "", "link": r["link"] or "", "modo": r["modo"] or "", "confirmado_em": r["confirmado_em"] or "", "criado_em": r["criado_em"] or ""}


def do_mes(con, mes: str, situacao: str = "valem", q: str = "") -> dict:
    """Ingressos e turmas de um mês (AAAA-MM). situacao: valem (pagos e gratuitos, padrão) | todas | uma das SITUACOES."""
    if not re.fullmatch(r"\d{4}-\d{2}", mes or ""):
        raise HTTPException(400, "Mês inválido (AAAA-MM)")
    rows = con.execute("SELECT * FROM ingresso WHERE data LIKE ? ORDER BY data, hora, nome", (mes + "-%",)).fetchall()
    itens = [_linha(r) for r in rows]
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
        turmas[t["chave"]] = {"chave": t["chave"], "data": t["data"], "hora": t["hora"], "vagas": t["vagas"], "compras": 0, "pessoas": 0, "entraram": 0, "bruto": 0.0, "desconto": 0.0, "total": 0.0, "amigos": 0}
    for x in (y for y in (_linha(r) for r in rows) if y["situacao"] in VALEM):
        t = turmas.setdefault(x["turma"], {"chave": x["turma"], "data": x["data"], "hora": x["hora"], "vagas": vagas_padrao, "compras": 0, "pessoas": 0, "entraram": 0, "bruto": 0.0, "desconto": 0.0, "total": 0.0, "amigos": 0})
        t["compras"] += 1
        t["pessoas"] += x["pessoas"]
        t["entraram"] += x["entraram"]
        t["bruto"] = round(t["bruto"] + x["bruto"], 2)
        t["desconto"] = round(t["desconto"] + x["desconto"], 2)
        t["total"] = round(t["total"] + x["total"], 2)
        t["amigos"] += 1 if x["amigo"] else 0
    ts = sorted(turmas.values(), key=lambda t: t["chave"])
    for t in ts:
        t["livres"] = max(0, (t["vagas"] or vagas_padrao) - t["pessoas"])
    tot = {k: (round(sum(t[k] for t in ts), 2) if isinstance(ts[0][k], float) else sum(t[k] for t in ts)) if ts else 0
           for k in ("compras", "pessoas", "entraram", "bruto", "desconto", "total", "amigos")}
    return {"mes": mes, "itens": itens, "turmas": ts, "totais": tot, "situacoes": SITUACOES, "config": cfg}


def anonimizar_por_email(con, email: str) -> int:
    """LGPD (apagar pessoa): tira nome, e-mail e telefone; ficam turma, pessoas e valores (receita). Não faz commit."""
    em = (email or "").strip().lower()
    if not em:
        return 0
    try:
        return con.execute("UPDATE ingresso SET nome=?, email=NULL, telefone=NULL, anonimizado=1 WHERE lower(email)=?", (REMOVIDO, em)).rowcount
    except Exception:  # noqa: BLE001  (banco sem a migração 230)
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
        d["site"] = {"ultima_busca": _estado(con, "ultima_busca") or None, "erro": _estado(con, "ultimo_erro") or None,
                     "sem_rota": _estado(con, "sem_rota") == "1", "minutos": coleta_min(con), "tem_senha": _tem_site(con)}
        return d
    finally:
        con.close()


@router.get("/exportar.csv")
def exportar(mes: str | None = None, situacao: str = "valem", u: dict = Depends(auth.exige("admin"))):
    """Planilha do mês para o Excel (separador ;, UTF-8 com BOM, valores com vírgula, sem fórmulas). Sem log de dados pessoais."""
    con = connect()
    try:
        d = do_mes(con, mes or _mes_padrao(), situacao)
    finally:
        con.close()

    def cel(v):
        s = f"{v:.2f}".replace(".", ",") if isinstance(v, float) else str(v if v is not None else "")
        return "'" + s if s[:1] in ("=", "+", "-", "@") else s

    buf = io.StringIO()
    wr = csv.writer(buf, delimiter=";")
    wr.writerow(["Data", "Hora", "Nome", "E-mail", "Telefone", "Pessoas", "Entraram", "Bruto (R$)", "Desconto Amigo (R$)", "Pago (R$)", "Amigo (categoria)", "Meio", "Situação", "Referência Mercado Pago"])
    for x in d["itens"]:
        wr.writerow([cel(v) for v in ("/".join(reversed(x["data"].split("-"))), x["hora"], x["nome"], x["email"], x["telefone"], x["pessoas"], x["entraram"],
                                       float(x["bruto"]), float(x["desconto"]), float(x["total"]), x["amigo"], x["meio"], x["situacao_nome"], x["ref"])])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="ingressos-joao-marino-{d["mes"]}.csv"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/sincronizar")
def sincronizar(u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    try:
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações: sem ela o painel não busca os ingressos")
        return coletar(con)
    finally:
        con.close()


@router.post("/{site_id}/reenviar")
def reenviar(site_id: int, u: dict = Depends(auth.exige("admin"))) -> dict:
    """Pede ao site para mandar de novo o ingresso (com o QR) ao comprador."""
    con = connect()
    try:
        if not con.execute("SELECT 1 FROM ingresso WHERE site_id=?", (site_id,)).fetchone():
            raise HTTPException(404, "Ingresso não encontrado no painel")
        if not _tem_site(con):
            raise HTTPException(409, "Falta a senha do site (Application Password) em Configurações")
        r = _wp().h.post(f"{ROTA}/{int(site_id)}/reenviar", json={})
        if r.status_code == 404:
            raise HTTPException(409, "O site ainda não tem o reenvio de ingressos: avise quem cuida do site")
        if r.status_code == 409:
            raise HTTPException(409, "Este ingresso não está pago: não há o que reenviar")
        if r.status_code >= 400:
            raise HTTPException(502, f"O site respondeu {r.status_code} ao reenviar")
        d = r.json() if callable(getattr(r, "json", None)) else {}
        if isinstance(d, dict) and isinstance(d.get("registro"), dict):
            _gravar(con, d["registro"])
            con.commit()
        registrar(logging.INFO, "ingressos_reenvio", "Ingresso reenviado pelo painel", site_id=int(site_id))
        return {"ok": bool((d or {}).get("ok", True))}
    finally:
        con.close()
