"""Google Analytics 4 direto pela Data API, com uma conta de serviço do Google (sem passar pelo Site Kit).

O Site Kit só responde se o usuário WordPress do painel estiver conectado ao Google dentro do Site Kit, e essa
conexão cai (token vencido, escopo novo, troca de usuário). Com a conta de serviço o painel fala direto com o GA4:
Configurações → ga4.propriedade (o número da propriedade) e ga4.conta_servico (o JSON da chave). No GA4, a conta
de serviço precisa ser adicionada como Leitor na propriedade (Administrador → Gerenciamento de acesso).
As respostas têm o mesmo formato do relatório do Site Kit (rows/dimensionHeaders/metricHeaders).
"""
from __future__ import annotations

import json
import time

import httpx

ESCOPO = "https://www.googleapis.com/auth/analytics.readonly"
ESCOPO_SC = "https://www.googleapis.com/auth/webmasters.readonly"     # 03/11: Search Console (só leitura)
API = "https://analyticsdata.googleapis.com/v1beta"
API_ADMIN = "https://analyticsadmin.googleapis.com/v1beta"             # 03/11: conferir a propriedade e os fluxos (G-…)
API_SC = "https://searchconsole.googleapis.com/webmasters/v3"
_TOKENS: dict = {}                                                       # (conta, escopo) -> {token, expira}


def _cfg(con, chave: str) -> str:
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    return (r[0] or "").strip() if r else ""


def configurado(con) -> dict | None:
    """{propriedade, conta} se as duas chaves estão preenchidas; senão None (o painel usa o Site Kit)."""
    prop, js = _cfg(con, "ga4.propriedade"), _cfg(con, "ga4.conta_servico")
    if not prop or not js:
        return None
    prop = prop.removeprefix("properties/").strip()
    if not prop.isdigit():
        raise RuntimeError("ga4.propriedade deve ser só o número da propriedade GA4 (ex.: 467114271), não o G-XXXX")
    try:
        conta = json.loads(js)
    except ValueError as e:
        raise RuntimeError("ga4.conta_servico não é um JSON válido: cole o conteúdo inteiro do arquivo da chave") from e
    if conta.get("type") != "service_account" or not conta.get("client_email") or not conta.get("private_key"):
        raise RuntimeError("ga4.conta_servico precisa ser a chave JSON de uma CONTA DE SERVIÇO (type service_account)")
    return {"propriedade": prop, "conta": conta}


def _token(conta: dict, cliente: httpx.Client, escopo: str = ESCOPO) -> str:
    """Token OAuth temporário (1 h) da conta de serviço, só de leitura, um por escopo (Analytics, Search Console)."""
    chave = (conta["client_email"] + conta.get("private_key_id", ""), escopo)
    t = _TOKENS.get(chave)
    if t and time.time() < t["expira"] - 60:
        return t["token"]
    import jwt   # pyjwt; assinatura RS256 usa o pacote cryptography
    agora = int(time.time())
    uri = conta.get("token_uri") or "https://oauth2.googleapis.com/token"
    afirmacao = jwt.encode({"iss": conta["client_email"], "scope": escopo, "aud": uri, "iat": agora, "exp": agora + 3600},
                           conta["private_key"], algorithm="RS256", headers={"kid": conta.get("private_key_id")} if conta.get("private_key_id") else None)
    r = cliente.post(uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": afirmacao})
    if r.status_code >= 400:
        raise RuntimeError(f"O Google recusou a conta de serviço ({r.status_code}): {_msg(r)}")
    j = r.json()
    _TOKENS[chave] = {"token": j["access_token"], "expira": time.time() + int(j.get("expires_in", 3600))}
    return j["access_token"]


def _msg(r) -> str:
    try:
        j = r.json()
        e = j.get("error")
        return (e.get("message") if isinstance(e, dict) else j.get("error_description") or e) or r.text[:200]
    except ValueError:
        return r.text[:200]


class GA4:
    def __init__(self, cfg: dict, cliente: httpx.Client | None = None):
        self.prop, self.conta = cfg["propriedade"], cfg["conta"]
        self.h = cliente or httpx.Client(timeout=30)

    def _post(self, caminho: str, corpo: dict) -> dict:
        r = self.h.post(f"{API}/properties/{self.prop}:{caminho}", json=corpo, headers={"Authorization": f"Bearer {_token(self.conta, self.h)}"})
        if r.status_code == 403:
            raise RuntimeError(f"A conta de serviço {self.conta['client_email']} não tem acesso à propriedade {self.prop}: "
                               "no GA4, Administrador → Gerenciamento de acesso à propriedade → adicionar esse e-mail como Leitor")
        if r.status_code >= 400:
            raise RuntimeError(f"GA4 recusou ({r.status_code}): {_msg(r)}")
        return r.json()

    def relatorio(self, *, start_date: str, end_date: str, metrics: list[str], dimensions: list[str] | None = None, limit: int | None = None) -> dict:
        corpo = {"dateRanges": [{"startDate": start_date, "endDate": end_date}], "metrics": [{"name": m} for m in metrics]}
        if dimensions:
            corpo["dimensions"] = [{"name": d} for d in dimensions]
            corpo["orderBys"] = [{"metric": {"metricName": metrics[0]}, "desc": True}]
        if limit:
            corpo["limit"] = limit
        return self._post("runReport", corpo)

    def agora(self) -> int:
        """Usuários ativos nos últimos 30 minutos (Realtime API)."""
        j = self._post("runRealtimeReport", {"metrics": [{"name": "activeUsers"}]})
        rows = j.get("rows") or []
        return int(rows[0]["metricValues"][0]["value"]) if rows else 0


    # ---- 03/11 (visitas com histórico): consulta completa com filtro e paginação, e a Admin API
    def run_report(self, corpo: dict, limite_total: int = 100000) -> list[dict]:
        """runReport com o corpo inteiro (dimensionFilter etc.), paginado; devolve as linhas como {dimensão|métrica: valor}."""
        out, offset = [], 0
        while True:
            j = self._post("runReport", {**corpo, "limit": 10000, "offset": offset})
            dims = [h["name"] for h in j.get("dimensionHeaders") or []]
            mets = [h["name"] for h in j.get("metricHeaders") or []]
            for r in j.get("rows") or []:
                d = {n: (v.get("value") or "") for n, v in zip(dims, r.get("dimensionValues") or [])}
                d.update({n: (v.get("value") or "0") for n, v in zip(mets, r.get("metricValues") or [])})
                out.append(d)
            total = int(j.get("rowCount") or 0)
            offset += 10000
            if offset >= total or offset >= limite_total or not j.get("rows"):
                return out

    def fluxos(self) -> list[dict]:
        """Os fluxos de dados da propriedade (Admin API): o G-… e o endereço de cada um."""
        r = self.h.get(f"{API_ADMIN}/properties/{self.prop}/dataStreams", headers={"Authorization": f"Bearer {_token(self.conta, self.h)}"})
        if r.status_code >= 400:
            raise RuntimeError(f"Admin API recusou ({r.status_code}): {_msg(r)}")
        return [{"nome": s.get("displayName"), "tipo": s.get("type"), "id_medicao": (s.get("webStreamData") or {}).get("measurementId"),
                 "endereco": (s.get("webStreamData") or {}).get("defaultUri")} for s in r.json().get("dataStreams") or []]


class SearchConsole:
    """Search Console API (searchAnalytics.query), com a MESMA conta de serviço. Ela precisa ser usuária da propriedade no Search
    Console (Configurações → Usuários e permissões → adicionar o e-mail da conta, permissão Restrita)."""

    def __init__(self, conta: dict, site: str, cliente: httpx.Client | None = None):
        self.conta, self.site = conta, site.strip()
        self.h = cliente or httpx.Client(timeout=60)

    def consulta(self, de: str, ate: str, dimensoes: list[str], limite_total: int = 100000) -> list[dict]:
        from urllib.parse import quote
        url = f"{API_SC}/sites/{quote(self.site, safe='')}/searchAnalytics/query"
        out, inicio = [], 0
        while True:
            r = self.h.post(url, json={"startDate": de, "endDate": ate, "dimensions": dimensoes, "rowLimit": 25000, "startRow": inicio,
                                       "dataState": "final"},
                            headers={"Authorization": f"Bearer {_token(self.conta, self.h, ESCOPO_SC)}"})
            if r.status_code == 403:
                raise RuntimeError(f"A conta de serviço {self.conta['client_email']} não tem acesso a {self.site} no Search Console: "
                                   "Configurações → Usuários e permissões → adicionar esse e-mail (Restrito)")
            if r.status_code >= 400:
                raise RuntimeError(f"Search Console recusou ({r.status_code}): {_msg(r)}")
            linhas = r.json().get("rows") or []
            out += [{**dict(zip(dimensoes, l.get("keys") or [])), "cliques": int(l.get("clicks") or 0), "impressoes": int(l.get("impressions") or 0),
                     "posicao": float(l.get("position") or 0)} for l in linhas]
            inicio += 25000
            if len(linhas) < 25000 or inicio >= limite_total:
                return out


# ---- 03/11 (Rafael: "continua sem funcionar… já preencha tudo que sabe que tem"): com a chave da conta de serviço o painel
# descobre sozinho o número da propriedade GA4 (pelo domínio do site ou pelo G-… colado no lugar) e a propriedade do Search Console.
def _dominio_de(url: str) -> str:
    from urllib.parse import urlparse
    h = (urlparse(url if "://" in url else "https://" + url).hostname or "").lower()
    return h.removeprefix("www.")


def descobrir_propriedade(conta: dict, cliente: httpx.Client, dominio: str = "", dica: str = "") -> dict:
    """{propriedade, nome, id_medicao, vistas:[...]} — a propriedade GA4 que a conta enxerga e cujo fluxo é o do site."""
    h = {"Authorization": f"Bearer {_token(conta, cliente)}"}
    r = cliente.get(f"{API_ADMIN}/accountSummaries", params={"pageSize": 200}, headers=h)
    if r.status_code >= 400:
        raise RuntimeError(f"Admin API recusou ({r.status_code}): {_msg(r)}")
    props = [(p.get("property", "").removeprefix("properties/"), p.get("displayName") or "")
             for a in r.json().get("accountSummaries") or [] for p in a.get("propertySummaries") or []]
    if not props:
        raise RuntimeError(f"A conta de serviço {conta['client_email']} não enxerga nenhuma propriedade GA4: no GA4, Administrador → "
                           "Gerenciamento de acesso à propriedade → adicionar esse e-mail como Leitor")
    dominio, dica = _dominio_de(dominio) if dominio else "", (dica or "").strip().upper()
    vistas, achou = [], None
    for num, nome in props:
        rr = cliente.get(f"{API_ADMIN}/properties/{num}/dataStreams", headers=h)
        fl = [(s_.get("webStreamData") or {}) for s_ in (rr.json().get("dataStreams") or [])] if rr.status_code < 400 else []
        for w in fl:
            vistas.append(f"{nome} ({num}): {w.get('measurementId')} {w.get('defaultUri') or ''}".strip())
            if achou is None and ((dica.startswith("G-") and (w.get("measurementId") or "").upper() == dica)
                                  or (dominio and _dominio_de(w.get("defaultUri") or "") == dominio)):
                achou = {"propriedade": num, "nome": nome, "id_medicao": w.get("measurementId")}
    if achou is None and len(props) == 1:
        achou = {"propriedade": props[0][0], "nome": props[0][1], "id_medicao": None}
    if achou is None:
        raise RuntimeError("Não achei a propriedade do site entre as que a conta enxerga: " + "; ".join(vistas or [f"{n} ({x})" for x, n in props])[:400]
                           + ". Preencha ga4.propriedade com o número certo.")
    achou["vistas"] = vistas
    return achou


def descobrir_search_console(conta: dict, cliente: httpx.Client, dominio: str) -> str:
    """A propriedade do Search Console do site que a conta enxerga (domínio primeiro, depois o prefixo https)."""
    r = cliente.get(f"{API_SC}/sites", headers={"Authorization": f"Bearer {_token(conta, cliente, ESCOPO_SC)}"})
    if r.status_code >= 400:
        raise RuntimeError(f"Search Console recusou ({r.status_code}): {_msg(r)}")
    sites = [x.get("siteUrl") for x in r.json().get("siteEntry") or [] if x.get("permissionLevel") != "siteUnverifiedUser"]
    d = _dominio_de(dominio)
    for alvo in (f"sc-domain:{d}", f"https://{d}/", f"https://www.{d}/", f"http://{d}/", f"http://www.{d}/"):
        if alvo in sites:
            return alvo
    raise RuntimeError(f"A conta de serviço {conta['client_email']} não tem acesso ao Search Console de {d}"
                       + (f" (enxerga: {', '.join(sites)})" if sites else "")
                       + ": no Search Console, Configurações → Usuários e permissões → adicionar esse e-mail (Restrito)")
