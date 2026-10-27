# Vocabulário único de publicação

Uma só linguagem em **todas** as telas, mensagens da API e documentos. Quem escrever texto novo deve seguir esta tabela.
`scripts/check_ui.py` falha (e portanto o `atualizar.sh` também) se uma frase antiga voltar.

## Estados (o que a coisa É)
| Valor interno (NÃO muda) | Rótulo | Chip (minúsculo) | O que significa |
|---|---|---|---|
| `nao_publicado` | Não publicado | `não publicado` | Existe só no painel; nunca foi ao site |
| `rascunho` | Rascunho | `rascunho` | Está no site, mas só quem está logado no WordPress vê |
| `no_ar` | Publicado | `publicado` | Público: qualquer visitante vê |
| `fora_do_ar` | Despublicado | `despublicado` | Retirado do público de propósito (privado no site); fundo exige motivo |

## Situação (onde o projeto ou o lote está no trabalho) — CAMP-146, decidido pelo Rafa em 22/10/2026
As MESMAS 5 em todo o painel: Fila, Projetos, página do projeto, Painel inicial e celular. Só o rótulo: a fase guardada
(`filas_fase.py`) e a API não mudam. Na tela vem sempre de `situacaoTag()` / `situacaoDe()` (`SITUACOES` no `index.html`).
| Fase interna (NÃO muda) | Situação | O que significa |
|---|---|---|
| `processando`, `importar` (e projeto sem folhas) | **Chegando** | o CAMP Vision está lendo, ou as folhas ainda não vieram para o painel |
| `conferir` | **Para conferir** | há folhas que ninguém conferiu |
| `aprovar`, `publicar` (e projeto com folhas fora do site) | **Pronto para publicar** | conferido; falta o clique de publicar |
| `publicado` (ou projeto público) | **No site** | qualquer visitante vê |
| `erro` (ou algo que trava o projeto inteiro) | **Com problema** | o CAMP Vision parou com erro, direitos com restrição registrada, projeto sem título ou bloqueio de pessoa |
- Ao lado da situação vem UMA frase do que falta ("3 folhas faltam conferir"). Nunca duas colunas dizendo a mesma coisa.
- O `check_ui` reprova as etiquetas antigas de situação (Em leitura, Na fila, Lendo, Importar folhas, Conferir N, Aprovar lote,
  Publicada, aguardando importação, em revisão, pronta para aprovar).
- "No site" é o nome da situação. O estado da folha/projeto no site (tabela acima) continua "publicado", "rascunho"…
- Direitos "não definida" NÃO impede publicar (padroes.md §12): a tela diz "não impede publicar; registre o termo quando tiver".
  O número "fundos travados por direitos" saiu do Painel inicial.

### Verificar destino (UX-01, 27/10/2026)
Lote que **chegou** (situação Chegando) cuja pasta não parece do projeto (nome × título abaixo de 50% ou pasta só com o código, ex. "P0001").
Não é uma 6ª situação: a situação continua **Chegando** e ao lado vem o chip `verificar destino` (âmbar) com a frase do porquê.
O botão é **Verificar destino** (no lugar de "Importar folhas"); as escolhas são **É deste projeto**, **Mover para F0xx-P000x (sugerido)**
e **Criar decisão**, sempre com justificativa (vai para o Histórico). "Importar todas" não importa esses lotes e diz quantos ficaram de fora.

## Menu (CAMP-154)
Os 5 destinos têm estes nomes em todo o painel (menu, trilha, aba do navegador, ajuda): **Precisa de você** (o Painel inicial),
**Projetos**, **Fundos e arquitetos**, **Pedidos do site** (antes "Pedidos de material") e **Máquinas** (antes "Máquinas e site"). O resto fica em **Mais**.

## Ações (o que o usuário FAZ)
| Botão | Efeito | Observação |
|---|---|---|
| **Publicar** | vai para `no_ar` | exige direitos autorizados, projeto autorizado e sem bloqueios |
| **Voltar para rascunho** | vai para `rascunho` | continua salvo para revisão; se estava publicado, exige admin master (tira do público, como despublicar) |
| **Despublicar** | vai para `fora_do_ar` | exige admin master quando já estava publicado; fundo pede o motivo |
| **Autorizar publicação** | marca o projeto como autorizado | não publica sozinho |

## Regras de texto
- Chips de estado em minúsculas; botões, filtros e títulos com inicial maiúscula.
- **Nunca** usar: "no ar", "fora do ar", "colocar no ar", "tirar do ar", "retirar da publicação", "não pública".
- **Nunca** mandar a pessoa ao WordPress ("wp-admin", "corrija no WordPress"): quem usa o painel não entra no site. A ação é um botão do painel; o que só se resolve no site é "avise quem cuida do site" (padroes.md §15).
- "Desativar/Reativar" é só para **contas de usuário** e **2FA**, nunca para conteúdo do acervo.
- Valores internos (`no_ar`, `fora_do_ar`, `tirar_do_ar` na API) ficam como estão por compatibilidade; só os rótulos mudam.
- Em português do Brasil, concordância normal: "projeto publicado", "folha publicada".

## Quem vê o quê (modo operador, 13/10/2026)
- Operador e leitura não veem nomes de sistema: nada de "Tainacan", "WordPress" ou "logado no WordPress" nos textos deles. Diga "o site", "a página pública", "só a equipe vê" (rascunho) e "retirado do público" (despublicado). O `check_ui` reprova "logado no WordPress".
- A tela "Máquinas e site" e o resumo de máquinas do topo são só para admin.
- Em texto novo, prefira "página pública" / "publicado" a "no site" quando falar do que o visitante vê (exceção: a situação **No site**, acima).

## Conferência (UX-10, 27/10/2026)
- **Tela cheia** / **Sair da tela cheia**: o botão (e a tecla F) da gaveta "Revisar folha". "Começar a conferir" já abre em tela cheia.
- **sugerido do projeto**: valor do projeto (ano, cidade, cliente) mostrado em cinza num campo vazio da folha. Não é dado lido nem
  confirmado; só vale se a pessoa aceitar (Tab) e salvar. Nunca chamar de "lido" ou "herdado" na tela.
- **Mais tipos**: onde ficam os tipos documentais além dos 4 mais usados no projeto.
- **Atalhos da conferência**: a lista que a tecla ? abre na revisão.
