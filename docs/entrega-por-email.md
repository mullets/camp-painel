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

- O link principal do e-mail baixa **tudo num só .zip**: `https://painel.camp.arq.br/entrega/<código>/tudo.zip`. Num pedido de
  projeto inteiro, é o projeto todo, com uma pasta por projeto dentro do zip (`F001-P0001/F001-P0001-1965-S01-D00001.tif`).
  - O zip é montado na hora, aos pedaços, sem cópia em disco.
  - É sem compressão, porque TIFF e JPG já são comprimidos; isso deixa o download começar na hora.
  - Funciona acima de 4 GB (ZIP64).
- O e-mail também leva a página `https://painel.camp.arq.br/entrega/<código>` (a configuração `painel.url` mais `/entrega/`). É uma
  página simples, sem login, com **Baixar tudo (.zip)** e um botão **Baixar** por arquivo, para quem preferir arquivo por arquivo.
- O link é **temporário**: vale `entrega.validade_dias` dias e pode ser cancelado a qualquer momento. Ele para às **23h59 (horário de
  São Paulo)** do último dia: pedido aprovado em 01/11 com 14 dias vale até "15 de novembro de 2026, às 23h59". O texto do e-mail sai
  do mesmo valor gravado (`entrega_link.expira_em`, em UTC), então a data do e-mail é o minuto exato em que o link para.
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
| `sender.campanha_entrega` | ID do e-mail transacional do Sender.net com o layout da entrega (desde 01/11/2026: o TR09, `bov4VK`, preenchido pela migração 202 só se estava vazio) |
| `sender.tr04_…` a `sender.tr09_…` | IDs dos 6 e-mails transacionais da CAMP no Sender.net (ver abaixo) |
| `sender.site_ativo` | `1` = o site manda os e-mails dele pelo Sender.net; `0` (padrão) = o site continua com o e-mail de sempre |

### Sender.net (canal padrão)

1. No Sender.net, crie um **e-mail transacional** (Transactional) a partir de um layout pronto da CAMP. Use as variáveis abaixo onde
   o texto deve entrar:

   | Variável | Conteúdo |
   |---|---|
   | `{{nome}}` | primeiro nome de quem pediu |
   | `{{nome_completo}}` | nome completo |
   | `{{link}}` | o link do .zip com tudo (use como endereço do botão "Baixar os arquivos") |
   | `{{link_pagina}}` | a página para baixar arquivo por arquivo |
   | `{{tamanho}}` | tamanho total do pacote (ex.: "410 MB") |
   | `{{validade}}` | até quando o link vale, por extenso: "15 de novembro de 2026, às 23h59" (horário de São Paulo; o minuto em que o link para) |
   | `{{validade_curta}}` | a mesma data em dd/mm/aaaa (era o `{{validade}}` até 01/11/2026) |
   | `{{material}}` | resumo curto do pacote (até 160 caracteres): "12 arquivos em alta resolução — F009-P0018, F009-P0020" |
   | `{{protocolo}}` | protocolo do pedido: `CAMP-<ano>-<id do pedido no site, 6 dígitos>` (o mesmo do e-mail "pedido recebido" do site); pedido só do painel: `CAMP-<ano>-P<id no painel, 6 dígitos>` |
   | `{{pedido}}` | número do pedido no painel |
   | `{{quantidade}}` | quantos arquivos |
   | `{{lista}}` | um arquivo por linha: código · título (resolução) |
   | `{{mensagem}}` | o recado escrito na hora de enviar (pode vir vazio) |

   O assunto e o remetente são os do e-mail transacional no Sender.net.
2. Copie o **ID** desse e-mail (aba API do transacional) para `sender.campanha_entrega`.
3. Em Settings → **API access tokens**, gere um token e cole em `sender.token`.
4. Em um pedido qualquer, use **Enviar um teste para mim** e confira o e-mail.

Como o painel chama o Sender.net: `POST https://api.sender.net/v2/message/<sender.campanha_entrega>/send`, com
`Authorization: Bearer <sender.token>` e o corpo `{"to": {"email", "name"}, "variables": {…}, "headers": {"X-CAMP-Protocolo": "<protocolo>"}}`. Uma resposta 4xx/5xx ou
`"success": false` conta como falha: o painel mostra a mensagem do Sender.net, sem o token, e não marca o pedido. Se o Sender.net
mudar o formato da API, o teste mostra o erro na hora.

### Os 6 e-mails transacionais da CAMP (Sender.net, 01/11/2026)

| Chave | ID | E-mail | Variáveis | Quem manda |
|---|---|---|---|---|
| `sender.tr04_solicitacao_recebida` | `egx4Z6` | pedido recebido | nome, protocolo | site |
| `sender.tr05_pdf_disponivel` | `ejv4Z5` | PDF disponível | nome, projeto, protocolo, link | site |
| `sender.tr06_visita_solicitada` | `bkw48X` | visita solicitada | nome, local, data, grupo, protocolo | site |
| `sender.tr07_visita_confirmada` | `elv4x6` | visita confirmada | nome, local, data, horario, grupo, protocolo | site |
| `sender.tr08_inscricao_recebida` | `bm24O0` | inscrição recebida | nome, curso, protocolo | site |
| `sender.tr09_material_download` | `bov4VK` | material para download | nome, material, protocolo, validade, link | painel (esta entrega) |

As chaves das variáveis são exatamente essas (minúsculas, sem acento). Datas por extenso, horário de São Paulo.

**Configuração enviada ao site.** Os IDs, o token (`sender.token`) e `sender.site_ativo` ficam no painel. Em Configurações → E-mail e
avisos, o botão **Enviar a configuração do Sender ao site** manda tudo ao site (`POST /wp-json/camp/v1/painel/sender`, contrato 1.5,
`docs/CONTRATO_UNICO.md` §6) e mostra o que o site ficou usando: Sender.net ligado ou desligado, token preenchido ou não, quantos
e-mails. O token nunca aparece na tela, na resposta nem no histórico. Token vazio no painel não é enviado: o site mantém o dele. O site só
usa o Sender.net com `sender.site_ativo = 1`, o token e o ID do e-mail preenchidos; senão continua com o e-mail de sempre. Site antigo
(sem a rota) responde 404: a tela diz "atualize o site" e nada muda. Rotas: `POST /api/configuracoes/sender/enviar-ao-site` e
`GET /api/configuracoes/sender/site` (admin).

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
  - `db/migrations/201_entrega_por_email.sql` e `202_sender_transacional.sql`;
  - `backend/app/wp.py` (`sincronizar_sender`) e `backend/app/rotas_admin.py` (`/api/configuracoes/sender/…`);
  - tela em `frontend/index.html` (`envioHTML`, `linksEnvioHTML`).
- Site: `wp-content/plugins/camp-acervo-auto-pages/includes/class-painel-api.php` (`send_request_mail`), versão 1.22.7.
- Testes:
  - `tests/teste_backend.py` modo `entrega_por_email` (30 verificações, com Sender.net e site falsos) e modo `sender_transacional`
    (migração 202, variáveis do TR09, configuração enviada ao site falso, 404 do site antigo);
  - `tests/navegador_entrega_email.js` (o clique de ponta a ponta com um Sender.net falso local:
    `CAMP_SENDER_URL=http://127.0.0.1:8898/v2 bash tests/rodar_um.sh tests/navegador_entrega_email.js`).

## Termo de uso antes do download (02/11/2026)

Pedido do Rafael: "na hora que ele receba o email com o link para download, ele tenha que dar OK no termo de uso … dando o aceite aí sim
abre o download".

- O link do e-mail (`{{link}}`) abre a página `/entrega/<código>` com o **termo de uso**. Ali não há botão de download.
- O termo diz que:
  - o uso é **só não comercial**;
  - o uso comercial depende de autorização por escrito e custa **R$ 150,00 por folha** (configuração `entrega.preco_comercial_folha`);
  - o crédito é obrigatório;
  - vale a Lei de Direitos Autorais (Lei nº 9.610/1998);
  - o uso em desacordo sujeita o responsável às sanções civis e penais.
- O texto padrão está em `entrega.TERMO_PADRAO`. Para mudar, escreva o termo inteiro em **Configurações → `entrega.termo`**; `{preco}` vira o
  valor por folha. **Peça a revisão do texto a quem cuida da parte jurídica da CAMP.**
- Para baixar, a pessoa escreve o **nome completo**, marca **Li e aceito** (a declaração de uso não comercial) e clica em
  **Aceitar e baixar**. Só então a página mostra **Baixar tudo (.zip)** e os arquivos um a um.
- Sem aceite, o `.zip` volta para o termo, e cada arquivo responde 403.
- O aceite fica guardado como prova em `entrega_link`: `aceite_em`, `aceite_nome`, `aceite_ip` e `aceite_termo`, o texto exato
  aceito, porque o termo pode mudar depois. Também gera o evento `termo_aceito`. Só o primeiro aceite conta.
- O pedido mostra a coluna **Termo de uso** nos links enviados: aceito por quem e quando.
- Para o layout do Sender.net (TR09), há a variável nova `{{preco_comercial}}` ("150,00"). O botão do e-mail deve usar `{{link}}`.

## Tudo no próprio pedido (02/11/2026)

- O pedido já abre com **Enviar o material**: o material pedido, os arquivos achados, o recado e **Aprovar e enviar**. Não é mais
  preciso clicar em "Ver o que entregar".
- O material pode ser editado ali mesmo: o formato (TIFF, JPG original, JPG 3000 px, PDF), **tirar**, **incluir código** e
  **trocar pelo projeto inteiro**, para mandar o projeto todo no .zip quando o site pediu uma folha. A rota é
  `PUT /api/solicitacoes/{id}/material`, só antes de entregar.
- O recado do e-mail já vem com as **condições de uso** gravadas no pedido.
- Em **Mais opções** ficam a lista com os caminhos no QNAP (CSV), **Já entreguei por outro meio** e o texto do e-mail do site.

## Aviso da situação da inscrição em curso (02/11/2026)

Pedido do Rafael: "quando coloco uma pessoa que se inscreveu no nosso painel, e mudo o status dela, devia mandar um e-mail para ela
avisando que status está".

- Em **Inscrições**, ao trocar a situação de uma **inscrição** para **em análise**, **selecionada** ou **não selecionada**, aparecem:
  - **Avisar por e-mail**, já marcado;
  - um **recado** opcional;
  - o texto do e-mail.
- **Salvar** muda a situação e manda o e-mail. A tela diz para quem foi ou por que não foi; a situação muda de qualquer jeito.
- Não manda e-mail para **desistiu**, para o "Avise-me" (interesse), nem quando só a nota mudou.
- **Canal:**
  - o e-mail transacional **TR10** do Sender.net, em `sender.tr10_inscricao_situacao`, com as variáveis `{{nome}}`,
    `{{nome_completo}}`, `{{curso}}`, `{{turma}}`, `{{situacao}}` ("Em análise", "Selecionada", "Não selecionada"),
    `{{situacao_codigo}}`, `{{texto}}` (o parágrafo padrão de cada situação) e `{{mensagem}}` (o recado);
  - sem TR10, sai pelo **e-mail do site**, só texto.
- Fica registrado no histórico como `aviso_situacao` ou `aviso_situacao_falhou`, com a situação, o canal e o erro.
- Código: `backend/app/inscricoes_aviso.py` e `PATCH /api/inscricoes/{id}` (`avisar`, `mensagem`); a prévia está em
  `GET /api/inscricoes/{id}/aviso?situacao=`. Migração 206.
