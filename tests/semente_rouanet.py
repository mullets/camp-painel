"""CAMP-ROUANET: semente do teste de navegador (tests/navegador_rouanet.js). Banco de TESTE (nunca o real): despesas da conta do projeto
(id 2, PRONAC 2613864) para o item 16 chegar a 90% e o 14 passar do orçado, um débito do extrato sem item (para ligar na tela), o débito
que paga a nota da CAMP e o plano mensal da coordenação (item 7) e da administração (item 27).
Uso: python3 tests/semente_rouanet.py /dev/shm/rou/n.db   (depois de tests/semear_banco_teste.py)"""
import sqlite3
import sys
from datetime import date

db = sys.argv[1]
c = sqlite3.connect(db)
hoje = date.today()
mes = hoje.strftime("%Y-%m")
d1 = hoje.replace(day=1).isoformat()
ins = "INSERT OR IGNORE INTO despesa (conta_id, data, valor, meio, contraparte, descricao, origem, chave, tipo, categoria, justificativa, orcamento_item, restrito) VALUES (2,?,?,?,?,?,?,?, 'despesa', ?,?,?,1)"
c.execute(ins, (d1, 45972.0, "transferencia", "Gráfica Ipsis", "TED", "manual", "manual:rou1", "servicos", "Impressão do livro (1ª parcela)", 16))
c.execute(ins, (d1, 450.0, "boleto", "CBL", "Boleto", "manual", "manual:rou2", "servicos", "Ficha catalográfica e ISBN", 14))
c.execute(ins, (d1, 1200.0, "outro", "Sedex Agência Central", "PAGTO SEDEX", "ofx", "ofx:2:rou3", None, None, None))
c.execute(ins, (hoje.isoformat(), 3665.68, "transferencia", "CAMP", "TED CAMP", "ofx", "ofx:2:rou4", None, None, None))
for m in range(5):
    a, mm = hoje.year + (hoje.month - 1 + m) // 12, (hoje.month - 1 + m) % 12 + 1
    c.execute("INSERT OR IGNORE INTO orcamento_plano (conta_id, item, mes, valor) VALUES (2, 7, ?, 2600)", (f"{a}-{mm:02d}",))
    c.execute("INSERT OR IGNORE INTO orcamento_plano (conta_id, item, mes, valor) VALUES (2, 27, ?, 1065.68)", (f"{a}-{mm:02d}",))
c.execute("UPDATE configuracao SET valor='Centro de Arquitetura (teste)' WHERE chave='faturamento.razao_social'")
c.commit()
print("ok", mes)
