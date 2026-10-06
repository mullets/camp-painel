#!/usr/bin/env bash
# Sobe o painel com banco sintético e roda as auditorias de navegador (jsdom). Uso: bash tests/rodar_auditoria.sh
set -u
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"; PY="${PYTHON:-python3}"
export CAMP_DB_PATH=/tmp/camp_auditoria.db CAMP_COOKIE_SECURE=false CAMP_BACKUP_DIR=/tmp/camp_auditoria_backups
export NODE_PATH="$(npm root -g)"
rm -rf "$CAMP_DB_PATH"* "$CAMP_BACKUP_DIR"
"$PY" "$RAIZ/tests/semear_banco_teste.py" || exit 1
( cd "$RAIZ/backend" && "$PY" -m uvicorn app.main:app --port 8765 --log-level warning >/tmp/camp_auditoria.log 2>&1 ) &
SRV=$!; trap 'kill $SRV 2>/dev/null' EXIT
for i in $(seq 1 30); do curl -sf http://127.0.0.1:8765/api/versao >/dev/null && break; sleep 0.5; done
echo "################ TELAS E FLUXOS PRINCIPAIS ################"
node "$RAIZ/tests/auditoria_painel.js"
echo
echo "################ FUNÇÕES NOVAS ################"
node "$RAIZ/tests/auditoria_novas_funcoes.js"
echo
echo "################ XSS: HTML digitado nos campos de texto ################"
"$PY" "$RAIZ/tests/envenenar_banco.py"
node "$RAIZ/tests/auditoria_xss.js"
echo
echo "--- erros 500 / tracebacks no log do servidor: $(grep -c 'Traceback\|Internal Server' /tmp/camp_auditoria.log)"
