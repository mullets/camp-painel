#!/usr/bin/env python3
"""Diagnóstico SOMENTE LEITURA: de onde vêm as imagens que o painel mostra para um projeto.
Uso (na pasta do repo):  .venv/bin/python scripts/diagnostico_imagens_projeto.py F006-P0001"""
import sqlite3, sys, re, json, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import settings

cod = (sys.argv[1] if len(sys.argv) > 1 else "").strip().upper()
if not re.fullmatch(r"F\d{3}-P\d{4}", cod):
    sys.exit("Uso: diagnostico_imagens_projeto.py F006-P0001")
con = sqlite3.connect(f"file:{settings.CAMP_DB_PATH}?mode=ro", uri=True); con.row_factory = sqlite3.Row
def base(u): return (u or "").split("?")[0].rsplit("/", 1)[-1] or "—"
def cfg(k, pad):
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (k,)).fetchone()
    return int(r[0]) if r and str(r[0]).strip().isdigit() else pad

print(f"banco: {settings.CAMP_DB_PATH}")
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
tela = con.execute("""SELECT id,colecao_id,status,titulo,codigo_detectado,thumb_url,documento_url FROM wp_item
    WHERE projeto_detectado=? AND fundo_detectado=? AND colecao_id=? AND codigo_detectado LIKE ?
    ORDER BY codigo_detectado,id""", (cod, p["fundo_codigo"], itens_cid, cod + "-%")).fetchall()
print(f"\n== O QUE A TELA MOSTRA: {len(tela)} folha(s) do site")
sem = [r for r in tela if not r["thumb_url"]]
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
print(f"\n== CITAM {cod} MAS FICAM FORA DA TELA: {len(fora)}")
for r in fora[:8]: print(f"   id {r['id']} coleção {r['colecao_id']} {r['status']} código {r['codigo_detectado']} fundo {r['fundo_detectado']} projeto {r['projeto_detectado']}")

# conferência com o catálogo local
loc = {r["codigo"]: r for r in con.execute("SELECT codigo,arquivo_jpg,arquivo_tif,tainacan_item_id FROM item WHERE projeto_codigo=?", (cod,))}
print(f"\n== CATÁLOGO LOCAL: {len(loc)} folha(s)")
div = []
for r in tela:
    l = loc.get(r["codigo_detectado"])
    if l and l["arquivo_jpg"]:
        a, b = Path(l["arquivo_jpg"]).stem.lower(), Path(base(r["thumb_url"])).stem.lower()
        if a not in b and b not in a: div.append((r["codigo_detectado"], Path(l["arquivo_jpg"]).name, base(r["thumb_url"])))
    if l and l["tainacan_item_id"] and l["tainacan_item_id"] != r["id"]: div.append((r["codigo_detectado"], f"item local aponta id {l['tainacan_item_id']}", f"tela usa id {r['id']}"))
print(f"   folhas em que o arquivo local e a miniatura do site NÃO combinam (ou ids diferentes): {len(div)}")
for d in div[:8]: print(f"      {d[0]}: local={d[1]}  site={d[2]}")
print(f"   no catálogo local mas sem item no site: {len([c for c in loc if c not in {r['codigo_detectado'] for r in tela}])}")

print("\n== AMOSTRA (primeiras 12 folhas da tela)")
for r in tela[:12]: print(f"   id {r['id']:>6} {r['status']:7} {r['codigo_detectado']:32} thumb={base(r['thumb_url'])}")
