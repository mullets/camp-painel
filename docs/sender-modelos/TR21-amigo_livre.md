# TR21 · Texto livre

**Situação:** Criar  
**Chave no sistema:** `amigo_livre`

## Para que serve
A equipe escreve assunto e texto no painel (ex.: convite para evento, aviso). O modelo é só a **moldura** com o layout da CAMP.

## Para quem vai
Amigos selecionados no painel.

## Assunto sugerido
`{{assunto}}`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Marina |
| `{{assunto}}` | Assunto escrito no painel | Convite: abertura da exposição |
| `{{texto}}` | Texto escrito no painel (vários parágrafos, com quebras de linha) | ... |
| `{{protocolo}}` | Referência | CAMP-2026-0450 |

## Texto sugerido
```
Olá, {{nome}}.

{{texto}}
```

## Atenção
- No campo de assunto do Sender, use {{assunto}}. Se o Sender não aceitar variável no assunto, use "CAMP | Mensagem para os Amigos da CAMP".

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **TR21** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").

