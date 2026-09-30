#!/usr/bin/env bash
# Instala o cloudflared e cria o serviço do túnel painel.camp.arq.br → localhost:8000
# Rodar na máquina campvision depois que o DNS estiver na Cloudflare.
set -e
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install -y cloudflared
cloudflared tunnel login
cloudflared tunnel create camp-painel
cloudflared tunnel route dns camp-painel painel.camp.arq.br
sudo mkdir -p /etc/cloudflared
cat <<CFG | sudo tee /etc/cloudflared/config.yml
tunnel: camp-painel
credentials-file: $HOME/.cloudflared/$(ls ~/.cloudflared | grep json | head -1)
ingress:
  - hostname: painel.camp.arq.br
    service: http://localhost:8000
  - service: http_status:404
CFG
sudo cloudflared service install
sudo systemctl enable --now cloudflared
echo "Túnel ativo. Configure o Cloudflare Access para painel.camp.arq.br no painel Zero Trust."
