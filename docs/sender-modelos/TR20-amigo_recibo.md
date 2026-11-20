# TR20 · Recibo simples

**Situação:** Criar  
**Chave no sistema:** `amigo_recibo`

## Para que serve
**Recibo** do pagamento da anuidade, enviado pela equipe no painel.

## Para quem vai
O Amigo que pagou.

## Assunto sugerido
`CAMP | Recibo da sua anuidade`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Marina |
| `{{nome_completo}}` | Nome completo (vai no recibo) | Marina Lopes |
| `{{valor_pago}}` | Valor pago | R$ 450,00 |
| `{{pago_em}}` | Data do pagamento | 18 de novembro de 2026 |
| `{{meio}}` | Forma de pagamento | Pix |
| `{{categoria}}` | Categoria | Amigo |
| `{{validade}}` | Válido até | 18 de novembro de 2027 |
| `{{protocolo}}` | Referência | CAMP-2026-0450 |

## Texto sugerido
```
Olá, {{nome}}.

Recebemos seu pagamento. Obrigado!

Recebemos de {{nome_completo}} o valor de {{valor_pago}}, em {{pago_em}}, por {{meio}}, referente à anuidade do Amigos da CAMP, categoria {{categoria}}, válida até {{validade}}.

Referência: {{protocolo}}

Este recibo não substitui documento fiscal.
```

## Atenção
- A frase "Este recibo não substitui documento fiscal" deve ficar (pode ser revista com a contabilidade).

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **TR20** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").

