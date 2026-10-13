"""Grava no painel onde a réplica do ACERVOS_CAMP está montada (configuracao 'replica.raiz'). Usado pelo montar_replica.sh."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import connect  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--raiz", required=True)
a = p.parse_args()
alvo = Path(a.raiz)
if not (alvo / "_campvision" / "sentinela.json").is_file():
    print(f"– aviso: não encontrei _campvision/sentinela.json em {alvo} (a réplica pode ainda não ter rodado; o painel vai mostrar vermelho até aparecer)")
con = connect()
con.execute("INSERT INTO configuracao (chave, valor, descricao, sensivel) VALUES ('replica.raiz', ?, 'Pasta da RÉPLICA do ACERVOS_CAMP (só leitura)', 0) "
            "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (str(alvo),))
con.commit(); con.close()
print(f"✔ painel configurado: replica.raiz = {alvo}")
