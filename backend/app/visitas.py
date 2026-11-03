"""Visitas ao site com histórico (03/11/2026).

Rafael: "para colocar o analytics no nosso painel, adapte essa solução para nós". O caminho:
Google Analytics 4 / Search Console → coletor no painel (uma vez por dia, em segundo plano) → banco do painel → tela "Visitas ao site".

- Credencial: a conta de serviço que o painel já usa (ga4.conta_servico; o JSON fica no banco do painel, chave sensível — o navegador
  nunca a recebe). Token OAuth temporário, só leitura: analytics.readonly (GA4) e webmasters.readonly (Search Console).
- GA4 (Data API, runReport, propriedade NUMÉRICA ga4.propriedade — não o G-…): por dia, usuários, sessões e visualizações; e dia ×
  canal, origem/mídia, página, cidade e dispositivo. Filtro de domínio ga4.dominio (hostName, com e sem www.) para separar o site
  público de outros sistemas. Pessoas (usuários únicos) não se somam dia a dia: os períodos da tela (7, 28, 90 dias, este mês, mês
  passado) vêm prontos do Google.
- Search Console (sc.site): pesquisas e páginas por dia (cliques, impressões, posição média). Dados agregados; o Google não mostra
  toda pesquisa (consultas raras ficam de fora) e chegam com 2 a 3 dias de atraso.
- Cada coleta fica em visita_coleta (fonte, período coberto, linhas, erro, quem pediu). Os últimos dias são recoletados (o Google
  ainda ajusta os números deles); o que é mais velho não muda.
- Diagnóstico (`diagnostico`): os pontos que mais travam — credencial, propriedade numérica, token, acesso, fluxo G-…, dados no
  período, filtro de domínio e Search Console — cada um com o que fazer.
"""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta

from .db import connect

METRICAS = ["activeUsers", "sessions", "screenPageViews"]
TIPOS = {"canal": ["sessionDefaultChannelGroup"], "origem": ["sessionSourceMedium"], "pagina": ["pagePath", "pageTitle"],
         "cidade": ["city", "country"], "dispositivo": ["deviceCategory"]}
REFAZ_GA = 3          # dias recoletados no GA4 (o Google ainda ajusta)
REFAZ_SC = 4          # no Search Console os dados chegam com atraso
_trava = threading.Lock()


def _cfg(con, chave: str, padrao: str = "") -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return ((r[0] if r else "") or "").strip() or padrao


def _filtro(dominio: str) -> dict | None:
    d = dominio.strip().lower().removeprefix("https://").removeprefix("http://").strip("/").removeprefix("www.")
    if not d:
        return None
    return {"filter": {"fieldName": "hostName", "inListFilter": {"values": [d, "www." + d]}}}


def _data(v: str) -> str:
    v = str(v or "")
    return f"{v[:4]}-{v[4:6]}-{v[6:8]}" if len(v) == 8 and v.isdigit() else v


def periodos(hoje: date) -> dict:
    ontem = hoje - timedelta(days=1)
    ini_mes = hoje.replace(day=1)
    fim_ant = ini_mes - timedelta(days=1)
    out = {"7d": (ontem - timedelta(days=6), ontem), "28d": (ontem - timedelta(days=27), ontem), "90d": (ontem - timedelta(days=89), ontem),
           "mes_anterior": (fim_ant.replace(day=1), fim_ant)}
    if ontem >= ini_mes:
        out["mes"] = (ini_mes, ontem)
    return {k: (a.isoformat(), b.isoformat()) for k, (a, b) in out.items()}


def _nova_coleta(con, fonte: str, de: str, ate: str, por: str) -> int:
    cid = con.execute("INSERT INTO visita_coleta (fonte, de, ate, por) VALUES (?,?,?,?)", (fonte, de, ate, por)).lastrowid
    con.commit()
    return cid


def _fim_coleta(con, cid: int, linhas: int, erro: str | None) -> None:
    con.execute("UPDATE visita_coleta SET fim=datetime('now'), linhas=?, erro=? WHERE id=?", (linhas, (erro or None) and erro[:500], cid))
    con.commit()


def _coletar_ga(con, g, hoje: date, por: str, filtrar: bool = True) -> dict:
    ontem = (hoje - timedelta(days=1)).isoformat()
    ultimo = con.execute("SELECT MAX(dia) FROM visita_dia").fetchone()[0]
    dias_ini = _cfg(con, "visitas.dias_iniciais", "90")
    dias_ini = max(1, min(480, int(dias_ini))) if dias_ini.isdigit() else 90
    de = (date.fromisoformat(ultimo) - timedelta(days=REFAZ_GA)).isoformat() if ultimo else (hoje - timedelta(days=dias_ini)).isoformat()
    de = min(de, ontem)
    cid = _nova_coleta(con, "ga4", de, ontem, por)
    try:
        filtro = _filtro(_cfg(con, "ga4.dominio")) if filtrar else None
        base = {"dateRanges": [{"startDate": de, "endDate": ontem}], "metrics": [{"name": m} for m in METRICAS], **({"dimensionFilter": filtro} if filtro else {})}
        dias = g.run_report({**base, "dimensions": [{"name": "date"}]})
        dims: dict[tuple, dict] = {}
        for tipo, nomes in TIPOS.items():
            for r in g.run_report({**base, "dimensions": [{"name": "date"}] + [{"name": n} for n in nomes]}):
                if tipo == "cidade":
                    valor = ", ".join(x for x in (r.get("city"), r.get("country")) if x and x != "(not set)") or "(não informado)"
                else:
                    valor = r.get(nomes[0]) or "(não informado)"
                k = (_data(r.get("date")), tipo, valor[:500])
                d = dims.setdefault(k, {"extra": (r.get("pageTitle") or "")[:300] if tipo == "pagina" else None, "u": 0, "s": 0, "v": 0})
                d["u"] += int(float(r.get("activeUsers") or 0)); d["s"] += int(float(r.get("sessions") or 0)); d["v"] += int(float(r.get("screenPageViews") or 0))
        pers = {}
        for chave, (pd, pa) in periodos(hoje).items():
            rows = g.run_report({**base, "dateRanges": [{"startDate": pd, "endDate": pa}]})
            r0 = rows[0] if rows else {}
            pers[chave] = (pd, pa, int(float(r0.get("activeUsers") or 0)), int(float(r0.get("sessions") or 0)), int(float(r0.get("screenPageViews") or 0)))
    except Exception as e:  # noqa: BLE001
        _fim_coleta(con, cid, 0, str(e))
        return {"ok": False, "erro": str(e)[:300], "de": de, "ate": ontem}
    con.execute("BEGIN")
    con.execute("DELETE FROM visita_dia WHERE dia BETWEEN ? AND ?", (de, ontem))
    con.execute("DELETE FROM visita_dimensao WHERE dia BETWEEN ? AND ?", (de, ontem))
    for r in dias:
        con.execute("INSERT OR REPLACE INTO visita_dia (dia, usuarios, sessoes, visualizacoes, coleta_id) VALUES (?,?,?,?,?)",
                    (_data(r.get("date")), int(float(r.get("activeUsers") or 0)), int(float(r.get("sessions") or 0)), int(float(r.get("screenPageViews") or 0)), cid))
    for (dia, tipo, valor), d in dims.items():
        con.execute("INSERT OR REPLACE INTO visita_dimensao (dia, tipo, valor, extra, usuarios, sessoes, visualizacoes, coleta_id) VALUES (?,?,?,?,?,?,?,?)",
                    (dia, tipo, valor, d["extra"], d["u"], d["s"], d["v"], cid))
    for chave, (pd, pa, u, s, v) in pers.items():
        con.execute("INSERT OR REPLACE INTO visita_periodo (chave, de, ate, usuarios, sessoes, visualizacoes, coleta_id) VALUES (?,?,?,?,?,?,?)",
                    (chave, pd, pa, u, s, v, cid))
    con.execute("COMMIT")
    n = len(dias) + len(dims)
    _fim_coleta(con, cid, n, None)
    return {"ok": True, "de": de, "ate": ontem, "linhas": n}


def _coletar_sc(con, sc, hoje: date, por: str) -> dict:
    if sc is None:
        return {"ok": False, "pulado": True, "erro": "Search Console não ligado"}
    ontem = (hoje - timedelta(days=1)).isoformat()
    ultimo = con.execute("SELECT MAX(dia) FROM busca_google").fetchone()[0]
    dias_ini = _cfg(con, "visitas.dias_iniciais", "90")
    dias_ini = max(1, min(480, int(dias_ini))) if dias_ini.isdigit() else 90
    de = (date.fromisoformat(ultimo) - timedelta(days=REFAZ_SC)).isoformat() if ultimo else (hoje - timedelta(days=dias_ini)).isoformat()
    de = min(de, ontem)
    cid = _nova_coleta(con, "search_console", de, ontem, por)
    try:
        linhas = [("consulta", r["date"], r.get("query") or "", r) for r in sc.consulta(de, ontem, ["date", "query"])]
        linhas += [("pagina", r["date"], r.get("page") or "", r) for r in sc.consulta(de, ontem, ["date", "page"])]
    except Exception as e:  # noqa: BLE001
        _fim_coleta(con, cid, 0, str(e))
        return {"ok": False, "erro": str(e)[:300], "de": de, "ate": ontem}
    con.execute("BEGIN")
    con.execute("DELETE FROM busca_google WHERE dia BETWEEN ? AND ?", (de, ontem))
    for tipo, dia, valor, r in linhas:
        con.execute("INSERT OR REPLACE INTO busca_google (dia, tipo, valor, cliques, impressoes, posicao, coleta_id) VALUES (?,?,?,?,?,?,?)",
                    (dia, tipo, valor[:500], r["cliques"], r["impressoes"], round(r["posicao"], 2), cid))
    con.execute("COMMIT")
    _fim_coleta(con, cid, len(linhas), None)
    return {"ok": True, "de": de, "ate": ontem, "linhas": len(linhas)}


def _erro_coleta(con, fonte: str, erro: str, por: str, hoje: date) -> dict:
    """Falha antes de chegar ao Google (nada ligado, chave inválida): fica registrada para a tela mostrar o motivo."""
    ontem = (hoje - timedelta(days=1)).isoformat()
    cid = _nova_coleta(con, fonte, ontem, ontem, por)
    _fim_coleta(con, cid, 0, erro)
    return {"ok": False, "erro": erro[:300]}


def _conta(con) -> dict | None:
    try:
        c = json.loads(_cfg(con, "ga4.conta_servico") or "null")
    except ValueError:
        return None
    return c if isinstance(c, dict) and c.get("type") == "service_account" and c.get("client_email") and c.get("private_key") else None


def _gravar_cfg(con, chave: str, valor: str) -> None:
    con.execute("UPDATE configuracao SET valor=? WHERE chave=?", (valor, chave))
    con.commit()


def preparar(con, cliente=None) -> list[str]:
    """03/11 (Rafael: "já preencha tudo que sabe que tem"): com a chave da conta de serviço, descobre e grava o número da propriedade
    GA4 (vazio ou um G-… colado no lugar) e a propriedade do Search Console (sc.site vazio). Devolve o que fez ou o que travou."""
    from . import ga4_direto
    import httpx
    conta = _conta(con)
    if not conta:
        return []
    h = cliente or httpx.Client(timeout=30)
    dominio = _cfg(con, "ga4.dominio") or "camp.arq.br"
    notas = []
    prop = _cfg(con, "ga4.propriedade").removeprefix("properties/").strip()
    if not prop.isdigit():
        try:
            a = ga4_direto.descobrir_propriedade(conta, h, dominio, prop)
            _gravar_cfg(con, "ga4.propriedade", a["propriedade"])
            notas.append(f"ga4.propriedade preenchida sozinha: {a['propriedade']} ({a['nome']}{', ' + a['id_medicao'] if a.get('id_medicao') else ''})")
        except Exception as e:  # noqa: BLE001
            notas.append(f"propriedade GA4: {str(e)[:300]}")
    if not _cfg(con, "sc.site"):
        try:
            site = ga4_direto.descobrir_search_console(conta, h, dominio)
            _gravar_cfg(con, "sc.site", site)
            notas.append(f"sc.site preenchido sozinho: {site}")
        except Exception as e:  # noqa: BLE001
            notas.append(f"Search Console: {str(e)[:300]}")
    return notas


class _SiteKitGA:
    """Sem conta de serviço: o mesmo relatório pelo Google Site Kit do site (o usuário do painel no site precisa estar conectado
    ao Google dentro do Site Kit). Sem filtro de domínio: a propriedade do Site Kit já é a do site."""

    def __init__(self, wp):
        self.wp = wp

    def run_report(self, corpo: dict, limite_total: int = 100000) -> list[dict]:
        r_ = corpo["dateRanges"][0]
        params = [("startDate", r_["startDate"]), ("endDate", r_["endDate"]), ("limit", 10000)]
        params += [(f"metrics[{i}][name]", m["name"]) for i, m in enumerate(corpo["metrics"])]
        params += [(f"dimensions[{i}][name]", d["name"]) for i, d in enumerate(corpo.get("dimensions") or [])]
        r = self.wp.h.get("/wp-json/google-site-kit/v1/modules/analytics-4/data/report", params=params)
        if r.status_code >= 400:
            raise RuntimeError(f"Site Kit (Analytics) recusou ({r.status_code}): {_msg_wp(r)}. Sem a chave da conta de serviço o painel usa o "
                               "Site Kit do site: avise quem cuida do site: o usuário do painel no site precisa estar conectado ao Google no Site Kit")
        j = r.json()
        dims = [x["name"] for x in j.get("dimensionHeaders") or []]
        mets = [x["name"] for x in j.get("metricHeaders") or []]
        out = []
        for row in j.get("rows") or []:
            d = {n: (v.get("value") or "") for n, v in zip(dims, row.get("dimensionValues") or [])}
            d.update({n: (v.get("value") or "0") for n, v in zip(mets, row.get("metricValues") or [])})
            out.append(d)
        return out


class _SiteKitSC:
    def __init__(self, wp):
        self.wp = wp

    def consulta(self, de: str, ate: str, dimensoes: list[str], limite_total: int = 25000) -> list[dict]:
        r = self.wp.h.get("/wp-json/google-site-kit/v1/modules/search-console/data/searchanalytics",
                          params={"startDate": de, "endDate": ate, "dimensions": ",".join(dimensoes), "limit": min(limite_total, 25000)})
        if r.status_code >= 400:
            raise RuntimeError(f"Site Kit (Search Console) recusou ({r.status_code}): {_msg_wp(r)}")
        j = r.json()
        linhas = j if isinstance(j, list) else (j.get("rows") or [])
        return [{**dict(zip(dimensoes, l.get("keys") or [])), "cliques": int(l.get("clicks") or 0), "impressoes": int(l.get("impressions") or 0),
                 "posicao": float(l.get("position") or 0)} for l in linhas]


def _msg_wp(r) -> str:
    try:
        j = r.json()
        return (j.get("message") or j.get("code") or "")[:200] if isinstance(j, dict) else r.text[:200]
    except ValueError:
        return r.text[:200]


def fontes(con, cliente=None) -> dict:
    """De onde vêm os números: {via, ga, sc, erro}. Preferência: conta de serviço (descobre o que falta); senão, o Site Kit do site."""
    from . import ga4_direto
    if _conta(con):
        notas = preparar(con, cliente)
        try:
            cfg = ga4_direto.configurado(con)
        except Exception as e:  # noqa: BLE001
            cfg, notas = None, notas + [str(e)]
        if not cfg:
            return {"via": "conta de serviço", "erro": "; ".join(notas) or "ga4.propriedade vazio", "notas": notas}
        site = _cfg(con, "sc.site")
        return {"via": "conta de serviço", "ga": ga4_direto.GA4(cfg, cliente), "filtrar": True,
                "sc": ga4_direto.SearchConsole(cfg["conta"], site, cliente) if site else None, "notas": notas}
    if _cfg(con, "ga4.conta_servico"):
        return {"via": "conta de serviço", "erro": "ga4.conta_servico não é a chave JSON de uma conta de serviço: cole o arquivo .json inteiro", "notas": []}
    try:
        from .wp import WP
        wp = WP() if cliente is None else WP.__new__(WP)
        if cliente is not None:
            wp.h = cliente
    except Exception as e:  # noqa: BLE001
        return {"via": "Site Kit", "erro": f"Nada ligado: sem a chave da conta de serviço (ga4.conta_servico) e o site não respondeu ({str(e)[:200]})", "notas": []}
    return {"via": "Site Kit", "ga": _SiteKitGA(wp), "filtrar": False, "sc": _SiteKitSC(wp), "notas": []}


def coletar(por: str = "automático", cliente=None, hoje: date | None = None) -> dict:
    """Uma coleta (GA4 + Search Console). Nunca levanta; uma por vez."""
    if not _trava.acquire(blocking=False):
        return {"ocupada": True}
    con = connect()
    con.isolation_level = None
    try:
        hoje = hoje or date.today()
        try:
            f = fontes(con, cliente)
        except Exception as e:  # noqa: BLE001
            f = {"erro": str(e)[:300], "notas": []}
        if f.get("erro"):
            return {"via": f.get("via"), "notas": f["notas"], "ga4": _erro_coleta(con, "ga4", f["erro"], por, hoje)}
        out = {"via": f["via"], "notas": f["notas"], "ga4": _coletar_ga(con, f["ga"], hoje, por, f["filtrar"]),
               "search_console": _coletar_sc(con, f["sc"], hoje, por)}
        return out
    finally:
        con.close()
        _trava.release()


def precisa_coletar(con, agora: datetime | None = None) -> bool:
    """A coleta automática do dia: depois da hora configurada, se ainda não houve uma certa hoje (e sem repetir erro em menos de 3 h)."""
    agora = agora or datetime.now()
    h = _cfg(con, "visitas.coleta_hora")
    if not h.isdigit() or agora.hour < int(h):
        return False
    hoje = agora.date().isoformat()
    ok = con.execute("SELECT 1 FROM visita_coleta WHERE fonte='ga4' AND erro IS NULL AND fim IS NOT NULL AND date(inicio, 'localtime')=?", (hoje,)).fetchone()
    if ok:
        return False
    ult = con.execute("SELECT inicio FROM visita_coleta WHERE fonte='ga4' AND date(inicio, 'localtime')=? ORDER BY id DESC LIMIT 1", (hoje,)).fetchone()
    if ult:
        quando = con.execute("SELECT (julianday('now') - julianday(?)) * 24", (ult[0],)).fetchone()[0]
        return quando >= 3
    return True


# ---------------------------------------------------------------- leitura (só do banco)
def resumo(con, de: str, ate: str, chave: str | None = None) -> dict:
    p = con.execute("SELECT * FROM visita_periodo WHERE chave=? AND de=? AND ate=?", (chave, de, ate)).fetchone() if chave else None
    tot = con.execute("SELECT COALESCE(SUM(usuarios),0) u, COALESCE(SUM(sessoes),0) s, COALESCE(SUM(visualizacoes),0) v, COUNT(*) n FROM visita_dia WHERE dia BETWEEN ? AND ?",
                      (de, ate)).fetchone()
    pessoas = p["usuarios"] if p else None
    por_dia = [dict(r) for r in con.execute("SELECT dia, usuarios, sessoes, visualizacoes FROM visita_dia WHERE dia BETWEEN ? AND ? ORDER BY dia", (de, ate))]

    def tabela(tipo, ordem="sessoes", n=15):
        return [dict(r) for r in con.execute(f"""SELECT valor, MAX(extra) AS extra, SUM(sessoes) AS sessoes, SUM(visualizacoes) AS visualizacoes
                                                   FROM visita_dimensao WHERE tipo=? AND dia BETWEEN ? AND ? GROUP BY valor ORDER BY {ordem} DESC LIMIT ?""",
                                             (tipo, de, ate, n))]

    def busca(tipo, n=25):
        return [{**dict(r), "ctr": round(100.0 * r["cliques"] / r["impressoes"], 1) if r["impressoes"] else 0.0}
                for r in con.execute("""SELECT valor, SUM(cliques) AS cliques, SUM(impressoes) AS impressoes,
                                               ROUND(SUM(posicao*impressoes)/NULLIF(SUM(impressoes),0), 1) AS posicao
                                          FROM busca_google WHERE tipo=? AND dia BETWEEN ? AND ? GROUP BY valor ORDER BY cliques DESC, impressoes DESC LIMIT ?""",
                                     (tipo, de, ate, n))]
    sc = con.execute("SELECT COALESCE(SUM(cliques),0) c, COALESCE(SUM(impressoes),0) i, MIN(dia) a, MAX(dia) b FROM busca_google WHERE tipo='consulta' AND dia BETWEEN ? AND ?",
                     (de, ate)).fetchone()
    cob = con.execute("SELECT MIN(dia), MAX(dia) FROM visita_dia").fetchone()
    return {"de": de, "ate": ate, "dias_com_dados": tot["n"],
            "total": {"pessoas": pessoas, "pessoas_exato": pessoas is not None, "sessoes": tot["s"], "visualizacoes": tot["v"]},
            "por_dia": por_dia, "canais": tabela("canal"), "origens": tabela("origem"), "paginas": tabela("pagina", "visualizacoes", 20),
            "cidades": tabela("cidade"), "dispositivos": tabela("dispositivo"),
            "busca": {"cliques": sc["c"], "impressoes": sc["i"], "de": sc["a"], "ate": sc["b"], "consultas": busca("consulta"), "paginas": busca("pagina", 15)},
            "cobertura": {"de": cob[0], "ate": cob[1]}, "coletas": ultimas_coletas(con)}


def ultimas_coletas(con, n: int = 6) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT id, inicio, fim, fonte, de, ate, linhas, erro, por FROM visita_coleta ORDER BY id DESC LIMIT ?", (n,))]


# ---------------------------------------------------------------- diagnóstico
def _dica(msg: str, projeto: str | None) -> str:
    m = msg.lower()
    if "has not been used" in m or "is disabled" in m or "service_disabled" in m:
        return f"Habilite esta API no projeto do Google Cloud {projeto or 'da conta de serviço'} (APIs e serviços → Biblioteca) e espere alguns minutos."
    return ""


def diagnostico(cliente=None) -> list[dict]:
    """Os pontos que mais travam, em ordem; cada um {item, ok, detalhe, fazer}."""
    from . import ga4_direto
    out = []

    def item(nome, ok, detalhe="", fazer=""):
        out.append({"item": nome, "ok": ok, "detalhe": detalhe, "fazer": fazer})
        return ok
    con = connect()
    try:
        for n in preparar(con, cliente):
            item("Preenchimento automático", "preenchid" in n, n)
        prop_txt, conta_txt = _cfg(con, "ga4.propriedade"), _cfg(con, "ga4.conta_servico")
        dominio, site = _cfg(con, "ga4.dominio"), _cfg(con, "sc.site")
        if not conta_txt:
            # sem a chave: o painel tenta o Site Kit do WordPress
            f = fontes(con, cliente)
    finally:
        con.close()
    if not conta_txt:
        item("Chave da conta de serviço (ga4.conta_servico)", False, "vazia: o painel tenta pelo Site Kit do site",
             "Mais estável: Google Cloud → IAM → Contas de serviço → criar chave JSON; cole o arquivo inteiro em ga4.conta_servico (o resto o painel preenche sozinho)")
        if f.get("erro"):
            item("Site Kit do site", False, f["erro"], "Confira wp.url, wp.usuario e wp.app_password em Configurações")
            return out
        hoje = date.today()
        de, ate = (hoje - timedelta(days=28)).isoformat(), (hoje - timedelta(days=1)).isoformat()
        try:
            rows = f["ga"].run_report({"dateRanges": [{"startDate": de, "endDate": ate}], "metrics": [{"name": "sessions"}]})
            item("Site Kit: Google Analytics", True, f"{(rows[0].get('sessions') if rows else 0)} sessões nos últimos 28 dias")
        except Exception as e:  # noqa: BLE001
            item("Site Kit: Google Analytics", False, str(e)[:300],
                 "Avise quem cuida do site: com o usuário do painel (wp.usuario), conectar o Google no Site Kit. Ou cole a chave da conta de serviço")
        try:
            n = len(f["sc"].consulta(de, ate, ["query"], 1000))
            item("Site Kit: Search Console", True, f"{n} pesquisas nos últimos 28 dias")
        except Exception as e:  # noqa: BLE001
            item("Site Kit: Search Console", False, str(e)[:300], "Conecte o Search Console no Site Kit")
        return out
    try:
        conta = json.loads(conta_txt) if conta_txt else None
    except ValueError:
        conta = None
    if not item("Conta de serviço (chave JSON)", bool(conta and conta.get("type") == "service_account" and conta.get("private_key")),
                (conta or {}).get("client_email", "não preenchida ou não é a chave de uma conta de serviço"),
                "Google Cloud → IAM → Contas de serviço → criar chave JSON; cole o arquivo inteiro em ga4.conta_servico"):
        return out
    projeto = conta.get("project_id")
    p = prop_txt.removeprefix("properties/").strip()
    if not item("ID numérico da propriedade GA4", p.isdigit(), p or "vazio",
                "O painel tenta achar sozinho (precisa da conta como Leitor no GA4); senão: GA4 → Administrador → Detalhes da propriedade → ID (só números)"):
        return out
    cfg = {"propriedade": p, "conta": conta}
    g = ga4_direto.GA4(cfg, cliente)
    try:
        ga4_direto._token(conta, g.h)
        item("Token só de leitura (analytics.readonly)", True, "o Google aceitou a conta de serviço")
    except Exception as e:  # noqa: BLE001
        item("Token só de leitura (analytics.readonly)", False, str(e)[:240], "Confira se a chave não foi apagada no Google Cloud (crie outra e cole de novo)")
        return out
    try:
        fl = g.fluxos()
        web = [f for f in fl if f.get("id_medicao")]
        item("Propriedade e fluxo do site (Admin API)", bool(web), "; ".join(f"{f['id_medicao']} · {f.get('endereco') or ''}" for f in web) or "nenhum fluxo da Web",
             "" if web else "Crie um fluxo da Web para o site no GA4 e instale a tag G-… no site")
    except Exception as e:  # noqa: BLE001
        item("Propriedade e fluxo do site (Admin API)", False, str(e)[:240],
             _dica(str(e), projeto) or "Habilite a Google Analytics Admin API e adicione a conta como Leitor na propriedade (Administrador → Gerenciamento de acesso)")
    hoje = date.today()
    de, ate = (hoje - timedelta(days=28)).isoformat(), (hoje - timedelta(days=1)).isoformat()
    try:
        sem = g.run_report({"dateRanges": [{"startDate": de, "endDate": ate}], "metrics": [{"name": "sessions"}], "dimensions": [{"name": "hostName"}]})
        total = sum(int(float(r.get("sessions") or 0)) for r in sem)
        item("Acesso à Data API e dados nos últimos 28 dias", total > 0, f"{total} sessões",
             "" if total else "A API funciona, mas o Google não recebeu visitas: confira se a tag G-… está no site e o consentimento de cookies")
        if dominio and total:
            f = _filtro(dominio)["filter"]["inListFilter"]["values"]
            com = sum(int(float(r.get("sessions") or 0)) for r in sem if (r.get("hostName") or "").lower() in f)
            outros = ", ".join(f"{r.get('hostName')} ({r.get('sessions')})" for r in sorted(sem, key=lambda r: -int(float(r.get('sessions') or 0)))[:5])
            item(f"Filtro do domínio ({dominio})", com > 0, f"{com} de {total} sessões são do site público · domínios vistos: {outros}",
                 "" if com else "Ajuste ga4.dominio para um dos domínios vistos")
    except Exception as e:  # noqa: BLE001
        item("Acesso à Data API e dados nos últimos 28 dias", False, str(e)[:240],
             _dica(str(e), projeto) or "Adicione o e-mail da conta de serviço como Leitor na propriedade GA4 (Administrador → Gerenciamento de acesso à propriedade)")
    if not site:
        item("Search Console", False, "sc.site vazio", "Preencha sc.site (sc-domain:camp.arq.br ou https://camp.arq.br/) e adicione a conta de serviço como usuária no Search Console")
    else:
        try:
            linhas = ga4_direto.SearchConsole(conta, site, g.h).consulta(de, ate, ["query"], limite_total=25000)
            item("Search Console (pesquisas no Google)", True, f"{len(linhas)} pesquisas nos últimos 28 dias em {site}")
        except Exception as e:  # noqa: BLE001
            item("Search Console (pesquisas no Google)", False, str(e)[:240],
                 _dica(str(e), projeto) or "Habilite a Search Console API e adicione a conta de serviço como usuária da propriedade (Restrito)")
    return out
