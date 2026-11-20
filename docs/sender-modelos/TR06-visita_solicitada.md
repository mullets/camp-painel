# TR06 · Visita solicitada

**Situação:** Já existe — revisar  
**Chave no sistema:** `visita_solicitada`

## Para que serve
Confirma que o pedido de **visita** ou **atividade educativa** a uma das casas chegou. A data ainda não está confirmada.

## Para quem vai
Quem pediu a visita.

## Assunto sugerido
`CAMP | Recebemos seu pedido de visita`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Ana |
| `{{local}}` | Casa pretendida | Residência João Marino |
| `{{data}}` | Data pedida, por extenso (ou "A combinar") | sexta-feira, 4 de dezembro de 2026 |
| `{{grupo}}` | Tamanho do grupo | grupo de 12 pessoas |
| `{{protocolo}}` | Referência | CAMP-2026-0420 |

## Texto sugerido
```
Olá, {{nome}}.

Recebemos seu pedido de visita.

Local: {{local}}
Data pedida: {{data}}
Participantes: {{grupo}}

Vamos confirmar a data e o horário por e-mail. A visita só está garantida depois da nossa confirmação.

Referência: {{protocolo}}
```

## Atenção
- Nunca saiu até hoje. Revisar antes do primeiro pedido.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: Administração → **E-mails do site** → cole o ID na linha **TR06** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").

