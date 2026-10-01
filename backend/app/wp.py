"""Cliente REST do WordPress + Tainacan. Só leitura nesta versão.

Credenciais: usuário WP + Application Password (Basic Auth por HTTPS).
Prioridade: valor em `configuracao` (editável pelo master no painel) > .env.
"""
from __future__ import annotations

import base64
import re
from typing import Iterator

import httpx

from .config import settings
from .db import connect

RE_CODIGO = re.compile(r"\bF(\d{3})(?:-P(\d{4}))?(?:-(\d{4}))?(?:-S(\d{2}))?(?:-D(\d{5}))?\b", re.I)


def _cfg(chave: str, padrao: str = "") -> str:
    con = connect()
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    con.close()
    return r[0] if r and r[0] else padrao


def detectar_codigo(*textos: str) -> tuple[str | None, str | None, str | None]:
    """Devolve (codigo_completo_encontrado, fundo, projeto) a partir de título/slug/metadados."""
    for t in textos:
        if not t:
            continue
        m = RE_CODIGO.search(t.replace("_", "-"))
        if m:
            f = f"F{m.group(1)}"
            p = f"{f}-P{m.group(2)}" if m.group(2) else None
            partes = [f] + [f"P{m.group(2)}" if m.group(2) else None, m.group(3), f"S{m.group(4)}" if m.group(4) else None, f"D{m.group(5)}" if m.group(5) else None]
            codigo = "-".join(x for x in partes if x)
            return codigo.upper(), f, p
    return None, None, None


class WP:
    def __init__(self, log=None) -> None:
        self.log = log or (lambda *_: None)
        self.base = (_cfg("wp.url", settings.WP_BASE_URL)).rstrip("/")
        usuario = _cfg("wp.usuario", settings.WP_USER)
        senha = _cfg("wp.app_password", settings.WP_APP_PASSWORD)
        if not senha:
            raise RuntimeError("Application Password não configurada (Configurações → wp.app_password ou WP_APP_PASSWORD no .env)")
        tok = base64.b64encode(f"{usuario}:{senha}".encode()).decode()
        self.h = httpx.Client(base_url=self.base, headers={"Authorization": f"Basic {tok}", "User-Agent": "CAMP-Painel/0.3"},
                              timeout=60, follow_redirects=True)

    def _get(self, path: str, **params) -> httpx.Response:
        r = self.h.get(path, params=params)
        if r.status_code == 401:
            raise RuntimeError("Site recusou as credenciais (401). Confira usuário e Application Password.")
        r.raise_for_status()
        return r

    def _paginado(self, path: str, log=None, **params) -> Iterator[dict]:
        """Pagina com proteção: para se a página repetir (servidor ignorando `paged`) ou passar de 500 páginas."""
        page, vistos = 1, set()
        while page <= 500:
            q = {"perpage": 100, "paged": page, **params}
            if "per_page" in q: q["page"] = page; q.pop("perpage"); q.pop("paged")
            q = {k: v for k, v in q.items() if v is not None}
            r = self._get(path, **q)
            dados = r.json()
            if isinstance(dados, dict) and "items" in dados:
                dados = dados["items"]
            if not dados:
                return
            ids = {d.get("id") for d in dados if isinstance(d, dict)}
            if ids and ids <= vistos:          # mesma página de novo -> servidor não paginou
                return
            vistos |= ids
            total_pag = int(r.headers.get("X-WP-TotalPages") or r.headers.get("x-wp-totalpages") or 0)
            total = r.headers.get("X-WP-Total") or r.headers.get("x-wp-total") or "?"
            if log:
                log(f"    página {page}{'/'+str(total_pag) if total_pag else ''} · {len(vistos)} de {total}")
            yield from dados
            if total_pag and page >= total_pag:
                return
            if not total_pag and len(dados) < 100:
                return
            page += 1

    # ---- Tainacan ----
    def colecoes(self) -> list[dict]:
        return self._get("/wp-json/tainacan/v2/collections", perpage=100).json()

    def metadados_da_colecao(self, cid: int) -> list[dict]:
        return self._get(f"/wp-json/tainacan/v2/collection/{cid}/metadata").json()

    def itens(self, cid: int, status: str = "publish,draft,private,pending") -> Iterator[dict]:
        yield from self._paginado(f"/wp-json/tainacan/v2/collection/{cid}/items", log=self.log, status=status, order="ASC", orderby="id")

    def taxonomias(self) -> list[dict]:
        return self._get("/wp-json/tainacan/v2/taxonomies", perpage=100).json()

    def termos(self, tid: int) -> Iterator[dict]:
        yield from self._paginado(f"/wp-json/tainacan/v2/taxonomy/{tid}/terms", log=None, hideempty=0)

    # ---- escrita (Tainacan) ----
    def atualizar_status_item(self, colecao_id: int, item_id: int, status: str) -> dict:
        """status: publish | draft | private. Única escrita permitida nesta versão."""
        if status not in ("publish", "draft", "private"):
            raise ValueError("status inválido")
        r = self.h.patch(f"/wp-json/tainacan/v2/collection/{colecao_id}/items/{item_id}", json={"status": status})
        if r.status_code >= 400:
            raise RuntimeError(f"Tainacan recusou ({r.status_code}) item {item_id}: {r.text[:200]}")
        return r.json()

    def criar_termo(self, taxonomia_id: int, nome: str, descricao: str = "") -> dict:
        r = self.h.post(f"/wp-json/tainacan/v2/taxonomy/{taxonomia_id}/terms", json={"name": nome, "description": descricao})
        if r.status_code >= 400:
            raise RuntimeError(f"Tainacan recusou criar termo: {r.status_code} {r.text[:200]}")
        return r.json()

    def atualizar_termo(self, taxonomia_id: int, termo_id: int, **campos) -> dict:
        r = self.h.patch(f"/wp-json/tainacan/v2/taxonomy/{taxonomia_id}/terms/{termo_id}", json=campos)
        if r.status_code >= 400:
            raise RuntimeError(f"Tainacan recusou editar termo {termo_id}: {r.status_code} {r.text[:200]}")
        return r.json()

    def criar_item(self, colecao_id: int, titulo: str, status: str = "draft", descricao: str = "") -> dict:
        r = self.h.post(f"/wp-json/tainacan/v2/collection/{colecao_id}/items", json={"title": titulo, "status": status, "description": descricao})
        if r.status_code >= 400:
            raise RuntimeError(f"Tainacan recusou criar item: {r.status_code} {r.text[:200]}")
        return r.json()

    def definir_metadado(self, item_id: int, metadado_id: int, valor) -> dict:
        r = self.h.patch(f"/wp-json/tainacan/v2/item/{item_id}/metadata/{metadado_id}", json={"values": valor})
        if r.status_code >= 400:
            raise RuntimeError(f"Tainacan recusou metadado {metadado_id} no item {item_id}: {r.status_code} {r.text[:200]}")
        return r.json()

    # ---- WordPress ----
    def paginas(self) -> Iterator[dict]:
        yield from self._paginado("/wp-json/wp/v2/pages", log=self.log, status="publish,draft,private", context="edit", per_page=100, page=None)

    def quem_sou(self) -> dict:
        return self._get("/wp-json/wp/v2/users/me", context="edit").json()


def metadados_texto(item: dict) -> dict:
    """Achata os metadados do item do Tainacan em {nome: texto}."""
    out = {}
    md = item.get("metadata") or {}
    valores = md.values() if isinstance(md, dict) else md
    for m in valores:
        if not isinstance(m, dict):
            continue
        nome = m.get("name") or (m.get("metadatum") or {}).get("name") or "?"
        v = m.get("value_as_string")
        if v in (None, ""):
            v = m.get("value")
            if isinstance(v, list):
                v = "; ".join(x.get("name", str(x)) if isinstance(x, dict) else str(x) for x in v)
            elif isinstance(v, dict):
                v = v.get("name") or str(v)
        out[nome] = "" if v is None else str(v)
    return out


# ---- extensões de escrita (01/10) ----
def _wp_patch_item(self, colecao_id: int, item_id: int, **campos) -> dict:
    r = self.h.patch(f"/wp-json/tainacan/v2/collection/{colecao_id}/items/{item_id}", json=campos)
    if r.status_code >= 400:
        raise RuntimeError(f"Tainacan recusou editar item {item_id}: {r.status_code} {r.text[:200]}")
    return r.json()


def _wp_upload_media(self, caminho: str, titulo: str = "") -> dict:
    """Sobe um arquivo para a biblioteca de mídia (wp/v2/media). Devolve o JSON do anexo (id, source_url)."""
    import mimetypes
    from pathlib import Path
    p = Path(caminho)
    if not p.exists():
        raise FileNotFoundError(f"arquivo não encontrado: {caminho}")
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    with p.open("rb") as fh:
        r = self.h.post("/wp-json/wp/v2/media", content=fh.read(),
                        headers={"Content-Disposition": f'attachment; filename="{p.name}"', "Content-Type": mime}, timeout=300)
    if r.status_code >= 400:
        raise RuntimeError(f"WordPress recusou o upload de {p.name}: {r.status_code} {r.text[:200]}")
    j = r.json()
    if titulo:
        self.h.post(f"/wp-json/wp/v2/media/{j['id']}", json={"title": titulo, "alt_text": titulo})
    return j


def _wp_definir_documento(self, colecao_id: int, item_id: int, media_id: int) -> dict:
    return self.patch_item(colecao_id, item_id, document=str(media_id), document_type="attachment", _thumbnail_id=media_id)


WP.patch_item = _wp_patch_item
WP.upload_media = _wp_upload_media
WP.definir_documento = _wp_definir_documento
