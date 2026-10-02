"""Operação: painel inicial, filas de processamento (QNAP/CAMP Vision), solicitações e erros."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .config import settings
from .db import connect

router = APIRouter(prefix="/api", tags=["operacao"])
ETAPAS = ["enviado", "processando", "revisao", "rascunho", "publicado"]


def _evento(con, entidade, codigo, tipo, ator, detalhe=None):
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,?)",
                (entidade, str(codigo), tipo, ator, json.dumps(detalhe, ensure_ascii=False) if detalhe else None))


def _cfg(chave: str, padrao: str = "") -> str:
    con = connect()
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    con.close()
    return r[0] if r and r[0] else padrao


def _qnap_raiz() -> Path:
    return Path(_cfg("qnap.raiz", settings.CAMP_QNAP_ROOT))


def _qnap_prontos_raiz() -> Path:
    """Raiz final já organizada pelo CAMP Vision 2."""
    return Path(_cfg("qnap.prontos_raiz", str(_qnap_raiz())))


# ---------------- painel inicial ----------------
@router.get("/painel")
def painel(u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    q = lambda sql, *p: con.execute(sql, p).fetchone()[0]  # noqa: E731
    d = {
        "filas": {"total": q("SELECT COUNT(*) FROM lista_processamento WHERE etapa NOT IN ('publicado')"),
                  "processando": q("SELECT COUNT(*) FROM lista_processamento WHERE etapa='processando'"),
                  "revisao": q("SELECT COUNT(*) FROM lista_processamento WHERE etapa='revisao'"),
                  "erro": q("SELECT COUNT(*) FROM lista_processamento WHERE etapa='erro'")},
        "solicitacoes": {"abertas": q("SELECT COUNT(*) FROM solicitacao WHERE situacao NOT IN ('entregue','recusada')"),
                         "aguardam": q("SELECT COUNT(*) FROM solicitacao WHERE situacao IN ('aguarda_resposta','aguarda_orcamento')")},
        "erros": {"abertos": q("SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao')"),
                  "bloqueantes": q("SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao') AND gravidade='bloqueia'")},
        "fundos": {"total": q("SELECT COUNT(*) FROM fundo WHERE ativo=1"), "no_ar": q("SELECT COUNT(*) FROM fundo WHERE status_site='no_ar'"),
                   "proximo": q("SELECT codigo FROM v_proximo_fundo"), "sem_sigla": q("SELECT COUNT(*) FROM fundo WHERE sigla IS NULL AND ativo=1")},
        "projetos": {"total": q("SELECT COUNT(*) FROM projeto"), "no_ar": q("SELECT COUNT(*) FROM projeto WHERE status_site='no_ar'"),
                     "rascunho": q("SELECT COUNT(*) FROM projeto WHERE status_site='rascunho'"), "bloqueados": q("SELECT COUNT(*) FROM projeto WHERE status_site='bloqueado'")},
        "itens": {"total": q("SELECT COUNT(*) FROM item"), "no_ar": q("SELECT COUNT(*) FROM item WHERE status_site='no_ar'"),
                  "rascunho": q("SELECT COUNT(*) FROM item WHERE status_site='rascunho'"), "autoria_divergente": q("SELECT COUNT(*) FROM item WHERE autoria_divergente=1")},
        "site": {"divergencias": q("SELECT COUNT(*) FROM divergencia_site WHERE resolvida=0")},
    }
    s = con.execute("SELECT iniciada_em, terminada_em, ok, itens FROM sincronizacao ORDER BY id DESC LIMIT 1").fetchone()
    d["site"]["ultima_sincronizacao"] = dict(s) if s else None
    d["precisa_de_voce"] = []
    for r in con.execute("SELECT codigo, descricao FROM erro WHERE situacao='aberto' AND gravidade='bloqueia' ORDER BY criado_em DESC LIMIT 3"):
        d["precisa_de_voce"].append({"tipo": "erro", "titulo": r[1], "codigo": r[0], "rota": "erros"})
    for r in con.execute("SELECT id, solicitante, situacao FROM solicitacao WHERE situacao IN ('aguarda_resposta','aguarda_orcamento') ORDER BY recebida_em LIMIT 3"):
        d["precisa_de_voce"].append({"tipo": "pedido", "titulo": f"{r[1]} — {r[2].replace('_', ' ')}", "codigo": str(r[0]), "rota": "solicitacoes"})
    for r in con.execute("SELECT id, nome, projeto_codigo FROM lista_processamento WHERE etapa='revisao' ORDER BY atualizado_em LIMIT 3"):
        d["precisa_de_voce"].append({"tipo": "fila", "titulo": f"Lote {r[1]} aguarda sua revisão", "codigo": r[2], "rota": f"projeto/{r[2]}"})
    for r in con.execute("SELECT codigo, titulo FROM fundo WHERE sigla IS NULL AND ativo=1 ORDER BY codigo"):
        d["precisa_de_voce"].append({"tipo": "fundo", "titulo": f"{r[1]} sem sigla", "codigo": r[0], "rota": "fundos"})
    for r in con.execute("SELECT nome_site FROM fundo_termo_site WHERE fundo_codigo IS NULL"):
        d["precisa_de_voce"].append({"tipo": "fundo", "titulo": f"Fundo \"{r[0]}\" existe no site sem código", "codigo": None, "rota": "fundos"})
    d["por_fundo_mes"] = [dict(r) for r in con.execute("""
        SELECT p.fundo_codigo AS fundo, f.titulo, COUNT(*) AS n FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo JOIN fundo f ON f.codigo=p.fundo_codigo
        WHERE i.criado_em >= date('now','-30 days') GROUP BY 1 ORDER BY 3 DESC LIMIT 6""")]
    d["eventos"] = [dict(r) for r in con.execute("SELECT entidade, codigo, tipo, ator, quando FROM evento ORDER BY id DESC LIMIT 12")]
    con.close()
    return d



def _slug_dashboard(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _sitekit_report(wp, *, start_date: str, end_date: str, metrics: list[str], dimensions: list[str] | None = None, limit: int | None = None) -> dict:
    params: list[tuple[str, str | int | bool]] = [
        ("startDate", start_date),
        ("endDate", end_date),
    ]
    for i, m in enumerate(metrics):
        params.append((f"metrics[{i}][name]", m))
    for i, d in enumerate(dimensions or []):
        params.append((f"dimensions[{i}][name]", d))
    if dimensions:
        params.extend([
            ("orderby[0][metric][metricName]", metrics[0]),
            ("orderby[0][desc]", "true"),
        ])
    if limit:
        params.append(("limit", limit))
    r = wp.h.get("/wp-json/google-site-kit/v1/modules/analytics-4/data/report", params=params)
    if r.status_code >= 400:
        msg = ""
        try:
            j = r.json()
            msg = j.get("message") or j.get("code") or ""
        except Exception:
            msg = r.text[:180]
        raise RuntimeError(f"Site Kit Analytics recusou ({r.status_code}): {msg}")
    return r.json()


def _sitekit_json(resp) -> dict:
    try:
        j = resp.json()
        return j if isinstance(j, dict) else {"dados": j}
    except Exception:
        return {"texto": (resp.text or "")[:500]}


def _sitekit_diagnostico(wp) -> dict:
    """Explica a cadeia WP -> usuário -> Site Kit -> GA4 sem expor segredos."""
    out = {
        "wp_ok": False,
        "wp_usuario": None,
        "wp_usuario_id": None,
        "wp_roles": [],
        "sitekit_auth_status": None,
        "sitekit_autenticado": None,
        "sitekit_reautenticar": None,
        "sitekit_escopos_faltantes": [],
        "analytics_modulo": None,
        "analytics_report_status": None,
        "mensagem": None,
    }
    try:
        me = wp.quem_sou()
        out["wp_ok"] = True
        out["wp_usuario"] = me.get("slug") or me.get("username") or me.get("name")
        out["wp_usuario_id"] = me.get("id")
        out["wp_roles"] = me.get("roles") or []
    except Exception as e:
        out["mensagem"] = f"Falha ao autenticar no WordPress: {str(e)[:220]}"
        return out

    try:
        r = wp.h.get("/wp-json/google-site-kit/v1/core/user/data/authentication")
        out["sitekit_auth_status"] = r.status_code
        j = _sitekit_json(r)
        if r.status_code < 400:
            out["sitekit_autenticado"] = j.get("isAuthenticated")
            out["sitekit_reautenticar"] = j.get("needReauthenticate")
            out["sitekit_escopos_faltantes"] = j.get("unsatisfiedScopes") or []
        else:
            out["mensagem"] = j.get("message") or j.get("code") or f"Site Kit respondeu HTTP {r.status_code}"
    except Exception as e:
        out["mensagem"] = f"Falha ao consultar autenticação do Site Kit: {str(e)[:220]}"
        return out

    try:
        r = wp.h.get("/wp-json/google-site-kit/v1/core/modules/data/list")
        j = _sitekit_json(r)
        if r.status_code < 400:
            mods = j.get("modules") if isinstance(j.get("modules"), list) else j.get("dados")
            if isinstance(mods, list):
                ga = next((m for m in mods if isinstance(m, dict) and m.get("slug") == "analytics-4"), None)
                if ga:
                    out["analytics_modulo"] = {
                        k: ga.get(k) for k in ("slug", "active", "connected", "ownerID", "shareable")
                        if k in ga
                    }
    except Exception:
        pass
    return out


def _metric_values(report: dict, names: list[str]) -> dict:
    rows = report.get("rows") or []
    if not rows:
        return {n: 0 for n in names}
    vals = rows[0].get("metricValues") or []
    out = {}
    for i, n in enumerate(names):
        try:
            raw = vals[i].get("value") if i < len(vals) else 0
            out[n] = float(raw) if "." in str(raw) else int(raw or 0)
        except Exception:
            out[n] = 0
    return out


def _top_rows(report: dict) -> list[dict]:
    out = []
    dim_headers = [x.get("name") for x in report.get("dimensionHeaders") or []]
    met_headers = [x.get("name") for x in report.get("metricHeaders") or []]
    for row in report.get("rows") or []:
        dims = [x.get("value", "") for x in row.get("dimensionValues") or []]
        mets = [x.get("value", "0") for x in row.get("metricValues") or []]
        d = {k: (dims[i] if i < len(dims) else "") for i, k in enumerate(dim_headers)}
        for i, k in enumerate(met_headers):
            try:
                v = mets[i] if i < len(mets) else "0"
                d[k] = float(v) if "." in str(v) else int(v or 0)
            except Exception:
                d[k] = 0
        out.append(d)
    return out


@router.get("/analytics")
def analytics(u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Audiência do site via Google Site Kit / GA4.

    Realtime não é inventado: se a instalação não expuser um endpoint realtime,
    o campo agora volta indisponível e o restante do dashboard continua funcionando.
    """
    from .wp import WP

    hoje = datetime.utcnow().date()
    periodos = {
        "hoje": (hoje.isoformat(), hoje.isoformat()),
        "7d": ((hoje - timedelta(days=6)).isoformat(), hoje.isoformat()),
        "30d": ((hoje - timedelta(days=29)).isoformat(), hoje.isoformat()),
    }
    out = {
        "disponivel": False,
        "origem": "Google Site Kit / GA4",
        "agora": {"disponivel": False, "usuarios": None, "janela_min": 30},
        "periodos": {},
        "top_fundos": [],
        "top_projetos": [],
        "top_paginas": [],
        "erro": None,
    }
    try:
        wp = WP()
        out["diagnostico"] = _sitekit_diagnostico(wp)
        if out["diagnostico"].get("wp_ok") and out["diagnostico"].get("sitekit_autenticado") is False:
            raise RuntimeError(
                "Site Kit não está autenticado para o usuário WordPress "
                + str(out["diagnostico"].get("wp_usuario") or "usado pelo painel")
            )
        if out["diagnostico"].get("sitekit_reautenticar"):
            raise RuntimeError(
                "Site Kit exige nova autenticação para o usuário WordPress "
                + str(out["diagnostico"].get("wp_usuario") or "usado pelo painel")
            )
        for chave, (ini, fim) in periodos.items():
            rep = _sitekit_report(
                wp,
                start_date=ini,
                end_date=fim,
                metrics=["activeUsers", "screenPageViews"],
            )
            out["periodos"][chave] = _metric_values(rep, ["activeUsers", "screenPageViews"])

        ini30, fim30 = periodos["30d"]
        top = _sitekit_report(
            wp,
            start_date=ini30,
            end_date=fim30,
            metrics=["screenPageViews"],
            dimensions=["pagePath", "pageTitle"],
            limit=100,
        )
        paginas = _top_rows(top)
        out["top_paginas"] = [
            {
                "caminho": r.get("pagePath") or "",
                "titulo": r.get("pageTitle") or r.get("pagePath") or "",
                "visualizacoes": int(r.get("screenPageViews") or 0),
            }
            for r in paginas[:10]
        ]

        con = connect()
        fundos = [
            dict(r) for r in con.execute(
                "SELECT codigo, sigla, titulo FROM fundo WHERE ativo=1"
            ).fetchall()
        ]
        projetos = [
            dict(r) for r in con.execute(
                "SELECT codigo, titulo, fundo_codigo FROM projeto"
            ).fetchall()
        ]
        con.close()

        fundos_slug = {}
        for f in fundos:
            for slug in {_slug_dashboard(f["titulo"]), _slug_dashboard(f"{f['codigo']}-{f['titulo']}")}:
                if slug:
                    fundos_slug[slug] = f
        projetos_slug = {}
        for p in projetos:
            cod = p["codigo"].lower()
            projetos_slug[_slug_dashboard(f"{cod}-{p['titulo']}")] = p
            projetos_slug[_slug_dashboard(p["titulo"])] = p

        soma_fundos: dict[str, dict] = {}
        soma_projetos: dict[str, dict] = {}
        for r in paginas:
            path = (r.get("pagePath") or "").strip("/")
            views = int(r.get("screenPageViews") or 0)
            if path.startswith("acervo/arquitetos/"):
                slug = path.split("/", 2)[2].strip("/")
                achado = None
                for s, f in fundos_slug.items():
                    if slug == s or slug.endswith(s) or s.endswith(slug):
                        achado = f
                        break
                key = achado["codigo"] if achado else slug
                item = soma_fundos.setdefault(key, {
                    "codigo": achado["codigo"] if achado else None,
                    "sigla": achado["sigla"] if achado else None,
                    "titulo": achado["titulo"] if achado else slug.replace("-", " ").title(),
                    "visualizacoes": 0,
                })
                item["visualizacoes"] += views
            elif path.startswith("acervo/projetos/"):
                slug = path.split("/", 2)[2].strip("/")
                achado = None
                m = re.match(r"(f\d{3}-p\d{4})-", slug, re.I)
                if m:
                    cod = m.group(1).upper()
                    achado = next((p for p in projetos if p["codigo"] == cod), None)
                if not achado:
                    for s, p in projetos_slug.items():
                        if slug == s or slug.endswith(s) or s.endswith(slug):
                            achado = p
                            break
                key = achado["codigo"] if achado else slug
                item = soma_projetos.setdefault(key, {
                    "codigo": achado["codigo"] if achado else None,
                    "titulo": achado["titulo"] if achado else slug.replace("-", " ").title(),
                    "fundo": achado["fundo_codigo"] if achado else None,
                    "visualizacoes": 0,
                })
                item["visualizacoes"] += views

        out["top_fundos"] = sorted(soma_fundos.values(), key=lambda x: x["visualizacoes"], reverse=True)[:10]
        out["top_projetos"] = sorted(soma_projetos.values(), key=lambda x: x["visualizacoes"], reverse=True)[:10]
        out["disponivel"] = True
        out["agora"]["motivo"] = "Realtime requer acesso específico à GA4 Realtime API; o Site Kit desta integração fornece os relatórios consolidados."
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:500]
        out["erro"] = msg
        low = msg.lower()
        diag = out.get("diagnostico") or {}
        usuario = diag.get("wp_usuario")
        if not diag.get("wp_ok", True):
            out["erro_codigo"] = "wordpress_auth"
            out["acao"] = "Confira wp.usuario e wp.app_password em Configurações."
        elif diag.get("sitekit_autenticado") is False:
            out["erro_codigo"] = "sitekit_usuario_nao_conectado"
            out["acao"] = (
                f'Entre no WordPress como "{usuario}" e conecte esse usuário ao Site Kit/Google.'
                if usuario else "Conecte ao Site Kit o mesmo usuário WordPress usado pelo painel."
            )
        elif diag.get("sitekit_reautenticar") or diag.get("sitekit_escopos_faltantes"):
            out["erro_codigo"] = "sitekit_reautenticar"
            out["acao"] = (
                f'Reautentique o Google no Site Kit logado como "{usuario}" e conceda os escopos solicitados.'
                if usuario else "Reautentique o Google no Site Kit e conceda os escopos solicitados."
            )
        elif "403" in msg and ("permission" in low or "permiss" in low or "caller" in low or "site kit" in low):
            out["erro_codigo"] = "analytics_permissao_propriedade"
            out["acao"] = (
                f'O usuário WordPress "{usuario}" está conectado ao Site Kit, mas a conta Google dele não tem acesso suficiente à propriedade GA4 configurada.'
                if usuario else "A conta Google conectada ao Site Kit não tem acesso suficiente à propriedade GA4."
            )
        elif "module must be active" in low or "analytics" in low and "active" in low:
            out["erro_codigo"] = "analytics_modulo_inativo"
            out["acao"] = "Ative e configure o Google Analytics no Site Kit."
        else:
            out["erro_codigo"] = "indisponivel"
            out["acao"] = "Use o diagnóstico do Analytics para ver a resposta exata do WordPress/Site Kit."
    return out



@router.get("/analytics/diagnostico")
def analytics_diagnostico(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Teste explícito da identidade WordPress e da autorização Site Kit/GA4."""
    from .wp import WP
    try:
        wp = WP()
    except Exception as e:
        return {"ok": False, "etapa": "wordpress_config", "erro": str(e)[:500]}
    d = _sitekit_diagnostico(wp)
    hoje = datetime.utcnow().date().isoformat()
    try:
        _sitekit_report(wp, start_date=hoje, end_date=hoje, metrics=["activeUsers"])
        d["analytics_report_status"] = 200
        d["ok"] = True
        d["mensagem"] = "WordPress, Site Kit e GA4 responderam corretamente para o usuário usado pelo painel."
    except Exception as e:
        d["ok"] = False
        d["erro"] = str(e)[:500]
        m = re.search(r"\((\d{3})\)", d["erro"])
        d["analytics_report_status"] = int(m.group(1)) if m else None
    return d

# ---------------- filas ----------------
class NovaLista(BaseModel):
    nome: str
    projeto_codigo: str
    pasta_qnap: str
    folhas_esperadas: int | None = None
    lote_teste: bool = False
    autorizar_site: bool = False


@router.get("/filas")
def listar_filas(u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect()
    rows = con.execute("""SELECT l.*, p.titulo AS projeto_titulo, p.fundo_codigo, f.titulo AS fundo, p.autorizado_site, p.lote_teste,
                                 (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=l.projeto_codigo) AS folhas_painel
                          FROM lista_processamento l JOIN projeto p ON p.codigo=l.projeto_codigo JOIN fundo f ON f.codigo=p.fundo_codigo
                          ORDER BY CASE l.etapa WHEN 'erro' THEN 0 WHEN 'revisao' THEN 1 WHEN 'processando' THEN 2 WHEN 'enviado' THEN 3 WHEN 'rascunho' THEN 4 ELSE 5 END, l.atualizado_em DESC""").fetchall()
    con.close()
    return [dict(r) for r in rows]


@router.post("/filas")
def criar_fila(d: NovaLista, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    p = con.execute("SELECT * FROM projeto WHERE codigo=?", (d.projeto_codigo,)).fetchone()
    if not p:
        con.close(); raise HTTPException(404, "Projeto não existe. Crie o projeto antes de abrir a lista (o código vem da tabela de autoridade, não da pasta).")
    if not d.nome.strip() or not d.pasta_qnap.strip():
        con.close(); raise HTTPException(400, "Nome e pasta são obrigatórios")
    if con.execute("SELECT 1 FROM lista_processamento WHERE projeto_codigo=? AND etapa NOT IN ('publicado','erro')", (d.projeto_codigo,)).fetchone():
        con.close(); raise HTTPException(409, "Já existe uma lista em andamento para este projeto")
    if d.autorizar_site and u["papel"] not in ("admin", "master"):
        con.close(); raise HTTPException(403, "Autorizar publicação exige admin")
    lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, folhas_esperadas, criado_por) VALUES (?,?,?,?,?)",
                      (d.nome.strip(), d.projeto_codigo, d.pasta_qnap.strip(), d.folhas_esperadas, u["id"])).lastrowid
    if d.lote_teste or d.autorizar_site:
        con.execute("UPDATE projeto SET lote_teste=MAX(lote_teste,?), autorizado_site=MAX(autorizado_site,?) WHERE codigo=?", (int(d.lote_teste), int(d.autorizar_site), d.projeto_codigo))
    _evento(con, "lista", lid, "criada", u["email"], {"projeto": d.projeto_codigo, "nome": d.nome})
    con.commit(); con.close()
    return {"id": lid}


class EtapaFila(BaseModel):
    etapa: str
    observacao: str | None = None


@router.patch("/filas/{lid}")
def mudar_etapa(lid: int, d: EtapaFila, u: dict = Depends(auth.exige("operador"))) -> dict:
    if d.etapa not in ETAPAS + ["erro"]:
        raise HTTPException(400, "Etapa inválida")
    con = connect()
    l = con.execute("SELECT l.*, p.autorizado_site FROM lista_processamento l JOIN projeto p ON p.codigo=l.projeto_codigo WHERE l.id=?", (lid,)).fetchone()
    if not l:
        con.close(); raise HTTPException(404, "Lista não existe")
    if d.etapa in ("rascunho", "publicado"):
        if not l["autorizado_site"]:
            con.close(); raise HTTPException(400, "Projeto não autorizado para o site. Autorize na página do projeto.")
        bloq = con.execute("SELECT itens_autoria_divergente, erros_bloqueantes FROM v_bloqueios_publicacao WHERE codigo=?", (l["projeto_codigo"],)).fetchone()
        if bloq and (bloq[0] or bloq[1]):
            con.close(); raise HTTPException(400, f"Bloqueado: {bloq[0] or 0} autoria divergente, {bloq[1] or 0} erro(s) bloqueante(s)")
        if u["papel"] not in ("admin", "master"):
            con.close(); raise HTTPException(403, "Mandar para o site exige admin")
    con.execute("UPDATE lista_processamento SET etapa=?, atualizado_em=datetime('now') WHERE id=?", (d.etapa, lid))
    if d.etapa == "revisao":
        con.execute("UPDATE projeto SET status_site=CASE WHEN status_site IN ('nao_publicado','bloqueado') THEN 'em_revisao' ELSE status_site END WHERE codigo=?", (l["projeto_codigo"],))
    _evento(con, "lista", lid, f"etapa_{d.etapa}", u["email"], {"obs": d.observacao} if d.observacao else None)
    _evento(con, "projeto", l["projeto_codigo"], f"fila_{d.etapa}", u["email"])
    con.commit(); con.close()
    return {"ok": True}


@router.get("/estacoes/contexto")
def contexto_estacao(u: dict = Depends(auth.exige("operador"))) -> dict:
    """Contexto único consumido pelos apps das estações de captura.

    Os apps não mantêm cadastro próprio de fundos nem operadores.
    """
    con = connect()
    fundos = [
        dict(r) for r in con.execute(
            """SELECT codigo, sigla, titulo, data_inicio, data_fim
                 FROM fundo
                WHERE ativo=1
                ORDER BY codigo"""
        ).fetchall()
    ]
    con.close()
    return {
        "operador": {
            "id": u["id"],
            "nome": u["nome"],
            "email": u["email"],
            "papel": u["papel"],
        },
        "fundos": fundos,
        "tipos_estacao": [
            {"codigo": "foto", "nome": "Estação de fotografia", "materiais": ["fotografia", "negativo", "slide", "transparencia"]},
            {"codigo": "contex", "nome": "Estação Contex", "materiais": ["prancha", "croqui", "desenho", "documento_grande"]},
            {"codigo": "universal", "nome": "Estação universal", "materiais": ["qualquer"]},
        ],
    }


@router.post("/filas/varrer-qnap")
def varrer_qnap(u: dict = Depends(auth.exige("operador"))) -> dict:
    """Lê somente material FINAL organizado pelo CAMP Vision 2.

    Fluxo:
      estações de captura -> entrada bruta do QNAP -> CAMP Vision 2 ->
      JSON/EXIF/organização -> raiz final -> painel.

    Material na entrada bruta nunca vira fila nem aviso de publicação.
    """
    raiz = _qnap_prontos_raiz()
    entrada_txt = _cfg("qnap.entrada_captura", "")
    entrada = Path(entrada_txt) if entrada_txt else None
    if not raiz.exists():
        raise HTTPException(503, f"Pasta final do QNAP não montada em {raiz}")

    con = connect()
    novas, atualizadas, ignoradas = 0, 0, []
    vistos: set[Path] = set()

    manifestos = list(raiz.rglob("info_projeto.json")) + list(raiz.rglob("status.json"))
    for arq in manifestos:
        pasta = arq.parent.resolve()
        if pasta in vistos:
            continue
        vistos.add(pasta)

        if entrada:
            try:
                entrada_resolvida = entrada.resolve()
                if pasta == entrada_resolvida or entrada_resolvida in pasta.parents:
                    continue
            except OSError:
                pass

        try:
            info_path = pasta / "info_projeto.json"
            status_path = pasta / "status.json"
            info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() and info_path.stat().st_size else {}
            status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() and status_path.stat().st_size else {}
        except Exception as e:  # noqa: BLE001
            ignoradas.append({"pasta": str(pasta), "motivo": f"manifesto inválido: {e}"})
            continue

        if info.get("teste") or pasta.name.lower() in ("teste", "asd", "sei la"):
            ignoradas.append({"pasta": str(pasta), "motivo": "lote de teste"})
            continue

        cod = None
        for texto in (
            info.get("codigo"),
            info.get("projeto_codigo"),
            status.get("codigo") if isinstance(status, dict) else None,
            pasta.name,
            pasta.parent.name + " " + pasta.name,
        ):
            if texto:
                from .wp import detectar_codigo
                _, _, p = detectar_codigo(str(texto))
                if p:
                    cod = p
                    break
        if not cod or not con.execute("SELECT 1 FROM projeto WHERE codigo=?", (cod,)).fetchone():
            ignoradas.append({"pasta": str(pasta), "motivo": "sem código de projeto reconhecido no material final"})
            continue

        exts = {".jpg", ".jpeg", ".tif", ".tiff", ".dng", ".png"}
        arquivos = [x for x in pasta.rglob("*") if x.is_file() and x.suffix.lower() in exts]
        n_arq = len(arquivos)

        st = status.get("status") if isinstance(status, dict) else None
        nome = info.get("nome") or info.get("titulo") or pasta.name
        esperadas = info.get("folhas_esperadas") or info.get("itens_esperados") or info.get("quantidade")
        contexto = {
            "origem": "campvision2",
            "estacao": info.get("estacao") or info.get("estacao_id") or info.get("origem_estacao"),
            "tipo_estacao": info.get("tipo_estacao"),
            "operador": info.get("operador") or info.get("operador_nome"),
            "operador_email": info.get("operador_email"),
            "fundo_codigo": info.get("fundo_codigo") or info.get("fundo"),
            "manifesto": info,
            "status": status,
        }

        ex = con.execute(
            "SELECT id, etapa, folhas_encontradas FROM lista_processamento WHERE pasta_qnap=? ORDER BY id DESC LIMIT 1",
            (str(pasta),),
        ).fetchone()

        if ex:
            if ex["etapa"] not in ("publicado", "rascunho") and ex["etapa"] != "revisao":
                con.execute(
                    "UPDATE lista_processamento SET etapa='revisao', status_json=?, folhas_encontradas=?, resultado=?, atualizado_em=datetime('now') WHERE id=?",
                    (st or "pronto_campvision2", n_arq, json.dumps(contexto, ensure_ascii=False), ex["id"]),
                )
                _evento(con, "lista", ex["id"], "material_pronto", "campvision2", {"pasta": str(pasta), "arquivos": n_arq})
                atualizadas += 1
            else:
                con.execute(
                    "UPDATE lista_processamento SET folhas_encontradas=?, status_json=?, resultado=?, atualizado_em=datetime('now') WHERE id=?",
                    (n_arq, st or "pronto_campvision2", json.dumps(contexto, ensure_ascii=False), ex["id"]),
                )
        else:
            lid = con.execute(
                """INSERT INTO lista_processamento
                   (nome, projeto_codigo, pasta_qnap, folhas_esperadas, folhas_encontradas, etapa, status_json, resultado)
                   VALUES (?,?,?,?,?,'revisao',?,?)""",
                (
                    nome,
                    cod,
                    str(pasta),
                    esperadas,
                    n_arq,
                    st or "pronto_campvision2",
                    json.dumps(contexto, ensure_ascii=False),
                ),
            ).lastrowid
            _evento(con, "lista", lid, "material_pronto", "campvision2", {"pasta": str(pasta), "arquivos": n_arq})
            _evento(con, "projeto", cod, "material_novo_pronto", "campvision2", contexto)
            novas += 1

    con.commit()
    con.close()
    return {
        "novas": novas,
        "atualizadas": atualizadas,
        "ignoradas": ignoradas[:50],
        "raiz_final": str(raiz),
        "entrada_bruta": str(entrada) if entrada else None,
        "mensagem": "Somente material já organizado pelo CAMP Vision 2 é considerado pronto.",
    }


# ---------------- solicitações ----------------
class NovaSolicitacao(BaseModel):
    solicitante: str
    email: str | None = None
    instituicao: str | None = None
    finalidade: str
    detalhe: str | None = None
    origem: str = "email"
    itens: list[dict] = []           # [{codigo, formato}]
    condicoes_uso: str | None = None


class EdicaoSolicitacao(BaseModel):
    situacao: str | None = None
    condicoes_uso: str | None = None
    valor: float | None = None
    detalhe: str | None = None
    responsavel: int | None = None


SITUACOES = ["aguarda_resposta", "aguarda_orcamento", "aguarda_credito", "em_preparacao", "entregue", "recusada"]


@router.get("/solicitacoes")
def listar_solicitacoes(situacao: str | None = None, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    sql = """SELECT s.*, us.nome AS responsavel_nome, (SELECT GROUP_CONCAT(codigo || ' (' || formato || ')', ' · ') FROM solicitacao_item si WHERE si.solicitacao_id=s.id) AS itens
             FROM solicitacao s LEFT JOIN usuario us ON us.id=s.responsavel"""
    p: list = []
    if situacao == "abertas": sql += " WHERE s.situacao NOT IN ('entregue','recusada')"
    elif situacao and situacao != "todos": sql += " WHERE s.situacao=?"; p.append(situacao)
    rows = con.execute(sql + " ORDER BY s.recebida_em DESC", p).fetchall()
    resumo = {r[0]: r[1] for r in con.execute("SELECT situacao, COUNT(*) FROM solicitacao GROUP BY 1")}
    top = con.execute("""SELECT substr(si.codigo,1,4) AS fundo, COUNT(*) AS n FROM solicitacao_item si GROUP BY 1 ORDER BY 2 DESC LIMIT 1""").fetchone()
    media = con.execute("SELECT AVG(julianday(entregue_em)-julianday(recebida_em)) FROM solicitacao WHERE entregue_em IS NOT NULL").fetchone()[0]
    con.close()
    return {"itens": [dict(r) for r in rows], "resumo": resumo, "fundo_mais_pedido": dict(top) if top else None, "dias_medio_entrega": round(media, 1) if media else None}


@router.post("/solicitacoes")
def criar_solicitacao(d: NovaSolicitacao, u: dict = Depends(auth.exige("operador"))) -> dict:
    if d.finalidade not in ("publicacao", "pesquisa", "editorial", "familia", "exposicao", "outro"):
        raise HTTPException(400, "Finalidade inválida")
    if not d.solicitante.strip():
        raise HTTPException(400, "Informe quem pediu")
    con = connect()
    sid = con.execute("INSERT INTO solicitacao (solicitante, email, instituicao, finalidade, detalhe, origem, condicoes_uso, responsavel) VALUES (?,?,?,?,?,?,?,?)",
                      (d.solicitante.strip(), d.email, d.instituicao, d.finalidade, d.detalhe, d.origem, d.condicoes_uso, u["id"])).lastrowid
    for it in d.itens:
        cod = (it.get("codigo") or "").strip().upper(); fmt = it.get("formato") or "jpg_3000"
        if cod and fmt in ("tif", "jpg_3000", "jpg_original", "pdf"):
            con.execute("INSERT OR IGNORE INTO solicitacao_item (solicitacao_id, codigo, formato) VALUES (?,?,?)", (sid, cod, fmt))
    _evento(con, "solicitacao", sid, "criada", u["email"], {"solicitante": d.solicitante})
    con.commit(); con.close()
    return {"id": sid}


@router.patch("/solicitacoes/{sid}")
def editar_solicitacao(sid: int, d: EdicaoSolicitacao, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    s = con.execute("SELECT * FROM solicitacao WHERE id=?", (sid,)).fetchone()
    if not s:
        con.close(); raise HTTPException(404, "Pedido não existe")
    campos, vals, mud = [], [], {}
    if d.situacao is not None:
        if d.situacao not in SITUACOES:
            con.close(); raise HTTPException(400, "Situação inválida")
        campos.append("situacao=?"); vals.append(d.situacao); mud["situacao"] = d.situacao
        if d.situacao == "entregue":
            campos.append("entregue_em=datetime('now')"); con.execute("UPDATE solicitacao_item SET entregue=1 WHERE solicitacao_id=?", (sid,))
    for k in ("condicoes_uso", "valor", "detalhe", "responsavel"):
        v = getattr(d, k)
        if v is not None:
            campos.append(f"{k}=?"); vals.append(v); mud[k] = v
    if campos:
        con.execute(f"UPDATE solicitacao SET {', '.join(campos)} WHERE id=?", (*vals, sid))
        _evento(con, "solicitacao", sid, "editada", u["email"], mud)
        con.commit()
    con.close()
    return {"ok": True}


# ---------------- erros ----------------
class NovoErro(BaseModel):
    gravidade: str
    categoria: str
    codigo: str
    descricao: str
    origem: str = "operador"
    relatado_por: str | None = None


class EdicaoErro(BaseModel):
    situacao: str | None = None
    resolucao: str | None = None
    gravidade: str | None = None


GRAV = ("bloqueia", "corrigir", "aviso")
CATS = ("autoria_divergente", "projeto_errado", "duplicata", "orientacao", "espelhado", "codigo", "metadado", "credito", "arquivo_corrompido", "outro")


@router.get("/erros")
def listar_erros(situacao: str | None = "abertos", u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect()
    sql = "SELECT * FROM erro"; p: list = []
    if situacao == "abertos": sql += " WHERE situacao IN ('aberto','em_correcao')"
    elif situacao and situacao != "todos": sql += " WHERE situacao=?"; p.append(situacao)
    rows = con.execute(sql + " ORDER BY CASE gravidade WHEN 'bloqueia' THEN 0 WHEN 'corrigir' THEN 1 ELSE 2 END, criado_em DESC", p).fetchall()
    con.close()
    return [dict(r) for r in rows]


@router.post("/erros")
def criar_erro(d: NovoErro, u: dict = Depends(auth.exige("operador"))) -> dict:
    if d.gravidade not in GRAV or d.categoria not in CATS:
        raise HTTPException(400, "Gravidade ou categoria inválida")
    if not d.codigo.strip() or not d.descricao.strip():
        raise HTTPException(400, "Código e descrição são obrigatórios")
    con = connect()
    cod = d.codigo.strip().upper()
    eid = con.execute("INSERT INTO erro (gravidade, categoria, origem, codigo, descricao, relatado_por) VALUES (?,?,?,?,?,?)",
                      (d.gravidade, d.categoria, d.origem, cod, d.descricao.strip(), d.relatado_por or u["email"])).lastrowid
    if d.categoria == "autoria_divergente" and cod.count("-") == 4:
        con.execute("UPDATE item SET autoria_divergente=1 WHERE codigo=?", (cod,))
    if d.gravidade == "bloqueia":
        pc = cod[:10] if len(cod) >= 10 else None
        if pc:
            con.execute("UPDATE projeto SET status_site='bloqueado' WHERE codigo=? AND status_site IN ('nao_publicado','em_revisao','rascunho')", (pc,))
    _evento(con, "erro", eid, "criado", u["email"], {"codigo": cod, "gravidade": d.gravidade})
    con.commit(); con.close()
    return {"id": eid}


@router.patch("/erros/{eid}")
def editar_erro(eid: int, d: EdicaoErro, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    e = con.execute("SELECT * FROM erro WHERE id=?", (eid,)).fetchone()
    if not e:
        con.close(); raise HTTPException(404, "Erro não existe")
    campos, vals = [], []
    if d.situacao:
        if d.situacao not in ("aberto", "em_correcao", "corrigido", "fechado", "ignorado"):
            con.close(); raise HTTPException(400, "Situação inválida")
        if d.situacao in ("corrigido", "fechado", "ignorado") and not (d.resolucao or e["resolucao"]):
            con.close(); raise HTTPException(400, "Descreva a resolução antes de fechar")
        campos.append("situacao=?"); vals.append(d.situacao)
        if d.situacao in ("corrigido", "fechado", "ignorado"):
            campos.append("resolvido_em=datetime('now')")
            if e["categoria"] == "autoria_divergente" and d.situacao != "ignorado":
                con.execute("UPDATE item SET autoria_divergente=0 WHERE codigo=?", (e["codigo"],))
            pc = e["codigo"][:10]
            resto = con.execute("SELECT COUNT(*) FROM erro WHERE (codigo=? OR codigo LIKE ?) AND gravidade='bloqueia' AND situacao IN ('aberto','em_correcao') AND id<>?", (pc, pc + "-%", eid)).fetchone()[0]
            if not resto:
                con.execute("UPDATE projeto SET status_site='em_revisao' WHERE codigo=? AND status_site='bloqueado'", (pc,))
    if d.resolucao is not None: campos.append("resolucao=?"); vals.append(d.resolucao)
    if d.gravidade:
        if d.gravidade not in GRAV: con.close(); raise HTTPException(400, "Gravidade inválida")
        campos.append("gravidade=?"); vals.append(d.gravidade)
    if campos:
        con.execute(f"UPDATE erro SET {', '.join(campos)} WHERE id=?", (*vals, eid))
        _evento(con, "erro", eid, "editado", u["email"], {"situacao": d.situacao})
        con.commit()
    con.close()
    return {"ok": True}
