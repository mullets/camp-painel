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
As cinco primeiras sempre vêm preenchidas. As outras (desde 20/11/2026) trazem **tudo o que a pessoa preencheu** e podem vir vazias: deixe cada uma **sozinha na sua linha**.

| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Helena |
| `{{acervo}}` | Arquiteto, escritório ou pessoa a quem o acervo pertenceu | Fulano de Tal |
| `{{protocolo}}` | Referência | CAMP-2026-000990 |
| `{{quantidade}}` | Faixa estimada (não é contagem) | De 51 a 500 itens |
| `{{fotos}}` | Fotos gerais enviadas (só a quantidade; as fotos não vão no e-mail) | 3 foto(s) |
| `{{nome_completo}}` | Nome completo | Helena Souza Prado |
| `{{email}}` | E-mail informado | helena@exemplo.com |
| `{{telefone}}` | Telefone / WhatsApp | (11) 98888-7777 |
| `{{relacao}}` | Relação com o acervo | Sou familiar ou herdeiro(a) |
| `{{descricao}}` | O que há no acervo (texto da pessoa) | Cerca de 40 rolos de plantas e 6 caixas |
| `{{tipos}}` | Tipos de material | Plantas, desenhos e croquis; Fotografias, slides ou negativos |
| `{{periodo}}` | Período dos documentos | 1960–1990 |
| `{{conservacao}}` | Conservação | Regular |
| `{{local}}` | Onde está guardado (cidade/UF) | Campinas/SP |
| `{{fotos_link}}` | Link das fotos (se mandou link) | https://drive.google.com/… |
| `{{direitos}}` | O que sabe dos direitos autorais | Sou herdeiro(a), mas os direitos precisam ser confirmados |
| `{{novidades}}` | Quer receber novidades da CAMP | sim |
| `{{endereco}}` | Endereço da pessoa (desde o site 1.35.0) | Rua das Flores, 100, apto 4 — Centro — Campinas/SP — CEP 13010-001 |
| `{{documento_mascarado}}` | CPF ou CNPJ **mascarado** (o número inteiro nunca vai no e-mail) | \*\*\*.456.789-\*\* |
| `{{valor_proposto}}` | Valor da contribuição escolhido no formulário | R$ 2.500,00 (ou "A combinar com a equipe") |

## Texto sugerido
```
Olá, {{nome}}.

Recebemos sua apresentação do acervo relacionado a {{acervo}}. Obrigado pelo contato e pela confiança na CAMP.

Nossa equipe vai avaliar as informações. Você não precisa fazer inventário nem contar os documentos agora.

O que você nos enviou:
Nome: {{nome_completo}}
E-mail: {{email}}
Telefone / WhatsApp: {{telefone}}
Relação com o acervo: {{relacao}}
Arquiteto, escritório ou pessoa: {{acervo}}
O que há no acervo:
{{descricao}}
Tipos de material: {{tipos}}
Quantidade estimada: {{quantidade}}
Período: {{periodo}}
Conservação: {{conservacao}}
Onde está guardado: {{local}}
Fotos gerais: {{fotos}}
Link das fotos: {{fotos_link}}
Direitos autorais: {{direitos}}
Quer receber novidades da CAMP: {{novidades}}
CPF ou CNPJ: {{documento_mascarado}}
Endereço: {{endereco}}
Valor da contribuição de preservação: {{valor_proposto}}

Este envio não formaliza uma doação nem autoriza publicação ou transferência de direitos. Se houver interesse de ambas as partes, entraremos em contato.

Referência: {{protocolo}}
```

## Atenção
- Sem ID sai o e-mail simples do site, com o mesmo conteúdo e o mesmo resumo ("O que você nos enviou", sem as linhas vazias).
- As fotos nunca vão anexadas: só a quantidade.
- O CPF/CNPJ nunca vai inteiro: só `{{documento_mascarado}}`. Nada é cobrado com este e-mail (a cobrança só vai junto com o contrato).

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
