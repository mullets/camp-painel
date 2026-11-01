# Entrega de pedidos de alta resolução por e-mail

Desde 01/11/2026, um pedido de material em alta resolução é aprovado e enviado pelo próprio painel. A pessoa recebe um e-mail com um
link de download com prazo. Pode ser o e-mail do Sender.net, com o layout pronto da CAMP, ou o e-mail do site. Ela baixa os arquivos
do QNAP por esse link.

## Como a equipe usa

1. **Pedidos de alta resolução** → abra o pedido → **Ver o que entregar**.
2. **Aprovar e enviar por e-mail**. A tela mostra:
   - para quem vai e até quando o link vale;
   - os arquivos achados no QNAP, com o tamanho;
   - o que **fica de fora**, e por quê: PDF, folha sem TIFF no QNAP, código desconhecido;
   - **Por onde sai o e-mail**: Sender.net ou e-mail do site;
   - **Recado no e-mail** (opcional): condições de uso, crédito pedido etc.;
   - **Ver o texto do e-mail**.
3. **Enviar um teste para mim**. Manda o mesmo e-mail para quem está logado, com um link de 1 dia, e não muda o pedido. Use para
   conferir o layout.
4. **Aprovar e enviar**. O pedido fica **entregue** só depois que o Sender.net ou o site aceitam o e-mail. Se o envio falhar, aparece o
   motivo, o link criado é cancelado e o pedido não muda.
5. Depois de enviado, o pacote mostra **Links de download enviados**: situação (ativo, venceu, cancelado) e quantos downloads houve.
   **Cancelar o link** faz o link parar na hora; serve, por exemplo, se o e-mail foi para o endereço errado.

"Marcar como entregue" continua existindo para o pedido entregue por outro meio (WeTransfer, pen drive).

## O que vai no pacote

| Pedido | Arquivo entregue |
|---|---|
| TIFF em resolução total | o TIFF da folha no QNAP, sem mudança |
| JPG na resolução original | o JPG corrigido na revisão (recorte/alinhamento), senão o JPG do QNAP, senão um JPG gerado do TIFF |
| JPG com 3000 px | o mesmo JPG, reduzido para 3000 px no lado maior |
| PDF | não sai pelo envio automático (fica de fora; mande à parte) |

Pedido de um projeto inteiro entrega todas as folhas do projeto, como no pacote de sempre. Os arquivos **não vão anexados**, porque um
TIFF tem centenas de MB. O TIFF sai direto do QNAP. Os JPG gerados ficam em `<pasta do banco>/entregas/<n>/`, e nada no QNAP é
alterado.

## O link de download

- Endereço: `https://painel.camp.arq.br/entrega/<código>` (a configuração `painel.url` mais `/entrega/`). É uma página simples, sem
  login, com um botão **Baixar** por arquivo.
- O código tem 43 caracteres aleatórios e só existe no e-mail: o banco guarda o hash (`entrega_link.token_hash`).
- O link vale `entrega.validade_dias` dias (padrão 14). Vencido ou cancelado, a página diz isso e não lista nada.
- A página e os arquivos não entram em cache nem em buscadores (`no-store`, `noindex`).
- A página só serve arquivos de dentro do QNAP ou das pastas do painel. Qualquer outro caminho dá 404, mesmo se alguém mexer no banco.
- Cada download é contado (`downloads`, `ultimo_download_em`).
- O código não aparece nos logs: o log técnico e o log de acesso do serviço mostram `/entrega/***`.

> **Cloudflare Access.** Se `painel.camp.arq.br` estiver atrás do Cloudflare Access (o login da Cloudflare antes do painel), a pessoa
> de fora não passa dele. No painel Zero Trust, crie uma aplicação para `painel.camp.arq.br/entrega/*` com a política **Bypass**
> (Everyone). O resto do painel continua protegido. Teste abrindo um link de entrega numa janela anônima.

## Configuração (Configurações → E-mail e avisos)

| Chave | O que é |
|---|---|
| `entrega.canal` | `sender` (padrão) ou `site`. Se o escolhido não estiver configurado, o painel usa o outro. |
| `entrega.validade_dias` | dias de validade do link (1 a 90; padrão 14) |
| `entrega.responder_para` | e-mail que recebe as respostas, no canal do site (vazio = `email_solicitacoes` do site) |
| `sender.token` | token da API do Sender.net (sensível: a tela só mostra se está preenchido) |
| `sender.campanha_entrega` | ID do e-mail transacional do Sender.net com o layout da entrega |

### Sender.net (canal padrão)

1. No Sender.net, crie um **e-mail transacional** (Transactional) a partir de um layout pronto da CAMP. Use as variáveis abaixo onde
   o texto deve entrar:

   | Variável | Conteúdo |
   |---|---|
   | `{{nome}}` | primeiro nome de quem pediu |
   | `{{nome_completo}}` | nome completo |
   | `{{link}}` | o link de download (use como endereço do botão "Baixar os arquivos") |
   | `{{validade}}` | até quando o link vale (dd/mm/aaaa) |
   | `{{pedido}}` | número do pedido no painel |
   | `{{quantidade}}` | quantos arquivos |
   | `{{lista}}` | um arquivo por linha: código · título (resolução) |
   | `{{mensagem}}` | o recado escrito na hora de enviar (pode vir vazio) |

   O assunto e o remetente são os do e-mail transacional no Sender.net.
2. Copie o **ID** desse e-mail (aba API do transacional) para `sender.campanha_entrega`.
3. Em Settings → **API access tokens**, gere um token e cole em `sender.token`.
4. Em um pedido qualquer, use **Enviar um teste para mim** e confira o e-mail.

Como o painel chama o Sender.net: `POST https://api.sender.net/v2/message/<sender.campanha_entrega>/send`, com
`Authorization: Bearer <sender.token>` e o corpo `{"to": {"email", "name"}, "variables": {…}}`. Uma resposta 4xx/5xx ou
`"success": false` conta como falha: o painel mostra a mensagem do Sender.net, sem o token, e não marca o pedido. Se o Sender.net
mudar o formato da API, o teste mostra o erro na hora.

### E-mail do site (alternativa)

Com `entrega.canal = site`, o painel pede ao site que mande o e-mail. A rota é
`POST /wp-json/camp/v1/painel/pedido/enviar`, do plugin `camp-acervo-auto-pages` 1.22.7 (contrato 1.4, `docs/CONTRATO_UNICO.md` §6).
O site usa `wp_mail`, que sai pelo plugin de SMTP ativo no site, o mesmo dos avisos de pedido novo. O e-mail é só texto, e as
respostas vão para `email_solicitacoes`. Com o id do pedido no site, ele fica marcado como atendido (`_camp_atendido_em`). A rota
aceita até 60 e-mails por hora. Para usar, basta a senha de aplicativo do site (`wp.app_password`), que o painel já tem.

## O que fica registrado

- `solicitacao.situacao = 'entregue'`, com `entregue_em` e o resumo em `entrega`. Exemplo: "2 arquivo(s), 410 MB · enviado por
  e-mail (Sender.net) para maria@… · link até 15/11/2026".
- `solicitacao_item.entregue = 1` só nos itens que foram no pacote.
- `entrega_link`: um registro por envio, com os arquivos, para quem foi, o canal, a validade, os downloads e o cancelamento.
- `evento`: `entregue_por_email`, `envio_teste` e `link_cancelado`, com quem fez, o canal e o número de arquivos.

## Arquivos

- Painel:
  - `backend/app/entrega.py` (regra);
  - `backend/app/rotas_pedidos.py` (`GET /api/solicitacoes/{id}/envio`, `POST …/enviar`, `POST …/cancelar-link`);
  - `backend/app/rotas_entrega.py` (página pública);
  - `backend/app/wp.py` (`enviar_email_pedido`);
  - `db/migrations/201_entrega_por_email.sql`;
  - tela em `frontend/index.html` (`envioHTML`, `linksEnvioHTML`).
- Site: `wp-content/plugins/camp-acervo-auto-pages/includes/class-painel-api.php` (`send_request_mail`), versão 1.22.7.
- Testes:
  - `tests/teste_backend.py` modo `entrega_por_email` (30 verificações, com Sender.net e site falsos);
  - `tests/navegador_entrega_email.js` (o clique de ponta a ponta com um Sender.net falso local:
    `CAMP_SENDER_URL=http://127.0.0.1:8898/v2 bash tests/rodar_um.sh tests/navegador_entrega_email.js`).
