# Pedidos de material vindos do site (contrato)

Dois contratos entre o painel e o site: a entrada automática de pedidos de material (abaixo) e o mapa de
redirecionamentos de códigos (no fim).

Cartão "Sobras" #12. O formulário de pedido de material do site (camp.arq.br) registra o pedido direto no painel, sem
ninguém precisar digitar de novo. O pedido aparece em **Pedidos de material**, na aba "Abertas", com origem "site", e o
admin recebe um e-mail (se `avisos.pedido_novo` = 1 e o SMTP estiver configurado).

O lado do site ainda **não** está ligado: este documento é o que a pessoa que fizer essa ligação precisa saber.

## Antes de ligar

1. No painel, em Configurações → "Site e sincronização", defina `pedidos.token` (é uma senha: use 32 letras/números
   aleatórios). Enquanto estiver vazio, a rota responde **503** e nada é gravado.
2. Guarde o mesmo valor no WordPress, **no servidor** (ex.: constante em `wp-config.php`). O token nunca pode ir para o
   navegador: a chamada é feita pelo PHP do site, depois que o formulário é enviado.

## Chamada

```
POST https://painel.camp.arq.br/api/pedidos/site
Content-Type: application/json
X-Camp-Token: <pedidos.token>
```

Corpo (JSON, no máximo 16 KB):

| campo         | obrigatório | regra                                                                                         |
|---------------|-------------|-----------------------------------------------------------------------------------------------|
| `nome`        | sim         | texto, 2 a 120 letras                                                                         |
| `email`       | sim         | endereço de e-mail válido, até 200 letras (a resposta da equipe vai para ele)                 |
| `instituicao` | não         | texto, até 200 letras                                                                         |
| `finalidade`  | sim         | um destes: `publicacao`, `pesquisa`, `editorial`, `familia`, `exposicao`, `outro`             |
| `mensagem`    | não*        | texto livre, até 2000 letras (quebras de linha são mantidas)                                  |
| `itens`       | não*        | lista com até 50 itens `{"codigo": "...", "formato": "..."}` (ou só o código, como texto)     |

\* É preciso mandar `itens` **ou** `mensagem` (pelo menos um).

Cada item:

- `codigo`: o código do projeto (`F026-P0001`, pede o projeto inteiro) ou da folha (`F026-P0001-1968-S01-D00003`).
- `formato` (padrão `jpg_3000`): `tif` (TIFF em resolução total), `jpg_3000` (JPG com 3000 px no lado maior),
  `jpg_original` (JPG na resolução original) ou `pdf`.

Itens repetidos (mesmo código e formato) contam uma vez. Campos a mais são ignorados. Caracteres de controle são tirados.

Exemplo:

```json
{
  "nome": "Marina Costa",
  "email": "marina.costa@usp.br",
  "instituicao": "FAU USP",
  "finalidade": "pesquisa",
  "mensagem": "Dissertação sobre o edifício.",
  "itens": [
    {"codigo": "F020-P0003", "formato": "jpg_3000"},
    {"codigo": "F020-P0003-1968-S01-D00002", "formato": "tif"}
  ]
}
```

## Respostas

As mensagens de erro vêm em português simples e podem ser mostradas a quem preencheu o formulário.

| HTTP | quando                                                        | corpo                                                       |
|------|---------------------------------------------------------------|-------------------------------------------------------------|
| 200  | pedido gravado                                                | `{"ok": true, "id": 123, "mensagem": "Pedido recebido. …"}` |
| 400  | campo faltando ou inválido; JSON quebrado                     | `{"erro": "O campo 'email' não parece um endereço de e-mail."}` |
| 401  | `X-Camp-Token` ausente ou diferente de `pedidos.token`        | `{"erro": "Token ausente ou inválido."}`                    |
| 413  | corpo maior que 16 KB                                         | `{"erro": "Pedido grande demais (máximo 16 KB)."}`          |
| 429  | mais de 60 pedidos aceitos na última hora (todas as origens)  | `{"erro": "Muitos pedidos na última hora. …"}`              |
| 503  | `pedidos.token` ainda vazio no painel                         | `{"erro": "O painel ainda não aceita pedidos do site …"}`   |

O site não deve repetir a chamada depois de um 200 (cada chamada cria um pedido). Em 5xx ou falha de rede, pode tentar
de novo uma vez; se falhar, mostre "tente mais tarde" ou mande o pedido por e-mail para a equipe.

## O que o painel faz com o pedido

- Grava em `solicitacao` (origem `site`, situação `aguarda_resposta`) e os itens em `solicitacao_item`.
- Registra no histórico do pedido ("criada", ator `site`).
- Manda o e-mail de aviso para `avisos.email` (depois de responder ao site; uma falha no e-mail não desfaz o pedido).
  Cada envio aparece em Máquinas e site → "Alertas por e-mail" → "Últimos envios".

## Redirecionamentos de códigos (para o 301)

Quando um admin muda o código de um projeto (cartão "Sobras" #9), o painel guarda o mapa antigo → novo. O site pode ler
`GET /api/redirecionamentos` (sem login; só códigos, nada além) e responder 301 do endereço antigo para o novo:

```json
{"total": 2, "itens": [
  {"antigo": "F014-P0004", "novo": "F014-P0009", "tipo": "projeto", "criado_em": "2026-10-13 12:00:00"},
  {"antigo": "F014-P0004-1960-S01-D00001", "novo": "F014-P0009-1960-S01-D00001", "tipo": "item", "criado_em": "2026-10-13 12:00:00"}
]}
```

Filtros opcionais: `?tipo=projeto` (ou `item`, `fundo`) e `?desde=2026-10-01` (só os criados a partir dessa data). Uma cadeia
(A → B e depois B → C) já vem resolvida: A aparece apontando para C. Se o código voltar a ser o original, o
redirecionamento dele some (nunca aponta para ele mesmo).

O mapa fica na tabela `redirecionamento` (`codigo_antigo`, `codigo_novo`, `entidade`, `motivo`, `criado_por`, `criado_em`,
`aplicado_no_site`). A coluna `aplicado_no_site` está prevista para o site marcar o que já virou 301; por enquanto o
painel só a zera quando o destino muda.

## O painel busca no site (CAMP-013)
Além de receber `POST /api/pedidos/site`, o painel **busca** no site a cada `site.coleta_pedidos_min` minutos (padrão 10; 0 desliga): `GET /wp-json/camp/v1/solicitacoes?marcar=1` com a Application Password. O que chega é guardado em `pedido_site` (chave = id do post no site, idempotente) e vira:
- `alta-resolucao` → pedido (origem `site`) com item pelo código, formato `tif`;
- `consulta` → pedido sem item (o código vai no texto: é visita aos originais, não arquivo);
- `correcao` → erro (origem `site`) ligado ao código da folha/projeto; sem código que o painel conheça, vira pedido comum para uma pessoa ver.
Falha do site fica em `pedido_site_coleta` (e no log) e nunca derruba o painel. `GET /api/pedidos/coleta` mostra a última volta; `POST /api/pedidos/coletar` (admin) busca agora.
