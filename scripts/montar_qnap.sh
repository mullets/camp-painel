#!/usr/bin/env bash
# Conecta um compartilhamento SMB neste servidor de forma PERMANENTE (volta sozinho após reiniciar) e configura o painel.
#   sudo bash scripts/montar_qnap.sh --host Server-Camp.local --compartilhamento "Backup Servidor CAMP" --usuario USUARIO \
#        --raiz /mnt/server-camp --subpasta "Arquivos/100 - Scanners"
#   --host: nome ou IP (nome é resolvido para IP na hora: o fstab guarda o IP, porque nome .local não existe no boot)
#   --convidado: sem usuário/senha   --simular: só mostra o que faria   --senha-de-stdin: senha vem da entrada padrão
#   --subpasta: pasta do MATERIAL PRONTO dentro do compartilhamento (o painel passa a ler dali)
set -euo pipefail
HOST=192.168.15.30; RAIZ=/mnt/qnap/acervos; SHARE=""; USUARIO=""; SUB=""; DONO=camp; VERS=3.0; SIMULAR=0; STDIN=0; CONVIDADO=0
while [ $# -gt 0 ]; do case "$1" in
  --host|--ip) HOST="$2"; shift 2;; --compartilhamento) SHARE="$2"; shift 2;; --usuario) USUARIO="$2"; shift 2;;
  --raiz) RAIZ="$2"; shift 2;; --subpasta) SUB="$2"; shift 2;; --dono) DONO="$2"; shift 2;; --vers) VERS="$2"; shift 2;;
  --simular) SIMULAR=1; shift;; --senha-de-stdin) STDIN=1; shift;; --convidado) CONVIDADO=1; shift;;
  *) echo "Opção desconhecida: $1"; exit 2;; esac; done
[ -n "$SHARE" ] && { [ -n "$USUARIO" ] || [ "$CONVIDADO" -eq 1 ]; } || { echo "Uso: sudo bash scripts/montar_qnap.sh --host NOME_OU_IP --compartilhamento NOME (--usuario USUARIO | --convidado) [--raiz $RAIZ] [--subpasta PASTA] [--simular]"; exit 2; }
if [ "$SIMULAR" -eq 0 ] && [ "$EUID" -ne 0 ]; then exec sudo bash "$0" "$@"; fi
REPO="$(cd "$(dirname "$0")/.." && pwd)"
# nome -> IP (o fstab precisa de IP)
IP="$HOST"
if ! [[ "$HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  IP="$(getent hosts "$HOST" 2>/dev/null | awk '{print $1; exit}' || true)"   # "|| true": sem isso o set -e mata o script em silêncio quando o nome não resolve
  if [ -z "$IP" ] && command -v avahi-resolve >/dev/null 2>&1; then IP="$(avahi-resolve -n "$HOST" 2>/dev/null | awk '{print $2; exit}' || true)"; fi
  if [ -z "$IP" ]; then echo "✖ não consegui descobrir o IP de '$HOST'. Use o IP direto (--host 192.168.15.X) ou instale: sudo apt install avahi-daemon libnss-mdns"; exit 1; fi
  echo "== '$HOST' = $IP (o fstab vai guardar o IP; o ideal é reservar esse IP fixo no roteador)"
fi
CRED=/etc/camp-qnap.cred
SHARE_FSTAB="${SHARE// /\\040}"
UID_DONO=$(id -u "$DONO" 2>/dev/null || echo 1000); GID_DONO=$(id -g "$DONO" 2>/dev/null || echo 1000)
if [ "$CONVIDADO" -eq 1 ]; then AUTH="guest"; else AUTH="credentials=$CRED"; fi
LINHA="//$IP/$SHARE_FSTAB $RAIZ cifs $AUTH,uid=$UID_DONO,gid=$GID_DONO,file_mode=0664,dir_mode=0775,vers=$VERS,iocharset=utf8,_netdev,nofail,x-systemd.automount,x-systemd.idle-timeout=0,x-systemd.mount-timeout=20 0 0"
if [ "$SIMULAR" -eq 1 ]; then
  echo "== SIMULAÇÃO (nada será alterado). O script faria:"
  echo "   1. instalar cifs-utils se faltar; criar a pasta $RAIZ"
  [ "$CONVIDADO" -eq 1 ] && echo "   2. montar como convidado (sem senha)" || echo "   2. gravar usuário/senha em $CRED (permissão 600, só root)"
  echo "   3. guardar cópia do /etc/fstab e acrescentar/atualizar esta linha:"; echo "      $LINHA"
  echo "   4. recarregar o systemd, montar e testar leitura e escrita como o usuário '$DONO'"
  [ -n "$SUB" ] && echo "   5. configurar o painel: pasta do material pronto = $RAIZ/$SUB (e a raiz = $RAIZ)"
  exit 0
fi
if [ "$CONVIDADO" -eq 0 ]; then
  if [ "$STDIN" -eq 1 ]; then IFS= read -r SENHA; else read -rsp "Senha do usuário '$USUARIO': " SENHA; echo; fi
  [ -n "$SENHA" ] || { echo "Senha vazia."; exit 2; }
fi
command -v mount.cifs >/dev/null 2>&1 || { echo "== instalando cifs-utils"; apt-get install -y cifs-utils >/dev/null; }
mkdir -p "$RAIZ"
if [ "$CONVIDADO" -eq 0 ]; then umask 077; printf 'username=%s\npassword=%s\n' "$USUARIO" "$SENHA" > "$CRED"; chmod 600 "$CRED"; chown root:root "$CRED"; fi
cp /etc/fstab "/etc/fstab.bak-$(date +%Y%m%d-%H%M%S)"
grep -v -F " $RAIZ " /etc/fstab > /etc/fstab.novo || true
printf '%s\n' "$LINHA" >> /etc/fstab.novo; mv /etc/fstab.novo /etc/fstab
systemctl daemon-reload
echo "== montando $RAIZ"
if ! mount "$RAIZ" 2>/tmp/montar_qnap.err; then
  echo "✖ NÃO montou. Motivo:"; cat /tmp/montar_qnap.err; dmesg 2>/dev/null | grep -i cifs | tail -4 || true
  echo "  Dicas: usuário/senha; NOME EXATO do compartilhamento (bash scripts/diagnostico_qnap.sh --host $HOST lista os nomes); SMB antigo: --vers 2.1."
  exit 1
fi
mountpoint -q "$RAIZ" || { echo "✖ a pasta não virou ponto de montagem"; exit 1; }
echo "✔ montado:"; findmnt -n -o SOURCE,TARGET,FSTYPE "$RAIZ"; df -h "$RAIZ" | tail -1
echo "== testando LEITURA e ESCRITA como '$DONO' (é com esse usuário que o painel roda)"
sudo -u "$DONO" ls "$RAIZ" >/dev/null && echo "✔ leitura ok" || { echo "✖ '$DONO' não consegue ler"; exit 1; }
T="$RAIZ/.camp-teste-escrita-$$"
if sudo -u "$DONO" sh -c "echo ok > '$T' && rm -f '$T'"; then echo "✔ escrita ok (arquivo de teste criado e apagado)"; else echo "– sem permissão de escrita (ok se o painel só precisa LER; confira as permissões do compartilhamento)"; fi
if [ -n "$SUB" ]; then
  if [ -d "$RAIZ/$SUB" ]; then echo "✔ a pasta do material pronto existe: $RAIZ/$SUB"
    PYX="$REPO/.venv/bin/python"; [ -x "$PYX" ] || PYX=python3
    if sudo -u "$DONO" "$PYX" "$REPO/scripts/configurar_qnap_painel.py" --raiz "$RAIZ" --prontos "$RAIZ/$SUB" --ip "$IP"; then :; else echo "– não consegui configurar o painel sozinho; faça em Configurações: qnap.raiz=$RAIZ e qnap.prontos_raiz=$RAIZ/$SUB"; fi
  else echo "✖ montou, mas a subpasta '$SUB' NÃO existe. O que há no compartilhamento:"; ls -1 "$RAIZ" | head -20 | sed 's/^/    /'; echo "  (confira o nome exato, incluindo maiúsculas e espaços)"; fi
fi
echo; echo "Pronto. Reinicie o painel para ele enxergar: sudo systemctl restart camp-painel"
