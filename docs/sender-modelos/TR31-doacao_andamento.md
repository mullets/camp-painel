# TR31 · Andamento da doação

**Situação:** Criar — sem ele a etapa muda, mas a pessoa não é avisada  
**Chave no sistema:** `doacao_andamento`

## Para que serve
Avisa quem apresentou um acervo que a **proposta de doação mudou de etapa**. Sai quando a equipe muda a etapa em **Doações de acervo** e deixa marcado **"Avisar a pessoa por e-mail"** (precisamos de mais informações, visita agendada, aprovada, não aprovada, acervo recebido, arquivada). Também sai sozinho quando o **pagamento da contribuição é confirmado** pelo Mercado Pago, se a configuração `doacao.avisar_pagamento` estiver ligada (vem ligada).
O contrato (TR30) e a cobrança (TR27) têm os e-mails deles: este não repete esses dois.

## Para quem vai
Quem apresentou o acervo.

## Assunto sugerido
`CAMP | Sua proposta de doação: {{etapa}}`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Helena |
| `{{acervo}}` | Arquiteto ou escritório do acervo | Fulano de Tal |
| `{{protocolo}}` | Referência | CAMP-2026-000990 |
| `{{etapa}}` | Nome da etapa nova | Visita agendada |
| `{{mensagem}}` | O texto da etapa (pronto, editável no painel) e, depois, a mensagem da equipe | Agendamos uma visita para conhecer o acervo… |
| `{{link}}` | Link útil (pode vir vazio) | https://camp.arq.br/… |

## Texto sugerido
```
Olá, {{nome}}.

Temos novidades sobre a proposta de doação do acervo {{acervo}}.

Etapa: {{etapa}}

{{mensagem}}

{{link}}

Qualquer dúvida, é só responder este e-mail.

Referência: {{protocolo}}
```

## Atenção
- Sem ID **não sai nada** (não há e-mail simples): a etapa muda do mesmo jeito e o painel avisa que falta o TR31.
- `{{mensagem}}` pode ter mais de um parágrafo; deixe-a **sozinha** no bloco dela.
- `{{link}}` pode vir vazio: deixe-o **sozinho na sua linha** (ou num botão que só apareça com link).
- Teste mandando para você mesmo antes do primeiro aviso de verdade.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base: logo da CAMP no topo, texto, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{mensagem}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **TR31** e clique em **Salvar**. A linha aparece depois da próxima atualização.
6. Teste: na mesma linha, **Enviar teste** antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").
