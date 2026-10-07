#!/usr/bin/env bash
# Roda UM teste de navegador isolado contra um servidor com banco sintético.  Uso: bash tests/rodar_um.sh tests/auditoria_atalhos.js
set -u
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"; PY="${PYTHON:-python3}"; ALVO="${1:?informe o arquivo .js do teste}"
export CAMP_DB_PATH=/tmp/camp_um.db CAMP_COOKIE_SECURE=false CAMP_BACKUP_DIR=/tmp/camp_um_backups NODE_PATH="$(npm root -g)"
pkill -f "uvicorn app.main:app --port 8765" 2>/dev/null; sleep 1
if curl -sf http://127.0.0.1:8765/api/versao >/dev/null 2>&1; then echo "ERRO: a porta 8765 continua ocupada por outro processo"; exit 3; fi
rm -rf "$CAMP_DB_PATH"* "$CAMP_BACKUP_DIR"
"$PY" "$RAIZ/tests/semear_banco_teste.py" >/dev/null || exit 1
( cd "$RAIZ/backend" && "$PY" -m uvicorn app.main:app --port 8765 --log-level warning >/tmp/camp_um.log 2>&1 ) &
SRV=$!; trap 'kill $SRV 2>/dev/null; pkill -f "uvicorn app.main:app --port 8765" 2>/dev/null' EXIT
for i in $(seq 1 30); do curl -sf http://127.0.0.1:8765/api/versao >/dev/null && break; sleep 0.5; done
node "$RAIZ/$ALVO"
