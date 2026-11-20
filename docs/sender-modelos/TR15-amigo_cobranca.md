# TR15 · Cobrança

**Situação:** Criar — PRIORIDADE  
**Chave no sistema:** `amigo_cobranca`

## Para que serve
Sai quando a equipe clica em **Enviar cobrança** no painel (uma pessoa ou várias). Leva o link do Mercado Pago no valor da categoria; se o Mercado Pago estiver desligado, leva as instruções de Pix.

## Para quem vai
Amigos selecionados no painel.

## Assunto sugerido
`CAMP | Sua anuidade do Amigos da CAMP`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Marina |
| `{{categoria}}` | Categoria | Guardião |
| `{{valor}}` | Valor | R$ 1.500,00 |
| `{{vence}}` | Prazo para pagar | 30 de novembro de 2026 |
| `{{pagamento}}` | Frase pronta sobre como pagar | Pague pelo link abaixo: Pix, cartão ou boleto. |
| `{{link}}` | Pagamento no Mercado Pago (PODE VIR VAZIO quando for Pix) | https://www.mercadopago.com.br/... |
| `{{pix}}` | Instruções de Pix (PODE VIR VAZIO quando houver link) | Chave Pix: ... |
| `{{protocolo}}` | Referência | CAMP-2026-0450 |

## Texto sugerido
```
Olá, {{nome}}.

Segue a cobrança da sua anuidade do Amigos da CAMP.

Categoria: {{categoria}}
Valor: {{valor}}
Pagar até: {{vence}}

{{pagamento}}

{{pix}}

Referência: {{protocolo}}
```

## Botão
Texto: **Pagar agora** · Link: `{{link}}`

## Atenção
- {{link}} e {{pix}} se alternam: um deles vem vazio. Deixe cada um sozinho numa linha; se o Sender permitir, esconda o botão quando {{link}} estiver vazio.
- É o e-mail da cobrança geral: teste mandando para você mesmo antes de enviar para todos.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **TR15** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").

