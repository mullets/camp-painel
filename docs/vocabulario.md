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

### Possível duplicata de projeto (UX-29, 27/10/2026)
Ao digitar o nome em **Novo projeto** ou **Editar**: "Já existe projeto parecido neste fundo" / "Com este nome, fica parecido com", cada um com
**Abrir este** (e, ao editar, **Não é duplicata**). Em Problemas, o quadro **Possíveis projetos duplicados (N)**. "Não é duplicata" vale para o
par (não volta); juntar dois projetos continua sendo **Mesclar**, no projeto.

## Menu (CAMP-154)
Os 5 destinos têm estes nomes em todo o painel (menu, trilha, aba do navegador, ajuda): **Precisa de você** (o Painel inicial),
**Projetos**, **Fundos e arquitetos**, **Pedidos do site** (antes "Pedidos de material") e **Máquinas** (antes "Máquinas e site"). O resto fica em **Mais**.

## Avisos (UX-22)
- Todo aviso rápido (toast) some sozinho em no máximo 8 s; o aviso de tarefa concluída no topo some em 8 s quando deu certo
  (o que falhou fica até a pessoa fechar). Tudo fica em **Tarefas e avisos recentes** (menu do avatar), com a seção
  **Avisos desta sessão**.
- Número que ainda está carregando aparece como esqueleto (barra cinza animada), nunca como "0".

## Ações (o que o usuário FAZ)
| Botão | Efeito | Observação |
|---|---|---|
| **Publicar** | vai para `no_ar` | exige direitos autorizados, projeto autorizado e sem bloqueios |
| **Voltar para rascunho** | vai para `rascunho` | continua salvo para revisão; se estava publicado, exige admin master (tira do público, como despublicar) |
| **Despublicar** | vai para `fora_do_ar` | exige admin master quando já estava publicado; fundo pede o motivo |
| **Autorizar publicação** | marca o projeto como autorizado | não publica sozinho |
| **Ler de novo esta pasta** | pede ao CAMP Vision a releitura da pasta do lote (UX-08) | é o botão principal de um lote parado com erro; antes de confirmar mostra o que muda e o que fica |
| **Tentar de novo** (lote parado) | devolve a pasta ao CAMP Vision como está, sem releitura | secundário; o tooltip diz: use só quando o erro foi passageiro |

## Ignorar um item (UX-03, 27/10/2026)
| Texto | Efeito |
|---|---|
| **Ignorar ▾** | menu em todo item do Precisa de você (quem só lê não vê) |
| **Agora não · esconder por 7 dias** | some só para quem clicou e volta sozinho na data do tooltip; Desfazer por 8 s |
| **Não mostrar mais (não era problema)** | só em problema: fecha como "Não era problema" com autor, data e justificativa (obrigatória se bloqueia) |
| **Ignorados (n)** | seção recolhida em Problemas: os escondidos por você ("Mostrar de novo") e os fechados pelo Ignorar ("Reabrir") |

## Etiquetas e lugar físico (UX-25)
| Termo | Onde | O que significa |
|---|---|---|
| **Etiquetar e guardar** | Próximo passo do projeto aprovado ou publicado | abre Etiquetas já preenchida, com o passo "Onde guardar" |
| **Onde guardar** / **Guardar nesta caixa** | Etiquetas, aba Pasta de projeto | põe numa caixa só as folhas do projeto que ainda não têm lugar |
| **Impressas** / **Reimprimir** | Etiquetas | histórico do que saiu no Imprimir; reimprimir volta a etiqueta como saiu |
| **sem lugar** | Painel inicial, Onde está guardado | folha sem caixa, gaveta, tubo, mapoteca ou estante cadastrada |

## Regras de texto
- Erro do CAMP Vision: primeiro o que aconteceu em linguagem de gente ("4 imagens têm o nome do autor longo demais no EXIF; ele foi cortado. Não impede publicar."), depois o que fazer; a mensagem técnica fica em **Ver detalhes técnicos** (fechado). UX-08.
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

## Título de projeto que é nome de pasta (UX-15)
- **Nome de pasta do sistema**: título que é nome de pasta ou código ("01 - Arquivo Arquivístico (TIFF)", "T099_Casa", "F000 - …", "Casa P0012",
  "Projeto Não Identificado 3"). Regra única em `similaridade.titulo_tecnico`: criar, importar planilha e editar recusam; **Publicar** bloqueia.
- **Título sugerido**: o título sem o prefixo de pasta. Botão **Usar o título sugerido** (uma pessoa aceita, um projeto por vez; nada é renomeado sozinho)
  e **Corrigir o título** (abre a edição).
- Cidade: a tela sugere a **forma do acervo** (a mais usada: "São Paulo, SP" × "São Paulo") com o botão **Usar**; o campo continua texto livre.

## Números e estado do topo (UX-05, 27/10/2026)
- Todo número de contagem vem de `backend/app/contagens.py` (a mesma regra em Home, Material novo, Máquinas, Relatórios e menu).
  Ao lado dele: "atualizado agora" / "atualizado há X" (nunca a hora solta).
- O topo diz "**N de M estações ligadas**" (só as de captura; o CAMP Vision e o QNAP têm a sua frase) e o pior estado:
  "QNAP ok" · "QNAP em atenção" · "QNAP quase cheio" · "QNAP desconectado"; "site ok" · "site lento" · "site não respondeu uma vez" · "site sem resposta".
- Em Material novo o filtro "Chegando" conta o mesmo que o resumo ("N chegando"): o CAMP Vision lendo + folhas que faltam importar.
- Alertas (UX-07): cada assunto mostra **normal**, **atenção**, **crítico** ou **não medido** (minúsculas, como chip). "Não medido" só
  quando a medição falhou ou não existe, e sempre com o porquê na frase ("Não medido: o endereço do site não está configurado…").
- Preservação (UX-02): o bloco do topo de Máquinas diz quantas cópias as imagens têm, em frase simples: "Suas imagens têm duas cópias"
  (verde), "A segunda cópia das imagens está atrasada" (âmbar), "Suas imagens têm só uma cópia" (vermelho). Chip: "duas cópias" ·
  "cópia atrasada" · "só uma cópia". Espaço: "enche em ~N dias" (menos de 30 = atenção; menos de 10 = crítico).

## Home: o que fica na frente (UX-18/21/30, 27/10/2026)
- Na frente da Home (**Precisa de você**) só ficam **O que fazer agora** (com **O caminho do material**), **Está tudo funcionando?** e **Hoje**.
- **Números do acervo**: bloco recolhido no fim da Home com Qualidade da base, Ritmo das últimas 2 semanas, Quanto do acervo já está no site,
  Melhorias de hoje e, com o Google Analytics ligado, Visitas ao site. Abre num clique e fica lembrado neste navegador.
- **Visitas ao site** com o Google Analytics desligado mora em **Configurações** (com "Ver como ligar"), não na Home.
- Fila de outro papel: aparece esmaecida e no fim, com "você acompanha; quem faz é um admin". Nunca se esconde o que a pessoa pode ver.
- O número de decisões só aparece com decisão pendente (nunca "0 decisões").

## Máquinas em abas (UX-24, 27/10/2026)
- Abas **Agora** · **Alertas** · **Logs**. "Agora" é o que o operador vê (Preservação, "Como está agora" e o caminho do material);
  "Alertas" (admin) e "Logs" (admin/master) somem para o operador, e o servidor recusa esses dados a ele (403).
- O que está desligado fora do horário de trabalho fica recolhido em "**N desligadas (normal)**".
- Nenhuma frase manda editar chave: o resumo do dia é o interruptor "**Mandar todo dia às 18h um e-mail com o resumo do dia**"
  e o campo "Quem recebe o resumo"; o e-mail diz "desligue o Resumo do dia em Máquinas → Alertas".
