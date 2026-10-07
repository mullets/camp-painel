#!/usr/bin/env bash
# Diagnóstico SOMENTE LEITURA: por que o QNAP não aparece como "montado" neste servidor?
# Uso (na pasta do repositório):  bash scripts/diagnostico_qnap.sh
cd "$(dirname "$0")/.." || exit 1
PY="${PY:-.venv/bin/python}"; [ -x "$PY" ] || PY=python3
mapfile -t CFG < <("$PY" - <<'PYEOF'
import sqlite3, sys
sys.path.insert(0, "backend")
from app.config import settings
c = sqlite3.connect(f"file:{settings.CAMP_DB_PATH}?mode=ro", uri=True)
g = lambda k, p="": ((c.execute("SELECT valor FROM configuracao WHERE chave=?", (k,)).fetchone() or [p])[0] or p)
print(g("qnap.ip", "192.168.15.30")); print(g("qnap.raiz", "/mnt/qnap/acervos")); print(g("qnap.usuario", "")); print(g("qnap.senha", ""))
PYEOF
) 2>/dev/null
IP="${CFG[0]:-192.168.15.30}"; RAIZ="${CFG[1]:-/mnt/qnap/acervos}"; USR="${CFG[2]}"; export PASSWD="${CFG[3]}"
ok(){ echo "  ✔ $*"; }; ruim(){ echo "  ✖ $*"; }; info(){ echo "  – $*"; }
echo "== QNAP configurado no painel: $IP · pasta esperada: $RAIZ · usuário: ${USR:-(não definido)} · senha: $([ -n "$PASSWD" ] && echo definida || echo "(não definida)")"
REDE=1; SMB=1; CIFS=1; PASTA=1; MONTADO=1
echo; echo "1) O QNAP responde na rede?"
if ping -c1 -W2 "$IP" >/dev/null 2>&1; then ok "ping em $IP"; REDE=0; else ruim "sem resposta ao ping em $IP (desligado? cabo? IP certo em Configurações?)"; fi
echo; echo "2) O compartilhamento SMB está aberto?"
if timeout 3 bash -c "</dev/tcp/$IP/445" 2>/dev/null; then ok "porta 445 (SMB) aberta"; SMB=0; else ruim "porta 445 fechada ou sem resposta (SMB desligado no QNAP?)"; fi
echo; echo "3) Este servidor sabe montar SMB?"
if command -v mount.cifs >/dev/null 2>&1; then ok "mount.cifs instalado (cifs-utils)"; CIFS=0; else ruim "falta o pacote cifs-utils (sudo apt install cifs-utils; o montar_qnap.sh instala sozinho)"; fi
echo; echo "4) A pasta $RAIZ"
if [ -d "$RAIZ" ]; then
  ok "a pasta existe"; PASTA=0
  if mountpoint -q "$RAIZ" 2>/dev/null; then ok "é um ponto de montagem ($(findmnt -n -o SOURCE,FSTYPE "$RAIZ" 2>/dev/null))"; MONTADO=0
  elif [ -n "$(ls -A "$RAIZ" 2>/dev/null | head -1)" ]; then info "não é ponto de montagem, mas tem arquivos"; MONTADO=0
  else ruim "existe mas está VAZIA e nada está montado nela (é isto que o painel chama de \"não conectado\")"; fi
else ruim "a pasta não existe"; fi
echo; echo "5) Montagem permanente (/etc/fstab)"
grep -n -i -E "qnap|$IP|$RAIZ" /etc/fstab 2>/dev/null | sed 's/password=[^, ]*/password=***/' | sed 's/^/    /' || true
grep -q -i -E "qnap|$IP|$RAIZ" /etc/fstab 2>/dev/null && ok "há linha para o QNAP no fstab" || ruim "nenhuma linha para o QNAP no /etc/fstab (por isso não volta a montar sozinho)"
echo; echo "6) Compartilhamentos que o QNAP oferece (precisa de usuário e senha no painel)"
if command -v smbclient >/dev/null 2>&1; then
  if [ -n "$USR" ] && [ -n "$PASSWD" ]; then
    smbclient -L "//$IP" -U "$USR" -m SMB3 2>/dev/null | awk '$2=="Disk"{print "    compartilhamento: " $1}' | grep . || ruim "não consegui listar (usuário/senha errados? SMB3 desligado?)"
  else info "usuário/senha do QNAP não estão em Configurações: sem eles não dá para listar os compartilhamentos"; fi
else info "smbclient não instalado (sudo apt install smbclient) — opcional, só serve para listar os nomes dos compartilhamentos"; fi
[ -d "$RAIZ" ] && [ $MONTADO -eq 0 ] && { echo; echo "7) Espaço e leitura"; df -h "$RAIZ" | sed 's/^/    /'; ls "$RAIZ" 2>/dev/null | head -5 | sed 's/^/    pasta: /'; }
echo; echo "== VEREDITO"
if   [ $REDE -ne 0 ];   then echo "  O QNAP não responde na rede. Confira se está ligado e o IP em Configurações (qnap.ip)."
elif [ $SMB -ne 0 ];    then echo "  O QNAP responde, mas o SMB está fechado. Ative o serviço 'Rede Microsoft' no QTS (Painel de controle > Serviços de rede e arquivos)."
elif [ $MONTADO -eq 0 ];then echo "  Está montado e com conteúdo: o painel deve mostrar 'ok'. Se não mostra, reinicie o painel: sudo systemctl restart camp-painel"
else
  echo "  O QNAP está no ar e o SMB aberto, mas NÃO está conectado a este servidor."
  echo "  Próximo passo (use o nome do compartilhamento listado no item 6, ou o que aparece no QTS):"
  echo "    sudo bash scripts/montar_qnap.sh --compartilhamento NOME --usuario USUARIO"
fi
