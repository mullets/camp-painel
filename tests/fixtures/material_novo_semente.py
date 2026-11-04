"""Semente de Material novo para tests/navegador_material_novo.js (e para os prints do redesenho): o fundo F075 com lotes em TODAS as
etapas reais (CAMP Vision lendo, aguardando, leitura interrompida, falta importar, conferir, aprovar, publicar, no site, parado com erro)
e 34 lotes já no site para a paginação. Só mexe em F075 (apaga e recria). Uso: python3 tests/fixtures/material_novo_semente.py <banco>"""
import json
import sqlite3
import sys

con = sqlite3.connect(sys.argv[1])
F = "F075"
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES (?,?,?,1)", (F, "Fundo Material Novo", "FMN"))
con.execute("DELETE FROM item WHERE projeto_codigo LIKE 'F075-%'")
con.execute("DELETE FROM pedido_releitura WHERE projeto_codigo LIKE 'F075-%'")
con.execute("DELETE FROM lista_processamento WHERE projeto_codigo LIKE 'F075-%'")
con.execute("DELETE FROM projeto WHERE codigo LIKE 'F075-%'")
TIT = {1: "Residência Taques Bittencourt", 2: "Edifício de escritórios na Rua José Maria Lisboa", 3: "Pavilhão de exposições",
       4: "Hotel em Campos do Jordão", 5: "Escola Estadual de Itanhaém", 6: "Pensionato geriátrico na Vila Madalena",
       7: "Clube de campo em Atibaia", 8: "Agência bancária na Avenida Paulista", 9: "Casa de praia no Guarujá",
       10: "Igreja matriz de Ourinhos", 11: "Fórum de Piracicaba", 12: "Edifício residencial Sabará"}
seq = [0]


def projeto(n, titulo, autoria=None, no_ar=False):
    P = "F075-P%04d" % n
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES (?,?)", (F, n))
    con.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano,autoria,status_site,autorizado_site) VALUES (?,?,?,?,1968,?,?,1)",
                (P, F, n, titulo, autoria, "no_ar" if no_ar else "nao_publicado"))
    return P


def lote(P, etapa, horas, folhas=0, conferidas=0, esperadas=None, encontradas=None, aprovado=False, no_site=False, nome=None, status=None, jpg=False):
    lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, folhas_esperadas, folhas_encontradas, status_json, criado_em) "
                      "VALUES (?,?,?,?,?,?,?,datetime('now',?))",
                      (nome or ("%s - %s" % (P, TIT.get(int(P[-4:]), "Projeto"))), P, "/mnt/qnap/ACERVOS_CAMP/F075 - Fundo Material Novo/01 - Projetos/" + P,
                       etapa, esperadas, encontradas, json.dumps(status) if status else None, "-%d hours" % (horas + 1))).lastrowid
    con.execute("UPDATE lista_processamento SET etapa_desde=datetime('now',?), atualizado_em=datetime('now','-20 minutes'), aprovado_em=? WHERE id=?",
                ("-%d hours" % horas, "2026-11-01 10:00:00" if aprovado else None, lid))
    for k in range(folhas):
        seq[0] += 1
        con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, origem, lote_id, revisao, status_site, titulo, arquivo_jpg) "
                    "VALUES (?,?,'S01',?,'campvision',?,?,?,'Planta',?)",
                    ("%s-1968-S01-D%05d" % (P, seq[0]), P, seq[0], lid, "conferida" if k < conferidas else "pendente",
                     "no_ar" if no_site else "nao_publicado", ("x/%s-1968-S01-D%05d.jpg" % (P, seq[0])) if jpg else None))
    return lid


lote(projeto(1, TIT[1]), "processando", 3, esperadas=24, encontradas=9)
lote(projeto(2, TIT[2]), "enviado", 1)
lote(projeto(3, TIT[3]), "processando", 177, esperadas=26, encontradas=26)                       # leitura interrompida (sem sinal do CAMP Vision)
lote(projeto(4, TIT[4]), "revisao", 5, encontradas=12)                                           # falta importar
lote(projeto(5, TIT[5]), "revisao", 30, folhas=9, conferidas=3)                                  # para conferir
lote(projeto(6, TIT[6], autoria="Arnaldo Martino"), "revisao", 60, folhas=23, conferidas=0, jpg=True)   # parado há mais de 48 h, autoria registrada
lote(projeto(7, TIT[7]), "revisao", 8, folhas=10, conferidas=10)                                 # falta aprovar
lote(projeto(8, TIT[8]), "revisao", 12, folhas=8, conferidas=8, aprovado=True)                    # falta publicar
lote(projeto(9, TIT[9], no_ar=True), "revisao", 20, folhas=6, conferidas=6, aprovado=True, no_site=True)   # no site
lote(projeto(10, TIT[10]), "erro", 4, status={"erro": "IPTC:By-line exceeds length limit"})
lote(projeto(11, TIT[11], autoria="Arnaldo Martino"), "revisao", 2, folhas=4, conferidas=1)
for n in range(12, 46):
    lote(projeto(n, "%s %02d" % (TIT[12], n), no_ar=True), "revisao", 200 + n, folhas=2, conferidas=2, aprovado=True, no_site=True)
con.commit()
print("semente F075 pronta:", con.execute("SELECT COUNT(*) FROM lista_processamento WHERE projeto_codigo LIKE 'F075-%'").fetchone()[0], "lotes")
