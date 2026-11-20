# TR13 · Pagamento recusado

**Situação:** Criar — PRIORIDADE  
**Chave no sistema:** `amigo_recusado`

## Para que serve
Avisa que o **Mercado Pago recusou** o pagamento e dá o link para tentar de novo.

## Para quem vai
Quem tentou pagar.

## Assunto sugerido
`CAMP | Seu pagamento não foi aprovado`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Marina |
| `{{categoria}}` | Categoria | Amigo |
| `{{link}}` | Tentar o pagamento de novo | https://www.mercadopago.com.br/... |
| `{{protocolo}}` | Referência | CAMP-2026-0450 |

## Texto sugerido
```
Olá, {{nome}}.

O pagamento da sua adesão ({{categoria}}) não foi aprovado pela operadora. Isso acontece, por exemplo, com limite ou dados do cartão.

Você pode tentar de novo, com a mesma ou outra forma de pagamento.

Referência: {{protocolo}}
```

## Botão
Texto: **Tentar de novo** · Link: `{{link}}`

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **TR13** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").

