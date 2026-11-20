# TR27 · Cobrança avulsa

**Situação:** Criar — PRIORIDADE (sem ele o painel não manda a cobrança)  
**Chave no sistema:** `cobranca_avulsa`

## Para que serve
Leva o **link de pagamento** de uma cobrança avulsa criada no painel (tela Cobranças avulsas): contribuição de doação de acervo, patrocínio, serviço…

## Para quem vai
A pessoa cobrada.

## Assunto sugerido
`CAMP | Pagamento: {{descricao}}`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Paulo |
| `{{valor}}` | Valor | R$ 2.000,00 |
| `{{descricao}}` | O que está sendo cobrado | Contribuição para a doação do acervo Fulano |
| `{{finalidade}}` | Finalidade | Doação de acervo |
| `{{vence}}` | Prazo para pagar | 10 de dezembro de 2026 |
| `{{link}}` | Pagamento no Mercado Pago | https://www.mercadopago.com.br/… |
| `{{protocolo}}` | Referência | CAMP-2026-P000031 |

## Texto sugerido
```
Olá, {{nome}}.

Segue o link para o pagamento combinado com a CAMP.

{{descricao}}
Valor: {{valor}}
Pagar até: {{vence}}

O pagamento é pelo Mercado Pago (Pix, cartão ou boleto), na conta da CAMP.

Referência: {{protocolo}}
```

## Botão
Texto: **Pagar agora** · Link: `{{link}}`

## Atenção
- Sem ID o painel não manda nada e avisa que falta o TR27.
- Teste mandando para você mesmo antes da primeira cobrança de verdade.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: Administração → **E-mails do site** → cole o ID na linha **TR27** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").
