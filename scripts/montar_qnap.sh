#!/usr/bin/env bash
# Conecta o compartilhamento SMB do QNAP em /mnt/qnap/acervos de forma PERMANENTE (volta sozinho após reiniciar).
#   sudo bash scripts/montar_qnap.sh --compartilhamento NOME --usuario USUARIO
#   (a senha é pedida no terminal; ou use --senha-de-stdin)   --simular só mostra o que faria, sem mudar nada
set -euo pipefail
IP=192.168.15.30; RAIZ=/mnt/qnap/acervos; SHARE=""; USUARIO=""; DONO=camp; VERS=3.0; SIMULAR=0; STDIN=0
while [ $# -gt 0 ]; do case "$1" in
  --compartilhamento) SHARE="$2"; shift 2;; --usuario) USUARIO="$2"; shift 2;; --ip) IP="$2"; shift 2;;
  --raiz) RAIZ="$2"; shift 2;; --dono) DONO="$2"; shift 2;; --vers) VERS="$2"; shift 2;;
  --simular) SIMULAR=1; shift;; --senha-de-stdin) STDIN=1; shift;;
  *) echo "Opção desconhecida: $1"; exit 2;; esac; done
[ -n "$SHARE" ] && [ -n "$USUARIO" ] || { echo "Uso: sudo bash scripts/montar_qnap.sh --compartilhamento NOME --usuario USUARIO [--ip $IP] [--raiz $RAIZ] [--simular]"; exit 2; }
if [ "$SIMULAR" -eq 0 ] && [ "$EUID" -ne 0 ]; then exec sudo bash "$0" "$@"; fi
CRED=/etc/camp-qnap.cred
SHARE_FSTAB="${SHARE// /\\040}"   # espaços no fstab viram \040
UID_DONO=$(id -u "$DONO" 2>/dev/null || echo 1000); GID_DONO=$(id -g "$DONO" 2>/dev/null || echo 1000)
LINHA="//$IP/$SHARE_FSTAB $RAIZ cifs credentials=$CRED,uid=$UID_DONO,gid=$GID_DONO,file_mode=0664,dir_mode=0775,vers=$VERS,iocharset=utf8,_netdev,nofail,x-systemd.automount,x-systemd.idle-timeout=0,x-systemd.mount-timeout=20 0 0"
if [ "$SIMULAR" -eq 1 ]; then
  echo "== SIMULAÇÃO (nada será alterado). O script faria:"
  echo "   1. instalar cifs-utils se faltar"; echo "   2. criar a pasta $RAIZ"
  echo "   3. gravar usuário/senha em $CRED (permissão 600, só root)"
  echo "   4. guardar cópia do /etc/fstab e acrescentar/atualizar esta linha:"; echo "      $LINHA"
  echo "   5. recarregar o systemd, montar e testar leitura e escrita como o usuário '$DONO'"; exit 0
fi
if [ "$STDIN" -eq 1 ]; then IFS= read -r SENHA; else read -rsp "Senha do usuário '$USUARIO' no QNAP: " SENHA; echo; fi
[ -n "$SENHA" ] || { echo "Senha vazia."; exit 2; }
command -v mount.cifs >/dev/null 2>&1 || { echo "== instalando cifs-utils"; apt-get install -y cifs-utils >/dev/null; }
mkdir -p "$RAIZ"
umask 077; printf 'username=%s\npassword=%s\n' "$USUARIO" "$SENHA" > "$CRED"; chmod 600 "$CRED"; chown root:root "$CRED"
cp /etc/fstab "/etc/fstab.bak-$(date +%Y%m%d-%H%M%S)"
grep -v -F " $RAIZ " /etc/fstab > /etc/fstab.novo || true
printf '%s\n' "$LINHA" >> /etc/fstab.novo; mv /etc/fstab.novo /etc/fstab
systemctl daemon-reload
echo "== montando $RAIZ"
if ! mount "$RAIZ" 2>/tmp/montar_qnap.err; then
  echo "✖ NÃO montou. Motivo:"; cat /tmp/montar_qnap.err; dmesg 2>/dev/null | grep -i cifs | tail -4 || true
  echo "  Dicas: confira usuário/senha e o NOME do compartilhamento (bash scripts/diagnostico_qnap.sh lista os nomes); se for SMB antigo, tente --vers 2.1."
  exit 1
fi
mountpoint -q "$RAIZ" || { echo "✖ a pasta não virou ponto de montagem"; exit 1; }
echo "✔ montado:"; findmnt -n -o SOURCE,TARGET,FSTYPE "$RAIZ"; df -h "$RAIZ" | tail -1
echo "== testando LEITURA e ESCRITA como '$DONO' (é com esse usuário que o painel roda)"
sudo -u "$DONO" ls "$RAIZ" >/dev/null && echo "✔ leitura ok" || { echo "✖ '$DONO' não consegue ler"; exit 1; }
T="$RAIZ/.camp-teste-escrita-$$"
if sudo -u "$DONO" sh -c "echo ok > '$T' && rm -f '$T'"; then echo "✔ escrita ok (arquivo de teste criado e apagado)"; else echo "– sem permissão de escrita (ok se o painel só precisa LER; confira as permissões do compartilhamento no QTS)"; fi
echo; echo "Pronto. Reinicie o painel para ele enxergar: sudo systemctl restart camp-painel"
