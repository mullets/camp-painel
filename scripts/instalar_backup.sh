#!/usr/bin/env bash
# Instala (ou atualiza) o backup diário do banco do painel. Idempotente: pode rodar de novo.
set -euo pipefail
cd "$(dirname "$0")/.."
for u in camp-painel-backup.service camp-painel-backup.timer; do
  if ! cmp -s "scripts/$u" "/etc/systemd/system/$u" 2>/dev/null; then
    echo "== instalando $u"
    sudo cp "scripts/$u" "/etc/systemd/system/$u"
  fi
done
sudo systemctl daemon-reload
sudo systemctl enable --now camp-painel-backup.timer
echo "== primeiro backup agora (confirma que tudo funciona)"
sudo systemctl start camp-painel-backup.service || true
systemctl status camp-painel-backup.service --no-pager -n 12 | sed -n 1,16p || true
echo "== próximo agendamento"
systemctl list-timers camp-painel-backup.timer --no-pager | head -4
echo "== situação do backup"
.venv/bin/python scripts/backup_banco.py --estado
