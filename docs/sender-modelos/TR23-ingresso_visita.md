# TR23 · Ingresso da visita (Residência João Marino)

**Situação:** Criar  
**Chave no sistema:** `ingresso_visita`

## Para que serve
É o **ingresso** da visita guiada à Residência João Marino, com o QR code. Sai quando o pagamento do ingresso é confirmado ou quando a equipe clica em **Reenviar** na tela Ingressos do painel.

## Para quem vai
Quem comprou o ingresso.

## Assunto sugerido
`CAMP | Seu ingresso: visita à Residência João Marino`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Ana |
| `{{visita}}` | Nome da visita | Visita guiada à Residência João Marino (em português) |
| `{{data}}` | Dia e horário, por extenso | sábado, 6 de dezembro de 2026, às 10h |
| `{{quantidade}}` | Pessoas (e aviso de meia-entrada, se houver) | 2 pessoas (1 inteira e 1 meia) — na entrada, quem tem meia-entrada apresenta o documento |
| `{{codigo}}` | Código do ingresso | ING-7K2Q |
| `{{link}}` | Página do ingresso | https://camp.arq.br/ingresso/… |
| `{{qr}}` | ENDEREÇO da imagem do QR code (use como imagem, não como texto) | https://camp.arq.br/…/qr.png |
| `{{endereco}}` | Endereço da casa | Rua …, São Paulo |
| `{{protocolo}}` | Referência | CAMP-2026-000812 |

## Texto sugerido
```
Olá, {{nome}}.

Seu ingresso para a {{visita}} está confirmado.

Quando: {{data}}
Pessoas: {{quantidade}}
Onde: {{endereco}}
Código: {{codigo}}

Apresente o QR code abaixo na entrada (no celular ou impresso).
[imagem: {{qr}}]

Chegue com 10 minutos de antecedência. Para remarcar ou tirar dúvidas, responda a este e-mail.

Referência: {{protocolo}}
```

## Botão
Texto: **Abrir meu ingresso** · Link: `{{link}}`

## Atenção
- {{qr}} é o endereço de uma **imagem**: no editor do Sender, insira um bloco de imagem e use {{qr}} como endereço (240 × 240).
- Sem ID sai o ingresso em HTML simples do site, com o mesmo QR: ninguém fica sem ingresso.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: Administração → **E-mails do site** → cole o ID na linha **TR23** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").
