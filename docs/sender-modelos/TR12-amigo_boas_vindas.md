# TR12 · Pagamento confirmado: boas-vindas

**Situação:** Criar — PRIORIDADE  
**Chave no sistema:** `amigo_boas_vindas`

## Para que serve
Dá as **boas-vindas** quando o pagamento é aprovado (Mercado Pago) ou registrado pela equipe no painel.

## Para quem vai
O novo Amigo.

## Assunto sugerido
`CAMP | Bem-vindo ao Amigos da CAMP`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Marina |
| `{{categoria}}` | Categoria | Amigo |
| `{{validade}}` | Até quando vale a anuidade | 18 de novembro de 2027 |
| `{{codigo}}` | Código de Amigo | AMG-0012 |
| `{{fundador}}` | Frase de Amigo Fundador (PODE VIR VAZIA) | Você é Amigo Fundador nº 12. |
| `{{protocolo}}` | Referência | CAMP-2026-0450 |
| `{{link}}` | Página do Amigos da CAMP | https://camp.arq.br/amigos/ |

## Texto sugerido
```
Olá, {{nome}}.

Seu pagamento foi confirmado. Bem-vindo ao Amigos da CAMP!

{{fundador}}

Categoria: {{categoria}}
Seu código: {{codigo}}
Válido até: {{validade}}

Obrigado por apoiar a preservação da arquitetura moderna paulista.

Referência: {{protocolo}}
```

## Botão
Texto: **Conhecer os benefícios** · Link: `{{link}}`

## Atenção
- {{fundador}} vem vazio para quem não está entre os 100 primeiros: deixe numa linha sozinha.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **TR12** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").

