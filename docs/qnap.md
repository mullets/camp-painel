# Conectar o QNAP ao servidor do painel

O painel (servidor `camp@camp`, `192.168.15.60`) precisa enxergar o acervo do QNAP numa pasta local, **`/mnt/qnap/acervos`**.
É dali que ele lê os lotes (`status.json`, `info_projeto.json`), a pasta final do CAMP Vision 2 e o espaço livre.
O QNAP pode estar funcionando perfeitamente nos Macs e **mesmo assim não estar conectado a este servidor**: são coisas diferentes.

O painel mostra **"QNAP não está conectado a este servidor"** quando essa pasta não existe ou está vazia (uma pasta vazia criada à mão não conta).

## Exemplo real: pasta do material pronto em `smb://Server-Camp/Backup Servidor CAMP/Arquivos/100 - Scanners`
O endereço `Server-Camp._smb._tcp.local` é o nome que o **Mac** enxerga. O servidor Ubuntu geralmente **não** resolve nomes `.local`: use o **IP** do Server-Camp
(no Mac: Finder > Server-Camp > Arquivo > Obter Informações, ou na tela do roteador; o ideal é reservar esse IP fixo). O compartilhamento é `Backup Servidor CAMP`
e `Arquivos/100 - Scanners` é a subpasta. Então (troque o IP e o usuário):
```
bash scripts/diagnostico_qnap.sh --host 192.168.15.X --compartilhamento "Backup Servidor CAMP" --usuario USUARIO --subpasta "Arquivos/100 - Scanners"
sudo bash scripts/montar_qnap.sh --host 192.168.15.X --compartilhamento "Backup Servidor CAMP" --usuario USUARIO --raiz /mnt/server-camp --subpasta "Arquivos/100 - Scanners"
sudo systemctl restart camp-painel
```
O segundo comando monta o compartilhamento em `/mnt/server-camp`, deixa permanente e configura o painel: `qnap.raiz = /mnt/server-camp` (é o que o painel testa) e
`qnap.prontos_raiz = /mnt/server-camp/Arquivos/100 - Scanners` (o material pronto). Se o Mac entra sem senha, use `--convidado` em vez de `--usuario`.
`scripts/configurar_qnap_painel.py` faz só a parte do painel (ou edite em Configurações).

## Conectar (3 passos, no servidor)
1. **Descobrir o que falta** (só lê, não muda nada):
   `bash scripts/diagnostico_qnap.sh`
   Ele checa rede, porta SMB, pacote `cifs-utils`, a pasta, o `/etc/fstab`, lista os compartilhamentos e dá um veredito com o próximo comando.
2. **Conectar e deixar permanente**:
   `sudo bash scripts/montar_qnap.sh --compartilhamento NOME --usuario USUARIO`
   (a senha é pedida no terminal). `--simular` mostra o que seria feito sem mudar nada.
   O nome do compartilhamento aparece no passo 1 ou no QTS: *Painel de controle > Privilégios > Pastas compartilhadas*.
3. **Reiniciar o painel**: `sudo systemctl restart camp-painel` — Estações deve mostrar "conectado".

## O que o script faz
- instala `cifs-utils` se faltar; cria `/mnt/qnap/acervos`;
- guarda usuário/senha em `/etc/camp-qnap.cred` (permissão 600, só root; **nunca** no repositório nem no histórico);
- faz cópia do `/etc/fstab` (`/etc/fstab.bak-AAAAMMDD-HHMMSS`) e coloca uma linha com `nofail` + `x-systemd.automount`
  (se o QNAP estiver desligado o servidor **não trava na inicialização**, e a pasta conecta no primeiro acesso);
- monta e testa leitura e escrita como o usuário `camp`, que é com quem o painel roda.

## Se der erro
| Sintoma | O que fazer |
|---|---|
| Diagnóstico: sem resposta ao ping | QNAP desligado, cabo, ou IP errado em Configurações (`qnap.ip`) |
| Porta 445 fechada | No QTS ligue *Rede Microsoft*: Painel de controle > Serviços de rede e arquivos |
| `mount error(13)` / permissão negada | usuário ou senha errados, ou o usuário não tem acesso àquele compartilhamento |
| `mount error(2)` / não encontrado | nome do compartilhamento errado (copie exatamente como no passo 1) |
| `mount error(95)` / protocolo | tente `--vers 2.1` |
| Monta, mas o painel não escreve | permissão de escrita do usuário no compartilhamento (QTS) |

## Desfazer
Apague a linha do QNAP em `/etc/fstab` (há cópia ao lado), rode `sudo umount /mnt/qnap/acervos` e `sudo rm /etc/camp-qnap.cred`.
