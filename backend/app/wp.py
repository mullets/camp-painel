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


# 27/10 (produção, F009-P0131): com o site respondendo em ~3,4 s e 5 folhas ao mesmo tempo, a criação do item passou dos 60 s de leitura
# ("The read operation timed out") e a folha "NÃO subiu". Leitura/escrita: 90 s (margem para o site sobrecarregado sem esperar para sempre).
# Conexão: 15 s (site sem resposta falha logo e entra na nova tentativa). O upload da imagem tem o próprio teto (300 s, em upload_media).
TIMEOUT_PADRAO = httpx.Timeout(90.0, connect=15.0)
# 27/10 (investigação do site): mudar o status (publicar/despublicar) faz o site limpar o cache INTEIRO dentro da própria requisição;
# passa fácil dos 60 s com o site lento. 120 s, e num tempo esgotado o painel RELÊ o item antes de dizer que falhou.
TIMEOUT_STATUS = httpx.Timeout(120.0, connect=15.0)
_RE_STATUS_PASSAGEIRO = re.compile(r"(?:recusou|falhou)[^:]*:\s*\(?(?:429|502|503|504)\b|\((?:429|502|503|504)\)")
_TEXTO_PASSAGEIRO = ("timed out", "timeout", "tempo esgotado", "connection reset", "connection refused", "connection aborted",
                     "server disconnected", "remoteprotocolerror", "connecterror", "readerror", "temporarily unavailable")


def erro_passageiro(e) -> bool:
    """O erro é do tipo que passa sozinho (site lento ou sobrecarregado): tempo de resposta esgotado, conexão caída, 429/502/503/504.
    Aceita a exceção ou o texto do erro (as rotinas de envio devolvem o texto). 400/401/403/404 e erro de validação NÃO são passageiros."""
    if isinstance(e, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)):
        return True
    if isinstance(e, httpx.HTTPStatusError):
        return e.response is not None and e.response.status_code in (429, 502, 503, 504)
    t = str(e or "").lower()
    return bool(t) and (any(x in t for x in _TEXTO_PASSAGEIRO) or bool(_RE_STATUS_PASSAGEIRO.search(t)))


def _cfg(chave: str, padrao: str = "") -> str:
    con = connect()
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (chave,)).fetchone()
    con.close()
    return r[0] if r and r[0] else padrao


def detectar_codigo(*textos: str) -> tuple[str | None, str | None, str | None]:
    """Devolve o código MAIS ESPECÍFICO encontrado em título/slug/metadados.

    Um item pode conter o código do projeto (Fxxx-Pxxxx) e, em outro metadado,
    o código completo da folha. Antes retornávamos a primeira ocorrência e isso
    podia associar miniaturas/itens ao projeto errado. Agora todas as ocorrências
    são avaliadas e vence a que contém mais partes.
    """
    candidatos: list[tuple[int, int, str, str, str | None]] = []
    ordem = 0
    for t in textos:
        if not t:
            continue
        normalizado = str(t).replace("_", "-")
        for m in RE_CODIGO.finditer(normalizado):
            f = f"F{m.group(1)}"
            p = f"{f}-P{m.group(2)}" if m.group(2) else None
            partes = [f] + [
                f"P{m.group(2)}" if m.group(2) else None,
                m.group(3),
                f"S{m.group(4)}" if m.group(4) else None,
                f"D{m.group(5)}" if m.group(5) else None,
            ]
            codigo = "-".join(x for x in partes if x).upper()
            especificidade = sum(x is not None for x in m.groups())
            candidatos.append((especificidade, -ordem, codigo, f, p))
            ordem += 1
    if not candidatos:
        return None, None, None
    _, _, codigo, fundo, projeto = max(candidatos)
    return codigo, fundo, projeto


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
                              timeout=TIMEOUT_PADRAO, follow_redirects=True)

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
    def editar_item(self, item_id: int, campos: dict, colecao_id: int | None = None, timeout=None) -> dict:
        """Edita um item do Tainacan. O endereço que o site aceita é /items/{id} (PLURAL, sem a coleção): conferido no site em produção.
        A forma /collection/{id}/items/{id} responde 404 `rest_no_route` (foi o que travou o Publicar); fica só como reserva, depois do POST.
        Só tenta outro endereço quando a resposta é 404/405 (rota inexistente); 400/401/403/5xx são erros de verdade e param na hora."""
        tentativas = [("patch", f"/wp-json/tainacan/v2/items/{item_id}")]
        if colecao_id:
            tentativas.append(("patch", f"/wp-json/tainacan/v2/collection/{colecao_id}/items/{item_id}"))
        tentativas.append(("post", f"/wp-json/tainacan/v2/items/{item_id}"))
        ultimo, tentados = None, []
        for metodo, url in tentativas:
            r = getattr(self.h, metodo)(url, json=campos, **({"timeout": timeout} if timeout is not None else {}))
            tentados.append(f"{metodo.upper()} {url.replace('/wp-json/tainacan/v2', '')}")
            if r.status_code < 400:
                return r.json()
            ultimo = r
            if r.status_code not in (404, 405):
                break
        quais = "" if len(tentados) == 1 else f" (tentei {'; '.join(tentados)})"
        raise RuntimeError(f"Tainacan recusou ({ultimo.status_code}) item {item_id}{quais}: {ultimo.text[:200]}")

    def atualizar_status_item(self, colecao_id: int, item_id: int, status: str) -> dict:
        """status: publish | draft | private. Confere se o site de fato ficou com o status pedido (um 200 que mantém 'draft' não é publicado)."""
        if status not in ("publish", "draft", "private"):
            raise ValueError("status inválido")
        try:
            j = self.editar_item(item_id, {"status": status}, colecao_id, timeout=TIMEOUT_STATUS)
        except httpx.TimeoutException as e:
            # 27/10: o site pode ter mudado o status e só demorado a responder (limpeza de cache). Relê antes de chamar de falha.
            j = self.ler_item(item_id, colecao_id)
            if not isinstance(j, dict) or j.get("status") != status:
                raise RuntimeError(f"O site não respondeu a tempo ao mudar o item {item_id} para '{status}' e, relido, continua "
                                   f"'{(j or {}).get('status') if isinstance(j, dict) else '?'}' (The read operation timed out)") from e
        ficou = j.get("status") if isinstance(j, dict) else None
        if ficou and ficou != status:
            raise RuntimeError(f"Tainacan aceitou, mas o item {item_id} continuou como '{ficou}' em vez de '{status}' (campo obrigatório vazio ou regra do site?)")
        return j

    def ler_item(self, item_id: int, colecao_id: int | None = None) -> dict | None:
        """27/10: o item como o site o tem agora (para conferir o status depois de um tempo esgotado). Tenta /items/{id}; na falta da rota, pela coleção."""
        urls = [f"/wp-json/tainacan/v2/items/{int(item_id)}"] + ([f"/wp-json/tainacan/v2/collection/{int(colecao_id)}/items/{int(item_id)}"] if colecao_id else [])
        for url in urls:
            r = self.h.get(url, params={"context": "edit"})
            if r.status_code in (404, 405):
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Tainacan recusou ler o item {item_id}: {r.status_code} {r.text[:160]}")
            return r.json()
        return None

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

    def gravar_hub(self, termo_id: int, meta: dict) -> dict:
        """B1/B9: grava campos da página-hub de um fundo (rota do plugin da CAMP; ver docs/site/painel-hub.php)."""
        r = self.h.post(f"/wp-json/camp/v1/painel/hub/{int(termo_id)}", json={"meta": meta})
        if r.status_code == 404 and "rest_no_route" in r.text:
            raise RuntimeError("O site ainda não tem a rota camp/v1/painel/hub: avise quem cuida do site (plugin da CAMP, docs/site/painel-hub.php)")
        if r.status_code >= 400:
            raise RuntimeError(f"O site recusou gravar a página do arquiteto: {r.status_code} {r.text[:200]}")
        resposta = r.json()
        if not isinstance(resposta, dict):
            raise RuntimeError("WordPress respondeu formato inválido ao atualizar o hub")
        # WP-AUD-13: HTTP 200 pode significar escrita parcial. Não declarar
        # publicação bem-sucedida antes de checar os campos confirmados.
        # Rotas antigas não enviam ok; manter compatibilidade com elas.
        if resposta.get("ok") is False:
            faltantes = resposta.get("retry") or []
            total = len(faltantes) if isinstance(faltantes, list) else 0
            raise RuntimeError(
                f"Atualização incompleta da página do arquiteto: {total} campo(s) sem confirmação. "
                "Confira pendências e tente novamente."
            )
        return resposta

    def criar_item(self, colecao_id: int, titulo: str, status: str = "draft", descricao: str = "") -> dict:
        r = self.h.post(f"/wp-json/tainacan/v2/collection/{colecao_id}/items", json={"title": titulo, "status": status, "description": descricao})
        if r.status_code >= 400:
            raise RuntimeError(f"Tainacan recusou criar item: {r.status_code} {r.text[:200]}")
        return r.json()

    def criar_metadado(self, colecao_id: int, nome: str, descricao: str = "") -> dict:
        """Metadado de TEXTO na coleção, oculto na página pública (display=no). Antes, confere se já existe com o mesmo nome."""
        for m in self.metadados_da_colecao(colecao_id) or []:
            if isinstance(m, dict) and (m.get("name") or "").strip().lower() == nome.strip().lower():
                return m
        r = self.h.post(f"/wp-json/tainacan/v2/collection/{colecao_id}/metadata",
                        json={"name": nome, "description": descricao, "metadata_type": "Tainacan\\Metadata_Types\\Text",
                              "status": "publish", "display": "no", "multiple": "no"})
        if r.status_code >= 400:
            raise RuntimeError(f"Tainacan recusou criar o metadado '{nome}': {r.status_code} {r.text[:200]}")
        return r.json()

    def definir_metadado(self, item_id: int, metadado_id: int, valor) -> dict:
        r = self.h.patch(f"/wp-json/tainacan/v2/item/{item_id}/metadata/{metadado_id}", json={"values": valor})
        if r.status_code >= 400:
            raise RuntimeError(f"Tainacan recusou metadado {metadado_id} no item {item_id}: {r.status_code} {r.text[:200]}")
        return r.json()

    # ---- WordPress ----
    def gravar_metadados_lote(self, item_id: int, corpo: dict) -> dict | None:
        """21/10: vários metadados de um item numa chamada (rota do plugin da CAMP, CAMP-055). None = o site não tem a rota (404):
        quem chama grava um por um, como antes."""
        r = self.h.post(f"/wp-json/camp/v1/painel/item/{int(item_id)}/metadados", json=corpo)
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise RuntimeError(f"O site recusou os metadados: {r.status_code} {r.text[:200]}")
        return r.json()

    def pagina_por_slug(self, slug: str) -> list[dict]:
        """21/10: páginas do WordPress com este slug (publicadas, rascunho ou privadas). Usado para achar a página do arquiteto."""
        r = self._get("/wp-json/wp/v2/pages", slug=slug, status="publish,draft,private,pending", context="edit", per_page=20)
        if r.status_code >= 400:
            raise RuntimeError(f"O site recusou a busca da página: {r.status_code} {r.text[:200]}")
        return r.json() if isinstance(r.json(), list) else []

    def mudar_status_pagina(self, page_id: int, status: str) -> dict:
        """21/10: publica (publish) ou tira do público (draft) uma página do WordPress — a página do arquiteto."""
        r = self.h.post(f"/wp-json/wp/v2/pages/{int(page_id)}", json={"status": status})
        if r.status_code >= 400:
            raise RuntimeError(f"O site recusou mudar a página do arquiteto: {r.status_code} {r.text[:200]}")
        return r.json()

    def paginas(self) -> Iterator[dict]:
        # 27/10: só os campos que o espelho guarda (antes vinha o conteúdo inteiro de ~5.200 páginas a cada rodada)
        yield from self._paginado("/wp-json/wp/v2/pages", log=self.log, status="publish,draft,private", context="edit", per_page=100, page=None,
                                  _fields="id,title,slug,link,status,parent,modified")

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
    return self.editar_item(item_id, campos, colecao_id)


def _wp_upload_media(self, caminho: str, titulo: str = "", nome: str | None = None) -> dict:
    """Sobe um arquivo para a biblioteca de mídia (wp/v2/media). Devolve o JSON do anexo (id, source_url)."""
    import mimetypes
    from pathlib import Path
    p = Path(caminho)
    if not p.exists():
        raise FileNotFoundError(f"arquivo não encontrado: {caminho}")
    arquivo = nome or p.name                      # o nome que o site guarda (e que vira o nome da imagem e do SEO) é o da folha, nunca um hash de cache
    mime = mimetypes.guess_type(arquivo)[0] or "application/octet-stream"
    with p.open("rb") as fh:
        r = self.h.post("/wp-json/wp/v2/media", content=fh.read(),
                        headers={"Content-Disposition": f'attachment; filename="{arquivo}"', "Content-Type": mime}, timeout=300)
    if r.status_code >= 400:
        raise RuntimeError(f"WordPress recusou o upload de {arquivo}: {r.status_code} {r.text[:200]}")
    j = r.json()
    if titulo:
        self.h.post(f"/wp-json/wp/v2/media/{j['id']}", json={"title": titulo, "alt_text": titulo})
    return j


def _wp_substituir_midia(self, media_id: int, caminho: str, nome: str | None = None) -> dict:
    """Troca o ARQUIVO de um anexo que já existe, mantendo o ID (girar folha já publicada). O WordPress não faz isso pela
    rota wp/v2/media (ela só cria anexo novo), então usa a rota do plugin da CAMP: docs/site/painel-midia.php."""
    import mimetypes
    from pathlib import Path
    p = Path(caminho)
    if not p.exists():
        raise RuntimeError(f"arquivo não encontrado: {caminho}")
    arquivo = nome or p.name
    mime = mimetypes.guess_type(arquivo)[0] or "image/jpeg"
    with p.open("rb") as fh:
        r = self.h.post(f"/wp-json/camp/v1/painel/midia/{int(media_id)}", content=fh.read(),
                        headers={"Content-Disposition": f'attachment; filename="{arquivo}"', "Content-Type": mime}, timeout=300)
    if r.status_code == 404 and "rest_no_route" in r.text:
        raise RuntimeError("O site ainda não tem a rota para trocar a imagem de um anexo: avise quem cuida do site (plugin da CAMP, docs/site/painel-midia.php)")
    if r.status_code == 401:
        raise RuntimeError("O site recusou as credenciais (401). Confira usuário e Application Password")
    if r.status_code >= 400:
        raise RuntimeError(f"O site recusou trocar a imagem do anexo {media_id}: {r.status_code} {r.text[:200]}")
    return r.json()


def _wp_definir_documento(self, colecao_id: int, item_id: int, media_id: int) -> dict:
    return self.patch_item(colecao_id, item_id, document=str(media_id), document_type="attachment", _thumbnail_id=media_id)


WP.patch_item = _wp_patch_item
WP.upload_media = _wp_upload_media
WP.definir_documento = _wp_definir_documento
WP.substituir_midia = _wp_substituir_midia


def _wp_anexos(self, ids) -> dict:
    """Resolve IDs de anexo -> {id: {url, mime, large, medium}} (lotes de 100)."""
    out: dict = {}
    ids = sorted({int(i) for i in ids})
    for k in range(0, len(ids), 100):
        lote = ids[k:k + 100]
        r = self.h.get("/wp-json/wp/v2/media", params={"include": ",".join(map(str, lote)), "per_page": 100,
                                                       "_fields": "id,source_url,mime_type,media_details"})
        if r.status_code >= 400:
            raise RuntimeError(f"WordPress recusou listar anexos ({r.status_code}): {r.text[:160]}")
        for m in r.json():
            sizes = (m.get("media_details") or {}).get("sizes") or {}
            out[m["id"]] = {"url": m.get("source_url"), "mime": m.get("mime_type"),
                            "large": (sizes.get("large") or {}).get("source_url"), "medium": (sizes.get("medium") or {}).get("source_url")}
    return out


WP.anexos = _wp_anexos


def _wp_buscar_por_codigo(self, colecao_id: int, metadado_id: int, codigo: str) -> list[dict]:
    """Itens da coleção (qualquer status) cujo metadado `metadado_id` ("Código do documento", 8030) é exatamente `codigo`."""
    r = self.h.get(f"/wp-json/tainacan/v2/collection/{int(colecao_id)}/items",
                   params={"metaquery[0][key]": int(metadado_id), "metaquery[0][value]": codigo, "metaquery[0][compare]": "=",
                           "status": "publish,draft,private,pending", "perpage": 10})
    if r.status_code >= 400:
        raise RuntimeError(f"Tainacan recusou procurar o código {codigo}: {r.status_code} {r.text[:160]}")
    dados = r.json()
    if isinstance(dados, dict):
        dados = dados.get("items") or []
    return [d for d in dados if isinstance(d, dict)]


WP.buscar_por_codigo = _wp_buscar_por_codigo


def _wp_buscar_por_titulo(self, colecao_id: int, titulo: str) -> list[dict]:
    """27/10: itens da coleção (qualquer status) com EXATAMENTE este título (busca de texto do próprio Tainacan, `search`, conferida aqui).
    Serve para achar o item que o site criou numa tentativa cuja resposta não chegou (tempo esgotado): ele ainda não tem o código gravado."""
    r = self.h.get(f"/wp-json/tainacan/v2/collection/{int(colecao_id)}/items",
                   params={"search": titulo, "status": "publish,draft,private,pending", "perpage": 50, "orderby": "id", "order": "DESC"})
    if r.status_code >= 400:
        raise RuntimeError(f"Tainacan recusou procurar o título: {r.status_code} {r.text[:160]}")
    dados = r.json()
    if isinstance(dados, dict):
        dados = dados.get("items") or []
    alvo = " ".join(str(titulo).split()).casefold()
    return [d for d in dados if isinstance(d, dict) and " ".join(str(d.get("title") or "").split()).casefold() == alvo]


WP.buscar_por_titulo = _wp_buscar_por_titulo


def _wp_apagar_pessoa(self, email: str) -> dict:
    """CAMP-050 · pede ao site para apagar/anonimizar uma pessoa nas 3 cópias (pedidos, downloads, Fluent Forms). Devolve as contagens."""
    r = self.h.post("/wp-json/camp/v1/painel/pessoa/apagar", json={"email": email.strip()})
    if r.status_code == 404 and "rest_no_route" in r.text:
        raise RuntimeError("O site ainda não tem a rota camp/v1/painel/pessoa/apagar")
    if r.status_code == 401:
        raise RuntimeError("O site recusou as credenciais (401)")
    if r.status_code >= 400:
        raise RuntimeError(f"O site recusou apagar a pessoa: {r.status_code}")
    try:
        return r.json()
    except ValueError:
        return {}


WP.apagar_pessoa = _wp_apagar_pessoa


def _wp_enviar_redirecionamentos(self, itens: list[dict]) -> dict:
    """CAMP-014 · manda o mapa antigo→novo (caminhos do site) ao mapa dinâmico de 301. Devolve {criados, atualizados, iguais, erros:[{indice, motivo}]}."""
    r = self.h.post("/wp-json/camp/v1/painel/redirecionamentos", json={"itens": itens})
    if r.status_code == 404 and "rest_no_route" in r.text:
        raise RuntimeError("O site ainda não tem a rota camp/v1/painel/redirecionamentos")
    if r.status_code == 401:
        raise RuntimeError("O site recusou as credenciais (401)")
    if r.status_code >= 400:
        raise RuntimeError(f"O site recusou os redirecionamentos: {r.status_code} {r.text[:120]}")
    try:
        return r.json()
    except ValueError:
        return {}


WP.enviar_redirecionamentos = _wp_enviar_redirecionamentos
