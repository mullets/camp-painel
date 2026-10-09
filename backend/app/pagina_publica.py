"""Confirma no SITE o endereço da página pública de um projeto, em vez de presumir.

O slug que o site usa NÃO é o título inteiro: ele corta o título na primeira vírgula (o resto é local/endereço) e guarda só as 6 primeiras palavras
(ex.: "Clube Ipê - Social, Rua Estado de Israel" -> f026-p0005-clube-ipe-social). _url_publica_projeto replica essa regra, mas ela é um palpite: aqui se
pergunta ao site (1) se o palpite abre; (2) senão, a busca pública do site por código devolve o endereço real. Nunca devolve nada fora do site da CAMP nem de outro projeto.
"""
from __future__ import annotations

import re

import httpx

SITE = "https://camp.arq.br"


def url_busca(codigo: str) -> str:
    """A busca pública do site por código: sempre abre e mostra o cartão do projeto, se existir."""
    return f"{SITE}/acervo/projetos/?q={codigo}"


def _http_get(url: str, timeout: float = 8.0) -> tuple[int, str]:
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "CAMP-Painel/1.0"})
        return r.status_code, r.text
    except Exception:  # noqa: BLE001  (sem rede, DNS, tempo esgotado: o painel segue sem confirmação)
        return 0, ""


def confirmar(codigo: str, palpite: str) -> dict:
    """{"url": endereço confirmado ou None, "como": "palpite" | "busca" | None}."""
    if palpite.startswith(SITE + "/acervo/projetos/") and _http_get(palpite)[0] == 200:
        return {"url": palpite, "como": "palpite"}
    status, html = _http_get(url_busca(codigo))
    if status == 200:
        achados = re.findall(rf'href="({re.escape(SITE)}/acervo/projetos/{re.escape(codigo.lower())}-[a-z0-9\-]+/)"', html)
        if achados:
            return {"url": achados[0], "como": "busca"}
    return {"url": None, "como": None}
