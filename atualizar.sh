#!/usr/bin/env bash
# Atualiza o painel no servidor: código, dependências, serviço. Uso: ./atualizar.sh
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
echo "== git pull"; git pull --ff-only
echo "== dependências"; pip install -q -r backend/requirements.txt
echo "== reiniciando serviço"; sudo systemctl restart camp-painel
sleep 2; systemctl is-active camp-painel && echo "serviço ativo" || { echo "SERVIÇO PAROU — log:"; journalctl -u camp-painel -n 30 --no-pager; exit 1; }
echo "== versão:"; git log --oneline -1
