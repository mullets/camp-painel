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
API = "https://analyticsdata.googleapis.com/v1beta"
_TOKEN: dict = {"chave": None, "token": None, "expira": 0.0}


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


def _token(conta: dict, cliente: httpx.Client) -> str:
    chave = conta["client_email"] + conta.get("private_key_id", "")
    if _TOKEN["chave"] == chave and _TOKEN["token"] and time.time() < _TOKEN["expira"] - 60:
        return _TOKEN["token"]
    import jwt   # pyjwt; assinatura RS256 usa o pacote cryptography
    agora = int(time.time())
    uri = conta.get("token_uri") or "https://oauth2.googleapis.com/token"
    afirmacao = jwt.encode({"iss": conta["client_email"], "scope": ESCOPO, "aud": uri, "iat": agora, "exp": agora + 3600},
                           conta["private_key"], algorithm="RS256", headers={"kid": conta.get("private_key_id")} if conta.get("private_key_id") else None)
    r = cliente.post(uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": afirmacao})
    if r.status_code >= 400:
        raise RuntimeError(f"O Google recusou a conta de serviço ({r.status_code}): {_msg(r)}")
    j = r.json()
    _TOKEN.update(chave=chave, token=j["access_token"], expira=time.time() + int(j.get("expires_in", 3600)))
    return _TOKEN["token"]


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
