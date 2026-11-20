# TR26 · Renovação encerrada

**Situação:** Criar  
**Chave no sistema:** `amigo_nao_renovar`

## Para que serve
Confirma que o Amigo escolheu **não renovar** a anuidade, na área do Amigo. Os benefícios valem até o fim do período já pago.

## Para quem vai
O Amigo.

## Assunto sugerido
`CAMP | Renovação encerrada`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Marina |
| `{{categoria}}` | Categoria | Amigo |
| `{{validade}}` | Até quando valem os benefícios ("já encerrada" se já venceu) | 18 de novembro de 2027 |
| `{{link}}` | Área do Amigo (para voltar a renovar) | https://camp.arq.br/amigos/conta/ |
| `{{protocolo}}` | Referência | CAMP-2026-000450 |

## Texto sugerido
```
Olá, {{nome}}.

Registramos que você não quer renovar o Amigos da CAMP (categoria {{categoria}}).

Benefícios válidos até: {{validade}}

Obrigado por ter apoiado a preservação da arquitetura moderna paulista. Se mudar de ideia, é só voltar à sua área do Amigo.

Referência: {{protocolo}}
```

## Botão
Texto: **Voltar a renovar** · Link: `{{link}}`

## Atenção
- Sem ID nada sai ao Amigo.
- {{validade}} pode vir "já encerrada": deixe a linha "Benefícios válidos até" de modo que a frase funcione nos dois casos.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **TR26** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").
