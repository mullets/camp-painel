"""Operação: painel inicial, filas de processamento (QNAP/CAMP Vision), solicitações e erros."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
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
def painel(ordem: str = "padrao", u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    q = lambda sql, *p: con.execute(sql, p).fetchone()[0]  # noqa: E731
    # UX-05: os números vêm da fonte única (contagens.py); os campos antigos continuam, com os MESMOS valores das outras telas
    from . import contagens as cg
    from . import pendencias as pd
    n = pd.contar_pendencias(con, com_listas=True, usuario_id=u["id"])
    cont = cg.medir(con, n=n)
    et, ns = cont["lotes_etapa"], cg.no_site(con)
    d = {
        "filas": {"total": sum(v for k, v in et.items() if k != "publicado"), "processando": et["processando"], "revisao": et["revisao"], "erro": et["erro"]},
        "solicitacoes": {"abertas": cont["pedidos_abertos"], "aguardam": cont["pedidos_aguardando"]},
        "erros": {"abertos": cont["erros_abertos"], "bloqueantes": cont["erros_bloqueantes"]},
        "fundos": {"total": ns["fundos"]["total"], "no_ar": ns["fundos"]["no_ar"],
                   "proximo": q("SELECT codigo FROM v_proximo_fundo"), "sem_sigla": q("SELECT COUNT(*) FROM fundo WHERE sigla IS NULL AND ativo=1")},
        "projetos": {"total": ns["projetos"]["total"], "no_ar": ns["projetos"]["no_ar"],
                     "rascunho": q(f"SELECT COUNT(*) FROM projeto WHERE status_site='rascunho' AND {cg.PROJETO_VIVO}"),
                     "bloqueados": q(f"SELECT COUNT(*) FROM projeto WHERE status_site='bloqueado' AND {cg.PROJETO_VIVO}")},
        "itens": {"total": ns["folhas"]["total"], "no_ar": ns["folhas"]["no_ar"],
                  "rascunho": q("SELECT COUNT(*) FROM item WHERE status_site='rascunho'"), "autoria_divergente": q("SELECT COUNT(*) FROM item WHERE autoria_divergente=1")},
        "site": {"divergencias": cont["site_divergencias"]},
        "decisoes": {"pendentes": cont["decisoes"]},
        "contagens": cont,
    }
    s = con.execute("SELECT iniciada_em, terminada_em, ok, itens FROM sincronizacao ORDER BY id DESC LIMIT 1").fetchone()
    d["site"]["ultima_sincronizacao"] = dict(s) if s else None
    d["precisa_de_voce"] = []
    from .decisoes import pergunta as _pergunta
    for r in con.execute("SELECT * FROM decisao WHERE situacao='pendente' ORDER BY criada_em, id LIMIT 4"):
        d["precisa_de_voce"].append({"tipo": "decisao", "id": r["id"], "titulo": _pergunta(r), "codigo": f"decisão {r['id']}" + (" · o CAMP Vision está esperando" if r["origem"] == "estacao" else ""), "rota": None})
    for r in con.execute("SELECT codigo, descricao FROM erro WHERE situacao='aberto' AND gravidade='bloqueia' ORDER BY criado_em DESC LIMIT 3"):
        d["precisa_de_voce"].append({"tipo": "erro", "titulo": r[1], "codigo": r[0], "rota": "erros"})
    for r in con.execute("SELECT id, solicitante, situacao FROM solicitacao WHERE situacao IN ('aguarda_resposta','aguarda_orcamento') ORDER BY recebida_em LIMIT 3"):
        d["precisa_de_voce"].append({"tipo": "pedido", "titulo": f"{r[1]} — {r[2].replace('_', ' ')}", "codigo": str(r[0]), "rota": "solicitacoes"})
    for r in con.execute("SELECT id, nome, projeto_codigo FROM lista_processamento WHERE descartado_em IS NULL AND etapa='revisao' ORDER BY atualizado_em LIMIT 3"):
        d["precisa_de_voce"].append({"tipo": "fila", "titulo": f"Lote {r[1]} aguarda sua revisão", "codigo": r[2], "rota": f"projeto/{r[2]}"})
    for r in con.execute("SELECT codigo, titulo FROM fundo WHERE sigla IS NULL AND ativo=1 ORDER BY codigo"):
        d["precisa_de_voce"].append({"tipo": "fundo", "titulo": f"{r[1]} sem sigla", "codigo": r[0], "rota": "fundos"})
    for r in con.execute("SELECT nome_site FROM fundo_termo_site WHERE fundo_codigo IS NULL"):
        d["precisa_de_voce"].append({"tipo": "fundo", "titulo": f"Fundo \"{r[0]}\" existe no site sem código", "codigo": None, "rota": "fundos"})
    d["por_fundo_mes"] = [dict(r) for r in con.execute("""
        SELECT p.fundo_codigo AS fundo, f.titulo, COUNT(*) AS n FROM item i JOIN projeto p ON p.codigo=i.projeto_codigo JOIN fundo f ON f.codigo=p.fundo_codigo
        WHERE i.criado_em >= date('now','-30 days') GROUP BY 1 ORDER BY 3 DESC LIMIT 6""")]
    d["eventos"] = [dict(r) for r in con.execute("SELECT entidade, codigo, tipo, ator, quando FROM evento ORDER BY id DESC LIMIT 12")]
    # H6b: o que fazer agora, o caminho do material, o quanto está no site e as frases do dia, TODOS da fonte única (pendencias)
    d["pendencias"] = dict(cont)          # UX-05: exatamente o que /api/pendencias devolve (a mesma função, contagens.medir)
    d["tarefas"] = pd.tarefas(con, u["papel"], n, usuario_id=u["id"], ordem=ordem)   # UX-09: ?ordem=parado = mais parado primeiro
    d["caminho"] = pd.caminho(con, n)
    d["no_site"] = pd.no_site(con)
    d["hoje_frases"] = pd.atividade_hoje(con)
    d["alertas"] = pd.alertas_criticos(con) if u["papel"] != "leitura" else []
    d["analytics_ligado"] = analytics_ligado(con)          # UX-12: desligado, a tela nem chama /api/analytics
    con.close()
    return d


@router.get("/painel/pendencias")
@router.get("/pendencias")
def pendencias(u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Só os números (contadores do menu, Filas e painel): a MESMA função do painel inicial."""
    from .contagens import medir
    con = connect()
    try:
        return medir(con, usuario_id=u.get("id"))   # 23/10: o "Agora não" de um lote tira o lote da contagem desta pessoa; UX-05: + no site, etapas, medido_em
    finally:
        con.close()


@router.get("/painel/ritmo")
def painel_ritmo(dias: int = 14, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """H6b: folhas conferidas/importadas/enviadas por dia, média e previsão de quando a fila de conferência zera."""
    from .pendencias import ritmo
    con = connect()
    try:
        return ritmo(con, dias)
    finally:
        con.close()



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
        out["mensagem"] = f"Falha ao autenticar no site: {str(e)[:220]}"
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


_ANALYTICS_CACHE: dict = {"t": 0.0, "v": None}


def analytics_ligado(con) -> bool:
    """UX-12: o Google Analytics está ligado ao painel? GA4 direto (as duas chaves preenchidas) ou o Site Kit pedido (analytics.site_kit=1).
    Só lê a configuração: nada de rede."""
    v = {r[0]: (r[1] or "").strip() for r in con.execute(
        "SELECT chave, valor FROM configuracao WHERE chave IN ('ga4.propriedade','ga4.conta_servico','analytics.site_kit')")}
    return bool(v.get("ga4.propriedade") and v.get("ga4.conta_servico")) or v.get("analytics.site_kit") == "1"


def _analytics_desligado() -> dict:
    return {"disponivel": False, "desligado": True, "origem": "Google Site Kit / GA4",
            "agora": {"disponivel": False, "usuarios": None, "janela_min": 30}, "periodos": {},
            "top_fundos": [], "top_projetos": [], "top_paginas": [], "erro": None,
            "acao": "Para ver as visitas, preencha ga4.propriedade e ga4.conta_servico em Configurações (ou analytics.site_kit = 1)."}


@router.get("/analytics")
def analytics(fresco: int = 0, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """Audiência (cache de 10 min quando deu certo, 60 s quando deu erro: a consulta ao Site Kit leva segundos e antes rodava a cada abertura do painel).
    UX-12: com o GA desligado responde na hora, sem ir ao site nem ao Google."""
    import time as _t
    con = connect()
    try:
        ligado = analytics_ligado(con)
    finally:
        con.close()
    if not ligado:
        return _analytics_desligado()
    c = _ANALYTICS_CACHE
    if not fresco and c["v"] is not None and _t.monotonic() - c["t"] < (600 if c["v"].get("disponivel") else 60):
        return c["v"]
    v = _analytics_calcular()
    c["t"], c["v"] = _t.monotonic(), v
    return v


# O Google devolve 403 "não concedeu todas as permissões durante a configuração" quando, ao conectar o Site Kit,
# a caixa de ler os dados do Analytics ficou desmarcada na tela de consentimento.
# 21/10 (Rafa): quem usa o painel não usa o WordPress. O que só se resolve no site vira "avise quem cuida do site", com o detalhe para essa pessoa.
ACAO_PERMISSOES_SITEKIT = ('Pelo painel: preencha ga4.propriedade e ga4.conta_servico em Configurações (não depende do site). '
                           'Ou avise quem cuida do site: o Google do Site Kit (usuário "{u}") precisa da permissão '
                           '"Ver e baixar seus dados do Google Analytics". Depois clique em Diagnosticar de novo.')


def _analytics_calcular() -> dict:
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
    from . import ga4_direto
    direto = None
    try:
        c0 = connect()
        try:
            cfg = ga4_direto.configurado(c0)
        finally:
            c0.close()
        if cfg:   # caminho preferido: GA4 direto pela conta de serviço (não depende da conexão do Site Kit)
            direto = ga4_direto.GA4(cfg)
            out["origem"] = "Google Analytics 4 (direto, conta de serviço)"
            relatorio = direto.relatorio
        else:
            wp = WP()
            relatorio = lambda **k: _sitekit_report(wp, **k)  # noqa: E731
    except Exception as e:  # noqa: BLE001
        out["erro"], out["erro_codigo"], out["acao"] = str(e)[:500], "ga4_config", "Confira ga4.propriedade e ga4.conta_servico em Configurações."
        return out
    try:
        if direto:
            out["diagnostico"] = {"via": "ga4_direto", "conta": direto.conta.get("client_email"), "propriedade": direto.prop}
        else:
            out["diagnostico"] = _sitekit_diagnostico(wp)
            out["diagnostico"]["via"] = "site_kit"
    except Exception as e:  # noqa: BLE001
        out["diagnostico"] = {"via": "site_kit", "mensagem": str(e)[:300]}
    try:
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
            rep = relatorio(
                start_date=ini,
                end_date=fim,
                metrics=["activeUsers", "screenPageViews"],
            )
            out["periodos"][chave] = _metric_values(rep, ["activeUsers", "screenPageViews"])

        ini30, fim30 = periodos["30d"]
        top = relatorio(
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
        if direto:   # com a conta de serviço o "agora" (últimos 30 min) vem da Realtime API
            try:
                out["agora"].update(disponivel=True, usuarios=direto.agora())
            except Exception as e:  # noqa: BLE001
                out["agora"]["motivo"] = f"Realtime indisponível: {str(e)[:160]}"
        else:
            out["agora"]["motivo"] = "Realtime requer acesso específico à GA4 Realtime API; o Site Kit desta integração fornece os relatórios consolidados."
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:500]
        out["erro"] = msg
        low = msg.lower()
        diag = out.get("diagnostico") or {}
        usuario = diag.get("wp_usuario")
        if direto:
            out["erro_codigo"] = "ga4_direto_permissao" if "não tem acesso" in msg else "ga4_direto"
            out["acao"] = msg if "não tem acesso" in msg else "Confira ga4.propriedade e ga4.conta_servico em Configurações (Diagnosticar mostra a resposta do Google)."
        elif not diag.get("wp_ok", True):
            out["erro_codigo"] = "wordpress_auth"
            out["acao"] = "Confira wp.usuario e wp.app_password em Configurações."
        elif diag.get("sitekit_autenticado") is False:
            out["erro_codigo"] = "sitekit_usuario_nao_conectado"
            out["acao"] = (
                f'Avise quem cuida do site: o usuário "{usuario}" do painel precisa estar conectado ao Site Kit/Google. Ou use ga4.propriedade e ga4.conta_servico em Configurações.'
                if usuario else "Avise quem cuida do site: o usuário do painel precisa estar conectado ao Site Kit/Google. Ou use ga4.propriedade e ga4.conta_servico em Configurações."
            )
        elif diag.get("sitekit_reautenticar") or diag.get("sitekit_escopos_faltantes"):
            out["erro_codigo"] = "sitekit_reautenticar"
            out["acao"] = (
                f'Avise quem cuida do site: o Google do Site Kit (usuário "{usuario}") precisa ser reconectado com as permissões pedidas.'
                if usuario else "Avise quem cuida do site: o Google do Site Kit precisa ser reconectado com as permissões pedidas."
            )
        elif "concedeu todas as permiss" in low or "granted all" in low or "insufficient scopes" in low:
            out["erro_codigo"] = "sitekit_permissoes_google"
            out["acao"] = ACAO_PERMISSOES_SITEKIT.format(u=usuario or "o usuário do painel")
        elif "403" in msg and ("permission" in low or "permiss" in low or "caller" in low or "site kit" in low):
            out["erro_codigo"] = "analytics_permissao_propriedade"
            out["acao"] = (
                f'O usuário WordPress "{usuario}" está conectado ao Site Kit, mas a conta Google dele não tem acesso suficiente à propriedade GA4 configurada.'
                if usuario else "A conta Google conectada ao Site Kit não tem acesso suficiente à propriedade GA4."
            )
        elif "module must be active" in low or "analytics" in low and "active" in low:
            out["erro_codigo"] = "analytics_modulo_inativo"
            out["acao"] = "Avise quem cuida do site: o Google Analytics não está ativo no Site Kit. Ou use ga4.propriedade e ga4.conta_servico em Configurações."
        else:
            out["erro_codigo"] = "indisponivel"
            out["acao"] = "Use o diagnóstico do Analytics para ver a resposta exata do WordPress/Site Kit."
    return out



@router.get("/analytics/diagnostico")
def analytics_diagnostico(u: dict = Depends(auth.exige("admin"))) -> dict:
    """Teste explícito da identidade WordPress e da autorização Site Kit/GA4 (ou do GA4 direto, se configurado)."""
    from . import ga4_direto
    from .wp import WP
    con = connect()
    try:
        cfg = ga4_direto.configurado(con)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "via": "ga4_direto", "etapa": "ga4_config", "erro": str(e)[:500]}
    finally:
        con.close()
    if cfg:
        g = ga4_direto.GA4(cfg)
        d = {"via": "ga4_direto", "conta": g.conta.get("client_email"), "propriedade": g.prop}
        hoje = datetime.utcnow().date().isoformat()
        try:
            rep = g.relatorio(start_date=hoje, end_date=hoje, metrics=["activeUsers"])
            d.update(ok=True, analytics_report_status=200, usuarios_hoje=_metric_values(rep, ["activeUsers"])["activeUsers"],
                     mensagem=f"GA4 respondeu direto (conta de serviço {g.conta.get('client_email')}, propriedade {g.prop}).")
        except Exception as e:  # noqa: BLE001
            d.update(ok=False, erro=str(e)[:500])
        return d
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
        lo = d["erro"].lower()
        if "concedeu todas as permiss" in lo or "granted all" in lo or "insufficient scopes" in lo:
            d["acao"] = ACAO_PERMISSOES_SITEKIT.format(u=d.get("wp_usuario") or "o usuário do painel")
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


def _erro_cv_bruto(d: dict) -> tuple[str | None, list]:
    """(mensagem inteira que o CAMP Vision deixou no status.json ou no resultado, os dicionários onde procurou)."""
    import json as _json
    todas = []
    for campo in ("status_json", "resultado"):
        try:
            j = _json.loads(d.get(campo) or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(j, dict):
            continue
        fontes = [j] + ([j["status"]] if isinstance(j.get("status"), dict) else [])     # contrato 2.2: resultado.status.motivo
        todas += fontes
        for fonte, k in ((f_, k_) for f_ in fontes for k_ in ("erro", "mensagem_erro", "motivo", "mensagem", "detalhe", "error", "message")):
            v = fonte.get(k)
            if isinstance(v, dict):
                v = v.get("mensagem") or v.get("message") or v.get("detalhe")
            if isinstance(v, str) and v.strip():
                return v.strip(), todas
    return None, todas


def _erro_do_cv(d: dict) -> str | None:
    """Mensagem de erro que o CAMP Vision deixou no status.json (ou no resultado) da pasta, em uma linha."""
    t, _ = _erro_cv_bruto(d)
    return " ".join(t.split())[:240] if t else None


def _erro_do_cv_explicado(d: dict) -> dict | None:
    """UX-08 (campo novo, opcional, só da tela): o mesmo erro em linguagem de gente + a mensagem técnica inteira (avisos_cv.explicar_erro)."""
    from .avisos_cv import explicar_erro
    t, fontes = _erro_cv_bruto(d)
    return explicar_erro(t, fontes)


@router.get("/filas")
def listar_filas(u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    con = connect()
    from .filas_fase import SQL_FORA_DO_SITE
    rows = con.execute(f"""SELECT l.*, p.titulo AS projeto_titulo, p.fundo_codigo, f.titulo AS fundo, p.autorizado_site, p.lote_teste,
                                 p.status_site AS projeto_status_site, {SQL_FORA_DO_SITE} AS fora_do_site,
                                 (SELECT COUNT(*) FROM item i WHERE i.projeto_codigo=l.projeto_codigo) AS folhas_painel,
                                 (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id AND i.projeto_codigo=l.projeto_codigo) AS itens_total,
                                 (SELECT COUNT(*) FROM item i WHERE i.lote_id=l.id AND i.projeto_codigo=l.projeto_codigo AND i.revisao='pendente') AS itens_pendentes
                          FROM lista_processamento l JOIN projeto p ON p.codigo=l.projeto_codigo JOIN fundo f ON f.codigo=p.fundo_codigo
                          WHERE l.descartado_em IS NULL AND p.mesclado_em IS NULL AND p.descartado_em IS NULL   -- UX-05: os mesmos lotes das contagens
                          ORDER BY CASE l.etapa WHEN 'erro' THEN 0 WHEN 'revisao' THEN 1 WHEN 'processando' THEN 2 WHEN 'enviado' THEN 3 WHEN 'rascunho' THEN 4 ELSE 5 END, l.atualizado_em DESC""").fetchall()
    from .qualidade_base import adiadas
    from .pendencias import chave_adiar_lote
    fora = adiadas(con, u["id"]) if u.get("id") else set()
    from .filas_fase import fase_da_lista
    from .pendencias import projetos_lendo_agora, releituras_abertas
    lendo, pedidos = projetos_lendo_agora(con), releituras_abertas(con)
    from .dispensa_lote import validas
    dispensados = validas(con)
    saida = []
    for r in rows:
        d = dict(r)
        d["adiado"] = chave_adiar_lote(d["id"]) in fora   # UX-05: "Agora não" desta pessoa: fica na lista, sai das contagens dela
        d["dispensado"] = dispensados.get(d["id"])         # UX-35 (campo novo, opcional): {por, em, motivo}; fica só em "Todas", para todos
        d["itens_conferidos"] = d["itens_total"] - d["itens_pendentes"]
        from .pendencias import identificador_lote, _e_complemento, marcar_parado
        marcar_parado(d, lendo)                          # UX-09 (campos novos, opcionais): parado_h, parado, leitura_interrompida
        d["releitura_pedida_em"] = pedidos.get(d["projeto_codigo"]) if d["leitura_interrompida"] else None
        d["identificador"] = identificador_lote(d["nome"], d["criado_em"], _e_complemento(d.get("resultado")))   # UX-04 (campo novo, opcional)
        d["fase"] = fase_da_lista(d["etapa"], d["itens_total"], d["itens_pendentes"], d.get("aprovado_em"), d.get("resultado"),
                                  d.get("projeto_status_site") == "no_ar", d.get("fora_do_site"))   # UX-36 (campos novos, opcionais)
        d["erro_cv"] = _erro_do_cv(d) if d["etapa"] == "erro" else None   # H7: o motivo que o CAMP Vision deixou, na própria linha
        d["erro_cv_explicado"] = _erro_do_cv_explicado(d) if d["etapa"] == "erro" else None   # UX-08: em linguagem de gente (campo novo, opcional)
        d["destino_suspeito"] = False                    # UX-01 (campo novo, opcional): a pasta não parece deste projeto → "Verificar destino"
        if d["fase"] == "importar":
            from .destino_lote import avaliar
            a = avaliar(con, r, completo=False)
            d["destino_suspeito"] = a["suspeito"] and not a["liberado"]
            d["destino_motivo"] = a["motivo"] if d["destino_suspeito"] else None
        saida.append(d)
    con.close()
    return saida


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
        from .publicacao import BLOQUEIO_DO_PROJETO
        bloqueios_humanos = con.execute(BLOQUEIO_DO_PROJETO, (l["projeto_codigo"],)).fetchone()[0]
        if bloqueios_humanos:
            con.close(); raise HTTPException(400, f"Bloqueado: {bloqueios_humanos} decisão(ões) humanas no projeto")
        if u["papel"] not in ("admin", "master"):
            con.close(); raise HTTPException(403, "Mandar para o site exige admin")
        if con.execute("SELECT 1 FROM item WHERE lote_id=? LIMIT 1", (lid,)).fetchone() and not l["aprovado_em"]:
            con.close(); raise HTTPException(400, "Revise e aprove o lote antes de mandar para o site")
    con.execute("UPDATE lista_processamento SET etapa=?, atualizado_em=datetime('now') WHERE id=?", (d.etapa, lid))
    if d.etapa == "revisao":
        con.execute("UPDATE projeto SET status_site=CASE WHEN status_site IN ('nao_publicado','bloqueado') THEN 'em_revisao' ELSE status_site END WHERE codigo=?", (l["projeto_codigo"],))
    _evento(con, "lista", lid, f"etapa_{d.etapa}", u["email"], {"obs": d.observacao} if d.observacao else None)
    _evento(con, "projeto", l["projeto_codigo"], f"fila_{d.etapa}", u["email"])
    con.commit(); con.close()
    return {"ok": True}


class DispensaLote(BaseModel):
    motivo: str | None = None


@router.post("/filas/{lid}/dispensar")
def dispensar_lote(lid: int, d: DispensaLote | None = None, u: dict = Depends(auth.exige("operador"))) -> dict:
    """UX-35: "Dispensar este lote" — lote com erro do CAMP Vision que ninguém consegue resolver sai das listas e das contagens de TODOS.
    Não apaga nada, não mexe no QNAP nem na etapa/status.json. Guarda a assinatura do erro: se o CAMP Vision reler e o erro mudar, volta."""
    from .dispensa_lote import assinatura_do_lote, _mensagem_cv, estado_dispensavel
    motivo = ((d.motivo if d else None) or "").strip()[:300] or None
    con = connect()
    try:
        l = con.execute("SELECT * FROM lista_processamento WHERE id=? AND descartado_em IS NULL", (lid,)).fetchone()
        if not l:
            raise HTTPException(404, "Lote não encontrado")
        estado = estado_dispensavel(l, con=con)       # UX-39: também leitura interrompida (processando > 2 h sem sinal do CAMP Vision)
        if not estado:
            raise HTTPException(400, "Só dá para dispensar um lote parado com erro do CAMP Vision ou com a leitura interrompida.")
        erro_cv = (_mensagem_cv(l["status_json"], l["resultado"])[:500] or None) if estado == "erro" else None
        con.execute("""INSERT INTO lote_dispensado (lote_id, assinatura, etapa, erro_cv, motivo, por, em) VALUES (?,?,?,?,?,?,datetime('now'))
                       ON CONFLICT(lote_id) DO UPDATE SET assinatura=excluded.assinatura, etapa=excluded.etapa, erro_cv=excluded.erro_cv,
                                                          motivo=excluded.motivo, por=excluded.por, em=excluded.em""",
                    (lid, assinatura_do_lote(l), l["etapa"], erro_cv, motivo, u["email"]))
        from .pendencias import identificador_lote, _e_complemento
        det = {"lote": lid, "identificador": identificador_lote(l["nome"], l["criado_em"], _e_complemento(l["resultado"])), "motivo": motivo, "erro_cv": (erro_cv or "")[:200] or None, "estado": estado}
        _evento(con, "projeto", l["projeto_codigo"], "lote_dispensado", u["email"], det)     # Histórico de ações e histórico do projeto
        con.commit()
        return {"ok": True, "id": lid, "mensagem": "Lote dispensado: saiu das listas e das contagens. Volta sozinho se o CAMP Vision ler a pasta de novo e o resultado mudar."}
    finally:
        con.close()


@router.delete("/filas/{lid}/dispensar")
def voltar_a_mostrar_lote(lid: int, u: dict = Depends(auth.exige("operador"))) -> dict:
    """UX-35: "Voltar a mostrar" desfaz a dispensa (o lote volta às listas e às contagens de todos)."""
    con = connect()
    try:
        l = con.execute("SELECT id, nome, criado_em, resultado, projeto_codigo FROM lista_processamento WHERE id=?", (lid,)).fetchone()
        if not l:
            raise HTTPException(404, "Lote não encontrado")
        if not con.execute("DELETE FROM lote_dispensado WHERE lote_id=?", (lid,)).rowcount:
            return {"ok": True, "id": lid, "mensagem": "Este lote já estava sendo mostrado."}
        from .pendencias import identificador_lote, _e_complemento
        _evento(con, "projeto", l["projeto_codigo"], "lote_dispensa_desfeita", u["email"],
                {"lote": lid, "identificador": identificador_lote(l["nome"], l["criado_em"], _e_complemento(l["resultado"]))})
        con.commit()
        return {"ok": True, "id": lid, "mensagem": "O lote voltou para as listas e as contagens."}
    finally:
        con.close()


@router.get("/estacoes/contexto-operador")
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


# Valores de `status` (status.json) que o painel entende. Contrato: docs/campvision.md.
STATUS_PRONTO = {"pronto", "campvision_concluido", "pronto_campvision2"}   # os dois últimos são valores antigos do CV2
STATUS_ANTIGOS = {"campvision_concluido", "pronto_campvision2"}   # CAMP-024: legado.status_antigos
STATUS_PROCESSANDO = {"processando", "enviado_windows"}   # enviado_windows NÃO é legado: é a marca de fim de lote do Windows (contrato C1)
STATUS_ERRO = {"erro", "falha"}
EVENTO_POR_ETAPA = {"revisao": "material_pronto", "processando": "material_processando", "erro": "material_com_erro"}


def _classificar_status(st, con=None) -> tuple[str, bool]:
    """(etapa da lista, status_conhecido). Sem status = pronto (comportamento antigo); valor desconhecido = pronto + aviso."""
    s = str(st or "").strip().lower()
    if s in STATUS_ANTIGOS:                                   # CAMP-024: conta o uso e respeita legado.status_antigos
        from . import legado
        legado.registrar_uso("status_antigos", s, con)
        return ("revisao", True) if (legado.ligado(con, "status_antigos") if con is not None else legado.ligado_agora("status_antigos")) else ("revisao", False)
    if not s or s in STATUS_PRONTO:
        return "revisao", True
    if s in STATUS_PROCESSANDO:
        return "processando", True
    if s in STATUS_ERRO:
        return "erro", True
    return "revisao", False


def _anotar_lote_teste(con, pasta: Path, codigo: str | None) -> None:
    """CAMP-114: o lote de teste continua IGNORADO (não vira fila, não importa folhas), mas o projeto que a estação reservou para ele fica
    sabendo: anota no histórico "o CAMP Vision mandou lote de teste desta pasta" (uma vez por pasta). Enquanto o projeto não tiver nenhuma
    folha, a publicação trata como lote de teste (não vai ao site) e a página diz isso; um lote de verdade depois volta ao normal."""
    cod = str(codigo or "").strip().upper()
    if not re.fullmatch(r"F\d{3}-P\d{4}", cod) or not con.execute("SELECT 1 FROM projeto WHERE codigo=?", (cod,)).fetchone():
        return
    det = {"pasta": str(pasta)}
    if con.execute("SELECT 1 FROM evento WHERE entidade='projeto' AND codigo=? AND tipo='lote_teste_ignorado' AND detalhe=?",
                   (cod, json.dumps(det, ensure_ascii=False))).fetchone():
        return
    _evento(con, "projeto", cod, "lote_teste_ignorado", "campvision", det)


def _ler_pasta(con, pasta: Path, entrada: Path | None, esperado: str | None = None) -> dict:
    """_ler_pasta_bruto + CAMP-122 (P1): "erro" do CAMP Vision que é só aviso [Minor] do exiftool não para o lote (avisos_cv.curar_lote)."""
    r = _ler_pasta_bruto(con, pasta, entrada, esperado)
    if r.get("etapa") == "erro" and r.get("acao") not in ("entrada", "ignorada"):
        from .avisos_cv import curar_lote
        l = con.execute("SELECT id FROM lista_processamento WHERE pasta_qnap=? AND descartado_em IS NULL ORDER BY id DESC LIMIT 1", (str(pasta),)).fetchone()
        nova = curar_lote(con, l["id"]) if l else None
        if nova:
            r["etapa"], r["erro_so_avisos"] = nova, True
    return r


def _ler_pasta_bruto(con, pasta: Path, entrada: Path | None, esperado: str | None = None) -> dict:
    """Lê UMA pasta de lote (info_projeto.json, status.json e as imagens) e cria ou atualiza a lista dela.

    Usada pela varredura completa e pelo aviso do CAMP Vision. Devolve {"acao": "entrada" | "ignorada" | "nova" | "atualizada" | "igual", ...}.
    `esperado` (opcional) é o código que o aviso disse; se a pasta disser outro, não importa nada.
    """
    if entrada:
        try:
            entrada_resolvida = entrada.resolve()
            if pasta == entrada_resolvida or entrada_resolvida in pasta.parents:
                return {"acao": "entrada", "pasta": str(pasta)}
        except OSError:
            pass
    info_path = pasta / "info_projeto.json"
    status_path = pasta / "status.json"
    try:
        info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() and info_path.stat().st_size else {}
        status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() and status_path.stat().st_size else {}
    except Exception as e:  # noqa: BLE001
        return {"acao": "ignorada", "pasta": str(pasta), "motivo": f"manifesto inválido: {e}"}
    sem_manifesto = False
    if not info_path.exists() and not status_path.exists():
        # Aviso do CAMP Vision (`esperado` = código que ele disse) de pasta que TEM o pacote do projeto mas não tem info_projeto.json/status.json
        # (pasta reorganizada por --reidentificar ou reconstruída: a releitura de F026-P0009 foi lida e o painel recusava o aviso, e nada mudava na tela).
        # Vale só quando o pacote é do MESMO projeto que o aviso disse; a varredura do QNAP (sem `esperado`) continua ignorando pasta sem manifesto.
        pacote_cod = _codigo_do_pacote(pasta)
        if esperado and pacote_cod and pacote_cod.upper() == esperado.strip().upper():
            info, status, sem_manifesto = {"codigo": pacote_cod}, {"status": "pronto"}, True
        else:
            return {"acao": "ignorada", "pasta": str(pasta), "motivo": "sem info_projeto.json nem status.json nesta pasta"}

    nome_teste = pasta.name.lower() in ("asd", "sei la")
    if nome_teste:
        from . import legado
        legado.registrar_uso("nomes_de_teste", pasta.name, con)
        nome_teste = legado.ligado(con, "nomes_de_teste")          # CAMP-024: desligado = só "teste": true (ou a pasta "teste") vale
    if info.get("teste") or pasta.name.lower() == "teste" or nome_teste:
        _anotar_lote_teste(con, pasta, info.get("codigo") or esperado)
        return {"acao": "ignorada", "pasta": str(pasta), "motivo": "lote de teste"}
    from .similaridade import normalizar as _norm_sim
    if re.match(r"^\d+ ?arquivo arquivistico", _norm_sim(pasta.name) or ""):   # "01 - Arquivo Arquivístico (TIFF)" é parte do lote da pasta de cima
        return {"acao": "ignorada", "pasta": str(pasta), "motivo": "subpasta '01 - Arquivo Arquivístico (TIFF)': faz parte do lote da pasta de cima"}

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
        return {"acao": "ignorada", "pasta": str(pasta), "motivo": "sem código de projeto reconhecido no material final"}
    if esperado and esperado.strip().upper() != cod.upper():
        return {"acao": "ignorada", "pasta": str(pasta), "codigo": cod,
                "motivo": f"o aviso diz {esperado.strip().upper()}, mas a pasta é do projeto {cod}: nada foi importado"}

    try:                                                    # CAMP-008: o erros.json do CAMP Vision entra em Erros relatados já na leitura da pasta
        from .importador_lote import registrar_erros_cv
        registrar_erros_cv(con, cod, pasta)
    except Exception:  # noqa: BLE001 - arquivo ruim nunca impede ler o lote
        pass
    from .qnap_folhas import contar_documentos
    n_arq, leitura_parcial = contar_documentos(pasta)   # DOCUMENTOS (série + nome), não arquivos: TIF/ e JPG/ do mesmo código são UM documento

    st = status.get("status") if isinstance(status, dict) else None
    etapa_alvo, conhecido = _classificar_status(st, con)
    aviso = None if conhecido else f"status desconhecido '{st}': tratado como pronto"
    if sem_manifesto:
        aviso = ((aviso + "; ") if aviso else "") + "a pasta não tem info_projeto.json nem status.json: lida pelo pacote do CAMP Vision"
    if leitura_parcial:
        aviso = ((aviso + "; ") if aviso else "") + "a pasta demorou para ser lida: a contagem de folhas pode estar incompleta"
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
    saida = {"pasta": str(pasta), "codigo": cod, "etapa": etapa_alvo, "folhas": n_arq, "aviso": aviso}

    ex = con.execute(
        "SELECT id, nome, etapa, folhas_encontradas, aprovado_em, resultado FROM lista_processamento WHERE pasta_qnap=? ORDER BY id DESC LIMIT 1",
        (str(pasta),),
    ).fetchone()

    # Lote JÁ fechado (aprovado, em rascunho ou publicado) e o CAMP Vision trouxe folhas que o painel ainda não tem: é MATERIAL NOVO do mesmo
    # projeto (a pasta do projeto recebe material várias vezes). Vira um lote novo em revisão, sem tocar no que já está fechado.
    if ex and etapa_alvo == "revisao" and (ex["etapa"] in ("publicado", "rascunho") or ex["aprovado_em"]):
        novos = _documentos_novos(con, pasta, cod, ex["id"])
        if novos:
            return _criar_lote_complemento(con, pasta, cod, nome, ex, novos, contexto, status, saida)

    ex_res: dict = {}
    if ex:
        try:
            ex_res = json.loads(ex["resultado"] or "{}") or {}
        except ValueError:
            ex_res = {}
    if isinstance(ex_res.get("importacao"), dict) and ex_res["importacao"].get("pacote_sha"):
        # 23/10: a varredura regrava o lote e apagava "já importado" (o lote sem folha nova voltava para Importar a cada passada).
        # Mesmo pacote na pasta = a importação continua valendo; pacote novo = importar de novo.
        from .importador_lote import assinatura_pacote, ler_pacote
        try:
            if assinatura_pacote(ler_pacote(pasta)) == ex_res["importacao"]["pacote_sha"]:
                contexto["importacao"] = ex_res["importacao"]
        except HTTPException:
            pass
    if ex_res.get("complemento"):                          # lote de complemento: a marca e a contagem são DELE, não da pasta inteira
        contexto.update({k: ex_res[k] for k in ("complemento", "lote_cv", "lote_origem", "novos") if k in ex_res})
        n_arq = ex["folhas_encontradas"] or 0
        saida["folhas"] = n_arq

    if ex:
        if ex["etapa"] not in ("publicado", "rascunho") and ex["etapa"] != etapa_alvo:   # nunca regride lote já publicado/em rascunho
            con.execute(
                "UPDATE lista_processamento SET etapa=?, status_json=?, folhas_encontradas=?, resultado=?, atualizado_em=datetime('now') WHERE id=?",
                (etapa_alvo, st or "pronto_campvision2", n_arq, json.dumps(contexto, ensure_ascii=False), ex["id"]),
            )
            _evento(con, "lista", ex["id"], EVENTO_POR_ETAPA[etapa_alvo], "campvision2", {"pasta": str(pasta), "arquivos": n_arq})
            return {**saida, "acao": "atualizada"}
        con.execute(
            "UPDATE lista_processamento SET folhas_encontradas=?, status_json=?, resultado=?, atualizado_em=datetime('now') WHERE id=?",
            (n_arq, st or "pronto_campvision2", json.dumps(contexto, ensure_ascii=False), ex["id"]),
        )
        return {**saida, "acao": "igual"}
    # lote NOVO cujo nome não parece o do projeto do código: avisa (não grava em silêncio como se estivesse tudo certo)
    # regra CONSERVADORA (falso alarme também é defeito): só avisa quando os dois nomes não têm NENHUMA palavra distintiva em comum
    from .similaridade import normalizar as _nz
    _vaz = {"com", "dos", "das", "para", "sem", "por", "uma", "nos", "nas"}
    _pal = lambda x: {w for w in (_nz(x) or "").split() if len(w) >= 3 and not any(ch.isdigit() for ch in w) and w not in _vaz}  # noqa: E731
    tit_proj = (con.execute("SELECT titulo FROM projeto WHERE codigo=?", (cod,)).fetchone() or [""])[0] or ""
    nome_limpo = re.sub(r"\s+", " ", re.sub(r"F\d{3}-P\d{4}", " ", str(nome)).replace("_", " ")).strip(" -")
    ta, tb = _pal(nome_limpo), _pal(tit_proj)
    if ta and tb and not (ta & tb):
        alerta = f"o nome da pasta ('{nome_limpo}') não parece o do projeto {cod} ('{tit_proj}'): confira se o lote caiu no projeto certo antes de importar"
        saida["aviso"] = ((saida["aviso"] + "; ") if saida["aviso"] else "") + alerta
        contexto["alerta_nome"] = alerta
        _evento(con, "projeto", cod, "lote_nome_diferente", "campvision2", {"pasta": str(pasta), "nome_pasta": nome_limpo, "titulo_projeto": tit_proj})
    # "Mais inteligência" (3): projeto com o MESMO nome em OUTRO fundo → nota forte no lote + pergunta em Decisões
    from .similaridade import buscar_em_outros_fundos
    from . import decisoes as _dec
    _p = con.execute("SELECT fundo_codigo, titulo, ano, cidade FROM projeto WHERE codigo=?", (cod,)).fetchone()
    outros = buscar_em_outros_fundos(con, _p["fundo_codigo"], _p["titulo"], _p["ano"], _p["cidade"]) if _p else []
    if outros:
        o = outros[0]
        nota = f"já existe '{o['titulo']}' no fundo {o['fundo_codigo']} ({o['codigo']}): é o mesmo projeto? Confira em Decisões"
        saida["aviso"] = ((saida["aviso"] + "; ") if saida["aviso"] else "") + nota
        contexto["outro_fundo"] = [{k: x[k] for k in ("codigo", "titulo", "fundo_codigo")} for x in outros]
        _dec.abrir_outro_fundo(con, cod, outros, "campvision")
    lid = con.execute(
        """INSERT INTO lista_processamento
           (nome, projeto_codigo, pasta_qnap, folhas_esperadas, folhas_encontradas, etapa, status_json, resultado)
           VALUES (?,?,?,?,?,?,?,?)""",
        (nome, cod, str(pasta), esperadas, n_arq, etapa_alvo, st or "pronto_campvision2", json.dumps(contexto, ensure_ascii=False)),
    ).lastrowid
    _evento(con, "lista", lid, EVENTO_POR_ETAPA[etapa_alvo], "campvision2", {"pasta": str(pasta), "arquivos": n_arq})
    if etapa_alvo == "revisao":
        _evento(con, "projeto", cod, "material_novo_pronto", "campvision2", contexto)
    return {**saida, "acao": "nova"}


def _codigo_do_pacote(pasta: Path) -> str | None:
    """Código do projeto que o pacote do CAMP Vision diz (None se não há pacote ou ele está ilegível)."""
    from .importador_lote import ler_pacote
    try:
        return str(((ler_pacote(pasta) or {}).get("projeto_codigo")) or "") or None
    except HTTPException:
        return None


def _documentos_novos(con, pasta: Path, cod: str, lote_id: int) -> list[str]:
    """Códigos que o pacote do CAMP Vision traz para o projeto e o painel ainda NÃO tem como folha.
    Não conta a folha que espera uma decisão de "lote colide" (ela não existe de propósito) nem pacote ilegível/ausente."""
    from .importador_lote import colisoes_decididas, ler_pacote
    try:
        pacote = ler_pacote(pasta)
    except HTTPException:
        return []
    docs = (pacote or {}).get("documentos") if isinstance((pacote or {}).get("documentos"), list) else (pacote or {}).get("itens")
    if not isinstance(docs, list) or (pacote or {}).get("projeto_codigo") != cod:
        return []
    tem = {r[0] for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo=?", (cod,))}
    tem |= {r[0] for r in con.execute("SELECT codigo_anterior FROM item WHERE codigo_anterior LIKE ? AND projeto_codigo<>?", (cod + "-%", cod))}   # folha movida para outro projeto não volta
    cobertas = set(colisoes_decididas(con, lote_id))
    return [c for c in (str(d.get("codigo") or "") for d in docs if isinstance(d, dict)) if c.startswith(cod + "-") and c not in tem and c not in cobertas]


def _criar_lote_complemento(con, pasta: Path, cod: str, nome: str, ex, novos: list[str], contexto: dict, status, saida: dict) -> dict:
    """Cria o lote NOVO (em revisão) do material que chegou a um projeto cujo lote já está fechado. Mesma pasta, mesmo projeto."""
    from datetime import date
    quando = date.today().strftime("%d/%m")
    # UX-04: o nome não leva mais "(N folhas)": era o número do pacote no dia (documentos que o painel não tinha), nunca atualizado, e brigava
    # com a contagem real do lote na tela ("complemento de 19/10 (19 folhas)" com 12 de 12). A contagem do lote é a das folhas (item.lote_id).
    nome_c = f"{nome} — complemento de {quando}"
    lote_cv = status.get("lote_atual") if isinstance(status, dict) else None
    ctx = {**contexto, "complemento": True, "lote_cv": lote_cv, "lote_origem": ex["id"], "novos": len(novos)}
    lid = con.execute(
        """INSERT INTO lista_processamento
           (nome, projeto_codigo, pasta_qnap, folhas_esperadas, folhas_encontradas, etapa, status_json, resultado)
           VALUES (?,?,?,?,?,?,?,?)""",
        (nome_c, cod, str(pasta), None, len(novos), "revisao", (status or {}).get("status") if isinstance(status, dict) else "pronto_campvision2",
         json.dumps(ctx, ensure_ascii=False)),
    ).lastrowid
    _evento(con, "lista", lid, EVENTO_POR_ETAPA["revisao"], "campvision2", {"pasta": str(pasta), "arquivos": len(novos), "complemento": True, "lote_origem": ex["id"]})
    _evento(con, "projeto", cod, "material_novo_pronto", "campvision2", {"complemento": True, "lote_id": lid, "folhas": len(novos), "lote_origem": ex["id"], "lote_cv": lote_cv})
    return {**saida, "acao": "complemento", "lote_id": lid, "folhas": len(novos), "novos": len(novos), "lote_origem": ex["id"], "nome_lote": nome_c}


def ler_pasta_do_aviso(con, pasta_txt: str, codigo: str | None) -> dict:
    """Aviso do CAMP Vision: relê SÓ esta pasta. Recusa (400) a própria raiz e qualquer caminho que escape dela."""
    raiz = _qnap_prontos_raiz()
    if not raiz.exists():
        raise HTTPException(503, f"Pasta final do QNAP não montada em {raiz}")
    txt = (pasta_txt or "").strip()
    if not txt:
        raise HTTPException(400, "Informe a pasta do projeto")
    p = Path(txt)
    alvo = (p if p.is_absolute() else raiz / p).resolve()
    raiz_r = raiz.resolve()
    if alvo == raiz_r or raiz_r not in alvo.parents:
        raise HTTPException(400, "A pasta tem de estar DENTRO da raiz final do QNAP (e não ser a própria raiz)")
    if not alvo.is_dir():
        return {"ok": False, "acao": "ignorada", "pasta": str(alvo), "motivo": "pasta não encontrada (ainda?)"}
    entrada_txt = _cfg("qnap.entrada_captura", "")
    r = _ler_pasta(con, alvo, Path(entrada_txt) if entrada_txt else None, codigo)
    if r["acao"] == "entrada":
        return {"ok": False, "acao": "ignorada", "pasta": str(alvo), "motivo": "pasta da entrada bruta: o painel só lê o material final"}
    r["ok"] = r["acao"] in ("nova", "atualizada", "igual", "complemento")
    if r["ok"] and r.get("etapa") == "revisao":
        r["importacao"] = _importar_se_tem_pacote(con, alvo)
    return r


def _importar_se_tem_pacote(con, pasta: Path) -> dict | None:
    """O aviso do CAMP Vision também traz as FOLHAS para o painel (antes só criava o lote e as folhas
    dependiam do botão "Importar"). Usa o mesmo importador: nunca sobrescreve folha revisada nem no site;
    lote aprovado não é tocado."""
    from .importador_lote import importar_lote, ler_pacote
    l = con.execute("SELECT id, aprovado_em FROM lista_processamento WHERE pasta_qnap=? ORDER BY id DESC LIMIT 1", (str(pasta),)).fetchone()
    if not l:
        return None
    if l["aprovado_em"]:
        return {"ignorado": "lote aprovado: não há folha nova para importar"}   # o aviso diz o que aconteceu (antes ficava silencioso)
    try:
        if ler_pacote(pasta) is None:
            return None
        return importar_lote(con, l["id"], "campvision (aviso)")
    except HTTPException as e:
        return {"erro": e.detail}


@router.post("/filas/varrer-qnap")
def varrer_qnap(tarefa: int = 0, u: dict = Depends(auth.exige("operador"))):
    """?tarefa=1 (H4): roda em segundo plano e devolve {tarefa_id}; a tela acompanha em /api/tarefas/{id}."""
    if not tarefa:
        return _varrer_qnap()
    if not _qnap_prontos_raiz().exists():
        raise HTTPException(503, f"Pasta final do QNAP não montada em {_qnap_prontos_raiz()}")
    from . import tarefas

    def rodar(p) -> dict:
        p.passo("Lendo as pastas do QNAP")
        r = _varrer_qnap()
        partes = [f"{r['novas']} pasta(s) nova(s)", f"{r['atualizadas']} atualizada(s)"] + ([f"{len(r['ignoradas'])} ignorada(s)"] if r["ignoradas"] else [])
        return {**r, "ok": True, "nota": r["mensagem"], "mensagem": ", ".join(partes) + "."}
    return tarefas.iniciar("varrer_qnap", "qnap", u, rodar)


def _varrer_qnap() -> dict:
    """Lê somente material FINAL organizado pelo CAMP Vision 2.

    Fluxo:
      estações de captura -> entrada bruta do QNAP -> CAMP Vision 2 ->
      JSON/EXIF/organização -> raiz final -> painel.

    Material na entrada bruta nunca vira fila nem aviso de publicação. O aviso do CAMP Vision (POST /api/campvision/aviso) lê uma pasta só;
    esta varredura anda pela raiz inteira e serve de reconciliação.
    """
    raiz = _qnap_prontos_raiz()
    entrada_txt = _cfg("qnap.entrada_captura", "")
    entrada = Path(entrada_txt) if entrada_txt else None
    if not raiz.exists():
        raise HTTPException(503, f"Pasta final do QNAP não montada em {raiz}")

    con = connect()
    novas = atualizadas = n_processando = n_erro = 0
    ignoradas: list[dict] = []
    avisos: list[dict] = []
    vistos: set[Path] = set()

    manifestos = list(raiz.rglob("info_projeto.json")) + list(raiz.rglob("status.json"))
    for arq in manifestos:
        if "_campvision" in arq.relative_to(raiz).parts:      # prévias e livro de registro do CAMP Vision: não são lotes
            continue
        pasta = arq.parent.resolve()
        if pasta in vistos:
            continue
        vistos.add(pasta)
        r = _ler_pasta(con, pasta, entrada)
        if r["acao"] == "entrada":
            continue
        if r["acao"] == "ignorada":
            ignoradas.append({"pasta": r["pasta"], "motivo": r["motivo"]})
            continue
        if r.get("aviso"):
            avisos.append({"pasta": r["pasta"], "motivo": r["aviso"]})
        n_processando += r["etapa"] == "processando"
        n_erro += r["etapa"] == "erro"
        novas += r["acao"] in ("nova", "complemento")
        atualizadas += r["acao"] == "atualizada"

    con.commit()
    con.close()
    return {
        "novas": novas,
        "atualizadas": atualizadas,
        "processando": n_processando,
        "com_erro": n_erro,
        "avisos": avisos[:50],
        "ignoradas": ignoradas[:50],
        "raiz_final": str(raiz),
        "entrada_bruta": str(entrada) if entrada else None,
        "mensagem": "Somente material já organizado pelo CAMP Vision 2 entra; lotes em processamento ou com erro aparecem nas Filas, mas não pedem revisão.",
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
    entrega: str | None = None          # H17: o que foi entregue (arquivos e tamanho)


# "Mais inteligência" (7): a MESMA pessoa (mesmo e-mail, ou mesmo nome quando não há e-mail) pediu o MESMO material (mesmo código, ou o projeto
# e uma folha dele) nos 30 dias ANTES deste pedido → o pedido anterior (o mais recente)
_PEDIDO_ANTERIOR = """SELECT {col} FROM solicitacao s2
   WHERE s2.id<>s.id AND (s2.recebida_em < s.recebida_em OR (s2.recebida_em = s.recebida_em AND s2.id < s.id))
     AND julianday(s.recebida_em) - julianday(s2.recebida_em) <= 30
     AND ((COALESCE(s.email,'')<>'' AND lower(s2.email)=lower(s.email)) OR (COALESCE(s.email,'')='' AND lower(trim(s2.solicitante))=lower(trim(s.solicitante))))
     AND EXISTS (SELECT 1 FROM solicitacao_item a JOIN solicitacao_item b ON (a.codigo=b.codigo OR a.codigo LIKE b.codigo || '-%' OR b.codigo LIKE a.codigo || '-%')
                  WHERE a.solicitacao_id=s.id AND b.solicitacao_id=s2.id)
   ORDER BY s2.recebida_em DESC, s2.id DESC LIMIT 1"""


def pedido_anterior(con, sid: int) -> dict | None:
    r = con.execute(f"SELECT ({_PEDIDO_ANTERIOR.format(col='s2.id')}), ({_PEDIDO_ANTERIOR.format(col='s2.recebida_em')}) FROM solicitacao s WHERE s.id=?", (sid,)).fetchone()
    return {"id": r[0], "recebida_em": r[1]} if r and r[0] else None


SITUACOES = ["aguarda_resposta", "aguarda_orcamento", "aguarda_credito", "em_preparacao", "entregue", "recusada"]


@router.get("/solicitacoes")
def listar_solicitacoes(situacao: str | None = None, u: dict = Depends(auth.exige("leitura"))) -> dict:
    con = connect()
    sql = f"""SELECT s.*, us.nome AS responsavel_nome, (SELECT GROUP_CONCAT(codigo || ' (' || formato || ')', ' · ') FROM solicitacao_item si WHERE si.solicitacao_id=s.id) AS itens,
                    ({_PEDIDO_ANTERIOR.format(col='s2.id')}) AS repetido_de, ({_PEDIDO_ANTERIOR.format(col='s2.recebida_em')}) AS repetido_de_em
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
def criar_solicitacao(d: NovaSolicitacao, tarefas: BackgroundTasks, u: dict = Depends(auth.exige("operador"))) -> dict:
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
    rep = pedido_anterior(con, sid)
    con.commit(); con.close()
    tarefas.add_task(_avisar_pedido_painel, sid, u["email"])   # cartão "Notificações": avisa por e-mail (assunto pedido_painel), depois de responder
    return {"id": sid, "repetido_de": rep}


def _avisar_pedido_painel(sid: int, quem: str) -> None:
    from . import alertas
    con = connect()
    try:
        alertas.avisar_pedido_novo(con, sid, registrado_por=quem)
    except Exception as e:  # noqa: BLE001  (o pedido já está salvo; a falha do aviso só vai para o log)
        import logging
        from .log_tecnico import registrar
        registrar(logging.WARNING, "pedido_aviso_falhou", "Não consegui avisar o pedido registrado no painel", pedido=sid, erro_tipo=type(e).__name__)
    finally:
        con.close()


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
        elif s["situacao"] == "entregue":           # saiu de "entregue" (ex.: o Desfazer do H4): deixa de contar como entregue
            campos.append("entregue_em=NULL"); con.execute("UPDATE solicitacao_item SET entregue=0 WHERE solicitacao_id=?", (sid,))
    for k in ("condicoes_uso", "valor", "detalhe", "responsavel", "entrega"):
        v = getattr(d, k)
        if v is not None:
            campos.append(f"{k}=?"); vals.append(v); mud[k] = v
    if campos:
        con.execute(f"UPDATE solicitacao SET {', '.join(campos)} WHERE id=?", (*vals, sid))
        _evento(con, "solicitacao", sid, "editada", u["email"], mud)
        con.commit()
    con.close()
    return {"ok": True}


@router.get("/solicitacoes/{sid}/historico")
def historico_solicitacao(sid: int, u: dict = Depends(auth.exige("leitura"))) -> dict:
    """H17: quando o pedido passou por cada situação (a trilha mostra a data de cada etapa) e o que foi entregue."""
    con = connect()
    try:
        s = con.execute("SELECT recebida_em, entregue_em, entrega FROM solicitacao WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Pedido não existe")
        etapas = {"aguarda_resposta": s["recebida_em"]}
        linhas = []
        for e in con.execute("SELECT quando, ator, detalhe FROM evento WHERE entidade='solicitacao' AND codigo=? ORDER BY id", (str(sid),)):
            try:
                det = json.loads(e["detalhe"] or "{}")
            except ValueError:
                det = {}
            if det.get("situacao"):
                etapas[det["situacao"]] = e["quando"]
            linhas.append({"quando": e["quando"], "ator": e["ator"], "situacao": det.get("situacao"), "entrega": det.get("entrega")})
        return {"etapas": etapas, "linhas": linhas, "entrega": s["entrega"]}
    finally:
        con.close()


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
ORIGENS_MANUAIS = ("operador", "revisao", "site")
CATS = ("autoria_divergente", "projeto_errado", "duplicata", "orientacao", "espelhado", "codigo", "metadado", "credito", "arquivo_corrompido", "outro")


class ErrosEmLote(BaseModel):
    ids: list[int]
    situacao: str
    resolucao: str | None = None


def _escondidos(con, usuario_id) -> list[int]:
    """UX-03: problemas que ESTA pessoa escondeu por 7 dias no Precisa de você (ficam em Problemas › Ignorados, não em Abertos/Avisos)."""
    from .qualidade_base import adiadas
    return [int(k[5:]) for k in adiadas(con, usuario_id) if k.startswith("erro:") and k[5:].isdigit()]


def _filtro_erros(situacao, gravidade, categoria, origem, projeto, q, escondidos=None) -> tuple[str, list]:
    """A mesma regra para a lista e para a contagem das abas: situação, gravidade, tipo (categoria), origem, projeto (ou fundo) e busca."""
    w, p = [], []
    from .contagens import ERROS_ABERTOS, ERROS_PEDEM_ACAO, ERROS_AVISOS
    if escondidos and situacao in ("pedem_acao", "avisos"):
        w.append(f"id NOT IN ({','.join('?' * len(escondidos))})"); p += list(escondidos)
    if situacao == "abertos": w.append(ERROS_ABERTOS)          # UX-05: a mesma regra do menu e da Home
    # UX-19: avisos em aba própria. "pedem_acao" = abertos que bloqueiam ou pedem correção; "avisos" = abertos só de aviso (regra em contagens.py).
    elif situacao == "pedem_acao": w.append(ERROS_PEDEM_ACAO)
    elif situacao == "avisos": w.append(ERROS_AVISOS)
    elif situacao == "corrigido": w.append("situacao IN ('corrigido','fechado')")
    elif situacao and situacao != "todos": w.append("situacao=?"); p.append(situacao)
    for col, v, ok_ in (("gravidade", gravidade, GRAV), ("categoria", categoria, CATS), ("origem", origem, ("campvision",) + ORIGENS_MANUAIS)):
        if v:
            if v not in ok_: raise HTTPException(400, f"Filtro inválido: {v}")
            w.append(f"{col}=?"); p.append(v)
    if projeto:
        pr = projeto.strip().upper()
        w.append("(codigo=? OR codigo LIKE ? || '-%')"); p += [pr, pr]
    if q and q.strip():
        t = "%" + q.strip().lower() + "%"
        w.append("(lower(codigo) LIKE ? OR lower(descricao) LIKE ? OR lower(coalesce(relatado_por,'')) LIKE ? OR lower(coalesce(resolucao,'')) LIKE ? "
                 "OR EXISTS (SELECT 1 FROM projeto pj WHERE pj.codigo=substr(erro.codigo,1,10) AND lower(pj.titulo) LIKE ?))"); p += [t] * 5
    return (" WHERE " + " AND ".join(w)) if w else "", p


def _fechar_sozinhos(con) -> None:
    """Antes de mostrar: fecha (com registro) o que se resolveu sozinho com certeza. Só banco, rápido; nunca o QNAP."""
    from . import problemas
    if problemas.fechar_resolvidos(con):
        con.commit()


@router.get("/erros/diagnostico")
def diagnostico_erros(u: dict = Depends(auth.exige("admin"))) -> dict:
    """REF-041: investigar o volume de erros sem fechar ou excluir registros."""
    from .diagnostico_erros import diagnosticar
    con = connect()
    try:
        return diagnosticar(con)
    finally:
        con.close()


@router.get("/erros/contagem")
def contar_erros(gravidade: str | None = None, categoria: str | None = None, origem: str | None = None, projeto: str | None = None, q: str | None = None,
                 u: dict = Depends(auth.exige("leitura"))) -> dict:
    """#94: a contagem das abas de situação (Abertos · Em correção · Resolvidos · Todos), nas mesmas regras do filtro da lista.
    19/10: respeita os filtros da tela e diz quantos abertos talvez já estejam resolvidos ('talvez')."""
    from . import problemas
    con = connect()
    try:
        _fechar_sozinhos(con)
        out = {}
        esc = _escondidos(con, u.get("id"))
        for k in ("abertos", "pedem_acao", "avisos", "em_correcao", "corrigido", "ignorado", "todos"):   # UX-19: pedem_acao e avisos (campos novos)
            w, p = _filtro_erros(k, gravidade, categoria, origem, projeto, q, esc)
            out[k] = con.execute("SELECT COUNT(*) FROM erro" + w, p).fetchone()[0]
        from .contagens import agora_iso
        out["medido_em"] = agora_iso()        # UX-05
        w, p = _filtro_erros("abertos", gravidade, categoria, origem, projeto, q)
        out["talvez"] = sum(1 for x in problemas.enriquecer(con, con.execute("SELECT * FROM erro" + w, p).fetchall()) if x["resolvido_sozinho"])
        # UX-06: com filtro, quantos existem SEM ele (campo novo, opcional). A tela usa para dizer "sem estes filtros há 574 abertos"
        # em vez de abas e lista zeradas sem explicação.
        if any(x and str(x).strip() for x in (gravidade, categoria, origem, projeto, q)):
            out["sem_filtro"] = {k: con.execute("SELECT COUNT(*) FROM erro" + _filtro_erros(k, None, None, None, None, None)[0],
                                                _filtro_erros(k, None, None, None, None, None)[1]).fetchone()[0] for k in ("abertos", "pedem_acao", "avisos", "todos")}
        return out
    finally:
        con.close()


@router.get("/erros/ignorados")
def erros_ignorados(u: dict = Depends(auth.exige("leitura"))) -> dict:
    """UX-03: Problemas › Ignorados. O que VOCÊ escondeu por 7 dias no Precisa de você (volta sozinho) e o que alguém fechou como
    "não era problema" pelo Ignorar nos últimos 30 dias (quem, quando e por quê)."""
    from .qualidade_base import adiadas, agora, _iso
    con = connect()
    try:
        escondidos = []
        if adiadas(con, u.get("id")):
            try:
                rows = con.execute("SELECT tarefa_id, ate, titulo FROM tarefa_adiada WHERE usuario_id=? AND ate>? ORDER BY ate", (u["id"], _iso(agora()))).fetchall()
            except Exception:  # noqa: BLE001  (sem a migração 166)
                rows = con.execute("SELECT tarefa_id, ate, NULL AS titulo FROM tarefa_adiada WHERE usuario_id=? AND ate>? ORDER BY ate", (u["id"], _iso(agora()))).fetchall()
            for r in rows:
                x = {"tarefa_id": r["tarefa_id"], "ate": r["ate"], "titulo": r["titulo"]}
                if r["tarefa_id"].startswith("erro:") and r["tarefa_id"][5:].isdigit():
                    e = con.execute("SELECT id, codigo, descricao, gravidade, situacao FROM erro WHERE id=?", (int(r["tarefa_id"][5:]),)).fetchone()
                    if e:
                        x.update({"erro": dict(e), "titulo": x["titulo"] or e["descricao"]})
                escondidos.append(x)
        nao_era = [dict(r) for r in con.execute("""SELECT e.id, e.codigo, e.descricao, e.gravidade, e.resolucao, e.resolvido_em, e.fechado_por FROM erro e
                                                   WHERE e.situacao='ignorado' AND e.resolvido_em >= datetime('now','-30 days')
                                                     AND EXISTS (SELECT 1 FROM evento v WHERE v.entidade='erro' AND v.codigo=CAST(e.id AS TEXT) AND v.tipo='ignorado')
                                                   ORDER BY e.resolvido_em DESC LIMIT 200""")]
        return {"escondidos": escondidos, "nao_era": nao_era, "total": len(escondidos) + len(nao_era)}
    finally:
        con.close()


class IgnorarErro(BaseModel):
    justificativa: str | None = None


@router.post("/erros/{eid}/ignorar")
def ignorar_erro(eid: int, d: IgnorarErro, u: dict = Depends(auth.exige("operador"))) -> dict:
    """UX-03: "Não mostrar mais (não era problema)" do Precisa de você. Muda o problema para "Não era problema" com autor, data e
    justificativa; o que bloqueia a publicação exige a justificativa. Devolve o token do Desfazer (o mesmo das ações em massa)."""
    con = connect()
    try:
        e = con.execute("SELECT * FROM erro WHERE id=?", (eid,)).fetchone()
        if not e:
            raise HTTPException(404, "Este problema não existe")
        if e["situacao"] not in ("aberto", "em_correcao"):
            raise HTTPException(409, "Este problema já está fechado")
        just = (d.justificativa or "").strip()[:300]
        if e["gravidade"] == "bloqueia" and len(just) < 3:
            raise HTTPException(400, "Este problema bloqueia a publicação: diga em uma frase por que não era problema")
        antes = [{"id": e["id"], "situacao": e["situacao"], "resolucao": e["resolucao"], "resolvido_em": e["resolvido_em"]}]
        con.execute("UPDATE erro SET situacao='ignorado', resolvido_em=datetime('now'), resolucao=?, fechado_por=? WHERE id=?",
                    (just or "Não era problema (ignorado no Precisa de você).", u["email"], eid))
        _evento(con, "erro", eid, "ignorado", u["email"], {"codigo": e["codigo"], "justificativa": just or None, "onde": "precisa_de_voce"})
        tok = _guardar_desfazer(con, u["email"], "ignorar", "ignorado", antes)
        con.commit()
        return {"ok": True, "desfazer": tok}
    finally:
        con.close()


class LimpezaGeral(BaseModel):
    simular: bool = True


NOTA_LIMPEZA = "Limpeza criteriosa: aviso automático comprovadamente resolvido, sem remover histórico."


@router.post("/erros/limpeza-geral")
def limpeza_geral(d: LimpezaGeral, u: dict = Depends(auth.exige("master"))) -> dict:
    """Prévia padrão; execução só dos avisos seguros. Nunca fecha bloqueios nem dúvidas de autoria/código."""
    from .limpeza_segura import candidatos_seguros
    con = connect()
    try:
        if not d.simular:
            con.execute("BEGIN IMMEDIATE")
        candidatos = candidatos_seguros(con)
        por_tipo_map = {}
        for x in candidatos:
            k = (x["categoria"], x["gravidade"])
            por_tipo_map[k] = por_tipo_map.get(k, 0) + 1
        por_tipo = [{"categoria": c, "gravidade": g, "n": n} for (c,g),n in
                    sorted(por_tipo_map.items(), key=lambda x:(-x[1], x[0]))]
        ficam = con.execute("""SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao')
                               AND origem NOT IN ('campvision','revisao')""").fetchone()[0]
        outros_auto = con.execute("""SELECT COUNT(*) FROM erro WHERE situacao IN ('aberto','em_correcao')
                                  AND origem IN ('campvision','revisao')""").fetchone()[0] - len(candidatos)
        out = {"simulado": d.simular, "fecha": len(candidatos), "por_tipo": por_tipo,
               "ficam_relatados_por_pessoas": ficam, "automaticos_que_pedem_decisao": outros_auto}
        if d.simular:
            return out
        ids = []
        for x in candidatos:
            n = con.execute("""UPDATE erro SET situacao='corrigido', resolvido_em=datetime('now'), resolucao=?
                              WHERE id=? AND situacao IN ('aberto','em_correcao')""",
                            (NOTA_LIMPEZA + " " + x["motivo"], x["id"])).rowcount
            if n:
                ids.append(x["id"])
                _evento(con, "erro", x["id"], "fechado_automatico", u["email"],
                        {"codigo": x["codigo"], "motivo": x["motivo"]})
        con.commit()
        return {**out, "fechados": len(ids)}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


@router.get("/erros")
def listar_erros(situacao: str | None = "abertos", gravidade: str | None = None, categoria: str | None = None, origem: str | None = None,
                 projeto: str | None = None, q: str | None = None, u: dict = Depends(auth.exige("leitura"))) -> list[dict]:
    """Lista de Problemas. Cada linha traz também (campos novos, opcionais): projeto_codigo/projeto_titulo, o_que, fazer, acao,
    acao_rotulo, lote_id, folha_existe e resolvido_sozinho ({seguro, motivo}) — ver problemas.py."""
    from . import problemas
    con = connect()
    try:
        _fechar_sozinhos(con)
        w, p = _filtro_erros(situacao, gravidade, categoria, origem, projeto, q, _escondidos(con, u.get("id")))
        rows = con.execute("SELECT * FROM erro" + w + " ORDER BY CASE gravidade WHEN 'bloqueia' THEN 0 WHEN 'corrigir' THEN 1 ELSE 2 END, criado_em DESC, id DESC", p).fetchall()
        return problemas.enriquecer(con, rows)
    finally:
        con.close()


@router.get("/erros/{eid}")
def ver_erro(eid: int, u: dict = Depends(auth.exige("leitura"))) -> dict:
    from . import problemas
    con = connect()
    try:
        e = con.execute("SELECT * FROM erro WHERE id=?", (eid,)).fetchone()
        if not e:
            raise HTTPException(404, "Este problema não existe")
        return problemas.enriquecer(con, [e])[0]
    finally:
        con.close()


@router.post("/erros")
def criar_erro(d: NovoErro, u: dict = Depends(auth.exige("operador"))) -> dict:
    if d.gravidade not in GRAV or d.categoria not in CATS:
        raise HTTPException(400, "Gravidade ou categoria inválida")
    if not d.codigo.strip() or not d.descricao.strip():
        raise HTTPException(400, "Código e descrição são obrigatórios")
    # cartão 13: 'campvision' é só do registro automático (importação do lote); 'site' = quem viu foi um visitante do site
    if d.origem not in ORIGENS_MANUAIS:
        raise HTTPException(400, "Origem inválida: escolha entre você mesmo, a revisão ou um visitante do site")
    relatado = (d.relatado_por or "").strip()[:160]
    if d.origem == "site" and not relatado:
        raise HTTPException(400, "Diga quem avisou pelo site (nome ou e-mail do visitante)")
    con = connect()
    cod = d.codigo.strip().upper()
    # o código precisa existir como fundo, projeto ou folha (antes qualquer texto era aceito e o erro ficava ligado a nada, contando como bloqueante)
    existe = (con.execute("SELECT 1 FROM fundo WHERE codigo=?", (cod,)).fetchone() if re.fullmatch(r"F\d{3}", cod) else
              con.execute("SELECT 1 FROM projeto WHERE codigo=?", (cod,)).fetchone() if re.fullmatch(r"F\d{3}-P\d{4}", cod) else
              con.execute("SELECT 1 FROM item WHERE codigo=?", (cod,)).fetchone() if cod.count("-") == 4 else None)
    if not existe:
        con.close()
        raise HTTPException(400, f"O código {cod} não existe. Confira ou busque o projeto.")
    eid = con.execute("INSERT INTO erro (gravidade, categoria, origem, codigo, descricao, relatado_por) VALUES (?,?,?,?,?,?)",
                      (d.gravidade, d.categoria, d.origem, cod, d.descricao.strip(), relatado or u["email"])).lastrowid
    if d.categoria == "autoria_divergente" and cod.count("-") == 4:
        con.execute("UPDATE item SET autoria_divergente=1 WHERE codigo=?", (cod,))
    # status_site espelha SÓ o site: o bloqueio é derivado dos erros abertos (nunca gravado no status). Se o projeto JÁ está publicado, a tela precisa perguntar o que fazer.
    pc = cod[:10] if len(cod) >= 10 else None
    no_ar = False
    if d.gravidade == "bloqueia" and pc:
        r_ = con.execute("SELECT status_site FROM projeto WHERE codigo=?", (pc,)).fetchone()
        no_ar = bool(r_ and r_[0] == "no_ar")
    _evento(con, "erro", eid, "criado", u["email"], {"codigo": cod, "gravidade": d.gravidade, "origem": d.origem, "publicado_com_bloqueio": no_ar})
    con.commit(); con.close()
    return {"id": eid, "publicado_com_bloqueio": no_ar, "projeto": pc if no_ar else None}


def _mudar_erro(con, e, d: EdicaoErro, ator: str) -> bool:
    """Muda situação/resolução/gravidade de UM problema (a regra da edição e do lote). Levanta HTTPException; não faz commit."""
    campos, vals = [], []
    if d.situacao:
        if d.situacao not in ("aberto", "em_correcao", "corrigido", "fechado", "ignorado"):
            raise HTTPException(400, "Situação inválida")
        if d.situacao in ("corrigido", "fechado", "ignorado") and not ((d.resolucao or "").strip() or e["resolucao"]):
            raise HTTPException(400, "Descreva a resolução antes de fechar")
        campos.append("situacao=?"); vals.append(d.situacao)
        campos.append("fechado_por=?"); vals.append(ator if d.situacao in ("corrigido", "fechado", "ignorado") else None)   # UX-03: quem fechou
        if d.situacao in ("corrigido", "fechado", "ignorado"):
            campos.append("resolvido_em=datetime('now')")
            if e["categoria"] == "autoria_divergente" and d.situacao != "ignorado":
                con.execute("UPDATE item SET autoria_divergente=0 WHERE codigo=?", (e["codigo"],))
    if d.resolucao is not None: campos.append("resolucao=?"); vals.append(d.resolucao)
    if d.gravidade:
        if d.gravidade not in GRAV: raise HTTPException(400, "Gravidade inválida")
        campos.append("gravidade=?"); vals.append(d.gravidade)
    if campos:
        con.execute(f"UPDATE erro SET {', '.join(campos)} WHERE id=?", (*vals, e["id"]))
        _evento(con, "erro", e["id"], "editado", ator, {"situacao": d.situacao})
    return bool(campos)


@router.patch("/erros/{eid}")
def editar_erro(eid: int, d: EdicaoErro, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        e = con.execute("SELECT * FROM erro WHERE id=?", (eid,)).fetchone()
        if not e:
            raise HTTPException(404, "Erro não existe")
        if _mudar_erro(con, e, d, u["email"]):
            con.commit()
        return {"ok": True}
    finally:
        con.close()


@router.post("/erros/lote")
def editar_erros_em_lote(d: ErrosEmLote, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Resolver vários de uma vez (19/10): a mesma situação e a mesma resolução para todos os escolhidos, tudo ou nada.
    Fechar (corrigido/ignorado) exige a frase do que foi feito, como um a um."""
    ids = list(dict.fromkeys(int(i) for i in d.ids))
    if not ids:
        raise HTTPException(400, "Escolha pelo menos um problema")
    if len(ids) > 500:
        raise HTTPException(400, "No máximo 500 de uma vez")
    if d.situacao not in ("aberto", "em_correcao", "corrigido", "ignorado"):
        raise HTTPException(400, "Situação inválida")
    if d.situacao in ("corrigido", "ignorado") and len((d.resolucao or "").strip()) < 3:
        raise HTTPException(400, "Escreva em uma frase o que foi feito (ou por que não era problema)")
    con = connect()
    try:
        rows = con.execute(f"SELECT * FROM erro WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
        if len(rows) != len(ids):
            raise HTTPException(404, f"{len(ids) - len(rows)} dos problemas escolhidos não existem mais: atualize a lista")
        ed = EdicaoErro(situacao=d.situacao, resolucao=(d.resolucao or "").strip() or None)
        antes = [{"id": e["id"], "situacao": e["situacao"], "resolucao": e["resolucao"], "resolvido_em": e["resolvido_em"]} for e in rows]
        n = sum(1 for e in rows if _mudar_erro(con, e, ed, u["email"]))
        desfazer = _guardar_desfazer(con, u["email"], "lote", d.situacao, antes)
        con.commit()
        return {"ok": True, "atualizados": n, "ids": ids, "desfazer": desfazer}
    finally:
        con.close()


# ---------------- UX-20: desfazer de verdade e mesclar mensagens repetidas ----------------
DESFAZER_MINUTOS = 30


def _guardar_desfazer(con, ator: str, acao: str, situacao: str, antes: list[dict]) -> int | None:
    """Guarda como os problemas estavam antes de uma ação em massa. Banco sem a migração 165: sem Desfazer (a ação vale igual)."""
    try:
        return con.execute("INSERT INTO erro_desfazer (ator, acao, situacao, antes) VALUES (?,?,?,?)",
                           (ator, acao, situacao, json.dumps(antes, ensure_ascii=False))).lastrowid
    except Exception:  # noqa: BLE001
        return None


@router.post("/erros/desfazer/{token}")
def desfazer_erros(token: int, u: dict = Depends(auth.exige("operador"))) -> dict:
    """Volta cada problema da ação em massa ao que era antes (situação, resolução e data). Só quem fez (ou um admin), uma vez,
    até 30 min depois; quem já foi mexido por alguém depois da ação fica como está (e a resposta diz quantos)."""
    con = connect()
    try:
        r = con.execute("SELECT * FROM erro_desfazer WHERE id=?", (token,)).fetchone()
        if not r:
            raise HTTPException(404, "Não há o que desfazer")
        if r["ator"] != u["email"] and u["papel"] not in ("admin", "master"):
            raise HTTPException(403, "Só quem fez (ou um admin) pode desfazer")
        if r["desfeito_em"]:
            raise HTTPException(409, "Já foi desfeito")
        if con.execute("SELECT datetime(?, ?) < datetime('now')", (r["criado_em"], f"+{DESFAZER_MINUTOS} minutes")).fetchone()[0]:
            raise HTTPException(409, f"Passou o prazo de {DESFAZER_MINUTOS} minutos para desfazer: reabra um a um")
        voltaram, ficaram = 0, 0
        for a in json.loads(r["antes"] or "[]"):
            n = con.execute("""UPDATE erro SET situacao=?, resolucao=?, resolvido_em=?,
                               fechado_por=CASE WHEN ? IN ('aberto','em_correcao') THEN NULL ELSE fechado_por END WHERE id=? AND situacao=?""",
                            (a["situacao"], a["resolucao"], a["resolvido_em"], a["situacao"], a["id"], r["situacao"])).rowcount
            if n:
                voltaram += 1
                _evento(con, "erro", a["id"], "desfeito", u["email"], {"situacao": a["situacao"], "acao": r["acao"]})
            else:
                ficaram += 1
        con.execute("UPDATE erro_desfazer SET desfeito_em=datetime('now') WHERE id=?", (token,))
        con.commit()
        return {"ok": True, "voltaram": voltaram, "ficaram": ficaram}
    finally:
        con.close()


class MesclarRepetidos(BaseModel):
    simular: bool = True
    codigo: str | None = None          # só os repetidos deste código (o "Mesclar" de um grupo); vazio = todos


def _grupos_repetidos(con, codigo: str | None) -> list[dict]:
    """Abertos com a MESMA origem, código e mensagem: fica o mais antigo, os outros fecham como repetidos."""
    w, p = "situacao IN ('aberto','em_correcao')", []
    if codigo and codigo.strip():
        w += " AND codigo=?"; p.append(codigo.strip().upper())
    out = []
    for g in con.execute(f"""SELECT origem, codigo, descricao, gravidade, COUNT(*) AS n, MIN(id) AS fica FROM erro WHERE {w}
                             GROUP BY origem, codigo, descricao HAVING COUNT(*)>1 ORDER BY n DESC, codigo""", p):
        ids = [r[0] for r in con.execute(f"SELECT id FROM erro WHERE {w} AND origem=? AND descricao=? AND id<>? AND codigo=? ORDER BY id",
                                         (*p, g["origem"], g["descricao"], g["fica"], g["codigo"]))]
        out.append({"codigo": g["codigo"], "descricao": g["descricao"], "origem": g["origem"], "gravidade": g["gravidade"],
                    "quantidade": g["n"], "fica": g["fica"], "fecham": ids})
    return out


@router.post("/erros/mesclar-repetidos")
def mesclar_repetidos(d: MesclarRepetidos, u: dict = Depends(auth.exige("admin"))) -> dict:
    """UX-20: o aviso "há mensagens repetidas" ganha Ver → Mesclar. Prévia é o padrão (simular); mesclar fecha as cópias
    como "Não era problema" com a resolução apontando o que ficou aberto, guarda o Desfazer e registra no histórico."""
    con = connect()
    try:
        if not d.simular:
            con.execute("BEGIN IMMEDIATE")
        grupos = _grupos_repetidos(con, d.codigo)
        out = {"simulado": d.simular, "grupos": grupos[:200], "fecham": sum(len(g["fecham"]) for g in grupos)}
        if d.simular or not grupos:
            if not d.simular:
                con.rollback()
            return out
        antes = []
        for g in grupos:
            for i in g["fecham"]:
                e = con.execute("SELECT id, situacao, resolucao, resolvido_em FROM erro WHERE id=?", (i,)).fetchone()
                antes.append(dict(e))
                con.execute("UPDATE erro SET situacao='ignorado', resolvido_em=datetime('now'), resolucao=? WHERE id=?",
                            (f"Mensagem repetida: o mesmo problema continua aberto no nº {g['fica']}.", i))
                _evento(con, "erro", i, "mesclado", u["email"], {"codigo": g["codigo"], "fica": g["fica"]})
        out["desfazer"] = _guardar_desfazer(con, u["email"], "mesclar", "ignorado", antes)
        con.commit()
        return out
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
