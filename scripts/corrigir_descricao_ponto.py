#!/usr/bin/env python3
"""Folhas já publicadas cuja descrição no site começa com ". " (folha sem título; bug corrigido em publicador.descricao_folha).
PADRÃO: só LISTA o que encontraria no espelho do painel (wp_item), sem alterar nada. Com --aplicar faz PATCH só do campo description,
tirando o ". " do começo. Rode primeiro sem --aplicar e confira a lista.  Uso: python scripts/corrigir_descricao_ponto.py [--aplicar]"""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from app.db import connect

aplicar = "--aplicar" in sys.argv
con = connect()
achados = []
for r in con.execute("SELECT id, colecao_id, codigo_detectado, titulo, json FROM wp_item"):
    try:
        d = (json.loads(r["json"] or "{}").get("description") or "")
    except Exception:
        continue
    if d.startswith(". "):
        achados.append((r["id"], r["colecao_id"], r["codigo_detectado"], r["titulo"], d[2:].lstrip()))
print(f"{len(achados)} item(ns) com descrição começando por '. '")
for i, c, cod, t, nova in achados[:30]:
    print(f"  #{i} {cod or '-'} | {t} -> {nova[:90]}")
if aplicar and achados:
    from app.wp import WP
    wp = WP()
    for i, c, cod, t, nova in achados:
        wp.editar_item(i, {"description": nova}, colecao_id=c)
        print(f"  corrigido #{i}")
elif achados:
    print("Nada foi alterado. Para corrigir: python scripts/corrigir_descricao_ponto.py --aplicar")
