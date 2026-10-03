"""Edição dos textos de uma folha (item): catalogação no painel + textos públicos no Tainacan.

Regras:
- Salva SEMPRE primeiro no painel; o envio ao site é uma segunda etapa que nunca desfaz a primeira.
- Só oferece para edição os campos que existem de verdade na coleção do site e cujo tipo sabemos gravar
  (texto, texto longo e taxonomia). Taxonomia só aceita termo que já existe.
- Auditoria com antes/depois.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import auth
from .db import connect
from .publicador import _meta, atualizar_folha_no_site
from .rotas_projetos import _colecao_config

router = APIRouter(prefix="/api", tags=["itens"])

LIMITES_LOCAIS = {"titulo": 300, "tipo_documento": 120, "folha": 40, "escala": 60, "dimensoes": 120, "suporte": 160, "credito": 300}
SITE_METADADOS = ("Tipo de desenho", "Técnica", "Suporte original", "Endereço", "Cliente", "Fotógrafo",
                  "Data do registro fotográfico", "Informação atribuída pela catalogação")
LIM_TEXTO_SITE = 5000
LIM_TITULO_SITE = 300


def _tipo_edicao(tipo: str | None) -> str | None:
    t = tipo or ""
    if "Taxonomy" in t:
        return "taxonomia"
    if "Textarea" in t:
        return "textarea"
    if t.endswith("\\Text") or t.endswith("Text"):
        return "texto"
    return None


def _item_e_site(con, codigo: str):
    i = con.execute("SELECT * FROM item WHERE codigo=?", (codigo,)).fetchone()
    if not i:
        raise HTTPException(404, "Folha não existe")
    cid = _colecao_config(con, "tainacan.itens_collection_id", 8013)
    w = con.execute("""SELECT id, colecao_id, status, titulo, metadados, json FROM wp_item
                        WHERE codigo_detectado=? AND colecao_id=? ORDER BY id DESC LIMIT 1""", (codigo, cid)).fetchone()
    return i, w


def _descricao_do_site(w) -> str:
    try:
        j = json.loads(w["json"] or "{}")
    except ValueError:
        j = {}
    d = j.get("description")
    if d is None:
        try:
            d = (json.loads(w["metadados"] or "{}")).get("Descrição")
        except ValueError:
            d = None
    return d or ""


def _campos_do_site(con, w) -> tuple[list[dict], list[dict]]:
    """(editaveis, somente_leitura) segundo os metadados que existem na coleção do item."""
    try:
        valores = json.loads(w["metadados"] or "{}")
    except ValueError:
        valores = {}
    editaveis, leitura = [], []
    for nome in SITE_METADADOS:
        mid, tipo = _meta(con, w["colecao_id"], nome)
        if not mid:
            continue
        kind = _tipo_edicao(tipo)
        atual = valores.get(nome) or ""
        if not kind:
            if atual:
                leitura.append({"nome": nome, "valor": atual, "motivo": "tipo de campo não editável aqui"})
            continue
        campo = {"nome": nome, "tipo": kind, "valor": atual}
        if kind == "taxonomia":
            tax = con.execute("SELECT taxonomia_id FROM wp_metadado WHERE id=?", (mid,)).fetchone()
            tid = tax[0] if tax else None
            campo["opcoes"] = [r[0] for r in con.execute("SELECT nome FROM wp_termo WHERE taxonomia_id=? ORDER BY nome", (tid,))] if tid else []
        editaveis.append(campo)
    return editaveis, leitura


@router.get("/itens/{codigo}/edicao")
def dados_edicao(codigo: str, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        i, w = _item_e_site(con, codigo)
        d = {"codigo": codigo, "status_site": i["status_site"], "no_site": bool(w),
             "local": {k: i[k] for k in (*LIMITES_LOCAIS, "ano_folha")},
             "tipos_documento": [r[0] for r in con.execute("SELECT nome FROM tipo_documento ORDER BY nome")],
             "site": None}
        if w:
            editaveis, leitura = _campos_do_site(con, w)
            d["site"] = {"status": w["status"], "titulo": w["titulo"] or "", "descricao": _descricao_do_site(w),
                         "campos": editaveis, "somente_leitura": leitura}
        return d
    finally:
        con.close()


class EdicaoItem(BaseModel):
    titulo: str | None = None
    tipo_documento: str | None = None
    folha: str | None = None
    escala: str | None = None
    ano_folha: int | None = None
    dimensoes: str | None = None
    suporte: str | None = None
    credito: str | None = None
    titulo_site: str | None = None
    descricao_site: str | None = None
    metadados_site: dict[str, str] | None = None


@router.patch("/itens/{codigo}")
def editar_item(codigo: str, d: EdicaoItem, u: dict = Depends(auth.exige("operador"))) -> dict:
    con = connect()
    try:
        i, w = _item_e_site(con, codigo)
        # ---------- validação (nada é gravado se algo estiver inválido) ----------
        novos, antes = {}, {}
        for k, lim in LIMITES_LOCAIS.items():
            v = getattr(d, k)
            if v is None:
                continue
            v = v.strip()
            if len(v) > lim:
                raise HTTPException(400, f"{k}: máximo de {lim} caracteres")
            if k == "tipo_documento" and v and not con.execute("SELECT 1 FROM tipo_documento WHERE nome=?", (v,)).fetchone():
                raise HTTPException(400, f"Tipo de documento '{v}' não existe no vocabulário")
            v = v or None
            if v != i[k]:
                novos[k], antes[k] = v, i[k]
        if d.ano_folha is not None:
            if d.ano_folha != 0 and not (1800 <= d.ano_folha <= 2100):
                raise HTTPException(400, "Ano da folha inválido (0 para limpar)")
            v = d.ano_folha or None
            if v != i["ano_folha"]:
                novos["ano_folha"], antes["ano_folha"] = v, i["ano_folha"]

        titulo_site = descricao_site = None
        md_envio: dict = {}
        site_antes: dict = {}
        quer_site = d.titulo_site is not None or d.descricao_site is not None or bool(d.metadados_site)
        if quer_site and not w:
            raise HTTPException(400, "Esta folha ainda não existe no site: só a catalogação do painel pode ser editada")
        if w:
            if d.titulo_site is not None:
                t = d.titulo_site.strip()
                if not t:
                    raise HTTPException(400, "O título da página no site não pode ficar vazio")
                if len(t) > LIM_TITULO_SITE:
                    raise HTTPException(400, f"Título no site: máximo de {LIM_TITULO_SITE} caracteres")
                if t != (w["titulo"] or ""):
                    titulo_site = t; site_antes["título da página"] = w["titulo"]
            if d.descricao_site is not None:
                t = d.descricao_site.strip()
                if len(t) > LIM_TEXTO_SITE:
                    raise HTTPException(400, f"Descrição: máximo de {LIM_TEXTO_SITE} caracteres")
                atual = _descricao_do_site(w)
                if t != atual:
                    descricao_site = t; site_antes["descrição"] = atual
            if d.metadados_site:
                editaveis = {c["nome"]: c for c in _campos_do_site(con, w)[0]}
                try:
                    valores_atuais = json.loads(w["metadados"] or "{}")
                except ValueError:
                    valores_atuais = {}
                for nome, bruto in d.metadados_site.items():
                    c = editaveis.get(nome)
                    if not c:
                        raise HTTPException(400, f"O campo '{nome}' não pode ser editado aqui (não existe na coleção ou o tipo não é suportado)")
                    v = (bruto or "").strip()
                    if len(v) > LIM_TEXTO_SITE:
                        raise HTTPException(400, f"{nome}: máximo de {LIM_TEXTO_SITE} caracteres")
                    if v == (valores_atuais.get(nome) or ""):
                        continue
                    mid, _ = _meta(con, w["colecao_id"], nome)
                    if c["tipo"] == "taxonomia" and v:
                        tid = con.execute("SELECT taxonomia_id FROM wp_metadado WHERE id=?", (mid,)).fetchone()[0]
                        termo = con.execute("SELECT id, nome FROM wp_termo WHERE taxonomia_id=? AND lower(nome)=lower(?)", (tid, v)).fetchone()
                        if not termo:
                            raise HTTPException(400, f"'{v}' não existe na lista de {nome}. Escolha um termo existente.")
                        md_envio[nome] = (mid, termo["id"], termo["nome"])
                    else:
                        md_envio[nome] = (mid, v, v)
                    site_antes[nome] = valores_atuais.get(nome) or ""
        # ---------- grava no painel ----------
        if novos:
            sets = ", ".join(f"{k}=?" for k in novos)
            con.execute(f"UPDATE item SET {sets}, atualizado_em=datetime('now') WHERE codigo=?", (*novos.values(), codigo))
        if novos or site_antes:
            depois = dict(novos)
            for k in site_antes:
                depois[f"site:{k}"] = (titulo_site if k == "título da página" else descricao_site if k == "descrição"
                                       else md_envio[k][2])
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('item',?,'editado',?,?)",
                        (codigo, u["email"], json.dumps({"antes": {**antes, **{f"site:{k}": v for k, v in site_antes.items()}},
                                                         "depois": depois}, ensure_ascii=False)))
        con.commit()
        wid, cid = (w["id"], w["colecao_id"]) if w else (None, None)
    finally:
        con.close()
    # ---------- envia ao site (nunca desfaz o que já foi salvo) ----------
    site = None
    if wid and (titulo_site is not None or descricao_site is not None or md_envio):
        site = atualizar_folha_no_site(codigo, wid, cid, titulo_site, descricao_site, md_envio, u["email"])
    campos = list(novos) + [f"site:{k}" for k in site_antes]
    return {"ok": True, "campos": campos, "site": site}
