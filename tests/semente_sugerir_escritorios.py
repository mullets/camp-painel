"""Semente do teste tests/navegador_sugerir_escritorios.js (CAMP-FICHA, 25/11/2026).

Uso: python3 tests/semente_sugerir_escritorios.py <banco.db>   (depois de tests/semear_banco_teste.py)
No projeto F023-P0011: folha 1 = detalhe de estrutura com o escritório de cálculo lido como Cliente e sem parceiros; folhas 2 e 3 com o
escritório de estrutura; 4, 5 e 7 com o de instalações elétricas; 2 a 5 com o cliente de verdade; o cliente do projeto fica vazio (para o
painel sugerir o das outras folhas).
"""
import json
import sqlite3
import sys

P = "F023-P0011"
D = lambda n: f"{P}-1959-S01-D{n:05d}"
c = sqlite3.connect(sys.argv[1])
DAPA = json.dumps([{"escritorio": "DAPA Lima Otero Engenharia", "disciplina": "Estrutura"}])
ELE = json.dumps([{"escritorio": "Eletro Projetos", "disciplina": "Instalações elétricas"}])
c.execute("UPDATE projeto SET cliente=NULL WHERE codigo=?", (P,))
c.execute("UPDATE item SET parceiros=NULL, cliente_folha=NULL WHERE projeto_codigo=?", (P,))
c.execute("UPDATE item SET titulo=?, tipo_lido='Detalhe / Estrutura', cliente_folha=? WHERE codigo=?",
          ("Detalhe da escada e lance pilares do 2º ao 1º sub-solo", "DAPA LIMA OTERO ENGENHARIA LTDA. S/C.", D(1)))
for n, pa in ((2, DAPA), (3, DAPA), (4, ELE), (5, ELE), (7, ELE)):
    c.execute("UPDATE item SET parceiros=? WHERE codigo=?", (pa, D(n)))
for n in (2, 3, 4, 5):
    c.execute("UPDATE item SET cliente_folha='Sr. Antonio Rodrigues' WHERE codigo=?", (D(n),))
c.execute("UPDATE item SET cliente_folha='Sra. Maria Souza' WHERE codigo=?", (D(6),))
c.commit()
print("semente de escritórios pronta:", sys.argv[1])
