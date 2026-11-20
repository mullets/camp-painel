# TR07 · Visita confirmada

**Situação:** Já existe — revisar  
**Chave no sistema:** `visita_confirmada`

## Para que serve
Avisa que a visita está **confirmada**. Sai quando a equipe clica em "Confirmar visita e avisar" no wp-admin.

## Para quem vai
Quem pediu a visita.

## Assunto sugerido
`CAMP | Sua visita está confirmada`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Ana |
| `{{local}}` | Casa | Residência João Marino |
| `{{data}}` | Data, por extenso | sexta-feira, 4 de dezembro de 2026 |
| `{{horario}}` | Horário | 10h |
| `{{grupo}}` | Tamanho do grupo | grupo de 12 pessoas |
| `{{protocolo}}` | Referência | CAMP-2026-0420 |

## Texto sugerido
```
Olá, {{nome}}.

Sua visita está confirmada.

Local: {{local}}
Data: {{data}}
Horário: {{horario}}
Participantes: {{grupo}}

Mudança de participantes, necessidade de acessibilidade ou de data: responda este e-mail antes da visita.

Referência: {{protocolo}}
```

## Atenção
- Nunca saiu até hoje. Revisar.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: Administração → **E-mails do site** → cole o ID na linha **TR07** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").

