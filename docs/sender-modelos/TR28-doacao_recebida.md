# TR28 · Intenção de doação de acervo recebida

**Situação:** Criar  
**Chave no sistema:** `doacao_recebida`

## Para que serve
Confirma que a **intenção de doação de acervo** chegou (formulário `/intencao-de-doacao-de-acervo/`). Não formaliza doação nem autoriza publicação.

## Para quem vai
Quem apresentou o acervo.

## Assunto sugerido
`CAMP | Recebemos sua intenção de doação de acervo`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Helena |
| `{{acervo}}` | Arquiteto ou escritório do acervo | Fulano de Tal |
| `{{protocolo}}` | Referência | CAMP-2026-000990 |
| `{{quantidade}}` | Faixa estimada de documentos | de 100 a 500 documentos |
| `{{fotos}}` | Fotos gerais enviadas | 3 foto(s) |

## Texto sugerido
```
Olá, {{nome}}.

Recebemos sua apresentação do acervo relacionado a {{acervo}}. Obrigado pelo contato e pela confiança na CAMP.

Quantidade estimada: {{quantidade}}
Fotos gerais: {{fotos}}

Nossa equipe vai avaliar as informações. Você não precisa fazer inventário nem contar os documentos agora.

Este envio não formaliza uma doação nem autoriza publicação ou transferência de direitos. Se houver interesse de ambas as partes, entraremos em contato.

Referência: {{protocolo}}
```

## Atenção
- Sem ID sai o e-mail simples do site, com o mesmo conteúdo.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **TR28** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").
