# TR25 · Mudança de categoria cancelada

**Situação:** Criar  
**Chave no sistema:** `amigo_categoria_cancelada`

## Para que serve
Confirma que o Amigo **cancelou** a mudança de categoria que tinha pedido.

## Para quem vai
O Amigo.

## Assunto sugerido
`CAMP | Mudança de categoria cancelada`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Marina |
| `{{categoria_atual}}` | Categoria que continua | Amigo |
| `{{data_efetivacao}}` | Data em que a mudança valeria | 18 de novembro de 2027 |
| `{{link}}` | Área do Amigo | https://camp.arq.br/amigos/conta/ |
| `{{protocolo}}` | Referência | CAMP-2026-000450 |

## Texto sugerido
```
Olá, {{nome}}.

Cancelamos o seu pedido de mudança de categoria, que passaria a valer em {{data_efetivacao}}.

Você continua na categoria {{categoria_atual}}.

Referência: {{protocolo}}
```

## Botão
Texto: **Ver minha área do Amigo** · Link: `{{link}}`

## Atenção
- Sem ID nada sai ao Amigo.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: Administração → **E-mails do site** → cole o ID na linha **TR25** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").
