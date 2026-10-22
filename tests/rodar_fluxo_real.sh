#!/usr/bin/env bash
# Teste de fluxo real de ponta a ponta (tests/fluxo_real.js): banco novo, QNAP falso numa pasta temporária, painel com site FALSO.
# Uso: bash tests/rodar_fluxo_real.sh [porta] [pasta-dos-prints]
set -euo pipefail
cd "$(dirname "$0")/.."
PORTA="${1:-8958}"; SAIDA="${2:-/tmp/fluxo_real}"
TMP="$(mktemp -d /tmp/fluxo_real_XXXX)"; DB="$TMP/painel.db"; RAIZ="$TMP/qnap_final"; mkdir -p "$RAIZ"
rm -rf "$SAIDA"; mkdir -p "$SAIDA"
CAMP_DB_PATH="$DB" TMPDIR="$TMP" python3 tests/semear_banco_teste.py >/dev/null
python3 - "$DB" "$RAIZ" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.execute("INSERT OR REPLACE INTO configuracao (chave, valor) VALUES ('qnap.prontos_raiz', ?)", (sys.argv[2],))
# pré-condição do fundo (feita uma vez, fora do fluxo do lote): os direitos do F026 estão autorizados
c.execute("INSERT OR REPLACE INTO direitos_fundo (fundo_codigo, situacao, titular, documento_autorizacao) VALUES ('F026','autorizado','Família','Termo assinado')")
c.commit()
PY
(cd backend && exec env CAMP_DB_PATH="$DB" CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 TMPDIR="$TMP" python3 ../tests/servidor_wp_falso.py "$PORTA" >"$TMP/servidor.log" 2>&1) &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
for _ in $(seq 1 40); do curl -s -o /dev/null "http://127.0.0.1:$PORTA/api/versao" && break; sleep 0.5; done
set +e
CAMP_BASE="http://127.0.0.1:$PORTA" CAMP_DB_PATH="$DB" FLUXO_RAIZ="$RAIZ" SAIDA="$SAIDA" node tests/fluxo_real.js
RC=$?
echo "prints e relatório: $SAIDA · log do servidor: $TMP/servidor.log"
exit $RC
