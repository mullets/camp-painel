"""Qual imagem pertence a cada item do Tainacan, e de onde ela vem.

- A imagem de verdade é o ANEXO do documento do item (document_type == 'attachment'; `document` é o ID do anexo).
- A miniatura do Tainacan (`thumbnail`) é só um derivado: pode faltar, ou ser um ícone genérico do plugin.
- O painel NUNCA inventa imagem: sem arquivo utilizável, a tela mostra "Sem imagem".
"""
from __future__ import annotations

import json
import re

RE_SRC = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", re.I)
EXT_IMAGEM = re.compile(r"\.(jpe?g|png|webp|gif)(\?.*)?$", re.I)
GENERICA = ("placeholder", "/plugins/tainacan", "/wp-includes/images/media/")
TAMANHOS = ("large", "tainacan-medium", "medium", "full")
SUFIXO_DERIVADO = re.compile(r"-(\d+x\d+|scaled|rotated)$", re.I)


def url_generica(u: str) -> bool:
    return any(x in u.lower() for x in GENERICA)


def e_imagem(url: str | None, mime: str | None = None) -> bool:
    """Navegador consegue mostrar? (TIFF e PDF não)."""
    if mime:
        return mime.lower() in ("image/jpeg", "image/png", "image/webp", "image/gif")
    return bool(url and EXT_IMAGEM.search(url))


def thumb_do_item(it: dict) -> str:
    """Miniatura do Tainacan, descartando ícone genérico do plugin e valores vazios (false)."""
    t = it.get("thumbnail")
    if isinstance(t, dict):
        for k in TAMANHOS:
            v = t.get(k)
            if isinstance(v, list) and v and isinstance(v[0], str) and v[0].startswith("http") and not url_generica(v[0]):
                return v[0]
    return ""


def documento_do_item(it: dict) -> tuple[str | None, int | None]:
    """(url direta do documento, id do anexo). Nunca devolve ID nem HTML no lugar de URL."""
    tipo = (it.get("document_type") or "").lower()
    doc = it.get("document")
    if isinstance(doc, str) and doc.startswith("http"):
        return doc, None
    if tipo == "attachment" and doc not in (None, "", False):
        try:
            anexo = int(str(doc))
        except ValueError:
            anexo = None
        m = RE_SRC.search(it.get("document_as_html") or "")
        url = m.group(1) if m and m.group(1).startswith("http") else None
        return url, anexo
    return None, None


def radical(url: str | None) -> str:
    """Nome-base do arquivo, sem extensão nem sufixo de derivado (-1024x768, -scaled): compara miniatura com original."""
    if not url:
        return ""
    nome = url.split("?")[0].rsplit("/", 1)[-1]
    stem = nome.rsplit(".", 1)[0].lower()
    while SUFIXO_DERIVADO.search(stem):
        stem = SUFIXO_DERIVADO.sub("", stem)
    return stem


def resolver_anexos(con, wp, colecao_id: int, divergencia=None, log=print, info: dict | None = None) -> dict:
    """Passo da sincronização: troca o ID do anexo pela URL real do arquivo, completa a miniatura que falta
    com o próprio documento (quando for imagem) e aponta miniaturas que não são do arquivo do item."""
    out = {"itens": 0, "com_miniatura": 0, "via_documento": 0, "sem_imagem": 0, "divergentes": 0, "anexos": 0}
    linhas = con.execute("SELECT id, codigo_detectado, thumb_url, json FROM wp_item WHERE colecao_id=?", (colecao_id,)).fetchall()
    dados, ids = [], set()
    for r in linhas:
        try:
            it = json.loads(r["json"] or "{}")
        except ValueError:
            it = {}
        url, anexo = documento_do_item(it)
        dados.append((r, it, url, anexo))
        if anexo:
            ids.add(anexo)
    if info is None:   # chamada avulsa: busca na rede aqui. Na sincronização os anexos já vêm buscados (sem rede dentro da transação).
        info = {}
        if ids:
            try:
                info = wp.anexos(sorted(ids))
            except Exception as e:  # noqa: BLE001  (sem resolver: segue com o que veio no próprio item)
                log(f"  (anexos da coleção {colecao_id}: {e})")
    out["anexos"] = len(info)
    for r, it, url, anexo in dados:
        a = info.get(anexo) if anexo else None
        documento = (a or {}).get("url") or url
        mime = (a or {}).get("mime") or it.get("document_mimetype")
        thumb = r["thumb_url"] or ""
        origem = ""
        if thumb:
            origem = "miniatura"
        elif documento and e_imagem(documento, mime):
            thumb = (a or {}).get("large") or (a or {}).get("medium") or documento
            origem = "documento"
        out["itens"] += 1
        out["com_miniatura" if origem == "miniatura" else "via_documento" if origem == "documento" else "sem_imagem"] += 1
        if origem == "miniatura" and documento and e_imagem(documento, mime) and radical(thumb) != radical(documento):
            out["divergentes"] += 1
            if divergencia:
                divergencia(con, "item", r["codigo_detectado"] or str(r["id"]), "miniatura_diferente_do_documento", radical(documento), radical(thumb))
        con.execute("UPDATE wp_item SET documento_url=?, thumb_url=?, imagem_origem=? WHERE id=?", (documento, thumb or None, origem, r["id"]))
    con.commit()
    return out
