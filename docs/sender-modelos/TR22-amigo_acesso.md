# TR22 · Link de acesso à área do Amigo

**Situação:** Criar — PRIORIDADE (sem ele a área do Amigo não abre)  
**Chave no sistema:** `amigo_acesso`

## Para que serve
Leva o **link de entrada** da área do Amigo. Sai quando o Amigo pede para entrar em `/amigos/entrar/` (digita o e-mail) ou quando a equipe manda o acesso pelo painel. O link vale uma vez só, por pouco tempo.

## Para quem vai
O Amigo (o e-mail cadastrado).

## Assunto sugerido
`CAMP | Seu link de acesso à área do Amigo`

## Variáveis
| Variável | O que é | Exemplo |
|---|---|---|
| `{{nome}}` | Primeiro nome | Marina |
| `{{link}}` | Link de entrada (uso único) | https://camp.arq.br/amigos/entrar/?t=… |
| `{{validade_link}}` | Por quanto tempo o link vale | 30 minutos |
| `{{protocolo}}` | Referência do Amigo | CAMP-2026-000450 |

## Texto sugerido
```
Olá, {{nome}}.

Use o botão abaixo para entrar na sua área do Amigo da CAMP.

O link vale por {{validade_link}} e só pode ser usado uma vez. Se ele expirar, peça outro na página de entrada.

Se você não pediu este acesso, pode ignorar este e-mail: ninguém entra sem o link.

Referência: {{protocolo}}
```

## Botão
Texto: **Entrar na área do Amigo** · Link: `{{link}}`

## Atenção
- **Sem este modelo o login não abre**: a página de entrada avisa que o acesso não saiu.
- Não ponha o link escrito no texto além do botão (evita que fique em encaminhamentos).
- Não mostre dados do Amigo além do primeiro nome.

## Como cadastrar

1. No Sender: **Transactional emails → New email**. Dê o nome exatamente como no título deste arquivo.
2. Use o layout do **TR08 · Inscrição recebida** como base (é o que está funcionando): logo da CAMP no topo, texto, botão laranja, rodapé com endereço e "responda este e-mail se tiver dúvida".
3. Escreva as variáveis **exatamente** como na tabela, com chaves duplas: `{{nome}}`. Letras minúsculas, sem espaço, sem acento.
4. Salve e copie o **ID** do e-mail (o código curto que o Sender mostra, como `egx4Z6`).
5. No **painel da CAMP**: menu **E-mails** → aba **Modelos do Sender** → cole o ID na linha **TR22** e clique em **Salvar**.
6. Teste: na mesma linha, **Enviar teste** (vai para o seu e-mail, com valores de exemplo) antes de usar com o público.

## Regras gerais
- Remetente: o da CAMP já usado nos outros transacionais. Responder para: contato@camp.arq.br (ou o e-mail da equipe definido no painel).
- Variável que pode vir vazia deve ficar **sozinha numa linha**, para não sobrar frase pela metade.
- Não escreva valores, datas ou nomes fixos no texto: use sempre a variável.
- Tom: cordial, direto, primeira pessoa do plural ("nós, da CAMP").
