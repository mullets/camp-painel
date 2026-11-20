# TR18 · Lembrete de renovação (7 dias ou menos)

**Situação:** Criar — depois  
**Chave no sistema:** `amigo_lembrete_7`

## Para que serve
Lembrete quando faltam **7 dias ou menos**. Tom mais urgente.

## Para quem vai
Amigos com anuidade vencendo na semana.

## Assunto sugerido
`CAMP | Faltam {{dias}} dias para sua anuidade vencer`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Marina |
| `{{categoria}}` | Categoria | Amigo |
| `{{validade}}` | Data de vencimento | 25 de novembro de 2026 |
| `{{dias}}` | Quantos dias faltam | 7 |
| `{{valor}}` | Valor da renovação | R$ 450,00 |
| `{{link}}` | Renovar | https://... |
| `{{protocolo}}` | Referência | CAMP-2026-0450 |

## Texto sugerido
```
Olá, {{nome}}.

Faltam {{dias}} dias: sua anuidade do Amigos da CAMP ({{categoria}}) vence em {{validade}}.

Renove pelo botão abaixo ({{valor}}) para não perder os benefícios.

Referência: {{protocolo}}
```

## Botão
Texto: **Renovar agora** · Link: `{{link}}`

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **TR18** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").

