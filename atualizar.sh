#!/usr/bin/env bash
# Atualiza o painel no servidor com proteção da base real.
# 19/10: mais rápido e mais quieto — sai na hora se já está na versão mais nova (--forcar roda mesmo assim), os testes rodam em
# paralelo e só mostram o resumo (o detalhe fica num arquivo de log), e não reinstala dependências que não mudaram.
# Tudo fica dentro de main(): o bash lê a função inteira antes de rodar, então o "git pull" que troca este arquivo no meio não o embaralha.
set -euo pipefail
cd "$(dirname "$0")"

main() {
INICIO=$SECONDS
FORCAR=0; [ "${1:-}" = "--forcar" ] && FORCAR=1

BRANCH="$(git branch --show-current)"
if [ "$BRANCH" != "main" ]; then
  echo "ERRO: este servidor está na branch '$BRANCH'."
  echo "A atualização de produção só é permitida a partir de 'main'."
  exit 10
fi

source .venv/bin/activate

echo "== procurando versão nova"
git fetch -q origin main
ATUAL="$(git rev-parse --short HEAD)"; NOVA="$(git rev-parse --short origin/main)"
if [ "$ATUAL" = "$NOVA" ] && [ "$FORCAR" = 0 ]; then
  echo "Já está na versão mais nova ($(git log -1 --format='%cd · %s' --date=format:'%d/%m %H:%M')). Nada a fazer."
  echo "(para rodar tudo mesmo assim: ./atualizar.sh --forcar)"
  return 0
fi
echo "versão nova: $(git log -1 --format='%cd · %s' --date=format:'%d/%m %H:%M' origin/main)"
echo "mudanças desde a atual: $(git rev-list --count HEAD..origin/main)"

echo "== base antes da atualização"
PYTHONPATH=backend python scripts/diagnostico_base.py

DB_PATH="$(PYTHONPATH=backend python - <<'PY'
from app.config import settings
print(settings.CAMP_DB_PATH)
PY
)"
BACKUP_DIR="backend/backups"
mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_DIR/camp-$STAMP.db"

echo "== backup do banco"
python - "$DB_PATH" "$BACKUP" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
orig = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
dest = sqlite3.connect(dst)
with dest:
    orig.backup(dest)
dest.close()
orig.close()
print(dst)
PY

# CAMP-040: a versão nova é testada ANTES de entrar. Os testes rodam numa cópia temporária de origin/main com bancos de teste (a base
# real e o serviço não são tocados). Se falhar, aborta aqui: nada é baixado para esta pasta e o serviço continua como está.
echo "== testes rápidos da versão nova (antes de atualizar; o detalhe vai para um arquivo)"
TESTE_DIR="$(mktemp -d)"
git worktree add --detach "$TESTE_DIR" origin/main >/dev/null
limpa_teste() { git worktree remove --force "$TESTE_DIR" >/dev/null 2>&1 || rm -rf "$TESTE_DIR"; git worktree prune; }
trap limpa_teste EXIT
cmp -s "$TESTE_DIR/backend/requirements.txt" backend/requirements.txt || pip install -q -r "$TESTE_DIR/backend/requirements.txt"
LOG_TESTE="backend/logs/teste-atualizar-$STAMP.log"; mkdir -p backend/logs
T0=$SECONDS
if ! (cd "$TESTE_DIR" && python tests/teste_backend.py --rapido) > "$LOG_TESTE" 2>&1; then
  grep -E "FALHA|Traceback|Error" "$LOG_TESTE" | head -40 || true
  echo "ERRO: os testes da versão nova falharam. NADA foi atualizado: o serviço continua na versão anterior."
  echo "Detalhe completo: $LOG_TESTE"
  echo "Avise o Rafael com o resultado acima. O backup desta rodada está em: $BACKUP"
  exit 20
fi
echo "testes ok: $(grep -c '^  ok' "$LOG_TESTE") verificações em $((SECONDS - T0)) s (detalhe: $LOG_TESTE)"
limpa_teste
trap - EXIT

echo "== git pull main"
git pull -q --ff-only origin main

echo "== checagem estrutural da UI"
python scripts/check_ui.py

if ! git diff --quiet "$ATUAL" HEAD -- backend/requirements.txt; then
  echo "== dependências mudaram: instalando"
  pip install -q -r backend/requirements.txt
fi

for u in camp-painel-backup.service camp-painel-backup.timer; do
  if [ -f "/etc/systemd/system/$u" ] && ! cmp -s "scripts/$u" "/etc/systemd/system/$u"; then
    echo "== unidade $u mudou; atualizando systemd"
    sudo cp "scripts/$u" "/etc/systemd/system/$u"
    sudo systemctl daemon-reload
  fi
done

if ! cmp -s scripts/camp-painel.service /etc/systemd/system/camp-painel.service; then
  echo "== arquivo do serviço mudou; atualizando systemd"
  sudo cp scripts/camp-painel.service /etc/systemd/system/camp-painel.service
  sudo systemctl daemon-reload
fi

git log -1 --format="%h %ad" --date=short > backend/VERSION

echo "== reiniciando serviço"
sudo systemctl restart camp-painel
sleep 2

if systemctl is-active --quiet camp-painel; then
  echo "serviço ativo"
else
  echo "SERVIÇO PAROU — restaurar o backup se necessário: $BACKUP"
  journalctl -u camp-painel -n 50 --no-pager
  exit 1
fi

echo "== escutando em:"
ss -ltn | grep ":8000" || { echo "porta 8000 não está aberta"; exit 1; }

echo "== versão:"
git log --oneline -1

echo "== base em uso:"
PYTHONPATH=backend python scripts/diagnostico_base.py

echo "== poda de backups antigos (mantém 24h + 14 dias + 8 semanas)"
python scripts/backup_banco.py --so-retencao || true

echo "== backup preservado em: $BACKUP"
echo "== pronto em $((SECONDS - INICIO)) s"
}

main "$@"
exit $?
