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
auth.criar_usuario("Leitor", "leitor@camp.arq.br", "senha-leitor-1234", "leitura", forcar_troca=False)

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
# folhas SEM imagem no site (miniatura ausente e documento TIFF): a tela não pode inventar desenho
for n, doc in ((1, None), (2, "https://exemplo.test/img/scan.tif")):
    ic = f"F001-P0001-1961-S01-D0000{n}"
    c.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,folha,ano_folha,tainacan_item_id,origem) VALUES (?,?,?,?,?,?,?,?,'importado')",
              (ic, "F001-P0001", "S01", n, f"Sem imagem {n}", f"0{n}/02", 1961, 3000 + n))
    c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,slug,url,documento_url,thumb_url,imagem_origem,codigo_detectado,fundo_detectado,projeto_detectado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
              (3000 + n, 8013, "draft", f"Sem imagem {n} — {ic}", ic.lower(), f"https://exemplo.test/{ic}", doc, None, "", ic, "F001", "F001-P0001"))
MT = "Tainacan\\Metadata_Types\\"
for mid, nome, tipo, tax in ((501, "Técnica", "Text", None), (502, "Tipo de desenho", "Taxonomy", 77), (503, "Endereço", "Textarea", None), (504, "Data do registro fotográfico", "Date", None)):
    c.execute("INSERT INTO wp_metadado (id,colecao_id,nome,tipo,taxonomia_id) VALUES (?,?,?,?,?)", (mid, 8013, nome, MT + tipo, tax))
c.execute("INSERT INTO wp_taxonomia (id,nome) VALUES (77,'Tipos de desenho')")
c.execute("INSERT INTO wp_termo (id,taxonomia_id,nome) VALUES (9001,77,'Planta'),(9002,77,'Corte'),(9003,77,'Elevação')")
import json
c.execute("UPDATE wp_item SET metadados=?, json=? WHERE codigo_detectado='F023-P0011-1959-S01-D00001' AND colecao_id=8013",
          (json.dumps({"Técnica": "nanquim sobre vegetal", "Tipo de desenho": "Planta", "Data do registro fotográfico": "1972"}), json.dumps({"description": "Planta baixa do pavimento térreo."})))
c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,slug,url,documento_url,thumb_url,codigo_detectado,fundo_detectado,projeto_detectado,metadados) VALUES (2999,8013,'draft','Folha nova só no site','folha-nova','https://exemplo.test/folha-nova','https://exemplo.test/img/novo.jpg','https://exemplo.test/img/novo-t.jpg','F002-P0002-1977-S01-D00001','F002','F002-P0002',?)",
          (json.dumps({"Código do documento": "F002-P0002-1977-S01-D00001"}),))
c.execute("INSERT INTO wp_item (id,colecao_id,status,titulo,slug,url,documento_url,thumb_url,codigo_detectado,fundo_detectado,projeto_detectado,metadados) VALUES (2998,8013,'draft','Segunda folha só no site','folha-nova-2','https://exemplo.test/folha-nova-2','https://exemplo.test/img/novo2.jpg','https://exemplo.test/img/novo2-t.jpg','F002-P0002-1977-S01-D00002','F002','F002-P0002',?)",
          (json.dumps({"Código do documento": "F002-P0002-1977-S01-D00002"}),))
c.execute("UPDATE wp_item SET status='publish' WHERE codigo_detectado='F023-P0011-1959-S01-D00002' AND colecao_id=8013")
c.execute("UPDATE projeto SET status_site='no_ar' WHERE codigo='F003-P0001'")
# divergências entre o painel e o site (4 tipos reais + 1 desconhecido) para o topo do painel e a lista explicada
for campo, ent, cod, vp, vs in (("sem_codigo", "item", "9001", None, "Foto de teste"), ("sem_codigo", "item", "9002", None, "Outra de teste"), ("sem_itens_no_site", "fundo", "F029", "Fundo sem folhas", None), ("publicado_em_fundo_fora_do_ar", "item", "F023-P0011-1959-S01-D00002", "fora_do_ar", "publish"), ("fundo_inexistente", "item", "F999-P0001-1970-S01-D00001", None, "F999")):
    c.execute("INSERT INTO divergencia_site (entidade,codigo,campo,valor_painel,valor_site) VALUES (?,?,?,?,?)", (ent, cod, campo, vp, vs))
# uso do acervo: 30 pedidos de download vindos do formulário do site (12 pessoas, 4 usos, 3 materiais e alguns sem material)
import json as _json
_usos = ["Pesquisa", "Publicação", "Exposição", "Família"]; _mats = ["F023-P0011-1959-S01-D00001", "F023-P0011-1959-S01-D00003", "F026-P0001", None]
for i in range(30):
    n = i % 12; mat = _mats[i % 4]; nome = f"Pessoa Teste {n}"; email = f"pessoa{n}@exemplo.org"; tel = f"(11) 9000-{n:04d}"; inst = f"Universidade {n % 4}"
    c.execute("""INSERT INTO uso_download (form_id,origem_id,recebida_em,nome,email,telefone,instituicao,uso,material_codigo,material_origem,projeto_codigo,fundo_codigo,pagina,resposta_json)
                 VALUES (3,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (100 + i, f"2026-10-{(i % 7) + 1:02d} {10 + i % 9:02d}:15:00", nome, email, tel, inst, _usos[i % 4], mat, "campo" if mat else None,
               "-".join(mat.split("-")[:2]) if mat else None, mat.split("-")[0] if mat else None, f"https://camp.arq.br/acervo/ficha-{i}/",
               _json.dumps({"names": nome, "email": email, "phone": tel, "universidade_empresa": inst, "uso_pretendido": _usos[i % 4], "codigo_material": mat or ""}, ensure_ascii=False)))
# o coletor automático dispara 20 s depois de o servidor subir e gravaria uma coleta VAZIA (o QNAP de teste não existe) por cima da semente:
# os testes não podem depender de relógio. 0 desliga a coleta automática; "Atualizar agora" (manual) continua funcionando.
c.execute("UPDATE configuracao SET valor='0' WHERE chave='qnap.coleta_min'")
c.execute("UPDATE configuracao SET valor='0' WHERE chave='uso.coleta_min'")
# histórico do QNAP (7 dias, ~17 GB/dia) e a última coleta completa, para o cartão do painel inicial
for i in range(8):
    c.execute("INSERT INTO qnap_snapshot (coletado_em, montado, total_gb, livre_gb) VALUES (datetime('now', ?, '-1 hours'), 1, 20000, ?)", (f"-{7 - i} days", 12000 - 17 * i))
c.execute("INSERT INTO qnap_snapshot (coletado_em, montado, latencia_ms, total_gb, livre_gb, entrada_bruta, parados, prontos, ultimo_material_em, ultimo_material_nome, duracao_ms) VALUES (datetime('now','-4 minutes'), 1, 42, 20000, 11880, 14, 2, 230, datetime('now','-3 hours'), 'F002-P0002-IGREJA/lote-12', 800)")
c.execute("INSERT INTO wp_pagina (id,titulo,slug,url,status,codigo_detectado) VALUES (5001,'Jardim','f003-p0001-slug-real-do-plugin','https://camp.arq.br/acervo/projetos/f003-p0001-slug-real-do-plugin/','publish','F003-P0001')")
c.execute("INSERT INTO wp_pagina (id,titulo,slug,url,status,codigo_detectado) VALUES (5002,'Pag rascunho','f001-p0001-pagina-em-rascunho','https://camp.arq.br/acervo/projetos/f001-p0001-pagina-em-rascunho/','draft',NULL)")
# estados "despublicado" e "rascunho" em fundo, projeto, agente e folha: exercitam os rótulos do vocabulário único
c.execute("UPDATE fundo SET status_site='fora_do_ar', motivo_fora_do_ar='a pedido da família' WHERE codigo='F029'")
c.execute("UPDATE projeto SET status_site='fora_do_ar' WHERE codigo='F002-P0001'")
c.execute("UPDATE projeto SET status_site='rascunho' WHERE codigo='F001-P0001'")
c.execute("UPDATE agente SET status_site='fora_do_ar' WHERE id=(SELECT min(id) FROM agente)")
c.execute("UPDATE item SET status_site='fora_do_ar' WHERE codigo='F023-P0011-1959-S01-D00003'")
c.execute("UPDATE item SET status_site='rascunho' WHERE codigo='F023-P0011-1959-S01-D00004'")
for i in range(12):
    c.execute("INSERT INTO evento (entidade,codigo,tipo,ator,detalhe) VALUES ('projeto',?,'visto','seed','{}')", (PROJ[i % len(PROJ)][0],))
c.commit(); c.close()
print("banco de teste pronto:", os.environ["CAMP_DB_PATH"])
