#!/usr/bin/env bash
# Testes de exaustão da página do projeto (CAMP-072 a CAMP-121): cada arquivo de tests/exaustao/ roda com banco NOVO,
# QNAP falso numa pasta temporária e o painel com o site FALSO (tests/servidor_wp_falso.py, via tests/exaustao/f_servidor_falho.py:
# igual ao falso, com a queda no meio da publicação armável pelo teste do CAMP-111). Prints e relatório em SAIDA/<arquivo>/.
# Uso: bash tests/rodar_exaustao.sh [arquivos...]   (sem argumento: todos)   ·  EXAUSTAO_PORTA=8960 EXAUSTAO_SAIDA=/tmp/exaustao
set -uo pipefail
cd "$(dirname "$0")/.."
PORTA="${EXAUSTAO_PORTA:-8960}"; SAIDA="${EXAUSTAO_SAIDA:-/tmp/exaustao}"; mkdir -p "$SAIDA"
ARQS=("$@"); [ ${#ARQS[@]} -eq 0 ] && ARQS=(tests/exaustao/[!_]*.js)
falhas=0; resumo=""
for arq in "${ARQS[@]}"; do
  nome="$(basename "$arq" .js)"; TMP="$(mktemp -d /tmp/exaustao_XXXX)"; DB="$TMP/painel.db"; RAIZ="$TMP/qnap_final"; mkdir -p "$RAIZ"
  CAMP_DB_PATH="$DB" TMPDIR="$TMP" python3 tests/semear_banco_teste.py >/dev/null
  python3 - "$DB" "$RAIZ" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.execute("INSERT OR REPLACE INTO configuracao (chave, valor) VALUES ('qnap.prontos_raiz', ?)", (sys.argv[2],))
c.execute("INSERT OR REPLACE INTO direitos_fundo (fundo_codigo, situacao, titular, documento_autorizacao) VALUES ('F026','autorizado','Família','Termo assinado')")
c.commit()
PY
  (cd backend && exec env CAMP_DB_PATH="$DB" CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 TMPDIR="$TMP" F_FALHA_ARQ="$TMP/falhar_folha" python3 ../tests/exaustao/f_servidor_falho.py "$PORTA" >"$TMP/servidor.log" 2>&1) &
  PID=$!
  for _ in $(seq 1 40); do curl -s -o /dev/null "http://127.0.0.1:$PORTA/api/versao" && break; sleep 0.5; done
  rm -rf "$SAIDA/$nome"; mkdir -p "$SAIDA/$nome"
  F_FALHA_ARQ="$TMP/falhar_folha" CAMP_BASE="http://127.0.0.1:$PORTA" CAMP_DB_PATH="$DB" FLUXO_RAIZ="$RAIZ" SAIDA="$SAIDA/$nome" timeout 900 node "$arq" > "$SAIDA/$nome/saida.txt" 2>&1
  rc=$?; kill $PID 2>/dev/null; wait $PID 2>/dev/null
  n_ok=$(grep -c '^ok' "$SAIDA/$nome/saida.txt"); n_f=$(grep -c '^FALHA' "$SAIDA/$nome/saida.txt")
  resumo+="$( [ $rc -eq 0 ] && echo 'ok   ' || echo 'FALHA') $nome: $n_ok ok, $n_f falha(s)"$'\n'
  [ $rc -ne 0 ] && falhas=$((falhas+1)) && grep '^FALHA' "$SAIDA/$nome/saida.txt" | sed 's/^/      /' | head -20
  rm -rf "$TMP"
done
printf '%s' "$resumo"; echo "prints e relatórios: $SAIDA"
exit $falhas
