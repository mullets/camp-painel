# TR29 · Ingresso da visita: link de pagamento

**Situação:** Criar  
**Chave no sistema:** `ingresso_cobranca`

## Para que serve
Leva de novo o **link de pagamento** de um ingresso da visita guiada à Residência João Marino que ainda não foi pago (reservado, recusado ou cancelado). Sai quando a equipe clica para reenviar o link na tela **Ingressos** do painel.

## Para quem vai
Quem reservou o ingresso.

## Assunto sugerido
`CAMP | Conclua o pagamento do seu ingresso`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Ana |
| `{{visita}}` | Nome da visita | Visita guiada à Residência João Marino (em português) |
| `{{data}}` | Dia e horário, por extenso | sábado, 6 de dezembro de 2026, às 10h |
| `{{quantidade}}` | Pessoas | 2 pessoas |
| `{{valor}}` | Total a pagar | R$ 180,00 |
| `{{link}}` | Pagamento no Mercado Pago | https://www.mercadopago.com.br/… |
| `{{validade}}` | Até quando o link vale | 4 de dezembro de 2026, às 23h59 |
| `{{protocolo}}` | Referência | CAMP-2026-000812 |

## Texto sugerido
```
Olá, {{nome}}.

Seu ingresso para a {{visita}} ainda não foi pago.

Quando: {{data}}
Pessoas: {{quantidade}}
Valor: {{valor}}

Use o botão abaixo para concluir o pagamento pelo Mercado Pago (Pix, cartão ou boleto). O link vale até {{validade}}; depois disso, a vaga pode voltar à venda.

Referência: {{protocolo}}
```

## Botão
Texto: **Pagar o ingresso** · Link: `{{link}}`

## Atenção
- Sem ID nada sai e o painel avisa que falta o TR29.
- O ingresso com QR code (TR23) só sai depois do pagamento confirmado.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: Administração → **E-mails do site** → cole o ID na linha **TR29** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").
