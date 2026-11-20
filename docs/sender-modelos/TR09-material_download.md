# TR09 · Material disponível para download

**Situação:** Já existe — CONFERIR (parece quebrado)  
**Chave no sistema:** `material_download`

## Para que serve
Entrega o **material em alta resolução** pedido pelo público. Sai pelo **painel**, quando a equipe aprova o pedido e envia.

## Para quem vai
Quem pediu o material.

## Assunto sugerido
`CAMP | Seu material está disponível`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Carla |
| `{{link}}` | Link do arquivo .zip com tudo (OBRIGATÓRIO no botão) | https://... |
| `{{material}}` | Resumo do pacote | 12 arquivos em alta resolução — F009-P0018, F009-P0020 |
| `{{validade}}` | Até quando o link funciona, por extenso | até 2 de dezembro de 2026, às 18h |
| `{{protocolo}}` | Referência | CAMP-2026-0399 |
| `{{nome_completo}}` | Nome completo (opcional) | Carla Souza |
| `{{link_pagina}}` | Página do pedido (opcional) | https://... |
| `{{tamanho}}` | Tamanho do arquivo (opcional) | 1,2 GB |
| `{{quantidade}}` | Quantos arquivos (opcional) | 12 |
| `{{lista}}` | Lista dos arquivos (opcional) | ... |
| `{{mensagem}}` | Recado da equipe (opcional, pode vir vazio) | ... |
| `{{validade_curta}}` | Validade dd/mm/aaaa (opcional) | 02/12/2026 |
| `{{pedido}}` | Número do pedido (opcional) | 157 |

## Texto sugerido
```
Olá, {{nome}}.

Seu material está pronto: {{material}}.

{{mensagem}}

O link funciona {{validade}}. Depois disso, peça de novo.

Ao usar este material, cite a fonte: Acervo CAMP – Casa da Arquitetura Moderna Paulista.

Referência: {{protocolo}}
```

## Botão
Texto: **Baixar o material** · Link: `{{link}}`

## Atenção
- **Problema provável:** a miniatura está diferente das outras e os cliques aparecem como "Disabled" — sinal de que o e-mail não tem o botão/link. Sem `{{link}}` a pessoa não recebe o material.
- Nunca saiu até hoje (0 enviados).

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: Administração → **E-mails do site** → cole o ID na linha **TR09** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").

