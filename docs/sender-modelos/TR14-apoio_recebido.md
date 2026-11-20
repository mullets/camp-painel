# TR14 · Proposta de adoção ou patrocínio recebida

**Situação:** Criar  
**Chave no sistema:** `apoio_recebido`

## Para que serve
Confirma o envio dos formulários **Adote um projeto** ou **Adote um arquiteto**.

## Para quem vai
Quem mandou a proposta.

## Assunto sugerido
`CAMP | Recebemos sua proposta`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Paulo |
| `{{frente}}` | Qual programa | Adote um projeto |
| `{{protocolo}}` | Referência | CAMP-2026-0460 |

## Texto sugerido
```
Olá, {{nome}}.

Recebemos seu interesse em {{frente}}. Muito obrigado!

A equipe da CAMP vai entrar em contato para conversar sobre a proposta.

Referência: {{protocolo}}
```

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **TR14** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").

