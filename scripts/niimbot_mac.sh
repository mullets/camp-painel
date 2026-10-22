#!/usr/bin/env bash
# Instala no Mac da etiquetadora o servidor de impressão da NIIMBOT D110 (niimblue-node, código aberto, MIT) e deixa ele ligando sozinho.
# O painel (Etiquetas → formato NIIMBOT → "Imprimir na NIIMBOT") manda as etiquetas para http://localhost:5000; o servidor fala com a D110
# pelo cabo USB-C (recomendado) ou Bluetooth. Uso: bash scripts/niimbot_mac.sh        Desinstalar: bash scripts/niimbot_mac.sh --remover
set -euo pipefail
VERSAO="1.4.1"; PORTA="5000"; ROTULO="br.arq.camp.niimbot"; PLIST="$HOME/Library/LaunchAgents/$ROTULO.plist"; LOG="$HOME/Library/Logs/camp-niimbot.log"

[ "$(uname)" = "Darwin" ] || { echo "Este script é para o Mac."; exit 1; }
if [ "${1:-}" = "--remover" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true; rm -f "$PLIST"; echo "Servidor da NIIMBOT desligado e removido do início automático."; exit 0
fi

echo "== 1/4 Ferramentas da Apple (o Bluetooth do servidor precisa compilar um módulo)"
if ! xcode-select -p >/dev/null 2>&1; then
  xcode-select --install || true
  echo "Termine a instalação que abriu na tela e rode este script de novo."; exit 1
fi

echo "== 2/4 Node.js"
if ! command -v node >/dev/null 2>&1; then
  # NÃO usa o Homebrew: em macOS antigo (ex.: Big Sur, Intel) o brew compila o Node do zero e quebra (sphinx-doc / pip).
  echo "Falta o Node.js. Baixe o instalador oficial (.pkg) da versão 22 LTS, que funciona do macOS 11 em diante:"
  echo "   https://nodejs.org/dist/latest-v22.x/   →  o arquivo node-v22.….pkg"
  echo "Instale (duplo clique), feche e abra o Terminal e rode este script de novo."
  open "https://nodejs.org/dist/latest-v22.x/" 2>/dev/null || true
  exit 1
fi
node -v

echo "== 3/4 niimblue-node $VERSAO"
if ! npm install -g "@mmote/niimblue-node@$VERSAO"; then
  echo "Sem permissão na pasta global do npm: tentando com sudo (pede a senha do Mac)."
  sudo npm install -g "@mmote/niimblue-node@$VERSAO"
fi
BIN="$(npm prefix -g)/bin/niimblue-cli"; [ -x "$BIN" ] || { echo "niimblue-cli não apareceu em $BIN"; exit 1; }

echo "== 4/4 Ligar sozinho ao entrar no Mac (só aceita conexões deste computador: 127.0.0.1:$PORTA)"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$ROTULO</string>
  <key>ProgramArguments</key><array><string>$BIN</string><string>server</string><string>--cors</string><string>-h</string><string>127.0.0.1</string><string>-p</string><string>$PORTA</string></array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$(dirname "$(command -v node)"):/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG</string><key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
sleep 3
if curl -fsS "http://127.0.0.1:$PORTA/" >/dev/null; then
  echo "PRONTO: servidor da NIIMBOT rodando em http://localhost:$PORTA (log: $LOG)."
else
  echo "O servidor não respondeu. Veja o log: $LOG"; exit 1
fi
cat <<TXT

Agora:
  1. Ligue a D110 e conecte o cabo USB-C (o jeito mais estável).
  2. No painel: Etiquetas → formato "NIIMBOT D110" → "Imprimir na NIIMBOT". Na primeira vez ele pergunta qual impressora usar.
Bluetooth: o macOS precisa permitir o Bluetooth para o servidor. Se pelo Bluetooth não achar a impressora, use o cabo ou rode
  "niimblue-cli server --cors" no Terminal (aí a permissão é do Terminal: Ajustes → Privacidade e Segurança → Bluetooth).
TXT
