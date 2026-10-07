#!/usr/bin/env bash
# Diagnóstico SOMENTE LEITURA: por que o armazenamento do acervo não aparece como conectado neste servidor?
#   bash scripts/diagnostico_qnap.sh
#   bash scripts/diagnostico_qnap.sh --host Server-Camp.local --compartilhamento "Backup Servidor CAMP" --subpasta "Arquivos/100 - Scanners"
# (--host aceita nome ou IP; sem argumentos usa o que está em Configurações do painel)
cd "$(dirname "$0")/.." || exit 1
HOST_ARG=""; SHARE_ARG=""; USR_ARG=""; SUB_ARG=""; RAIZ_ARG=""
while [ $# -gt 0 ]; do case "$1" in
  --host|--ip) HOST_ARG="$2"; shift 2;; --compartilhamento) SHARE_ARG="$2"; shift 2;; --usuario) USR_ARG="$2"; shift 2;;
  --subpasta) SUB_ARG="$2"; shift 2;; --raiz) RAIZ_ARG="$2"; shift 2;; *) echo "Opção desconhecida: $1"; exit 2;; esac; done
PY="${PY:-.venv/bin/python}"; [ -x "$PY" ] || PY=python3
mapfile -t CFG < <("$PY" - <<'PYEOF'
import sqlite3, sys
sys.path.insert(0, "backend")
from app.config import settings
c = sqlite3.connect(f"file:{settings.CAMP_DB_PATH}?mode=ro", uri=True)
g = lambda k, p="": ((c.execute("SELECT valor FROM configuracao WHERE chave=?", (k,)).fetchone() or [p])[0] or p)
print(g("qnap.ip", "192.168.15.30")); print(g("qnap.raiz", "/mnt/qnap/acervos")); print(g("qnap.usuario", "")); print(g("qnap.senha", "")); print(g("qnap.prontos_raiz", ""))
PYEOF
) 2>/dev/null
HOST="${HOST_ARG:-${CFG[0]:-192.168.15.30}}"; RAIZ="${RAIZ_ARG:-${CFG[1]:-/mnt/qnap/acervos}}"; USR="${USR_ARG:-${CFG[2]}}"; export PASSWD="${CFG[3]}"; PRONTOS="${CFG[4]}"
if [ -n "$USR" ] && [ -z "$PASSWD" ] && [ -t 0 ]; then read -rsp "Senha de '$USR' no servidor de arquivos (Enter = tentar sem senha): " PASSWD; echo; export PASSWD; fi
ok(){ echo "  ✔ $*"; }; ruim(){ echo "  ✖ $*"; }; info(){ echo "  – $*"; }
echo "== Servidor de arquivos: $HOST · pasta esperada neste servidor: $RAIZ · usuário: ${USR:-(nenhum / convidado)}${SHARE_ARG:+ · compartilhamento: $SHARE_ARG}"
IP="$HOST"; RESOLVE=0; REDE=1; SMB=1; MONTADO=1
echo; echo "1) Descobrir o endereço de '$HOST'"
if [[ "$HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then ok "já é um IP"
else
  IP="$(getent hosts "$HOST" 2>/dev/null | awk '{print $1; exit}')"
  [ -z "$IP" ] && command -v avahi-resolve >/dev/null 2>&1 && IP="$(avahi-resolve -n "$HOST" 2>/dev/null | awk '{print $2; exit}')"
  if [ -n "$IP" ]; then ok "$HOST = $IP"; else
    ruim "este servidor NÃO consegue descobrir o IP de '$HOST' (nomes .local do Mac costumam não funcionar no Ubuntu)"
    info "opção A: sudo apt install avahi-daemon libnss-mdns   |   opção B (melhor): use o IP direto: --host 192.168.15.X"
    info "o IP aparece no Mac: Finder > Server-Camp > menu Arquivo > Obter Informações, ou na tela do roteador"; RESOLVE=1; fi
fi
echo; echo "2) O servidor responde na rede?"
if [ $RESOLVE -eq 0 ] && ping -c1 -W2 "$IP" >/dev/null 2>&1; then ok "ping em $IP"; REDE=0; elif [ $RESOLVE -eq 0 ]; then ruim "sem resposta ao ping em $IP (desligado? cabo? IP certo?)"; else info "pulado: sem IP"; fi
echo; echo "3) O compartilhamento SMB está aberto?"
if [ $RESOLVE -eq 0 ] && timeout 3 bash -c "</dev/tcp/$IP/445" 2>/dev/null; then ok "porta 445 (SMB) aberta"; SMB=0; elif [ $RESOLVE -eq 0 ]; then ruim "porta 445 fechada ou sem resposta (SMB desligado?)"; else info "pulado: sem IP"; fi
echo; echo "4) Este servidor sabe montar SMB?"
command -v mount.cifs >/dev/null 2>&1 && ok "mount.cifs instalado (cifs-utils)" || ruim "falta o pacote cifs-utils (o montar_qnap.sh instala sozinho)"
echo; echo "5) A pasta $RAIZ neste servidor"
if [ -d "$RAIZ" ]; then
  if mountpoint -q "$RAIZ" 2>/dev/null; then ok "é um ponto de montagem ($(findmnt -n -o SOURCE,FSTYPE "$RAIZ" 2>/dev/null))"; MONTADO=0
  elif [ -n "$(ls -A "$RAIZ" 2>/dev/null | head -1)" ]; then info "não é ponto de montagem, mas tem arquivos"; MONTADO=0
  else ruim "existe mas está VAZIA e nada está montado nela (é isto que o painel chama de \"não conectado\")"; fi
else ruim "a pasta não existe"; fi
if [ $MONTADO -eq 0 ] && [ -n "$SUB_ARG" ]; then [ -d "$RAIZ/$SUB_ARG" ] && ok "a subpasta '$SUB_ARG' existe" || ruim "montado, mas a subpasta '$SUB_ARG' NÃO existe aqui (nome diferente? veja: ls \"$RAIZ\")"; fi
[ $MONTADO -eq 0 ] && [ -n "$PRONTOS" ] && { [ -d "$PRONTOS" ] && ok "pasta do material pronto configurada no painel existe: $PRONTOS" || ruim "pasta do material pronto configurada no painel NÃO existe: $PRONTOS"; }
echo; echo "6) Montagem permanente (/etc/fstab)"
if grep -q -i -E "qnap|$IP|$RAIZ|server-camp" /etc/fstab 2>/dev/null; then ok "há linha no fstab:"; grep -n -i -E "qnap|$IP|$RAIZ|server-camp" /etc/fstab | sed 's/password=[^, ]*/password=***/; s/^/      /'
else ruim "nenhuma linha no /etc/fstab (por isso não volta a montar sozinho depois de reiniciar)"; fi
echo; echo "7) Compartilhamentos que o servidor oferece"
if command -v smbclient >/dev/null 2>&1 && [ $SMB -eq 0 ]; then
  if [ -n "$USR" ]; then LISTA="$(smbclient -L "//$IP" -U "$USR" -m SMB3 2>/dev/null | awk -F'  +' '/Disk/{gsub(/^[ \t]+/,"",$2); print $2}')"
  else LISTA="$(smbclient -L "//$IP" -N -m SMB3 2>/dev/null | awk -F'  +' '/Disk/{gsub(/^[ \t]+/,"",$2); print $2}')"; fi
  if [ -n "$LISTA" ]; then echo "$LISTA" | sed 's/^/      compartilhamento: /'
    [ -n "$SHARE_ARG" ] && { echo "$LISTA" | grep -Fxq "$SHARE_ARG" && ok "o compartilhamento '$SHARE_ARG' existe" || ruim "NÃO achei '$SHARE_ARG' na lista acima (copie o nome exatamente)"; }
  else ruim "não consegui listar (precisa de usuário/senha? use --usuario NOME)"; fi
else info "smbclient não instalado ou SMB fechado — opcional (sudo apt install smbclient)"; fi
[ $MONTADO -eq 0 ] && [ -d "$RAIZ" ] && { echo; echo "8) Espaço"; df -h "$RAIZ" | sed 's/^/    /'; }
echo; echo "== VEREDITO"
if   [ $RESOLVE -ne 0 ]; then echo "  Falta saber o IP de '$HOST'. Rode de novo com o IP: bash scripts/diagnostico_qnap.sh --host 192.168.15.X"
elif [ $REDE -ne 0 ];    then echo "  O servidor de arquivos não responde na rede. Confira se está ligado e o endereço."
elif [ $SMB -ne 0 ];     then echo "  Responde, mas o SMB está fechado. Ative o serviço de compartilhamento SMB no servidor de arquivos."
elif [ $MONTADO -eq 0 ]; then echo "  Está conectado e com conteúdo: o painel deve mostrar 'conectado'. Se não mostra: sudo systemctl restart camp-painel"
else
  echo "  O servidor de arquivos está no ar e o SMB aberto, mas NÃO está conectado a este servidor. Próximo passo:"
  echo "    sudo bash scripts/montar_qnap.sh --host $HOST --compartilhamento \"${SHARE_ARG:-NOME}\" --usuario USUARIO --raiz /mnt/server-camp${SUB_ARG:+ --subpasta \"$SUB_ARG\"}"
fi
