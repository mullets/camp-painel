#!/usr/bin/env python3
"""Backup consistente do banco do painel (ver backend/app/backup.py).

  python scripts/backup_banco.py                 # backup + cópia extra (se configurada) + retenção
  python scripts/backup_banco.py --so-retencao   # só poda backups antigos (usado pelo atualizar.sh)
  python scripts/backup_banco.py --estado        # mostra a situação e sai
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import backup as bk  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--sem-gzip", action="store_true")
ap.add_argument("--sem-extra", action="store_true")
ap.add_argument("--so-retencao", action="store_true")
ap.add_argument("--estado", action="store_true")
a = ap.parse_args()

if a.estado:
    print(json.dumps(bk.estado(), ensure_ascii=False, indent=1))
    sys.exit(0)
if a.so_retencao:
    r = bk.aplicar_retencao(bk.PASTA)
    print(f"retenção: {len(r)} backup(s) antigo(s) removido(s) de {bk.PASTA}")
    sys.exit(0)
try:
    r = bk.fazer_backup(destino_extra=None if a.sem_extra else bk.destino_extra_configurado(), comprimir=not a.sem_gzip)
except bk.BackupErro as e:
    print(f"ERRO NO BACKUP: {e}", file=sys.stderr)
    sys.exit(1)
c = r["contagens"]
print(f"backup ok: {bk.PASTA / r['arquivo']} ({r['tamanho_bytes'] / 1024 ** 2:.1f} MB) — fundos {c['fundo']}, projetos {c['projeto']}, itens {c['item']}, usuários {c['usuario']}")
if r["extra"]:
    print("cópia extra:", "ok em " + r["extra"]["caminho"] if r["extra"]["ok"] else "FALHOU — " + r["extra"].get("erro", "?"))
print(f"retenção: {r['removidos']} backup(s) antigo(s) removido(s)")
sys.exit(0 if not (r["extra"] and not r["extra"]["ok"]) else 2)   # 2 = backup local ok, cópia extra falhou
