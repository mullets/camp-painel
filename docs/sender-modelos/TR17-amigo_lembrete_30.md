# TR17 · Lembrete de renovação (mais de 7 dias)

**Situação:** Criar — depois  
**Chave no sistema:** `amigo_lembrete_30`

## Para que serve
Lembrete de renovação quando faltam **mais de 7 dias** (normalmente 30) para vencer. O envio automático vem desligado no painel.

## Para quem vai
Amigos com anuidade perto de vencer.

## Assunto sugerido
`CAMP | Sua anuidade vence em {{dias}} dias`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Marina |
| `{{categoria}}` | Categoria | Amigo |
| `{{validade}}` | Data de vencimento | 18 de dezembro de 2026 |
| `{{dias}}` | Quantos dias faltam | 30 |
| `{{valor}}` | Valor da renovação | R$ 450,00 |
| `{{link}}` | Renovar | https://... |
| `{{protocolo}}` | Referência | CAMP-2026-0450 |

## Texto sugerido
```
Olá, {{nome}}.

Sua anuidade do Amigos da CAMP ({{categoria}}) vence em {{validade}} (faltam {{dias}} dias).

Para continuar apoiando, renove pelo botão abaixo ({{valor}}).

Referência: {{protocolo}}
```

## Botão
Texto: **Renovar** · Link: `{{link}}`

## Atenção
- Se o Sender não aceitar variável no assunto, use "CAMP | Sua anuidade vai vencer".

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **TR17** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").

