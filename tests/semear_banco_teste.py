#!/usr/bin/env python3
"""Cria um banco SINTÉTICO para a auditoria de navegador (nunca usar em produção).
Uso: CAMP_DB_PATH=/tmp/auditoria.db python tests/semear_banco_teste.py"""
import os, sys, pathlib, subprocess
RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))
from app.db import init_db, aplicar_migracoes, connect
from app import auth

init_db(); aplicar_migracoes()
subprocess.run([sys.executable, str(RAIZ / "scripts/importar_fundos.py"), "--db", os.environ["CAMP_DB_PATH"]],
               check=True, capture_output=True)
auth.criar_usuario("Rafael", "rafael@camp.arq.br", "senha-bem-longa-123", "master", forcar_troca=False)
auth.criar_usuario("Estagiária", "operador@camp.arq.br", "senha-operador-123", "operador", forcar_troca=False)

c = connect()
c.execute("INSERT OR REPLACE INTO wp_colecao (id,nome,slug,total_itens) VALUES (8007,'Projetos CAMP','projetos',0),(8013,'Acervo CAMP','acervo',0)")
# (codigo, fundo, numero, titulo, ano, n_folhas)
PROJ = [("F026-P0001","F026",1,"Casa Tarumã",1968,6), ("F026-P0002","F026",2,"Edifício Paulista",1970,0),
        ("F023-P0011","F023",11,"Residência Riviera",1959,35), ("F010-P0006","F010",6,"Agência Banespa",1972,0),
        ("F001-P0001","F001",1,"Residência Martino",1961,0), ("F002-P0001","F002",1,"Paróquia São José",1975,0),
        ("F002-P0002","F002",2,"Escola Estadual",1977,0), ("F003-P0001","F003",1,"Jardim Residencial",1965,0)]
wid = 1000
for cod, fundo, num, titulo, ano, nf in PROJ:
    c.execute("INSERT INTO numero_p (fundo_codigo, numero) VALUES (?,?)", (fundo, num))
    wid += 1
    c.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,tainacan_item_id) VALUES (?,?,?,?,?,?,?)",
              (cod, fundo, num, titulo, ano, "São Paulo", wid))
    c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,slug,url,codigo_detectado,fundo_detectado,projeto_detectado) VALUES (?,?,?,?,?,?,?,?,?)",
              (wid, 8007, "draft", f"{cod} — {titulo}", cod.lower(), f"https://exemplo.test/{cod}", cod, fundo, cod))
    for s in range(1, nf + 1):
        ic = f"{cod}-{ano}-S01-D{s:05d}"; wid += 1
        c.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,folha,ano_folha,tainacan_item_id,origem) VALUES (?,?,?,?,?,?,?,?,'importado')",
                  (ic, cod, "S01", s, f"Planta {s}", f"{s:02d}/{nf:02d}", ano, wid))
        c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,slug,url,documento_url,thumb_url,codigo_detectado,fundo_detectado,projeto_detectado) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (wid, 8013, "draft", f"Planta {s} — {ic}", ic.lower(), f"https://exemplo.test/{ic}",
                   f"https://exemplo.test/img/{ic}.jpg", f"https://exemplo.test/img/{ic}-t.jpg", ic, fundo, cod))
for i in range(12):
    c.execute("INSERT INTO evento (entidade,codigo,tipo,ator,detalhe) VALUES ('projeto',?,'visto','seed','{}')", (PROJ[i % len(PROJ)][0],))
c.commit(); c.close()
print("banco de teste pronto:", os.environ["CAMP_DB_PATH"])
