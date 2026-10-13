#!/usr/bin/env bash
# Cartão 149: monta a RÉPLICA do ACERVOS_CAMP (no TS-231P) neste servidor, SÓ LEITURA e de forma permanente, e configura o painel.
#   sudo bash scripts/montar_replica.sh --host 192.168.15.31 --compartilhamento "Replica ACERVOS" --usuario USUARIO --pasta "ACERVOS_CAMP"
#   --pasta: caminho, dentro do compartilhamento, da pasta que é a cópia do ACERVOS_CAMP (onde fica _campvision/sentinela.json)
#   --simular: só mostra o que faria   --senha-de-stdin: senha pela entrada padrão
# Mesmo padrão do montar_qnap.sh: fstab com nofail + x-systemd.automount (não trava o boot), credenciais em arquivo 600 só do root.
# Diferença: monta com 'ro' (só leitura) — o painel nunca escreve na réplica.
set -euo pipefail
HOST=""; SHARE=""; USUARIO=""; PASTA=""; RAIZ=/mnt/qnap/replica; DONO=camp; VERS=3.0; SIMULAR=0; STDIN=0
while [ $# -gt 0 ]; do case "$1" in
  --host) HOST="$2"; shift 2;; --compartilhamento) SHARE="$2"; shift 2;; --usuario) USUARIO="$2"; shift 2;; --pasta) PASTA="$2"; shift 2;;
  --raiz) RAIZ="$2"; shift 2;; --vers) VERS="$2"; shift 2;; --simular) SIMULAR=1; shift;; --senha-de-stdin) STDIN=1; shift;;
  *) echo "Opção desconhecida: $1"; exit 2;; esac; done
[ -n "$HOST" ] && [ -n "$SHARE" ] && [ -n "$USUARIO" ] || { echo "Uso: sudo bash scripts/montar_replica.sh --host IP --compartilhamento NOME --usuario USUARIO [--pasta ACERVOS_CAMP] [--simular]"; exit 2; }
if [ "$SIMULAR" -eq 0 ] && [ "$EUID" -ne 0 ]; then exec sudo bash "$0" "$@"; fi
REPO="$(cd "$(dirname "$0")/.." && pwd)"
CRED=/etc/camp-replica.cred
SHARE_FSTAB="${SHARE// /\\040}"
UID_DONO=$(id -u "$DONO" 2>/dev/null || echo 1000); GID_DONO=$(id -g "$DONO" 2>/dev/null || echo 1000)
LINHA="//$HOST/$SHARE_FSTAB $RAIZ cifs ro,credentials=$CRED,uid=$UID_DONO,gid=$GID_DONO,file_mode=0444,dir_mode=0555,vers=$VERS,iocharset=utf8,_netdev,nofail,x-systemd.automount 0 0"
ALVO="$RAIZ${PASTA:+/$PASTA}"
if [ "$SIMULAR" -eq 1 ]; then
  echo "== SIMULAÇÃO (nada será alterado). O script faria:"
  echo "   1. instalar cifs-utils se faltar; criar a pasta $RAIZ"
  echo "   2. gravar usuário/senha em $CRED (permissão 600, só root)"
  echo "   3. guardar cópia do /etc/fstab e acrescentar/atualizar esta linha (SÓ LEITURA):"; echo "      $LINHA"
  echo "   4. recarregar o systemd, montar e testar a LEITURA como '$DONO' (e confirmar que NÃO dá para escrever)"
  echo "   5. procurar $ALVO/_campvision/sentinela.json e configurar o painel: replica.raiz = $ALVO"
  exit 0
fi
command -v mount.cifs >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq cifs-utils; }
mkdir -p "$RAIZ"
if [ "$STDIN" -eq 1 ]; then IFS= read -r SENHA; else read -rsp "Senha do usuário '$USUARIO' na réplica: " SENHA; echo; fi
[ -n "$SENHA" ] || { echo "Senha vazia."; exit 2; }
umask 077; printf 'username=%s\npassword=%s\n' "$USUARIO" "$SENHA" > "$CRED"; chmod 600 "$CRED"; unset SENHA
cp /etc/fstab "/etc/fstab.antes-replica.$(date +%Y%m%d%H%M%S)"
grep -v " $RAIZ cifs " /etc/fstab > /tmp/fstab.novo || true; echo "$LINHA" >> /tmp/fstab.novo; cat /tmp/fstab.novo > /etc/fstab
systemctl daemon-reload
mount "$RAIZ" 2>/tmp/montar_replica.err || { echo "✖ NÃO montou:"; cat /tmp/montar_replica.err; exit 1; }
mountpoint -q "$RAIZ" || { echo "✖ a pasta não virou ponto de montagem"; exit 1; }
echo "✔ montado (só leitura):"; findmnt -n -o SOURCE,TARGET,FSTYPE,OPTIONS "$RAIZ" | cut -c1-160
sudo -u "$DONO" ls "$ALVO" >/dev/null && echo "✔ leitura ok em $ALVO" || { echo "✖ '$DONO' não consegue ler $ALVO"; exit 1; }
if sudo -u "$DONO" sh -c "echo x > '$RAIZ/.camp-teste-$$'" 2>/dev/null; then rm -f "$RAIZ/.camp-teste-$$"; echo "✖ ATENÇÃO: deu para ESCREVER na réplica. Ela deveria ser só leitura (passo 3 do cartão)."; else echo "✔ escrita bloqueada (como deve ser)"; fi
PYX="$REPO/.venv/bin/python"; [ -x "$PYX" ] || PYX=python3
sudo -u "$DONO" "$PYX" "$REPO/scripts/configurar_replica_painel.py" --raiz "$ALVO" || echo "– não consegui configurar o painel sozinho; faça em Configurações → replica.raiz = $ALVO"
echo; echo "Pronto. Reinicie o painel: sudo systemctl restart camp-painel"
