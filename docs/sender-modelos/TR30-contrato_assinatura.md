# TR30 · Contrato para assinatura

**Situação:** Criar — PRIORIDADE (sem ele o painel não manda o contrato)  
**Chave no sistema:** `contrato_assinatura`

## Para que serve
Leva o **link do contrato para assinar** (Clicksign, D4Sign, gov.br, DocuSign…). Sai pelo botão **"Enviar contrato para assinatura"** em **Doações de acervo**, ou numa **Cobrança avulsa** que tenha link de contrato.
A cobrança do Mercado Pago, quando houver, vai em **outro e-mail**, separado (TR27). Por isso este e-mail **não** tem link de pagamento.

## Para quem vai
A pessoa que vai assinar (doador ou responsável pelo acervo).

## Assunto sugerido
`CAMP | Contrato para assinatura`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Paulo |
| `{{link_contrato}}` | Link para assinar o contrato | https://app.clicksign.com/… |
| `{{valor}}` | Valor combinado (pode vir vazio) | R$ 2.000,00 |
| `{{prazo}}` | Prazo para assinar (pode vir vazio) | 10 de dezembro de 2026 |
| `{{protocolo}}` | Referência | CAMP-2026-D000012 |

## Texto sugerido
```
Olá, {{nome}}.

Obrigado por confiar o seu acervo à CAMP.

Segue o link para ler e assinar o contrato combinado com a gente.
A assinatura é digital e leva poucos minutos.

Valor combinado: {{valor}}
Assinar até: {{prazo}}

Se houver cobrança, ela chega em outro e-mail, com o link de pagamento do Mercado Pago.

Qualquer dúvida, é só responder este e-mail.

Referência: {{protocolo}}
```

## Botão
Texto: **Assinar o contrato** · Link: `{{link_contrato}}`

## Atenção
- Sem ID o painel não manda nada (nem o contrato, nem a cobrança) e avisa que falta o TR30.
- `{{valor}}` e `{{prazo}}` podem vir vazios: deixe cada um **sozinho na sua linha**.
- Teste mandando para você mesmo antes do primeiro contrato de verdade.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base: logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{link_contrato}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **TR30** e clique em **Salvar**. A linha aparece depois da próxima atualização.
6. Teste: na mesma linha, **Enviar teste** antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").
