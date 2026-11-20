# TR10 · Pré-adesão (pagamento desligado)

**Situação:** Criar — prioridade baixa  
**Chave no sistema:** `amigo_pre_adesao`

## Para que serve
Confirma a adesão ao **Amigos da CAMP** quando o pagamento online está desligado; avisa que o link de pagamento vai depois.

## Para quem vai
Quem aderiu pelo site.

## Assunto sugerido
`CAMP | Recebemos sua adesão ao Amigos da CAMP`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Marina |
| `{{categoria}}` | Categoria escolhida | Amigo |
| `{{valor}}` | Valor | R$ 450,00 por ano |
| `{{protocolo}}` | Referência | CAMP-2026-0450 |

## Texto sugerido
```
Olá, {{nome}}.

Obrigado por querer ser Amigo da CAMP!

Categoria: {{categoria}}
Valor: {{valor}}

Em breve enviaremos o link para o pagamento.

Referência: {{protocolo}}
```

## Atenção
- Com o Mercado Pago ligado este quase não sai mais.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: Administração → **E-mails do site** → cole o ID na linha **TR10** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").

