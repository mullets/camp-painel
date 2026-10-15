#!/usr/bin/env bash
# Atualiza o painel no servidor com proteção da base real.
set -euo pipefail
cd "$(dirname "$0")"

BRANCH="$(git branch --show-current)"
if [ "$BRANCH" != "main" ]; then
  echo "ERRO: este servidor está na branch '$BRANCH'."
  echo "A atualização de produção só é permitida a partir de 'main'."
  exit 10
fi

source .venv/bin/activate

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
echo "== testes rápidos da versão nova (antes de atualizar)"
git fetch origin main
TESTE_DIR="$(mktemp -d)"
git worktree add --detach "$TESTE_DIR" origin/main >/dev/null
limpa_teste() { git worktree remove --force "$TESTE_DIR" >/dev/null 2>&1 || rm -rf "$TESTE_DIR"; git worktree prune; }
trap limpa_teste EXIT
pip install -q -r "$TESTE_DIR/backend/requirements.txt"
if ! (cd "$TESTE_DIR" && python tests/teste_backend.py --rapido); then
  echo "ERRO: os testes da versão nova falharam. NADA foi atualizado: o serviço continua na versão anterior."
  echo "Avise o Rafael com o resultado acima. O backup desta rodada está em: $BACKUP"
  exit 20
fi
limpa_teste
trap - EXIT

echo "== git pull main"
git pull --ff-only origin main

echo "== checagem estrutural da UI"
python scripts/check_ui.py

echo "== dependências"
pip install -q -r backend/requirements.txt

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

echo "== base depois do pull, antes do restart"
PYTHONPATH=backend python scripts/diagnostico_base.py

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
