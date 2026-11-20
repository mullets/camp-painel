# TR08 · Inscrição recebida

**Situação:** Já existe — funciona, revisar texto  
**Chave no sistema:** `inscricao_recebida`

## Para que serve
Confirma a **inscrição** em curso, oficina ou na **Residência**.

## Para quem vai
Quem se inscreveu.

## Assunto sugerido
`CAMP | Sua inscrição foi recebida`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Bruno |
| `{{curso}}` | Nome do curso | Preservação de slides |
| `{{protocolo}}` | Referência | CAMP-2026-0431 |
| `{{link}}` | Página do curso (pode vir vazio) | https://camp.arq.br/cursos/... |
| `{{inicio}}` | Início (só Residência; pode vir vazio) | 2 de março de 2027 |
| `{{dias}}` | Dias e horário (pode vir vazio) | terças, 19h–21h |
| `{{carga}}` | Duração (pode vir vazio) | 8 semanas |
| `{{vagas}}` | Vagas (pode vir vazio) | 20 vagas |
| `{{formato}}` | Formato (pode vir vazio) | presencial |
| `{{conteudo}}` | O que se aprende (pode vir vazio) | ... |
| `{{prazo}}` | Prazo das inscrições (pode vir vazio) | até 15 de fevereiro |

## Texto sugerido
```
Olá, {{nome}}.

Recebemos sua inscrição em {{curso}}.

{{inicio}}
{{dias}}
{{carga}}
{{formato}}

Vamos confirmar sua vaga por e-mail.

Referência: {{protocolo}}
```

## Botão
Texto: **Ver o curso** · Link: `{{link}}`

## Atenção
- É o modelo de referência: 11 enviados, 82% de abertura.
- Os campos da Residência vêm vazios nos outros cursos: cada um numa linha própria, ou use rótulos dentro da própria variável.
- O botão só faz sentido quando houver {{link}}; se o Sender permitir, esconda o botão quando vazio.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: Administração → **E-mails do site** → cole o ID na linha **TR08** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").

