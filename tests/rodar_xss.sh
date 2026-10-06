#!/usr/bin/env bash
# Só a auditoria de XSS (mais rápida que rodar_auditoria.sh). Uso: bash tests/rodar_xss.sh
set -u
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"; PY="${PYTHON:-python3}"
export CAMP_DB_PATH=/tmp/camp_xss.db CAMP_COOKIE_SECURE=false CAMP_BACKUP_DIR=/tmp/camp_xss_backups NODE_PATH="$(npm root -g)"
rm -rf "$CAMP_DB_PATH"* "$CAMP_BACKUP_DIR"
"$PY" "$RAIZ/tests/semear_banco_teste.py" >/dev/null || exit 1
( cd "$RAIZ/backend" && "$PY" -m uvicorn app.main:app --port 8765 --log-level warning >/tmp/camp_xss.log 2>&1 ) &
SRV=$!; trap 'kill $SRV 2>/dev/null' EXIT
for i in $(seq 1 30); do curl -sf http://127.0.0.1:8765/api/versao >/dev/null && break; sleep 0.5; done
"$PY" "$RAIZ/tests/envenenar_banco.py"
node "$RAIZ/tests/auditoria_xss.js"
