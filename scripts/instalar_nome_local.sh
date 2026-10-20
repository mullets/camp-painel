#!/usr/bin/env bash
# Nome fixo do painel na rede local: http://painel.local (sem IP e sem :8000).
#
#  - painel.local: o servidor anuncia o nome na rede (mDNS/avahi). Mac, iPhone, Windows 10+ e Linux com avahi
#    acham sozinhos, sem configurar nada nas máquinas. Se o IP do servidor mudar, o nome acompanha.
#  - porta 80: uma regra do firewall manda a porta 80 para a 8000 do painel. O IP de quem acessa continua o
#    mesmo (as estações na LAN seguem sem token, ver backend/app/rede.py). http://192.168.15.60:8000 continua
#    valendo, e o túnel (painel.camp.arq.br) não muda.
#
# Uso no servidor (usuário camp, com sudo):
#   bash scripts/instalar_nome_local.sh --simular   # só mostra o que faria
#   bash scripts/instalar_nome_local.sh             # instala
#   bash scripts/instalar_nome_local.sh --verificar # confere nome e porta
#   bash scripts/instalar_nome_local.sh --desfazer  # tira tudo
set -euo pipefail

NOME="${CAMP_NOME_LOCAL:-painel.local}"
PORTA_PAINEL="${CAMP_PORTA_PAINEL:-8000}"
SVC_NOME=camp-painel-nome
SVC_PORTA=camp-painel-porta80
ANUNCIAR=/usr/local/sbin/camp-painel-anunciar-nome
MODO="${1:-instalar}"

SIMULAR=0
[ "$MODO" = "--simular" ] && SIMULAR=1
roda() { if [ "$SIMULAR" = 1 ]; then echo "  [simular] $*"; else "$@"; fi; }
grava() { # grava <arquivo>  (conteúdo pela entrada)
  local destino="$1" conteudo; conteudo="$(cat)"
  if [ "$SIMULAR" = 1 ]; then echo "  [simular] gravaria $destino:"; sed 's/^/      /' <<<"$conteudo"; else printf '%s\n' "$conteudo" | sudo tee "$destino" >/dev/null; fi
}
ip_servidor() { { ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}'; } || true; }
ip_servidor_ou_outro() { local i; i="$(ip_servidor_ou_outro)"; [ -n "$i" ] || i="$(hostname -I 2>/dev/null | awk '{print $1}')"; echo "$i"; }

# Regras: só tráfego destinado a ESTA máquina (addrtype LOCAL), para não pegar nada que só passa por ela.
REGRA_FORA=(PREROUTING -p tcp -m addrtype --dst-type LOCAL --dport 80 -j REDIRECT --to-ports "$PORTA_PAINEL")
REGRA_DENTRO=(OUTPUT -p tcp -m addrtype --dst-type LOCAL --dport 80 -j REDIRECT --to-ports "$PORTA_PAINEL")

verificar() {
  local ip ok=0; ip="$(ip_servidor_ou_outro)"
  echo "IP do servidor: ${ip:-não achei}"
  if command -v avahi-resolve >/dev/null && r="$(timeout 5 avahi-resolve -4 -n "$NOME" 2>/dev/null)" && [ -n "$r" ]; then
    echo "ok    $NOME responde na rede: $r"
  else echo "FALHA $NOME não respondeu (systemctl status $SVC_NOME)"; ok=1; fi
  local cod; cod="$(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://${ip:-127.0.0.1}/api/versao" || true)"
  if [ "$cod" = 200 ]; then echo "ok    http://${ip}/ (porta 80) abre o painel"; else echo "FALHA porta 80 não chegou ao painel (código ${cod:-nenhum}; systemctl status $SVC_PORTA)"; ok=1; fi
  [ "$ok" = 0 ] && echo -e "\nPronto: abra http://$NOME nas máquinas da CAMP." || true
  return "$ok"
}

desfazer() {
  for s in "$SVC_NOME" "$SVC_PORTA"; do
    sudo systemctl disable --now "$s" 2>/dev/null || true
    sudo rm -f "/etc/systemd/system/$s.service"
  done
  sudo rm -f "$ANUNCIAR"
  sudo systemctl daemon-reload
  sudo iptables -t nat -D "${REGRA_FORA[@]}" 2>/dev/null || true
  sudo iptables -t nat -D "${REGRA_DENTRO[@]}" 2>/dev/null || true
  echo "Desfeito: $NOME e a porta 80 saíram. O painel segue em http://$(ip_servidor_ou_outro):$PORTA_PAINEL"
}

instalar() {
  [ "$SIMULAR" = 1 ] && echo "Modo simular: nada é alterado."
  # 1) a porta 80 tem de estar livre (se já houver nginx/apache, não mexemos)
  if ss -ltnH 'sport = :80' 2>/dev/null | grep -q .; then
    echo "PARE: já há um programa usando a porta 80 neste servidor:"; ss -ltnp 'sport = :80' 2>/dev/null || true
    echo "Nada foi alterado. Desligue esse programa ou fale com quem cuida do painel."; exit 1
  fi
  # 2) o painel tem de estar respondendo na porta dele
  if ! curl -s -o /dev/null -m 5 "http://127.0.0.1:$PORTA_PAINEL/api/versao"; then
    echo "AVISO: o painel não respondeu em 127.0.0.1:$PORTA_PAINEL agora. Sigo assim mesmo (a regra vale quando ele subir)."
  fi
  # 3) avahi (mDNS)
  if ! command -v avahi-publish >/dev/null || ! systemctl list-unit-files avahi-daemon.service >/dev/null 2>&1; then
    echo "Instalando avahi (anuncia o nome na rede)…"
    roda sudo apt-get install -y avahi-daemon avahi-utils libnss-mdns
  fi
  roda sudo systemctl enable --now avahi-daemon

  # 4) serviço que anuncia painel.local com o IP do servidor (script auxiliar: o systemd mexe em "$" de linha de comando)
  grava "$ANUNCIAR" <<'EOF'
#!/bin/sh
# Anuncia o nome do painel na rede (mDNS) com o IP atual. Instalado por scripts/instalar_nome_local.sh.
IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')
[ -n "$IP" ] || IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -n "$IP" ] || { echo "sem IP ainda"; exit 1; }
exec avahi-publish -a -R "$1" "$IP"
EOF
  roda sudo chmod 755 "$ANUNCIAR"
  grava "/etc/systemd/system/$SVC_NOME.service" <<EOF
[Unit]
Description=CAMP painel: anuncia $NOME na rede local (mDNS)
After=network-online.target avahi-daemon.service
Wants=network-online.target
Requires=avahi-daemon.service

[Service]
ExecStart=$ANUNCIAR $NOME
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

  # 5) serviço que liga a regra porta 80 → painel a cada boot (e tira ao parar)
  local add_fora add_dentro del_fora del_dentro
  add_fora="iptables -t nat -C ${REGRA_FORA[*]} 2>/dev/null || iptables -t nat -A ${REGRA_FORA[*]}"
  add_dentro="iptables -t nat -C ${REGRA_DENTRO[*]} 2>/dev/null || iptables -t nat -A ${REGRA_DENTRO[*]}"
  del_fora="iptables -t nat -D ${REGRA_FORA[*]} 2>/dev/null || true"
  del_dentro="iptables -t nat -D ${REGRA_DENTRO[*]} 2>/dev/null || true"
  grava "/etc/systemd/system/$SVC_PORTA.service" <<EOF
[Unit]
Description=CAMP painel: porta 80 vai para a $PORTA_PAINEL (http://$NOME sem :$PORTA_PAINEL)
After=network-online.target ufw.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c '$add_fora; $add_dentro'
ExecStop=/bin/sh -c '$del_fora; $del_dentro'

[Install]
WantedBy=multi-user.target
EOF

  roda sudo systemctl daemon-reload
  roda sudo systemctl enable --now "$SVC_PORTA"
  roda sudo systemctl enable --now "$SVC_NOME"

  # 6) ufw: a 8000 já está liberada para a LAN; a 80 entra junto (o pacote chega à 8000 depois do desvio)
  if command -v ufw >/dev/null && sudo ufw status 2>/dev/null | grep -q "Status: active"; then
    roda sudo ufw allow 80/tcp
  fi

  if [ "$SIMULAR" = 1 ]; then echo -e "\nSimulação concluída. Rode sem --simular para instalar."; return 0; fi
  sleep 3; echo; verificar || true
  cat <<EOF

Nas máquinas:
  - Mac, iPhone, Windows 10/11: abra http://$NOME
  - Android antigo ou alguma máquina que não ache: use http://$(ip_servidor_ou_outro) (sem :$PORTA_PAINEL também funciona)
  - Estações e CAMP Vision podem continuar no IP; não precisa mudar nada nelas.
Para tirar: bash scripts/instalar_nome_local.sh --desfazer
EOF
}

case "$MODO" in
  instalar|--simular) instalar ;;
  --verificar) verificar ;;
  --desfazer) desfazer ;;
  -h|--help) sed -n 2,15p "$0" ;;
  *) echo "Opção desconhecida: $MODO (use --simular, --verificar, --desfazer)"; exit 2 ;;
esac
