#!/usr/bin/env bash
# Atualiza o painel no servidor: código, dependências, serviço. Uso: ./atualizar.sh
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
echo "== git pull"; git pull --ff-only
echo "== dependências"; pip install -q -r backend/requirements.txt
if ! cmp -s scripts/camp-painel.service /etc/systemd/system/camp-painel.service; then
  echo "== arquivo do serviço mudou; atualizando systemd"
  sudo cp scripts/camp-painel.service /etc/systemd/system/camp-painel.service && sudo systemctl daemon-reload
fi
git log -1 --format="%h %ad" --date=short > backend/VERSION
echo "== reiniciando serviço"; sudo systemctl restart camp-painel
sleep 2; systemctl is-active camp-painel && echo "serviço ativo" || { echo "SERVIÇO PAROU — log:"; journalctl -u camp-painel -n 30 --no-pager; exit 1; }
echo "== escutando em:"; ss -ltn | grep ":8000" || echo "porta 8000 não está aberta"
echo "== versão:"; git log --oneline -1
