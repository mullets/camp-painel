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

### Verificar destino pelo painel (UX-43, 27/10/2026)
Quadro em Material novo e linha em cada lote em "Verificar destino". Modos (admin): **Desligado**, **Simular** (padrão: "o painel mostra o que faria e não
muda nada") e **Aplicar sozinho**. Em cada lote: **O painel faria: mover para F0xx-P0yyy “Título”** / **criar F0xx-P0yyy “Título”** / **deixar para uma
pessoa: <motivo>**. O botão do admin é **Aplicar estas N decisões**. Depois de aplicado, o lote fica com o chip `movendo` e a frase
"movendo para F0xx-P0yyy (“Título”): o CAMP Vision vai reorganizar a pasta"; quando o material chega lá, `concluído`. **O que o painel fez (N)** lista as
decisões com **Desfazer**; **Projetos criados pelo painel (N)** lista os projetos novos com `revise o título` / `título revisado`. No Histórico, o autor é
"O painel (automático)".

### Possível duplicata de projeto (UX-29, 27/10/2026)
Ao digitar o nome em **Novo projeto** ou **Editar**: "Já existe projeto parecido neste fundo" / "Com este nome, fica parecido com", cada um com
**Abrir este** (e, ao editar, **Não é duplicata**). Em Problemas, o quadro **Possíveis projetos duplicados (N)**. "Não é duplicata" vale para o
par (não volta); juntar dois projetos continua sendo **Mesclar**, no projeto.

### Lotes do mesmo projeto (UX-04, 27/10/2026)
- **Identificador do lote**: o que distingue um lote dos outros do mesmo projeto, sempre abaixo do título (Precisa de você, Material novo,
  página do projeto): **complemento de 19/10** (material novo que chegou a um projeto com lote fechado) ou **lote de 14/10** (a data em que chegou).
  A contagem ao lado é a das folhas REAIS do lote ("12 folhas"); o nome do lote não leva mais "(N folhas)".
- **N lotes prontos**: lotes do mesmo projeto prontos para publicar ficam numa linha só, com o botão **Publicar projeto** (publicar é do projeto:
  o mesmo clique leva os lotes juntos).
- No **Hoje**, a mesma ação da mesma pessoa no mesmo projeto em até 10 min é UMA frase, com **(2×)** quando ela repetiu de verdade.

### Estados travados e idade do lote (UX-09, 27/10/2026)
- **Leitura interrompida**: lote em "sendo lido" (situação Chegando) há mais de 2 h sem o CAMP Vision dizer, no sinal dele, que lê este projeto.
  Não é uma 6ª situação: é o chip `leitura interrompida` (vermelho) ao lado de **Chegando**. O botão é **Ler de novo** (1 clique: o mesmo pedido de
  releitura do projeto; clicar de novo não cria outro). Depois do clique a linha diz **releitura pedida agora** e o botão vira **Ver na Fila**. Se nada mudar, **Dispensar este lote** (UX-39) tira o lote das listas para todos.
  28/10: pedido parado há mais de 2 h → o botão volta como **Pedir de novo** (o pedido velho fica "Sem resposta do CAMP Vision: substituído por um
  pedido novo"). Depois que uma releitura termina, a linha diz "**A última releitura terminou (…)**" ou "**A última releitura falhou (…)**". O aviso do clique
  acrescenta "**Atenção: o CAMP Vision não consulta os pedidos há N min: ele pode estar parado.**" (ou "nunca consultou") quando for o caso.
- **parado há 16 dias** / **parado há 5 h**: tempo do lote na MESMA etapa (não "esperando há", que media a última leitura da pasta).
  Em Material novo a coluna se chama **Parado há** e o clique no título ordena pelo mais parado; na Home, **mais parado primeiro**.

### Clique duplo em Publicar e Importar (UX-17, 27/10/2026)
- Enquanto trabalha, o botão fica apagado e diz **Publicando…** / **Importando…** (o andamento aparece no próprio bloco).
- Antes do clique, o Próximo passo diz o que muda: "ao publicar, **N folhas ficam públicas na hora** (M vão ao site agora)". Depois:
  **Publicado ✓ · N folhas públicas** com **Desfazer** (volta para rascunho; o mesmo de antes, CAMP-148).
- O segundo clique não repete a ação: com a publicação rodando, a tela acompanha a mesma; logo depois de publicar, sem folha nova,
  "Este projeto acabou de ser publicado: **nada foi feito de novo**". Importar o mesmo lote ao mesmo tempo: "Este lote **já está sendo importado** agora".

### Projeto publicado e em dia (UX-36, 27/10/2026)
- Lote aprovado com o projeto **publicado** e as folhas que vão ao site já lá (retida e duplicata não contam) está na situação **No site**,
  não em **Pronto para publicar** (Fila, Projetos, chip do projeto e Próximo passo).
- No Próximo passo do projeto publicado: **Atualizar no site** só aparece quando há o que enviar, e diz o que muda antes do clique
  ("No site · ao atualizar, **N folhas ficam públicas** e **M correções vão ao site**"). Em dia, a frase é "**Painel e site iguais**" e o
  botão azul é a 1ª pendência de "O que falta para fechar este projeto"; sem pendência, "**✔ Projeto fechado:** painel e site iguais" e
  nenhum botão azul.
- Uma informação uma vez só (UX-36, visual): publicado, o chip **No site** fica no cabeçalho da página e o bloco Próximo passo não o repete;
  o "Projeto fechado" é dito no próprio Próximo passo (sem faixa verde separada), com os **avisos menores** ao lado da contagem das folhas.

## Menu (UX-28; antes CAMP-154)
Os itens do menu têm estes nomes em todo o painel (menu, título da página, trilha, aba do navegador, ajuda), em grupos na ordem do trabalho:
topo **Precisa de você** (o Painel inicial), **Material novo**, **Problemas**, **Decisões**, **Projetos**, **Busca**; **Acervo** (**Fundos**, **Arquitetos**, …);
**Público** (**Pedidos de alta resolução**, antes "Pedidos do site" e "Pedidos de material"; **Downloads**, antes "Downloads do site");
**Acompanhamento**; **Administração** (**Máquinas**, antes "Máquinas e site"; **Configurações**); **Ajuda**. O resto fica em **Mais**.
"Fundos e arquitetos" deixou de existir: são dois itens, cada um com a sua página.
**Recolher menu** / **Expandir menu** (UX-28): o botão "‹" no topo do menu e as teclas `[` ou `⌘/Ctrl+B`. Recolhido, o menu é uma barra
estreita só com ícones; o nome do item, o número e a tecla aparecem na dica ao passar o mouse ou focar. Não usar "barra lateral".

## Avisos (UX-22)
- Todo aviso rápido (toast) some sozinho em no máximo 8 s; o aviso de tarefa concluída no topo some em 8 s quando deu certo
  (o que falhou fica até a pessoa fechar). Tudo fica em **Tarefas e avisos recentes** (menu do avatar), com a seção
  **Avisos desta sessão**.
- Número que ainda está carregando aparece como esqueleto (barra cinza animada), nunca como "0".
- Cartão de tarefa (27/10): título ("⏳ Publicando F009-P0092"), depois "**começou 15:08 · Rafael**" (o NOME cadastrado, nunca o
  e-mail; só a hora quando é hoje, "26/10, 15:08" de outro dia), a etapa atual numa linha própria em destaque ("**Publicando** · 23 s até
  agora") e a lista de passos com a hora ("15:08 · Projeto liberado para publicação"), sem repetir a etapa atual.
- A sincronização automática com o site é do painel ("O painel (automático)"): não aparece em "Suas tarefas" nem no chip do topo.
  Em Máquinas → Catálogo local × site: "**conferindo agora**" enquanto roda e, com intervalo abaixo de 60 min, "A conferência completa
  leva vários minutos: recomendado a cada 60 min (ajuste o intervalo da sincronização automática em Configurações)."

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
| **Dispensar este lote** (UX-35, UX-39) | só em lote parado com erro do CAMP Vision ou com a **Leitura interrompida** (UX-39: o "Ler de novo" já foi pedido e nada muda), operador ou acima: o lote sai das listas e das contagens **para todos** (Material novo, Precisa de você, menu, alertas por e-mail). Nada é apagado nem muda no QNAP; volta sozinho se o CAMP Vision ler a pasta de novo e o resultado mudar (na leitura interrompida: se o lote sair de "sendo lido" ou recomeçar a etapa). Em Material novo é secundário, depois de "Tentar de novo" ou "Ler de novo". No Ignorar ▾ aparece como **Dispensar este lote (para todos)**. Desfazer por 8 s |
| **dispensado** / **Voltar a mostrar** (UX-35, UX-39) | o lote dispensado continua em Material novo › Todas com o chip "dispensado"; "Voltar a mostrar" desfaz a dispensa (fica no Histórico como "lote parado dispensado") |

## Etiquetas e lugar físico (UX-25)
| Termo | Onde | O que significa |
|---|---|---|
| **Etiquetar e guardar** | Próximo passo do projeto aprovado ou publicado | abre Etiquetas já preenchida, com o passo "Onde guardar" |
| **Onde guardar** / **Guardar nesta caixa** | Etiquetas, aba Pasta de projeto | põe numa caixa só as folhas do projeto que ainda não têm lugar |
| **Impressas** / **Reimprimir** | Etiquetas | histórico do que saiu no Imprimir; reimprimir volta a etiqueta como saiu |
| **Imprimir** (formatos NIIMBOT, UX-42) | Etiquetas | como nas outras impressoras: abre a janela de impressão, onde se escolhe a NIIMBOT da rede. Não usar mais "Imprimir na NIIMBOT", "Procurando a NIIMBOT", "NIIMBOT não encontrada" |
| **Baixar imagens** | Etiquetas, formatos NIIMBOT | opção secundária: uma imagem por etiqueta |
| **sem lugar** | Painel inicial, Onde está guardado | folha sem caixa, gaveta, tubo, mapoteca ou estante cadastrada |

### Página do arquiteto incompleta (UX-38, 27/10/2026)
- Quadro **Página do arquiteto no site** (fundo e arquiteto): faltando biografia, fonte da biografia ou retrato, a ação principal é
  **Completar os dados do arquiteto** (abre a edição do arquiteto com os campos que faltam destacados e o cursor no primeiro).
  **Publicar a página do arquiteto** continua permitido, mas não é o botão azul. Sem arquiteto, a ação é **Vincular arquiteto**.
- Frase do que falta: "Falta para a página ficar boa: datas de nascimento e morte, biografia, fonte da biografia, retrato." (UX-41: as datas entram) Fundo sem projeto publicado: "Este fundo
  ainda não tem projeto publicado: mesmo publicada, a página só aparece no site com o primeiro projeto publicado (e é publicada junto com ele)."
- Na edição do arquiteto, o bloco **O que falta para a página no site** (cada item leva ao campo) e **Voltar ao fundo F0xx**.
  UX-41: as **datas de nascimento e morte** (escritório/família: **datas de início e fim**) também vão à página do arquiteto no site
  (lá: Nascimento, Falecimento ou Período de atuação); não se diz mais "fica só no painel; o site não recebe".
- O site sem a página do arquiteto: nunca "espere um minuto". O erro diz o que houve ("O fundo não chegou ao site…" ou "O site tem o fundo,
  mas não criou a página deste arquiteto… o site cria as páginas que faltam uma vez por hora") e vem com os botões que resolvem
  (**Completar os dados do arquiteto**, **Ver os projetos**, **Vincular arquiteto**).

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
- Coluna da esquerda: **O que fazer agora**, **O caminho do material** e **Ritmo das últimas 2 semanas**.
- Coluna da direita, completa: **Está tudo funcionando?**, **Hoje** e, abaixo, **Qualidade da base**, **Melhorias de hoje**,
  **Quanto do acervo já está no site** e (admin) **Visitas ao site**. Tudo sempre aberto: nada de bloco recolhido.
  Pedido do Rafael em 27/10/2026 ("eu gostava dessa barra completa"): desfaz o bloco recolhido **Números do acervo** do UX-30.
- **Visitas ao site** com o Google Analytics desligado mostra **desligado** na Home sem perguntar ao Google (UX-12) e também aparece em
  **Configurações** (com "Ver como ligar").
- **N folhas publicadas sem lugar** (UX-25) fica no fim de **O que fazer agora**, porque pede uma ação (guardar).
- Fila de outro papel: aparece esmaecida e no fim, com "você acompanha; quem faz é um admin". Nunca se esconde o que a pessoa pode ver.
- O número de decisões só aparece com decisão pendente (nunca "0 decisões").

## Máquinas em abas (UX-24, 27/10/2026)
- Abas **Agora** · **Alertas** · **Logs**. "Agora" é o que o operador vê (Preservação, "Como está agora" e o caminho do material);
  "Alertas" (admin) e "Logs" (admin/master) somem para o operador, e o servidor recusa esses dados a ele (403).
- O que está desligado fora do horário de trabalho fica recolhido em "**N desligadas (normal)**".
- Nenhuma frase manda editar chave: o resumo do dia é o interruptor "**Mandar todo dia às 18h um e-mail com o resumo do dia**"
  e o campo "Quem recebe o resumo"; o e-mail diz "desligue o Resumo do dia em Máquinas → Alertas".

## Correções esperando o site (UX-40, 27/10/2026)
- Em Máquinas → **Catálogo local × site**, ao lado de "**N escritas pendentes**": "**N correções de folhas esperando o site**" e o botão
  (só admin/master) "**Enviar as N agora**" ("Enviar a correção agora" com uma; "Enviar 50 das N agora" acima de 50, o teto da rodada).
  Confirmação: "Manda agora ao site as N correções que estão esperando. Uma rodada só; o reenvio automático continua desligado."
- Resultado: "**Enviadas** · **falharam** · **ainda na fila**", com cada folha que falhou e o motivo. Folha que falhou "**espera a próxima
  tentativa**" (não sai de novo no clique seguinte). "**Nada a enviar**: o painel não vê diferença desta folha para o site."
- "Escritas pendentes" conta toda gravação no site que falhou (fundo, projeto, arquiteto, folha). UX-47 (28/10/2026): o botão manda as
  correções de folhas e também as escritas pendentes de fundos, projetos e arquitetos (criar o fundo ou o dossiê sem duplicar, nome,
  "Sobre o acervo", dados e capa do projeto, página do arquiteto), sempre com o valor de agora no painel. A contagem diz
  "**N correções de folhas e N escritas de fundos, projetos e arquitetos esperando o site**" (só a parte que existe).
  Publicar ou tirar do ar (situação do fundo, página do arquiteto) não entra: isso continua sendo pedido na tela.
  Dossiê que o site já tinha: no Histórico, "**página do projeto que já estava no site ligada (sem criar outra)**".
- No andamento, a escrita que esbarrou no site lento: "**o site não respondeu a tempo, continua na fila**" (não conta como falha;
  entra em "ainda na fila"). Recusa do site (4xx) conta em "falharam" e espera a próxima tentativa.
- Ao lado de **Sincronizar agora**: "Só lê o site e atualiza as diferenças: não envia nada."
- No Histórico de ações: "{quem} mandou ao site as correções e escritas que estavam esperando" · "N enviadas, N falharam, N ainda na fila".

## Publicação paciente com o site lento (27/10/2026)
- No acompanhamento da publicação: "**Folha X: o site demorou (…). Tentando de novo em N s (tentativa 2 de 3)**"; quando o painel
  passa a mandar menos folhas juntas: "**O site está lento: enviando N de cada vez**"; quando volta: "**O site voltou a responder bem:
  enviando N de cada vez**". Folha que não subiu nem na 3ª: "**NÃO subiu (depois de 3 tentativas)**".
- No resultado: "**N folha(s) precisaram de nova tentativa (o site demorou)**". Falha de vez: "(o site não respondeu em 3 tentativas)" e
  "o próximo Publicar envia só as que faltam, sem duplicar as já enviadas".

## Publicação sem duplicar (27/10/2026)
- Uma folha com erro não para a publicação: as demais seguem e o resultado diz "**N folha(s) enviada(s), N com erro**" (com a primeira
  folha e o erro) e "**As enviadas foram publicadas.**". Durante: "Enviadas N folha(s); faltam N. N com erro até agora."
- Em Divergências com o site: "**Item duplicado no site ao publicar**" (o painel ligou a folha no item mais antigo, ou no publicado, e
  não criou outro; "mande os itens que sobraram para a lixeira no site") e "**Folha com mais de um item no site**" (achado na sincronização).

## Recorte automático das imagens públicas (UX-44, 27/10/2026)
- Só a imagem que vai ao site (até 1.920 px) e o "**Ver como vai ao site**" são recortados na borda do papel e clareados (branco e contraste
  pelo papel). O TIF e a prévia do CAMP Vision não mudam. O recorte feito à mão ("Recortar e alinhar") sempre vence.
- Na conferência, sobre a prévia: o retângulo tracejado e o selo **recorte automático** (com "o tracejado é o que vai ao site; o original
  não muda") ou **recorte automático incerto** (com o motivo: "Vai inteira ao site; se precisar, use “Recortar e alinhar” (K).").
- Botões: **Usar recorte inteiro (sem recorte)** e, depois dele, **Usar recorte automático**; o selo da escolha é
  **sem recorte (escolhido na conferência)**.
- Rotina de admin: **Reprocessar imagens públicas com recorte automático** (simula por padrão; só reenvia confirmando "REPROCESSAR").
