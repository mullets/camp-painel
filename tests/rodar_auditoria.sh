#!/usr/bin/env bash
# Sobe o painel com banco sintético e roda as auditorias de navegador (jsdom). Uso: bash tests/rodar_auditoria.sh
set -u
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"; PY="${PYTHON:-python3}"
export CAMP_DB_PATH=/tmp/camp_auditoria.db CAMP_COOKIE_SECURE=false CAMP_BACKUP_DIR=/tmp/camp_auditoria_backups
export NODE_PATH="$(npm root -g)"
# um servidor de teste esquecido na porta 8765 faria a auditoria bater no banco ERRADO: encerra e confere
pkill -f "uvicorn app.main:app --port 8765" 2>/dev/null; sleep 1
if curl -sf http://127.0.0.1:8765/api/versao >/dev/null 2>&1; then echo "ERRO: a porta 8765 continua ocupada por outro processo; libere-a e rode de novo"; exit 3; fi
rm -rf "$CAMP_DB_PATH"* "$CAMP_BACKUP_DIR"
"$PY" "$RAIZ/tests/semear_banco_teste.py" || exit 1
( cd "$RAIZ/backend" && "$PY" -m uvicorn app.main:app --port 8765 --log-level warning >/tmp/camp_auditoria.log 2>&1 ) &
SRV=$!; trap 'kill $SRV 2>/dev/null; pkill -f "uvicorn app.main:app --port 8765" 2>/dev/null' EXIT   # o filho do subshell também
for i in $(seq 1 30); do curl -sf http://127.0.0.1:8765/api/versao >/dev/null && break; sleep 0.5; done
# Etapas (a bateria inteira passa de 5 minutos; rode por partes quando o tempo for curto):
#   bash tests/rodar_auditoria.sh                 -> todas, na ordem
#   bash tests/rodar_auditoria.sh novas xss       -> só essas
ETAPAS="${*:-painel novas atalhos xss}"
for E in $ETAPAS; do case "$E" in
  painel)  echo "################ TELAS E FLUXOS PRINCIPAIS ################"; node "$RAIZ/tests/auditoria_painel.js"; echo;;
  novas)   echo "################ FUNÇÕES NOVAS ################"; node "$RAIZ/tests/auditoria_novas_funcoes.js"; echo;;
  atalhos) echo "################ ATALHOS DE TECLADO ################"; node "$RAIZ/tests/auditoria_atalhos.js"; echo;;
  xss)     echo "################ XSS: HTML digitado nos campos de texto ################"; "$PY" "$RAIZ/tests/envenenar_banco.py"; node "$RAIZ/tests/auditoria_xss.js"; echo;;
  *) echo "etapa desconhecida: $E (use: painel novas atalhos xss)";;
esac; done
echo "--- erros 500 / tracebacks no log do servidor: $(grep -c 'Traceback\|Internal Server' /tmp/camp_auditoria.log)"
