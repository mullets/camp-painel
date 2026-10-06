"""Importa do espelho do site (wp_item) para as tabelas do painel: projeto e item.

Idempotente: reexecutar atualiza ids/status e preenche o que falta; nunca apaga nem
sobrescreve o que foi editado no painel (só campos ainda vazios).
Coleção 8007 "Projetos CAMP" -> projeto (dossiê). Coleção 8013 "Acervo CAMP" -> item.
O código vem de "Código de Catalogação" / "Código do documento" ou, na falta, do título/slug.
"""
from __future__ import annotations

import json
import re

from .db import connect
from .wp import detectar_codigo

COL_PROJETOS, COL_ACERVO = 8007, 8013
STATUS = {"publish": "no_ar", "draft": "rascunho", "private": "fora_do_ar", "pending": "rascunho"}
TIPOS = {"planta": "Planta", "corte": "Corte", "elevação": "Elevação", "elevacao": "Elevação", "fachada": "Elevação",
         "detalhe": "Detalhe", "estrutura": "Estrutura", "croqui": "Croqui", "perspectiva": "Perspectiva",
         "levantamento": "Levantamento", "mobiliário": "Mobiliário", "mobiliario": "Mobiliário", "documento": "Documento",
         "fotografia": "Fotografia", "foto": "Fotografia", "negativo": "Negativo", "slide": "Slide"}
RE_PREFIXO_TITULO = re.compile(r"^\s*P\d{4}\s*[—–-]\s*")
RE_SUFIXO_TITULO = re.compile(r"\s*[—–-]\s*P\d{4}\s*[—–-].*$")


def _arquivo_preview(v):
    """Só aceita URL de verdade. ID de anexo ou trecho de HTML (gravados por versões antigas do sincronizador) são descartados."""
    v = (v or "").strip()
    return v if v.lower().startswith(("http://", "https://")) else None


def _int(v):
    try:
        m = re.search(r"\d{4}", str(v or ""))
        return int(m.group()) if m else None
    except Exception:  # noqa: BLE001
        return None


def _tipo(v: str | None):
    if not v:
        return None
    v = v.lower()
    for k, t in TIPOS.items():
        if k in v:
            return t
    return None


def executar(log=print, simular: bool = False, projeto: str | None = None, item: str | None = None, so_itens: bool = False) -> dict:
    """simular=True roda EXATAMENTE o mesmo código, mas desfaz tudo no fim (prévia fiel do que a importação faria).
    projeto/item restringem às folhas daquele projeto ou àquela folha; so_itens NÃO mexe em projetos (importar uma folha
    "só no site" não pode alterar o projeto que já existe no painel)."""
    con = connect()
    n = {"projetos_novos": 0, "projetos_atualizados": 0, "itens_novos": 0, "itens_atualizados": 0,
         "sem_codigo": [], "fundo_desconhecido": [], "item_sem_projeto": [],
         "projetos_novos_lista": [], "itens_novos_lista": []}
    fundos = {r[0] for r in con.execute("SELECT codigo FROM fundo")}
    equiv = {r[0]: r[1] for r in con.execute("SELECT nome_site, fundo_codigo FROM fundo_termo_site")}

    # ---- projetos ----
    for it in ([] if so_itens else con.execute("SELECT * FROM wp_item WHERE colecao_id=?", (COL_PROJETOS,)).fetchall()):
        md = json.loads(it["metadados"] or "{}")
        cod, f, p = detectar_codigo(md.get("Código de Catalogação", ""), it["titulo"] or "", it["slug"] or "")
        if projeto and p != projeto:
            continue
        if not p:
            n["sem_codigo"].append((it["id"], it["titulo"], md.get("Fundo")))
            continue
        if f not in fundos:
            n["fundo_desconhecido"].append((it["id"], it["titulo"], f)); continue
        numero = int(p[6:])
        titulo = RE_PREFIXO_TITULO.sub("", it["titulo"] or p).strip() or p
        ano = _int(md.get("Ano")) or 0
        status = STATUS.get(it["status"], "nao_publicado")
        con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero, reservado_por) VALUES (?,?,NULL)", (f, numero))
        ex = con.execute("SELECT codigo FROM projeto WHERE codigo=?", (p,)).fetchone()
        if ex:
            con.execute("""UPDATE projeto SET tainacan_item_id=?, status_site=?, autorizado_site=MAX(autorizado_site, ?),
                           cidade=COALESCE(NULLIF(cidade,''),?), endereco_obra=COALESCE(NULLIF(endereco_obra,''),?),
                           cliente=COALESCE(NULLIF(cliente,''),?), tipologia=COALESCE(NULLIF(tipologia,''),?),
                           ambito_conteudo=COALESCE(NULLIF(ambito_conteudo,''),?), ano=CASE WHEN ano=0 THEN ? ELSE ano END,
                           atualizado_em=datetime('now') WHERE codigo=?""",
                        (it["id"], status, int(status == "no_ar"), md.get("Cidade"), md.get("Endereço"), md.get("Cliente (divulgável)"),
                         md.get("Programa / uso"), md.get("Descrição"), ano, p))
            n["projetos_atualizados"] += 1
        else:
            con.execute("""INSERT INTO projeto (codigo, fundo_codigo, numero, titulo, ano, cidade, endereco_obra, cliente, tipologia,
                           ambito_conteudo, autorizado_site, status_site, tainacan_item_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (p, f, numero, titulo, ano, md.get("Cidade"), md.get("Endereço"), md.get("Cliente (divulgável)"),
                         md.get("Programa / uso"), md.get("Descrição"), int(status == "no_ar"), status, it["id"]))
            con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('projeto',?,'importado','site',?)",
                        (p, json.dumps({"tainacan_id": it["id"]})))
            n["projetos_novos"] += 1
            n["projetos_novos_lista"].append((p, titulo, f))
    if not simular:
        con.commit()
    log(f"projetos: {n['projetos_novos']} novos, {n['projetos_atualizados']} atualizados, {len(n['sem_codigo'])} sem código")

    # ---- itens ----
    proj_por_wp = {r[1]: r[0] for r in con.execute("SELECT codigo, tainacan_item_id FROM projeto WHERE tainacan_item_id IS NOT NULL")}
    projetos = {r[0] for r in con.execute("SELECT codigo FROM projeto")}
    for it in con.execute("SELECT * FROM wp_item WHERE colecao_id=?", (COL_ACERVO,)).fetchall():
        md = json.loads(it["metadados"] or "{}")
        cod, f, p = detectar_codigo(md.get("Código do documento", ""), it["titulo"] or "", it["slug"] or "")
        if not cod or cod.count("-") != 4:
            if not projeto and not item:   # numa importação de uma folha/projeto só, "sem código" dos outros não interessa
                n["sem_codigo"].append((it["id"], it["titulo"], md.get("Fundo")))
            continue
        if item and cod != item:
            continue
        # projeto pelo código, ou pelo id do dossiê no metadado "Projeto"
        if p not in projetos:
            wpid = md.get("Projeto")
            p_alt = proj_por_wp.get(int(wpid)) if str(wpid or "").isdigit() else None
            if not p_alt:
                n["item_sem_projeto"].append((it["id"], cod)); continue
            p = p_alt
        if projeto and p != projeto:
            continue
        partes = cod.split("-")
        serie, seq = partes[3], int(partes[4][1:])
        titulo = RE_SUFIXO_TITULO.sub("", md.get("Título") or it["titulo"] or "").strip() or None
        status = STATUS.get(it["status"], "nao_publicado")
        ex = con.execute("SELECT codigo FROM item WHERE codigo=?", (cod,)).fetchone()
        if ex:
            con.execute("""UPDATE item SET tainacan_item_id=?, status_site=?, arquivo_jpg=CASE WHEN arquivo_jpg IS NULL OR arquivo_jpg NOT GLOB '*[^0-9]*' OR arquivo_jpg LIKE '<%' THEN ? ELSE arquivo_jpg END,
                           atualizado_em=datetime('now') WHERE codigo=?""", (it["id"], status, _arquivo_preview(it["documento_url"]), cod))
            n["itens_atualizados"] += 1
        else:
            con.execute("""INSERT OR IGNORE INTO item (codigo, projeto_codigo, serie_codigo, sequencial, titulo, tipo_documento, folha,
                           escala, ano_folha, suporte, arquivo_jpg, status_site, tainacan_item_id, origem, credito)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'importado',?)""",
                        (cod, p, serie, seq, titulo, _tipo(md.get("Tipo de desenho")), md.get("Folha") or None,
                         md.get("Escala") or None, _int(md.get("Ano")), md.get("Suporte original") or None,
                         _arquivo_preview(it["documento_url"]), status, it["id"],
                         f"Acervo {md.get('Arquiteto') or md.get('Fundo') or ''}/CAMP - Casa da Arquitetura Moderna Paulista"))
            n["itens_novos"] += 1
            n["itens_novos_lista"].append((cod, titulo, p, f))
    if not simular:
        con.commit()
    log(f"itens: {n['itens_novos']} novos, {n['itens_atualizados']} atualizados, {len(n['item_sem_projeto'])} sem projeto")

    # ids dos termos de fundo no site
    for r in ([] if (projeto or item or so_itens) else con.execute("SELECT x.id, x.nome FROM wp_termo x JOIN wp_taxonomia t ON t.id=x.taxonomia_id WHERE t.nome='Fundos'").fetchall()):
        f = equiv.get(r[1])
        if f:
            con.execute("UPDATE fundo SET tainacan_term_id=? WHERE codigo=?", (r[0], f))
    if simular:
        con.rollback()
    else:
        con.commit()
    con.close()
    return n
