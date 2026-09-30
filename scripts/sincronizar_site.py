"""Lê o site (Tainacan/WordPress) e atualiza o espelho + divergências. Não grava nada no site.

    python scripts/sincronizar_site.py            # sincroniza e imprime resumo
    python scripts/sincronizar_site.py --relatorio  # só mostra as divergências da última execução
"""
import argparse, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "backend"))
from app.db import init_db, aplicar_migracoes, connect  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("--relatorio", action="store_true"); a = ap.parse_args()
init_db(); aplicar_migracoes()
if not a.relatorio:
    from app.sincronizador import executar
    r = executar()
    if not r["ok"]:
        sys.exit(1)
con = connect()
print("\n=== Divergências abertas ===")
for campo, qtd in con.execute("SELECT campo, COUNT(*) FROM divergencia_site WHERE resolvida=0 GROUP BY campo ORDER BY 2 DESC"):
    print(f"{qtd:5}  {campo}")
print("\nPrimeiras 40:")
for r in con.execute("SELECT entidade, codigo, campo, valor_site FROM divergencia_site WHERE resolvida=0 ORDER BY campo, codigo LIMIT 40"):
    print(f"  {r[0]:6} {r[1] or '-':32} {r[2]:28} {r[3] or ''}")
print("\nItens por fundo no site:")
for r in con.execute("SELECT fundo_detectado, status, COUNT(*) FROM wp_item GROUP BY 1,2 ORDER BY 1,2"):
    print(f"  {r[0] or '(sem código)':14} {r[1]:8} {r[2]}")
