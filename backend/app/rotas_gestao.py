"""Entrada de acervo, direitos por fundo, localização física, estações/saúde do site, auditoria."""
from __future__ import annotations

import json
import shutil
import socket
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .config import settings
from .db import connect

router = APIRouter(prefix="/api", tags=["gestao"])


def _evento(con, entidade, codigo, tipo, ator, detalhe=None):
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)",
                (entidade, str(codigo), tipo, ator, json.dumps(detalhe, ensure_ascii=False) if detalhe else None))


def _cfg(con, chave, padrao=""):
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return r[0] if r and r[0] else padrao


# ---------------- entrada de acervo ----------------
class NovaEntrada(BaseModel):
    fundo_codigo: str
    tipo: str
    data: str | None = None
    entregue_por: str | None = None
    contato: str | None = None
    documento: str | None = None
    conteudo: str | None = None
    volumes: int | None = None
    estado_conservacao: str | None = None
    observacoes: str | None = None


@router.get("/fundos/{codigo}/entradas")
def entradas(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect(); rows = con.execute("SELECT * FROM entrada_acervo WHERE fundo_codigo=? ORDER BY data DESC, id DESC", (codigo,)).fetchall(); con.close()
    return [dict(r) for r in rows]


@router.post("/entradas")
def criar_entrada(d: NovaEntrada, u: dict = Depends(auth.exige("operador"))) -> dict:
    if d.tipo not in ("doacao", "comodato", "deposito", "compra", "transferencia", "outro"):
        raise HTTPException(400, "Tipo inválido")
    if d.estado_conservacao and d.estado_conservacao not in ("bom", "regular", "ruim", "critico"):
        raise HTTPException(400, "Estado de conservação inválido")
    con = connect()
    if not con.execute("SELECT 1 FROM fundo WHERE codigo=?", (d.fundo_codigo,)).fetchone():
        con.close(); raise HTTPException(404, "Fundo não existe")
    eid = con.execute("""INSERT INTO entrada_acervo (fundo_codigo, tipo, data, entregue_por, contato, documento, conteudo, volumes, estado_conservacao, observacoes, registrado_por)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (d.fundo_codigo, d.tipo, d.data, d.entregue_por, d.contato, d.documento, d.conteudo, d.volumes, d.estado_conservacao, d.observacoes, u["email"])).lastrowid
    # procedência do fundo (ISAD 3.2.4) preenchida se estiver vazia
    con.execute("UPDATE fundo SET procedencia=COALESCE(NULLIF(procedencia,''), ?) WHERE codigo=?",
                (f"{d.tipo.capitalize()}{' de ' + d.entregue_por if d.entregue_por else ''}{' em ' + d.data if d.data else ''}", d.fundo_codigo))
    _evento(con, "fundo", d.fundo_codigo, "entrada_registrada", u["email"], {"tipo": d.tipo, "volumes": d.volumes})
    con.commit(); con.close()
    return {"id": eid}


# ---------------- direitos ----------------
class Direitos(BaseModel):
    situacao: str
    titular: str | None = None
    documento_autorizacao: str | None = None
    data_autorizacao: str | None = None
    validade: str | None = None
    resolucao_max: str = "jpg_3000"
    credito_exigido: str | None = None
    licenca: str | None = None
    restricoes: str | None = None


@router.get("/fundos/{codigo}/direitos")
def direitos(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect(); r = con.execute("SELECT * FROM direitos_fundo WHERE fundo_codigo=?", (codigo,)).fetchone(); con.close()
    return dict(r) if r else {"fundo_codigo": codigo, "situacao": "nao_definida", "resolucao_max": "jpg_3000"}


@router.put("/fundos/{codigo}/direitos")
def salvar_direitos(codigo: str, d: Direitos, u: dict = Depends(auth.exige("admin"))) -> dict:
    if d.situacao not in ("nao_definida", "autorizado", "restrito", "nao_autorizado"):
        raise HTTPException(400, "Situação inválida")
    if d.resolucao_max not in ("tif", "jpg_3000", "jpg_1200"):
        raise HTTPException(400, "Resolução inválida")
    if d.situacao == "autorizado" and not (d.documento_autorizacao or "").strip():
        raise HTTPException(400, "Para marcar como autorizado, informe o documento/e-mail que autoriza (referência ou caminho)")
    con = connect()
    if not con.execute("SELECT 1 FROM fundo WHERE codigo=?", (codigo,)).fetchone():
        con.close(); raise HTTPException(404, "Fundo não existe")
    con.execute("""INSERT INTO direitos_fundo (fundo_codigo, situacao, titular, documento_autorizacao, data_autorizacao, validade, resolucao_max, credito_exigido, licenca, restricoes, atualizado_por, atualizado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
                   ON CONFLICT(fundo_codigo) DO UPDATE SET situacao=excluded.situacao, titular=excluded.titular, documento_autorizacao=excluded.documento_autorizacao,
                   data_autorizacao=excluded.data_autorizacao, validade=excluded.validade, resolucao_max=excluded.resolucao_max, credito_exigido=excluded.credito_exigido,
                   licenca=excluded.licenca, restricoes=excluded.restricoes, atualizado_por=excluded.atualizado_por, atualizado_em=datetime('now')""",
                (codigo, d.situacao, d.titular, d.documento_autorizacao, d.data_autorizacao, d.validade, d.resolucao_max, d.credito_exigido, d.licenca, d.restricoes, u["email"]))
    if d.credito_exigido:
        con.execute("UPDATE fundo SET condicoes_reproducao=COALESCE(NULLIF(condicoes_reproducao,''),?) WHERE codigo=?", (d.credito_exigido, codigo))
    _evento(con, "fundo", codigo, "direitos", u["email"], {"situacao": d.situacao, "resolucao_max": d.resolucao_max})
    con.commit(); con.close()
    return {"ok": True}


def direitos_permitem_publicar(con, fundo_codigo: str) -> str | None:
    """None se pode; senão a mensagem do porquê não."""
    r = con.execute("SELECT situacao FROM direitos_fundo WHERE fundo_codigo=?", (fundo_codigo,)).fetchone()
    s = r[0] if r else "nao_definida"
    if s == "autorizado":
        return None
    return {"nao_definida": "Direitos do fundo não definidos — registre a autorização em Fundo → Direitos antes de publicar",
            "restrito": "Fundo com direitos restritos — publicação só com liberação registrada",
            "nao_autorizado": "Fundo sem autorização de publicação"}[s]


# ---------------- localização física ----------------
class NovaLocalizacao(BaseModel):
    tipo: str
    identificador: str
    fundo_codigo: str | None = None
    descricao: str | None = None


class Alocacao(BaseModel):
    localizacao_id: int
    codigos: list[str] = []           # folhas; ou
    projeto_codigo: str | None = None  # todas as folhas do projeto


@router.get("/localizacoes")
def localizacoes(u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect()
    rows = con.execute("""SELECT l.*, f.titulo AS fundo, (SELECT COUNT(*) FROM item_localizacao il WHERE il.localizacao_id=l.id) AS itens,
                                 (SELECT GROUP_CONCAT(DISTINCT substr(il.item_codigo,1,10)) FROM item_localizacao il WHERE il.localizacao_id=l.id) AS projetos
                          FROM localizacao_fisica l LEFT JOIN fundo f ON f.codigo=l.fundo_codigo ORDER BY l.fundo_codigo, l.tipo, l.identificador""").fetchall()
    con.close()
    return [dict(r) for r in rows]


@router.post("/localizacoes")
def criar_localizacao(d: NovaLocalizacao, u: dict = Depends(auth.exige("operador"))) -> dict:
    if d.tipo not in ("caixa", "gaveta", "tubo", "mapoteca", "estante"):
        raise HTTPException(400, "Tipo inválido")
    ident = d.identificador.strip().upper()
    if not ident:
        raise HTTPException(400, "Informe o identificador (ex.: CX07, MAP-02-G3)")
    con = connect()
    if con.execute("SELECT 1 FROM localizacao_fisica WHERE identificador=? AND COALESCE(fundo_codigo,'')=COALESCE(?,'')", (ident, d.fundo_codigo)).fetchone():
        con.close(); raise HTTPException(409, f"Já existe {ident} neste fundo")
    lid = con.execute("INSERT INTO localizacao_fisica (fundo_codigo, tipo, identificador, descricao) VALUES (?,?,?,?)", (d.fundo_codigo, d.tipo, ident, d.descricao)).lastrowid
    _evento(con, "localizacao", lid, "criada", u["email"], {"identificador": ident, "fundo": d.fundo_codigo})
    con.commit(); con.close()
    return {"id": lid, "identificador": ident}


@router.get("/localizacoes/{lid}/itens")
def itens_da_localizacao(lid: int, u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect()
    rows = con.execute("""SELECT i.codigo, i.titulo, i.serie_codigo, i.folha, p.titulo AS projeto FROM item_localizacao il JOIN item i ON i.codigo=il.item_codigo
                          JOIN projeto p ON p.codigo=i.projeto_codigo WHERE il.localizacao_id=? ORDER BY i.codigo""", (lid,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


@router.post("/localizacoes/alocar")
def alocar(d: Alocacao, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    if not con.execute("SELECT 1 FROM localizacao_fisica WHERE id=?", (d.localizacao_id,)).fetchone():
        con.close(); raise HTTPException(404, "Localização não existe")
    cods = [c.strip().upper() for c in d.codigos if c.strip()]
    if d.projeto_codigo:
        cods += [r[0] for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo=?", (d.projeto_codigo.strip().upper(),))]
    ok, nao = 0, []
    for c in cods:
        if con.execute("SELECT 1 FROM item WHERE codigo=?", (c,)).fetchone():
            con.execute("INSERT OR REPLACE INTO item_localizacao (item_codigo, localizacao_id) VALUES (?,?)", (c, d.localizacao_id)); ok += 1
        else:
            nao.append(c)
    _evento(con, "localizacao", d.localizacao_id, "alocacao", u["email"], {"itens": ok})
    con.commit(); con.close()
    return {"alocados": ok, "nao_encontrados": nao}


@router.get("/itens/{codigo}/localizacao")
def localizacao_do_item(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> dict | None:
    con = connect()
    r = con.execute("SELECT l.* FROM item_localizacao il JOIN localizacao_fisica l ON l.id=il.localizacao_id WHERE il.item_codigo=?", (codigo,)).fetchone()
    con.close()
    return dict(r) if r else None


# ---------------- estações e saúde do site ----------------
def _porta(ip: str, porta: int, timeout: float = 0.8) -> bool:
    if not ip:
        return False
    try:
        with socket.create_connection((ip, porta), timeout=timeout):
            return True
    except OSError:
        return False


@router.get("/estacoes")
def estacoes(u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    raiz = Path(_cfg(con, "qnap.raiz", settings.CAMP_QNAP_ROOT))
    out = {"qnap": {"raiz": str(raiz), "montado": raiz.exists()}, "maquinas": [], "pendentes": {}, "site": {}}
    if raiz.exists():
        try:
            du = shutil.disk_usage(raiz)
            out["qnap"].update({"total_gb": round(du.total / 1e9), "livre_gb": round(du.free / 1e9), "uso_pct": round(100 * du.used / du.total)})
        except OSError:
            pass
        contagem = {}
        for sj in list(raiz.glob("*/status.json")) + list(raiz.glob("*/*/status.json")):
            try:
                st = json.loads(sj.read_text(encoding="utf-8") or "{}")
                st = st.get("status") if isinstance(st, dict) else str(st)
            except Exception:  # noqa: BLE001
                st = "json_invalido"
            contagem[st or "sem_status"] = contagem.get(st or "sem_status", 0) + 1
        out["pendentes"] = contagem
    for nome, chave, porta in (("QNAP TS-932PX", "qnap.ip", 445), ("QNAP TS-231P (backup)", "qnap.backup_ip", 445), ("Estação Contex (Windows)", "contex.ip", 445), ("Mac VueScan", "vuescan.ip", 548)):
        ip = _cfg(con, chave)
        out["maquinas"].append({"nome": nome, "ip": ip or None, "online": _porta(ip, porta) if ip else None})
    s = con.execute("SELECT * FROM sincronizacao ORDER BY id DESC LIMIT 1").fetchone()
    out["site"] = {
        "ultima_sincronizacao": dict(s) if s else None,
        "divergencias": con.execute("SELECT COUNT(*) FROM divergencia_site WHERE resolvida=0").fetchone()[0],
        "escritas_pendentes": con.execute("SELECT COUNT(*) FROM divergencia_site WHERE resolvida=0 AND campo LIKE 'pendente%'").fetchone()[0],
        "rascunhos_no_site": con.execute("SELECT COUNT(*) FROM wp_item WHERE status='draft'").fetchone()[0],
        "publicados_sem_codigo": con.execute("SELECT COUNT(*) FROM wp_item WHERE status='publish' AND codigo_detectado IS NULL").fetchone()[0],
        "intervalo_sync_min": _cfg(con, "sync.intervalo_min", "15"),
    }
    url = _cfg(con, "wp.url", settings.WP_BASE_URL)
    try:
        import httpx
        t0 = time.time(); r = httpx.get(url + "/wp-json/", timeout=8, follow_redirects=True)
        out["site"]["http"] = {"status": r.status_code, "ms": round((time.time() - t0) * 1000), "ok": r.status_code == 200}
    except Exception as e:  # noqa: BLE001
        out["site"]["http"] = {"status": None, "ok": False, "erro": str(e)[:120]}
    con.close()
    return out


# ---------------- auditoria ----------------
@router.get("/eventos")
def eventos(entidade: str | None = None, ator: str | None = None, tipo: str | None = None, q: str | None = None,
            desde: str | None = None, limite: int = 200, u: dict = Depends(auth.exige("admin"))) -> dict:
    con = connect()
    sql = "SELECT * FROM evento WHERE 1=1"; p: list = []
    if entidade: sql += " AND entidade=?"; p.append(entidade)
    if ator: sql += " AND ator LIKE ?"; p.append(f"%{ator}%")
    if tipo: sql += " AND tipo LIKE ?"; p.append(f"%{tipo}%")
    if q: sql += " AND (codigo LIKE ? OR detalhe LIKE ?)"; p += [f"%{q}%", f"%{q}%"]
    if desde: sql += " AND quando >= ?"; p.append(desde)
    total = con.execute(f"SELECT COUNT(*) FROM ({sql})", p).fetchone()[0]
    rows = con.execute(sql + " ORDER BY id DESC LIMIT ?", [*p, min(limite, 1000)]).fetchall()
    facetas = {"entidades": [r[0] for r in con.execute("SELECT DISTINCT entidade FROM evento ORDER BY 1")],
               "atores": [r[0] for r in con.execute("SELECT ator FROM evento GROUP BY ator ORDER BY COUNT(*) DESC LIMIT 20")],
               "tipos": [r[0] for r in con.execute("SELECT tipo FROM evento GROUP BY tipo ORDER BY COUNT(*) DESC LIMIT 40")]}
    con.close()
    return {"total": total, "eventos": [dict(r) for r in rows], "facetas": facetas}
