# TR24 · Mudança de categoria registrada

**Situação:** Criar  
**Chave no sistema:** `amigo_categoria_pedida`

## Para que serve
Confirma que o Amigo pediu **mudança de categoria** na área do Amigo. A nova categoria vale a partir da data de efetivação (na renovação).

## Para quem vai
O Amigo.

## Assunto sugerido
`CAMP | Mudança de categoria registrada`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Marina |
| `{{categoria_atual}}` | Categoria de hoje | Amigo |
| `{{categoria_nova}}` | Categoria pedida | Guardião |
| `{{valor_novo}}` | Valor da nova categoria | R$ 1.500,00 por ano |
| `{{data_efetivacao}}` | Quando passa a valer | 18 de novembro de 2027 |
| `{{link}}` | Área do Amigo | https://camp.arq.br/amigos/conta/ |
| `{{protocolo}}` | Referência | CAMP-2026-000450 |

## Texto sugerido
```
Olá, {{nome}}.

Registramos o seu pedido de mudança de categoria.

Categoria de hoje: {{categoria_atual}}
Nova categoria: {{categoria_nova}}
Novo valor: {{valor_novo}}
Passa a valer em: {{data_efetivacao}}

Até lá, seus benefícios continuam os da categoria de hoje. Para cancelar o pedido, use a sua área do Amigo.

Referência: {{protocolo}}
```

## Botão
Texto: **Ver minha área do Amigo** · Link: `{{link}}`

## Atenção
- Sem ID nada sai ao Amigo (o pedido fica registrado do mesmo jeito).

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: Administração → **E-mails do site** → cole o ID na linha **TR24** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").
