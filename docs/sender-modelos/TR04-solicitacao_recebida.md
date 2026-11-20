# TR04 · Solicitação recebida

**Situação:** Já existe — revisar  
**Chave no sistema:** `solicitacao_recebida`

## Para que serve
Confirma que o pedido chegou. Sai quando alguém manda o **formulário de contato**, pede **material do acervo** ou faz pedido de **biblioteca / proposta cultural ou audiovisual**.

## Para quem vai
A pessoa que mandou o pedido.

## Assunto sugerido
`CAMP | Recebemos sua solicitação`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome da pessoa | Rafael |
| `{{protocolo}}` | Referência do pedido | CAMP-2026-0412 |

## Texto sugerido
```
Olá, {{nome}}.

Recebemos sua solicitação. A equipe da CAMP vai analisar e responder por este e-mail.

Guarde a referência do seu pedido: {{protocolo}}

Se quiser acrescentar algo, é só responder esta mensagem.
```

## Atenção
- Já mandou 2 e-mails. Funciona; só revisar o texto.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **TR04** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").

