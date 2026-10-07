#!/usr/bin/env python3
"""Aponta o painel para o armazenamento do acervo (mexe só nas chaves qnap.* que NÃO são senha).

    .venv/bin/python scripts/configurar_qnap_painel.py --raiz /mnt/server-camp --prontos "/mnt/server-camp/Arquivos/100 - Scanners" --ip 192.168.15.X
Também dá para fazer em Configurações (admin master). Registra o que mudou na auditoria.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import connect  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--raiz"); ap.add_argument("--prontos"); ap.add_argument("--entrada"); ap.add_argument("--ip")
a = ap.parse_args()
chaves = {"qnap.raiz": a.raiz, "qnap.prontos_raiz": a.prontos, "qnap.entrada_captura": a.entrada, "qnap.ip": a.ip}
alvo = {k: v for k, v in chaves.items() if v}
if not alvo:
    sys.exit("Nada para configurar: informe --raiz, --prontos, --entrada ou --ip")
con = connect()
mudou = {}
for k, v in alvo.items():
    r = con.execute("SELECT valor FROM configuracao WHERE chave=?", (k,)).fetchone()
    if r is None:
        sys.exit(f"Chave {k} não existe neste banco (rode o atualizar.sh para aplicar as migrações)")
    antes = r[0] or ""
    if antes != v:
        con.execute("UPDATE configuracao SET valor=?, atualizado_em=datetime('now'), atualizado_por='script' WHERE chave=?", (v, k))
        mudou[k] = {"antes": antes, "depois": v}
    print(f"  {k}: {antes or '(vazio)'} -> {v}" + ("" if antes != v else "  (já estava assim)"))
if mudou:
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES ('sistema','qnap','config_alterada','script',?)", (json.dumps(mudou, ensure_ascii=False),))
con.commit(); con.close()
print("Painel configurado. Reinicie para aplicar: sudo systemctl restart camp-painel")
