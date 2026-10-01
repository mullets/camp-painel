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
from .log_tecnico import LOG_FILE, ler_logs

router = APIRouter(prefix="/api", tags=["gestao"])


def _evento(con, entidade, codigo, tipo, ator, detalhe=None):
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)",
                (entidade, str(codigo), tipo, ator, json.dumps(detalhe, ensure_ascii=False) if detalhe else None))


def _cfg(con, chave, padrao=""):
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return r[0] if r and r[0] else padrao



# ---------------- busca global ----------------
@router.get("/busca")
def busca_global(q: str, limite: int = 20, u: dict = Depends(auth.exige("leitura"))) -> dict:
    termo = (q or "").strip()
    if not termo:
        return {"q": termo, "resultados": []}
    limite = max(5, min(limite, 40))
    like = f"%{termo}%"
    prefix = f"{termo}%"
    con = connect()
    resultados = []

    for r in con.execute("""SELECT codigo, sigla, titulo FROM fundo
                            WHERE ativo=1 AND (codigo LIKE ? OR sigla LIKE ? OR titulo LIKE ?)
                            LIMIT 10""", (like, like, like)).fetchall():
        exato = termo.upper() in (str(r["codigo"]).upper(), str(r["sigla"] or "").upper())
        prefixo = str(r["codigo"]).upper().startswith(termo.upper()) or str(r["titulo"]).lower().startswith(termo.lower())
        resultados.append({"tipo": "fundo", "codigo": r["codigo"], "titulo": r["titulo"],
                           "subtitulo": r["sigla"] or "", "rota": f"fundo/{r['codigo']}",
                           "score": 0 if exato else 1 if prefixo else 2})

    for r in con.execute("""SELECT p.codigo, p.titulo, p.fundo_codigo, p.cidade
                              FROM projeto p
                             WHERE p.codigo LIKE ? OR p.titulo LIKE ? OR p.cidade LIKE ?
                             LIMIT 12""", (like, like, like)).fetchall():
        exato = str(r["codigo"]).upper() == termo.upper()
        prefixo = str(r["codigo"]).upper().startswith(termo.upper()) or str(r["titulo"]).lower().startswith(termo.lower())
        resultados.append({"tipo": "projeto", "codigo": r["codigo"], "titulo": r["titulo"],
                           "subtitulo": " · ".join(x for x in (r["fundo_codigo"], r["cidade"]) if x),
                           "rota": f"projeto/{r['codigo']}", "score": 0 if exato else 1 if prefixo else 2})

    for r in con.execute("""SELECT codigo, titulo, projeto_codigo, tipo_documento
                              FROM item
                             WHERE codigo LIKE ? OR titulo LIKE ?
                             LIMIT 10""", (like, like)).fetchall():
        exato = str(r["codigo"]).upper() == termo.upper()
        prefixo = str(r["codigo"]).upper().startswith(termo.upper())
        resultados.append({"tipo": "documento", "codigo": r["codigo"], "titulo": r["titulo"] or r["tipo_documento"] or "Documento",
                           "subtitulo": r["projeto_codigo"], "rota": f"item/{r['codigo']}",
                           "score": 0 if exato else 1 if prefixo else 2})

    for r in con.execute("""SELECT DISTINCT a.id, a.forma_autorizada, a.tipo
                              FROM agente a
                              LEFT JOIN agente_forma_variante v ON v.agente_id=a.id
                             WHERE a.forma_autorizada LIKE ? OR v.forma LIKE ?
                             LIMIT 10""", (like, like)).fetchall():
        prefixo = str(r["forma_autorizada"]).lower().startswith(termo.lower())
        resultados.append({"tipo": "arquiteto", "codigo": str(r["id"]), "titulo": r["forma_autorizada"],
                           "subtitulo": str(r["tipo"]).replace("_", " "), "rota": "arquitetos",
                           "filtro": r["forma_autorizada"], "score": 1 if prefixo else 2})

    con.close()
    ordem_tipo = {"fundo": 0, "projeto": 1, "documento": 2, "arquiteto": 3}
    resultados.sort(key=lambda x: (x["score"], ordem_tipo.get(x["tipo"], 9), x["titulo"].lower()))
    for x in resultados:
        x.pop("score", None)
    return {"q": termo, "resultados": resultados[:limite]}

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
    con = connect()
    r = con.execute("SELECT * FROM direitos_fundo WHERE fundo_codigo=?", (codigo,)).fetchone()
    f = con.execute("SELECT titulo FROM fundo WHERE codigo=?", (codigo,)).fetchone()
    con.close()
    d = dict(r) if r else {"fundo_codigo": codigo, "situacao": "nao_definida", "resolucao_max": "jpg_3000"}
    nome = f["titulo"] if f else codigo
    # Modelo operacional derivado do Termo de Doação padrão CAMP.
    # Não muda a situação jurídica: só é autorizado se houver termo/documento registrado.
    d["modelo_padrao"] = {
        "nome": "Termo de Doação de Acervo — CAMP",
        "propriedade_fisica_digital": True,
        "preservacao_higienizacao_catalogacao": True,
        "digitalizacao": True,
        "restauracao_quando_necessaria": True,
        "consulta_publica": True,
        "pesquisa": True,
        "exposicoes": True,
        "publicacoes": True,
        "redes_sociais_plataformas_digitais": True,
        "uso_educativo_cientifico": True,
        "uso_editorial": True,
        "uso_comercial_reproducoes": True,
        "licenciamento_cultural": True,
        "identificacao_doador_autor": True,
        "irrevogavel_irretratavel": True,
        "sem_contrapartida_financeira": True,
        "credito_sugerido": f"Acervo {nome} / CAMP",
        "validade_padrao": "sem prazo",
    }
    return d


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

@router.get("/projetos/{codigo}/volumes")
def volumes_do_projeto(codigo: str, u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    """Embalagens/localizações físicas de um projeto, com contagem real de documentos."""
    con = connect()
    rows = con.execute("""
        SELECT l.id, l.tipo, l.identificador, l.descricao,
               COUNT(DISTINCT il.item_codigo) AS quantidade_documentos
          FROM item_localizacao il
          JOIN item i ON i.codigo=il.item_codigo
          JOIN localizacao_fisica l ON l.id=il.localizacao_id
         WHERE i.projeto_codigo=?
         GROUP BY l.id, l.tipo, l.identificador, l.descricao
         ORDER BY l.id
    """, (codigo,)).fetchall()
    con.close()
    return [
        {**dict(r), "volume": n, "total_volumes": len(rows)}
        for n, r in enumerate(rows, 1)
    ]



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
    entrada_txt = _cfg(con, "qnap.entrada_captura", "")
    prontos_txt = _cfg(con, "qnap.prontos_raiz", "")
    entrada = Path(entrada_txt) if entrada_txt else None
    prontos = Path(prontos_txt) if prontos_txt else raiz

    out = {
        "qnap": {
            "raiz": str(raiz),
            "montado": raiz.exists(),
            "entrada_captura": str(entrada) if entrada else None,
            "entrada_montada": entrada.exists() if entrada else None,
            "prontos_raiz": str(prontos),
            "prontos_montada": prontos.exists(),
        },
        "maquinas": [],
        "pipeline": {
            "entrada_bruta": 0,
            "prontos": 0,
            "aguardando_revisao": 0,
        },
        "site": {},
    }

    if raiz.exists():
        try:
            du = shutil.disk_usage(raiz)
            out["qnap"].update({
                "total_gb": round(du.total / 1e9),
                "livre_gb": round(du.free / 1e9),
                "uso_pct": round(100 * du.used / du.total),
            })
        except OSError:
            pass

    if entrada and entrada.exists():
        try:
            out["pipeline"]["entrada_bruta"] = sum(
                1 for p in entrada.iterdir() if not p.name.startswith(".")
            )
        except OSError:
            pass

    if prontos.exists():
        try:
            pastas = {p.parent.resolve() for p in prontos.rglob("info_projeto.json")}
            pastas |= {p.parent.resolve() for p in prontos.rglob("status.json")}
            out["pipeline"]["prontos"] = len(pastas)
        except OSError:
            pass

    out["pipeline"]["aguardando_revisao"] = con.execute(
        "SELECT COUNT(*) FROM lista_processamento WHERE etapa='revisao'"
    ).fetchone()[0]

    heartbeats = {r["estacao_id"]: dict(r) for r in con.execute("""
        SELECT *,
               CAST((julianday('now') - julianday(atualizado_em)) * 86400 AS INTEGER) AS idade_segundos
          FROM estacao_heartbeat
    """).fetchall()}
    estacoes_cfg = [
        ("foto1", "Estação Foto 1", "estacao.foto1.ip", 548, "foto",
         "Fotos, negativos, slides, transparências"),
        ("foto2", "Estação Foto 2", "estacao.foto2.ip", 548, "foto",
         "Fotos, negativos, slides, transparências"),
        ("contex1", "Estação Contex", "estacao.contex.ip", 445, "contex",
         "Pranchas, croquis, desenhos e materiais grandes"),
        ("universal1", "Estação Universal 1", "estacao.universal1.ip", 548, "universal",
         "Qualquer material; operador escolhe tipo e informa dados"),
        ("universal2", "Estação Universal 2", "estacao.universal2.ip", 548, "universal",
         "Qualquer material; operador escolhe tipo e informa dados"),
        (None, "CAMP Vision 2", "campvision2.ip", 22, "processamento",
         "Lê imagens, gera JSON/EXIF e organiza na pasta final"),
        (None, "QNAP TS-932PX", "qnap.ip", 445, "armazenamento",
         "Entrada bruta e acervo final"),
    ]
    for estacao_id, nome, chave, porta, tipo, funcao in estacoes_cfg:
        ip = _cfg(con, chave)
        hb = heartbeats.get(estacao_id) if estacao_id else None
        app_online = bool(hb and hb["idade_segundos"] is not None and hb["idade_segundos"] <= 75)
        out["maquinas"].append({
            "estacao_id": estacao_id,
            "nome": nome,
            "tipo": tipo,
            "funcao": funcao,
            "ip": ip or None,
            "online": _porta(ip, porta) if ip else None,
            "app_online": app_online if estacao_id else None,
            "app_estado": hb.get("estado") if hb else None,
            "app_versao": hb.get("versao") if hb else None,
            "app_hostname": hb.get("hostname") if hb else None,
            "app_ip_local": hb.get("ip_local") if hb else None,
            "app_operador": hb.get("operador") if hb else None,
            "app_fundo": hb.get("fundo_codigo") if hb else None,
            "app_projeto": hb.get("projeto_codigo") if hb else None,
            "app_ultimo_erro": hb.get("ultimo_erro") if hb else None,
            "app_heartbeat_em": hb.get("atualizado_em") if hb else None,
            "app_heartbeat_idade_segundos": hb.get("idade_segundos") if hb else None,
        })

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
        t0 = time.time()
        r = httpx.get(url + "/wp-json/", timeout=8, follow_redirects=True)
        out["site"]["http"] = {
            "status": r.status_code,
            "ms": round((time.time() - t0) * 1000),
            "ok": r.status_code == 200,
        }
    except Exception as e:  # noqa: BLE001
        out["site"]["http"] = {"status": None, "ok": False, "erro": str(e)[:120]}
    con.close()
    return out



# ---------------- logs técnicos ----------------
@router.get("/logs")
def logs_tecnicos(nivel: str | None = None, q: str | None = None, limite: int = 200,
                  u: dict = Depends(auth.exige("admin"))) -> dict:
    """Últimos eventos técnicos. Nunca inclui corpo de requisição, senha, cookie ou token."""
    itens = ler_logs(limite=min(limite, 1000), nivel=nivel, q=q)
    resumo = {
        "total_retornado": len(itens),
        "erros": sum(1 for x in itens if x.get("nivel") == "ERROR"),
        "avisos": sum(1 for x in itens if x.get("nivel") == "WARNING"),
        "arquivo": str(LOG_FILE),
    }
    return {"resumo": resumo, "itens": itens}

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
