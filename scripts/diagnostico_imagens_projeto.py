#!/usr/bin/env python3
"""Diagnóstico SOMENTE LEITURA: de onde vêm as imagens que o painel mostra para um projeto.
Uso (na pasta do repo):  .venv/bin/python scripts/diagnostico_imagens_projeto.py F006-P0001"""
import sqlite3, sys, re, json, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import settings
from app.imagens import radical, e_imagem

arg = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
RE_PROJ, RE_ITEM = r"F\d{3}-P\d{4}", r"F\d{3}-P\d{4}-\d{4}-S\d{2}-D\d{5}"
modo = "projeto" if re.fullmatch(RE_PROJ, arg.upper()) else "item" if re.fullmatch(RE_ITEM, arg.upper()) else "url" if arg else None
if not modo:
    sys.exit("Uso: diagnostico_imagens_projeto.py F006-P0001 | F006-P0001-1972-S01-D00003 | https://camp.arq.br/acervo-camp/<slug>/")
cod = arg.upper()
con = sqlite3.connect(f"file:{settings.CAMP_DB_PATH}?mode=ro", uri=True); con.row_factory = sqlite3.Row
def base(u): return (u or "").split("?")[0].rsplit("/", 1)[-1] or "—"
def cfg(k, pad):
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (k,)).fetchone()
    return int(r[0]) if r and str(r[0]).strip().isdigit() else pad

print(f"banco: {settings.CAMP_DB_PATH}")

def _linha(r):
    return (f"id {r['id']:>6} · coleção {r['colecao_id']} · {r['status']:7} · código {r['codigo_detectado'] or '—'}\n"
            f"        título : {r['titulo']}\n        url    : {r['url']}\n        thumb  : {base(r['thumb_url'])}   documento: {base(r['documento_url'])}")

def _quem_aponta(wid):
    return [x["codigo"] for x in con.execute("SELECT codigo FROM item WHERE tainacan_item_id=?", (wid,))] + \
           [x["codigo"] for x in con.execute("SELECT codigo FROM projeto WHERE tainacan_item_id=?", (wid,))]

def modo_url(entrada):
    from urllib.parse import urlparse
    slug = [x for x in urlparse(entrada).path.split("/") if x][-1] if "/" in entrada else entrada
    print(f"\n== PÁGINA PÚBLICA: slug '{slug}'")
    rs = con.execute("SELECT * FROM wp_item WHERE slug=? OR url LIKE ?", (slug, f"%{slug}%")).fetchall()
    if not rs: sys.exit("   nenhum item do espelho tem esse slug/URL (espelho desatualizado? ou a página não é de um item do Tainacan)")
    for r in rs:
        print("   " + _linha(r))
        print(f"        painel aponta para este item: {_quem_aponta(r['id']) or 'NINGUÉM'}")
        for c in _quem_aponta(r["id"]):
            t = con.execute("SELECT titulo FROM item WHERE codigo=?", (c,)).fetchone()
            if t: print(f"        título no catálogo do painel ({c}): {t['titulo']}")
        if r["status"] != "publish":
            print(f"        ⚠ ESTA PÁGINA NÃO É PÚBLICA (status '{r['status']}'): visitante sem login recebe erro 404. Só abre para quem está logado no WordPress.")
        if r["codigo_detectado"]:
            outros = con.execute("SELECT id,colecao_id,status,slug FROM wp_item WHERE codigo_detectado=? AND id<>?", (r["codigo_detectado"], r["id"])).fetchall()
            print(f"        outros itens do site com o MESMO código {r['codigo_detectado']}: {len(outros)}" + ("  -> " + ", ".join(f"id {o['id']} ({o['status']}, {o['slug']})" for o in outros) if outros else ""))
    sys.exit(0)

def modo_item(codigo):
    i = con.execute("SELECT codigo,titulo,tainacan_item_id,status_site,arquivo_jpg FROM item WHERE codigo=?", (codigo,)).fetchone()
    if not i: sys.exit(f"Folha {codigo} não existe no painel")
    print(f"\n== FOLHA: {i['codigo']} · {i['titulo']} · status {i['status_site']} · item local aponta para id {i['tainacan_item_id']} · arquivo local {base(i['arquivo_jpg'])}")
    cid = cfg("tainacan.itens_collection_id", 8013)
    rs = con.execute("SELECT * FROM wp_item WHERE codigo_detectado=? OR id=? ORDER BY id", (codigo, i["tainacan_item_id"] or -1)).fetchall()
    print(f"\n== ITENS DO SITE LIGADOS A ESTA FOLHA: {len(rs)}")
    for r in rs: print("   " + _linha(r))
    usado = con.execute("SELECT id,url FROM wp_item WHERE codigo_detectado=? AND colecao_id=? ORDER BY id DESC LIMIT 1", (codigo, cid)).fetchone()
    print(f"\n== O QUE A TELA DA FOLHA USA (maior id com esse código na coleção {cid}): " + (f"id {usado['id']} -> {usado['url']}" if usado else "nenhum"))
    if i["tainacan_item_id"] and usado and usado["id"] != i["tainacan_item_id"]:
        print(f"   ATENÇÃO: a folha aponta para o id {i['tainacan_item_id']}, mas a tela usa o id {usado['id']} (itens diferentes!)")
    if len([r for r in rs if r["colecao_id"] == cid]) > 1:
        print("   ATENÇÃO: mais de um item do site com o mesmo código — a tela pode estar mostrando o item errado.")
    sys.exit(0)

if modo == "url": modo_url(arg)
if modo == "item": modo_item(cod)
p = con.execute("SELECT codigo,fundo_codigo,titulo,status_site,tainacan_item_id FROM projeto WHERE codigo=?", (cod,)).fetchone()
if not p: sys.exit(f"Projeto {cod} não existe no painel")
print(f"\n== PROJETO: {p['codigo']} · {p['titulo']} · status {p['status_site']} · dossiê no site id {p['tainacan_item_id']}")
itens_cid, proj_cid = cfg("tainacan.itens_collection_id", 8013), cfg("tainacan.projetos_collection_id", 8007)
print(f"coleções configuradas: dossiês={proj_cid}  folhas={itens_cid}")
ult = con.execute("SELECT max(visto_em) FROM wp_item").fetchone()[0]
s = con.execute("SELECT * FROM sincronizacao ORDER BY rowid DESC LIMIT 1").fetchone()
sd = dict(s) if s else {}
print(f"espelho do site atualizado em: {ult}")
print(f"última sincronização: início {sd.get('iniciada_em')} · fim {sd.get('terminada_em')} · ok={sd.get('ok')}" if s else "última sincronização: nenhuma registrada")

# EXATAMENTE o filtro que a tela do projeto usa
tem_origem = "imagem_origem" in {r[1] for r in con.execute("PRAGMA table_info(wp_item)")}
col_origem = "imagem_origem" if tem_origem else "NULL"
tela = con.execute("SELECT id,colecao_id,status,titulo,codigo_detectado,thumb_url,documento_url," + col_origem + " AS imagem_origem FROM wp_item "
    "WHERE projeto_detectado=? AND fundo_detectado=? AND colecao_id=? AND codigo_detectado LIKE ? ORDER BY codigo_detectado,id",
    (cod, p["fundo_codigo"], itens_cid, cod + "-%")).fetchall()
print(f"\n== O QUE A TELA MOSTRA: {len(tela)} folha(s) do site")
sem = [r for r in tela if not r["thumb_url"]]
if not tem_origem or all(r["imagem_origem"] is None for r in tela):
    print("   ATENÇÃO: o espelho ainda é de uma versão anterior (sem origem da imagem). Rode a sincronização e repita.")
por_origem = collections.Counter((r["imagem_origem"] if r["imagem_origem"] is not None else "(não sincronizado)") or "nenhuma" for r in tela)
print(f"   origem da imagem: {dict(por_origem)}")
print(f"   documento_url é URL de verdade: {len([r for r in tela if (r['documento_url'] or '').startswith('http')])} de {len(tela)}")
dif = [r for r in tela if r["thumb_url"] and r["imagem_origem"] == "miniatura" and (r["documento_url"] or "").startswith("http")
       and e_imagem(r["documento_url"]) and radical(r["thumb_url"]) != radical(r["documento_url"])]
print(f"   MINIATURA DE OUTRO ARQUIVO (diferente do documento do item): {len(dif)}")
for r in dif[:8]: print(f"      {r['codigo_detectado']}: miniatura={base(r['thumb_url'])}  documento={base(r['documento_url'])}")
print(f"   sem miniatura: {len(sem)}")
dup_cod = {k: v for k, v in collections.Counter(r["codigo_detectado"] for r in tela).items() if v > 1}
print(f"   códigos que aparecem em mais de um item do site: {len(dup_cod)}" + (f"  -> {list(dup_cod.items())[:6]}" if dup_cod else ""))
mesma = collections.defaultdict(list)
for r in tela: mesma[base(r["thumb_url"])].append(r["codigo_detectado"])
rep = {k: v for k, v in mesma.items() if len(v) > 1 and k != "—"}
print(f"   MESMA imagem usada por vários códigos diferentes: {len(rep)}")
for k, v in list(rep.items())[:6]: print(f"      {k}  <- {', '.join(v[:5])}{' …' if len(v) > 5 else ''}")

# itens do site que citam este projeto mas a tela NÃO mostra (coleção/fundo/código divergentes)
fora = con.execute("""SELECT id,colecao_id,status,codigo_detectado,fundo_detectado,projeto_detectado FROM wp_item
    WHERE (codigo_detectado LIKE ? OR projeto_detectado=?) AND id NOT IN (%s)""" % (",".join(str(r["id"]) for r in tela) or "0"),
    (cod + "-%", cod)).fetchall()
fora = [r for r in fora if r["colecao_id"] != proj_cid]   # o dossiê (coleção Projetos) é esperado, não é problema
print(f"\n== CITAM {cod} MAS FICAM FORA DA TELA: {len(fora)}")
for r in fora[:8]: print(f"   id {r['id']} coleção {r['colecao_id']} {r['status']} código {r['codigo_detectado']} fundo {r['fundo_detectado']} projeto {r['projeto_detectado']}")

# ---- por onde o site liga itens a este projeto (3 caminhos independentes) ----
def _md(r):
    try: return json.loads(r["metadados"] or "{}")
    except ValueError: return {}
def _agrupa(rs):
    g = collections.Counter((r["fundo_detectado"] or "—", r["projeto_detectado"] or "—", r["status"]) for r in rs)
    return ", ".join(f"[fundo {a} · projeto {b} · {c}] x{n}" for (a, b, c), n in g.most_common(5)) or "nenhum"
dossie = p["tainacan_item_id"]
todos = con.execute("SELECT id,colecao_id,status,titulo,slug,codigo_detectado,fundo_detectado,projeto_detectado,metadados FROM wp_item WHERE colecao_id=?", (itens_cid,)).fetchall()
por_rel = [r for r in todos if dossie and str(_md(r).get("Projeto") or "").strip() == str(dossie)]
por_txt = [r for r in todos if cod in f"{r['titulo'] or ''} {r['slug'] or ''} {r['metadados'] or ''}".upper().replace(" ", "")]
print(f"\n== COMO O SITE LIGA ITENS A ESTE PROJETO (dossiê id {dossie})")
print(f"   1) pelo vínculo 'Projeto' do Tainacan : {len(por_rel)} item(ns) -> classificados como {_agrupa(por_rel)}")
print(f"   2) pelo texto (título/slug/metadados)  : {len(por_txt)} item(ns) citam {cod} -> {_agrupa(por_txt)}")
locais_id = [(x["codigo"], x["tainacan_item_id"]) for x in con.execute("SELECT codigo,tainacan_item_id FROM item WHERE projeto_codigo=?", (cod,))]
com_id = [(c, i) for c, i in locais_id if i]
espelho = {r["id"]: r for r in todos}
achados = [(c, espelho[i]) for c, i in com_id if i in espelho]
ok_cls = [c for c, r in achados if r["projeto_detectado"] == cod and r["fundo_detectado"] == p["fundo_codigo"] and (r["codigo_detectado"] or "").startswith(cod + "-")]
print(f"   3) pelo ID guardado em cada folha local: {len(com_id)} de {len(locais_id)} folhas têm ID do site; {len(achados)} desses IDs existem no espelho; {len(ok_cls)} estão classificados neste projeto")
for c, r in [(c, r) for c, r in achados if c not in ok_cls][:6]:
    print(f"      {c} -> item {r['id']} ({r['status']}) classificado como código={r['codigo_detectado']} fundo={r['fundo_detectado']} projeto={r['projeto_detectado']}")
sumidos = [c for c, i in com_id if i not in espelho]
if sumidos: print(f"      {len(sumidos)} folha(s) apontam para um ID que NÃO existe mais no espelho (apagado/na lixeira no site?), ex.: {sumidos[:3]}")

# ---- página pública do projeto: a real (espelho do site) e a que o painel montaria ----
from app.rotas_projetos import _url_publica_projeto
pags = con.execute("""SELECT url, status, codigo_detectado FROM wp_pagina WHERE (codigo_detectado=? OR lower(slug) LIKE ?) AND url LIKE '%/acervo/projetos/%'""", (cod, cod.lower() + "-%")).fetchall()
print(f"\n== PÁGINA PÚBLICA DO PROJETO")
print(f"   no espelho do site: {len(pags)} página(s)")
for r in pags: print(f"      {r['status']:8} {r['url']}")
print(f"   endereço que o painel monta se não achar a página: {_url_publica_projeto(cod, p['titulo'], None)}")
if not pags: print("   ⚠ nenhuma página em /acervo/projetos/ no espelho: a página ainda não foi gerada, ou o espelho está desatualizado")

# conferência com o catálogo local
loc = {r["codigo"]: r for r in con.execute("SELECT codigo,arquivo_jpg,arquivo_tif,tainacan_item_id FROM item WHERE projeto_codigo=?", (cod,))}
def _sujo(v): return bool(re.fullmatch(r"\d+", str(v).strip())) or str(v).lstrip().startswith("<")
sujos = [c for c, l in loc.items() if l["arquivo_jpg"] and _sujo(l["arquivo_jpg"])]
print(f"\n== CATÁLOGO LOCAL: {len(loc)} folha(s)")
if sujos: print(f"   ATENÇÃO: {len(sujos)} folha(s) com arquivo_jpg sujo (ID de anexo/HTML de versão antiga, ex.: {loc[sujos[0]]['arquivo_jpg']!r}). Corrige sozinho ao atualizar o painel (migração 028).")
div = []
for r in tela:
    l = loc.get(r["codigo_detectado"])
    if l and l["arquivo_jpg"] and not _sujo(l["arquivo_jpg"]):
        a, b = Path(l["arquivo_jpg"]).stem.lower(), Path(base(r["thumb_url"])).stem.lower()
        if a not in b and b not in a: div.append((r["codigo_detectado"], Path(l["arquivo_jpg"]).name, base(r["thumb_url"])))
    if l and l["tainacan_item_id"] and l["tainacan_item_id"] != r["id"]: div.append((r["codigo_detectado"], f"item local aponta id {l['tainacan_item_id']}", f"tela usa id {r['id']}"))
print(f"   folhas em que o arquivo local e a miniatura do site NÃO combinam (ou ids diferentes): {len(div)}")
for d in div[:8]: print(f"      {d[0]}: local={d[1]}  site={d[2]}")
print(f"   no catálogo local mas sem item no site: {len([c for c in loc if c not in {r['codigo_detectado'] for r in tela}])}")

print("\n== AMOSTRA (primeiras 12 folhas da tela)")
for r in tela[:12]: print(f"   id {r['id']:>6} {r['status']:7} {r['codigo_detectado']:32} thumb={base(r['thumb_url'])}  doc={base(r['documento_url'])}  origem={r['imagem_origem']}")
