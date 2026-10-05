#!/usr/bin/env python3
"""Verifica ou restaura um backup NUM ARQUIVO NOVO (nunca sobrescreve o banco em uso).

  python scripts/restaurar_backup.py backend/backups/camp-20261005-033000.db.gz            # só verifica (arquivo temporário)
  python scripts/restaurar_backup.py ARQUIVO --para /tmp/camp-restaurado.db                # restaura e verifica

Para trocar o banco em produção (manual, de propósito):
  sudo systemctl stop camp-painel && cp /tmp/camp-restaurado.db backend/camp.db && sudo systemctl start camp-painel
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import backup as bk  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("arquivo")
ap.add_argument("--para")
ap.add_argument("--forcar", action="store_true")
a = ap.parse_args()
origem = Path(a.arquivo)
if not origem.is_file():
    sys.exit(f"Arquivo não encontrado: {origem}")
destino = Path(a.para) if a.para else Path(tempfile.mkdtemp()) / "verificacao.db"
try:
    v = bk.restaurar_para(origem, destino, forcar=a.forcar)
except bk.BackupErro as e:
    sys.exit(f"ERRO: {e}")
print(f"restauração verificada em {destino}")
print(f"integridade: {v['integridade']} | fundos {v['fundo']} | projetos {v['projeto']} | itens {v['item']} | usuários {v['usuario']}")
if not a.para:
    destino.unlink(missing_ok=True)
    print("(arquivo temporário descartado; use --para para manter a restauração)")
