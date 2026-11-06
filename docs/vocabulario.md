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

## Menu (redesenho §3, 04/11/2026; UX-28; antes CAMP-154)
**Grupos (redesenho §3; o 1º grupo passou de "Principal" a **Visão geral** no redesenho de Material novo §3, 04/11/2026):** **Visão geral** · **Acervo** · **Público e processos** · **Administração** · **Ajuda** ("Público" e "Acompanhamento" deixaram de ser
grupos: Visitas ao site e Relatórios estão em Público e processos; Histórico de ações e Qualidade do CAMP Vision em Administração). No celular:
**Abrir menu** / **Fechar menu** (o botão ☰ do cabeçalho). Os nomes abaixo continuam.
Os itens do menu têm estes nomes em todo o painel (menu, título da página, trilha, aba do navegador, ajuda), em grupos na ordem do trabalho:
topo **Precisa de você** (o Painel inicial), **Material novo**, **Problemas**, **Decisões**, **Projetos**, **Busca**; **Acervo** (**Fundos**, **Arquitetos**, …);
**Público** (**Pedidos de alta resolução**, antes "Pedidos do site" e "Pedidos de material"; **Inscrições** (título da tela: **Inscrições em cursos**), vindas do site, tecla S, só admin e master, filtro por curso (curso · turma; sem curso: "(curso não informado)"), duas abas: **Inscrições** (com o currículo; situações **Nova**, **Em análise**, **Selecionada**, **Não selecionada**, **Desistiu**) e **Avise-me** (quem pediu aviso da próxima turma; **Aguardando aviso**, **Avisado**; botões **Copiar e-mails**, **Baixar CSV**, **Marcar como avisados**); **Downloads**, antes "Downloads do site");
**Acompanhamento**; **Administração** (**Máquinas**, antes "Máquinas e site"; **Configurações**); **Ajuda**. O resto fica em **Mais**.
"Fundos e arquitetos" deixou de existir: são dois itens, cada um com a sua página.
**Protocolo** (02/11/2026, contrato 1.7): o número que a pessoa recebeu do site, igual em todas as telas do Público e na busca do topo. `CAMP-AAAA-NNNNNN` (pedido, inscrição, Avise-me), `CAMP-AAAA-DNNNNNN` (cadastro de download), `CAMP-AAAA-PNNNNNN` (pedido registrado só no painel). Em fonte de código, com **copiar** no detalhe; busca com ou sem hífens. Não usar "número do pedido" nem "ticket".
**Marca do menu** (Rafael, 04/11/2026): o logo da CAMP + **CAMP** (não "Acervos", sem "administração interna"); é um link com o nome acessível
"**CAMP — ir para a página inicial**" que leva SEMPRE ao **Precisa de você** (a Home), também com o menu recolhido e na gaveta do celular.
A aba do navegador diz "**CAMP — Administração**".
**Recolher menu** / **Expandir menu** (UX-28): o botão "‹" no topo do menu e as teclas `[` ou `⌘/Ctrl+B`. Recolhido, o menu é uma barra
estreita só com ícones; o nome do item, o número e a tecla aparecem na dica ao passar o mouse ou focar. Não usar "barra lateral".

## Material novo (redesenho, 04/11/2026 — documento do Rafael §4–7)
- Subtítulo: "Acompanhe os lotes que o CAMP Vision leu e o que ainda precisa de uma pessoa: importar, conferir, aprovar e publicar."
- Ações do cabeçalho: **Varrer QNAP** (operador+) e **Novo lote** (antes "Nova lista"; operador+; registra à mão um lote de pasta antiga, fora
  do fluxo). **Importar todas (N)** fica ao lado do número de registros, só com 2 ou mais lotes para importar.
- Cartões: **lotes precisam de você** (= o número do menu), **folhas para conferir** ("em N lotes"), **parados há mais de 48 h** ("na mesma
  etapa, esperando uma pessoa"), **projetos no site** ("de N projetos · ver em Projetos"; abre Projetos › No site).
  "No site" × "publicações totais" (consolidado): o cartão conta PROJETOS publicados (`contagens.projetos_no_site`); a aba **No site** conta
  os LOTES concluídos. Não existe "publicações totais".
- Abas: **Precisam de você** · **Chegando** · **Para conferir** · **Pronto para publicar** · **Com problema** · **No site** · **Todos**. A dica de
  cada uma diz o que conta. Filtro fino que vem de um link (ex.: "Chegando: falta importar", "Esperam um admin") aparece como aba extra.
- Filtros: **Buscar** ("Filtrar por projeto, fundo ou lote… (tecla F)"), **Autoria** (só a **autoria registrada no projeto**; "Sem autoria
  registrada" — o fundo não diz quem projetou), **Fundo**, **Etapa** (CAMP Vision lendo · Falta importar · Verificar destino · Leitura
  interrompida · Falta conferir · Falta aprovar o lote · Falta publicar · Parado com erro · No site · Parado há mais de 48 h · Lote de teste ·
  Dispensados), **Ordenar** (Ordem do trabalho · Mais recente · Parado há mais tempo · Projeto (A–Z) · Fundo (A–Z)), **Limpar filtros**,
  "**N registros**" / "**N de M registros**". Vazio com filtro: "**Nenhum lote com estes filtros.**" "Há N lotes nesta aba; os filtros escondem todos."
- Colunas: **Projeto / lote**, **Fundo / autoria** ("autoria: Nome" só quando registrada), **Progresso**, **Situação**, **Parado há**. O
  progresso diz o que mede: **Arquivos recebidos** ("9 de 24 arquivos esperados"), **Leitura parada**, **Importação** ("0 de 12 folhas no
  painel"), **Conferência** ("3 de 9 folhas conferidas"), **Aprovação** ("10 folhas conferidas · falta aprovar o lote"), **Publicação**
  ("0 de 8 folhas no site" / "lote no site"). No celular, o tempo vem como "**Na mesma etapa:** há 4 h"; abaixo, "atualizado há X"
  (a última mudança no lote; a leitura do QNAP também conta).
- Chip novo: **escondido por você** (o "Agora não" de 7 dias). Sem permissão para importar: "**Falta um operador importar**".
- **⋯** (Mais ações: código · lote): Tentar de novo, Dispensar este lote, Apagar lote (as mesmas ações e confirmações de antes).
- Detalhe do lote (▸ "Ver os detalhes do lote …"): **Identificação**, **Etapas e folhas**, **Pendências e alertas** ("Nenhuma pendência além da
  etapa atual."), **Último evento e histórico** ("Último evento:", "Abrir o projeto (histórico completo, folhas e publicação)").
- Rodapé: "Mostrando a–b de N", **‹ Anterior** / **Próxima ›**, **Por página**, **Densidade**: **Confortável** / **Compacta**.
- **Ferramentas avançadas** (recolhida): "Verificar destino pelo painel · modo Simular · o painel faria N decisões" e o aviso "Funções
  operacionais sensíveis: mudam para onde os lotes vão. …".

## Projetos (redesenho, 04/11/2026 — documento do Rafael §8)
- Pergunta da tela: "Qual projeto quero localizar, consultar ou administrar?". Subtítulo: "Localize, consulte e administre os projetos do
  acervo. Um projeto é o dossiê: …". Ação do cabeçalho: **Novo projeto** (admin).
- Cartões (o número é do acervo inteiro; clicar liga o filtro): **projetos no acervo** ("sem os juntados e os descartados"; limpa os
  filtros), **projetos no site** ("N% do acervo; qualquer visitante vê" = `contagens.projetos_no_site`), **com material digitalizado** ("ao
  menos uma folha no painel"), **sem imagem** ("nenhuma folha com imagem no painel"), **com pendências** ("problema em aberto ou lote
  esperando uma pessoa" = as regras de "Com problema" e "Precisa de você" juntas).
- Abas (as de antes, CAMP-149): **Precisa de você** · **Pronto para publicar** · **No site** · **Com problema** · **Todos**; vindas de link:
  **Não publicados**, **Sem folhas**. A aba conta o que ela mostra com a busca e os filtros ligados.
- Filtros: **Buscar** ("Título, código, arquiteto ou cidade… (tecla F)"; dica: "Acha sem acento e com parte do código: 0233, F026P0233 ou F026-P0233"; acha também cliente e
  identificação original), **Fundo**, **Arquiteto** (só a **autoria registrada no projeto**, "Nome (N)"; "**Sem autoria registrada (N)**"),
  **Período** (as décadas com projeto, "1950–1959 (N)"; "**Sem data (N)**"; a obra de 1958–61 entra nas duas décadas), **Material**
  (Com material digitalizado · Sem material digitalizado · Sem imagem), **Pendências** (Com pendências), **Ordenar** (Código ·
  Atualizados por último · Nome (A–Z) · Mais folhas · Fundo (A–Z) · Data da obra · Arquiteto (A–Z)), **Limpar filtros**. Vazio com filtro:
  "**Nenhum projeto com estes filtros.**" "A busca e os filtros somam: tire um deles ou limpe todos."
- Colunas: **Projeto** (miniatura + nome; embaixo a cidade), **Código**, **Arquitetos** (sem registro: "**não registrada**" — nunca o
  fundo), **Fundo**, **Data** ("1958–1961", "**sem data**"), **Folhas**, **Situação** (a situação do CAMP-146 + "objetivos N/M" + "**Site:**
  não publicado / rascunho / despublicado" quando não é "No site" + a frase do que falta), **Atualizado** ("há 3 dias" + a data).
  Colunas que saem na lista estreita vão para baixo do nome ("Fundo F003 · Burle Marx", "autoria não registrada", "12 folhas").
- Ação: **Abrir projeto** (link; nome acessível "Abrir projeto F003-P0001") e **⋯** (Mais ações: código · título): **Conferir folhas**
  (projeto com folhas para conferir), **Publicar no site…** (mostra o plano do lote antes), **Autorizar para o site…**, **Imprimir etiqueta
  da pasta**, **Exportar (CSV)**, **Voltar para rascunho…** (vermelho, com a confirmação de sempre). Cada um só para quem pode.
- Rodapé: "Mostrando a–b de N", **‹ Anterior** / **Próxima ›**, **Por página** (25 · 50 · 100), **Densidade**: **Confortável** / **Compacta**.

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
| **Publicar como está** (UX-73) | o mesmo Publicar, quando ainda há objetivo aberto | com `publicacao.exige_conferencia = 0` (padrão), folhas não conferidas também vão; os objetivos que faltam ficam no quadro |
| **Voltar para rascunho** | vai para `rascunho` | continua salvo para revisão; se estava publicado, exige admin master (tira do público, como despublicar) |
| **Despublicar** | vai para `fora_do_ar` | exige admin master quando já estava publicado; fundo pede o motivo |
| **Autorizar publicação** | marca o projeto como autorizado | não publica sozinho |
| **Ler de novo esta pasta** | pede ao CAMP Vision a releitura da pasta do lote (UX-08) | é o botão principal de um lote parado com erro; antes de confirmar mostra o que muda e o que fica |
| **Tentar de novo** (lote parado) | devolve a pasta ao CAMP Vision como está, sem releitura | secundário; o tooltip diz: use só quando o erro foi passageiro |

## Ignorar um item (UX-03, 27/10/2026)
| Texto | Efeito |
|---|---|
| **⋯** (Mais ações; antes **Ignorar ▾**) | menu discreto em todo item do Precisa de você (quem só lê não vê); o nome acessível é "Mais ações: <título>" |
| **Agora não · esconder por 7 dias** | some só para quem clicou e volta sozinho na data do tooltip; Desfazer por 8 s. Em item **Urgente** pede o motivo ("Esconder um item urgente por 7 dias?", "Por que esconder agora?", botão **Esconder por 7 dias**), que vai para o Histórico de ações |
| **Não mostrar mais (não era problema)** | só em problema: fecha como "Não era problema" com autor, data e justificativa (obrigatória se bloqueia) |
| **Ignorados (n)** | seção recolhida em Problemas: os escondidos por você ("Mostrar de novo") e os fechados pelo Ignorar ("Reabrir") |
| **N motivos** (UX-64) | em Problemas, a mesma folha com vários problemas vira UMA linha; embaixo do código, "2 motivos"; cada motivo tem a própria caixa, o "O que fazer" e o botão. Problema de folha retirada pelo CAMP Vision (menos o "de outro projeto", que leva a decisão) fecha sozinho com "A folha foi retirada do lote pelo CAMP Vision e não está no painel: quem decide é o problema da retirada (Devolver à revisão). Volta sozinho se a folha entrar no painel."; mensagem automática repetida fecha sozinha com "Mensagem repetida: o mesmo problema continua aberto no nº N." |
| **Dispensar este lote** (UX-35, UX-39) | só em lote parado com erro do CAMP Vision ou com a **Leitura interrompida** (UX-39: o "Ler de novo" já foi pedido e nada muda), operador ou acima: o lote sai das listas e das contagens **para todos** (Material novo, Precisa de você, menu, alertas por e-mail). Nada é apagado nem muda no QNAP; volta sozinho se o CAMP Vision ler a pasta de novo e o resultado mudar (na leitura interrompida: se o lote sair de "sendo lido" ou recomeçar a etapa). Em Material novo é secundário, depois de "Tentar de novo" ou "Ler de novo". No Ignorar ▾ aparece como **Dispensar este lote (para todos)**. Desfazer por 8 s |
| **dispensado** / **Voltar a mostrar** (UX-35, UX-39) | o lote dispensado continua em Material novo › Todos (antes "Todas") com o chip "dispensado"; "Voltar a mostrar" desfaz a dispensa (fica no Histórico como "lote parado dispensado") |

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
- A tela "Máquinas e site" e o resumo de máquinas do topo (o botão **Estado dos sistemas**) são só para admin. O alerta que impede o trabalho (QNAP, CAMP Vision, site) aparece para todos (redesenho §4).
- Em texto novo, prefira "página pública" / "publicado" a "no site" quando falar do que o visitante vê (exceção: a situação **No site**, acima).

## Conferência (UX-10, 27/10/2026)
- **Tela cheia** / **Sair da tela cheia**: o botão (e a tecla F) da gaveta "Revisar folha". "Iniciar conferência" / "Continuar conferência"
  (antes "Começar a conferir") já abre em tela cheia.
- **sugerido do projeto**: valor do projeto (ano, cidade, cliente) mostrado em cinza num campo vazio da folha. Não é dado lido nem
  confirmado; só vale se a pessoa aceitar (Tab) e salvar. Nunca chamar de "lido" ou "herdado" na tela.
- **Mais tipos**: onde ficam os tipos documentais além dos 4 mais usados no projeto.
- **Atalhos da conferência**: a lista que a tecla ? abre na revisão (e o botão **? atalhos** da barra da folha).
- **Girar à esquerda** · **Girar 90°** · **Girar 180°** (UX-66; redesenho de 04/11/2026): os botões da barra de ferramentas logo acima da
  imagem, sempre à vista; **Girar 90°** é a mesma rotina da tecla R (90° para a direita) — os antigos "Virar à esquerda/direita" de baixo
  da imagem viraram **Girar à esquerda** e **Girar 90°** na barra. 180° é para a folha de cabeça para baixo.
- **orientação incerta — confira** (UX-59): a folha de orientação incerta que o CAMP Vision mandou com giro sugerido aparece já girada
  como sugerido; **nada é gravado** até a pessoa agir. **Usar sugestão** (em "Sugestões do CAMP Vision"; antes "Gravar este giro") grava;
  **Ver como chegou** mostra a imagem original; salvar ou confirmar a folha grava o giro junto; girar conta a partir do que está na tela.

## Título de projeto que é nome de pasta (UX-15)
- **Nome de pasta do sistema**: título que é nome de pasta ou código ("01 - Arquivo Arquivístico (TIFF)", "T099_Casa", "F000 - …", "Casa P0012",
  "Projeto Não Identificado 3"). Regra única em `similaridade.titulo_tecnico`: criar, importar planilha e editar recusam; **Publicar** bloqueia
  só com `publicacao.exige_conferencia = 1` (UX-73: no padrão é o objetivo "Título de obra (não nome de pasta)").
- **Título sugerido**: o título sem o prefixo de pasta. Botão **Usar o título sugerido** (uma pessoa aceita, um projeto por vez; nada é renomeado sozinho)
  e **Corrigir o título** (abre a edição).
- Cidade: a tela sugere a **forma do acervo** (a mais usada: "São Paulo, SP" × "São Paulo") com o botão **Usar**; o campo continua texto livre.
- UX-67 (03/11/2026): a **contagem de folhas da pasta** no fim do nome ("Teatro Piracicaba - 12 Folhas", "(12 fls)", "12 folhas") também é
  nome de pasta. Projeto novo (reserva da estação, decisão, destino automático) já nasce sem ela e sem os códigos de pasta; o nome da pasta fica
  no histórico do projeto.
- **Corrigir vários títulos** (admin, no aviso da tela Projetos): uma lista com o título de hoje riscado e o **título novo** já preenchido com
  a sugestão **no carimbo** (o nome da obra que a maioria das folhas diz: "no carimbo: Teatro Municipal de Piracicaba (4 de 5 folhas)") ou
  **da pasta** (sem a contagem e os códigos). **Ver o que muda** só mostra ("N títulos mudam (nada foi gravado ainda)"); **Aplicar N títulos**
  grava depois da confirmação. **Histórico das correções** com **Desfazer** (volta o título de antes; o que alguém mudou depois fica como está).
  O código do projeto nunca muda; no Histórico do projeto: "título corrigido (veio da pasta)" / "correção de título desfeita".

## Números e estado do topo (UX-05, 27/10/2026)
- Todo número de contagem vem de `backend/app/contagens.py` (a mesma regra em Home, Material novo, Máquinas, Relatórios e menu).
  Ao lado dele: "atualizado agora" / "atualizado há X" (nunca a hora solta).
- O topo diz (desde o redesenho §4, no painel do botão **Estado dos sistemas**) "**N de M estações ligadas**" (só as de captura; o CAMP Vision e o QNAP têm a sua frase) e o pior estado:
  "QNAP ok" · "QNAP em atenção" · "QNAP quase cheio" · "QNAP desconectado"; "site ok" · "site lento" · "site não respondeu uma vez" · "site sem resposta".
- Em Material novo o filtro "Chegando" conta o mesmo que o resumo ("N chegando"): o CAMP Vision lendo + folhas que faltam importar.
- UX-60: em **Qualidade do CAMP Vision**, o quadro **Folhas sem leitura por resposta quebrada**: "**N folhas ficaram sem leitura** em N projetos:
  a resposta do modelo veio quebrada e o CAMP Vision descartou o campo, em vez de gravar um valor errado. Abra a folha e preencha o campo na
  conferência." Cada folha (uma vez só) com os campos e "esperando conferência" / a revisão / "fora do painel". Sem nenhuma: "Nenhuma folha
  ficou sem leitura por resposta quebrada do modelo."
- UX-70: o número do menu é o da tela que ele abre, e o menu diz o que conta (dica ao passar o mouse). **Material novo** = aba
  "**Precisam de você**" ("Lotes que dependem de uma pessoa: importar, conferir, aprovar, publicar ou parados com erro."); **Problemas** =
  aba "**Abertos**" ("Só o que pede ação: bloqueia a publicação ou pede correção, sem os avisos."). No resumo de Problemas:
  "**N pedem ação: é o número do menu Problemas e da aba Abertos. Contando os N avisos, são N abertos no total; N marcados como bloqueio.**"
- Alertas (UX-07): cada assunto mostra **normal**, **atenção**, **crítico** ou **não medido** (minúsculas, como chip). "Não medido" só
  quando a medição falhou ou não existe, e sempre com o porquê na frase ("Não medido: o endereço do site não está configurado…").
- Preservação (UX-02): o bloco do topo de Máquinas diz quantas cópias as imagens têm, em frase simples: "Suas imagens têm duas cópias"
  (verde), "A segunda cópia das imagens está atrasada" (âmbar), "Suas imagens têm só uma cópia" (vermelho). Chip: "duas cópias" ·
  "cópia atrasada" · "só uma cópia". Espaço: "enche em ~N dias" (menos de 30 = atenção; menos de 10 = crítico).

## Home: o que fica na frente (UX-18/21/30, 27/10/2026)
- Coluna da esquerda: **O que fazer agora**, **O caminho do material**, **Folhas conferidas por dia — últimas 2 semanas** (era "Ritmo das
  últimas 2 semanas") e, logo abaixo (admin), **Visitas ao site** (03–05/11/2026).
- Coluna da direita, completa: **Está tudo funcionando?**, **Hoje** e, abaixo, **Qualidade da base**, **Melhorias de hoje**,
  **Quanto do acervo já está no site**. Tudo sempre aberto: nada de bloco recolhido.
  Pedido do Rafael em 27/10/2026 ("eu gostava dessa barra completa"): desfaz o bloco recolhido **Números do acervo** do UX-30.
- **Visitas ao site** com o Google Analytics desligado mostra **desligado** na Home sem perguntar ao Google (UX-12) e também aparece em
  **Configurações** (com "Ver como ligar").
- **Visitas ao site** (04/11/2026, especificação do Rafael; desde 05/11 a Home tem só o resumo, abaixo): na tela do menu, o módulo completo: "Acompanhe a evolução dos acessos e descubra quais projetos despertam mais interesse.", o filtro
  **Últimos 7 dias** · **Últimos 30 dias** · **Últimos 90 dias** · **Intervalo personalizado** (**Aplicar**), as datas com "horário de São
  Paulo · termina ontem, porque o dia de hoje ainda não terminou" e "**Última sincronização:** …" (chip **falhou**).
  - **Evolução das visitas**: **Visitas no período** ("sessões no site público"), **Média de visitas por dia** ("total ÷ N dias"),
    **Variação vs. período anterior** ("sem base para comparar" quando o anterior é zero; "sem dados completos do período anterior").
    "**Visitas** = sessões: cada vez que alguém entra no site conta uma visita…". **Comparar com período anterior**, **Ver os números**,
    "pico: …". **Visitas** é sempre sessão; não use "acessos", "pessoas" ou "páginas vistas" como sinônimo.
  - **Projetos mais visitados**: "Ranking dos projetos do acervo que receberam mais acessos no período selecionado.", "**Visualizações** da
    página do projeto…" (é a medida do ranking; nunca chame de "visitas"), **Ver todos os projetos (N)** / **Mostrar só os 10 mais
    visitados**, "Buscar projeto ou arquiteto", **Mais visitados** · **Menos visitados** · **Maior crescimento**, **Exportar CSV**,
    **Página pública**, "novo" (sem visualização no período anterior), "**Páginas não identificadas:** …(fora do ranking, para investigar)",
    "Fora do ranking também: …". Sem autoria cadastrada: "**Acervo** <fundo>" (nunca o titular como autor).
  - Estados: "Carregando as visitas…", "**Sem visitas registradas neste período**", "**Não foi possível carregar os dados de visitas**"
    (com o erro técnico, **Tentar de novo** e **Ver o diagnóstico**), chip **desligado** / **sem dados** no título da Home.
    Botão da Home para a tela: **Ver análise completa de visitas →** (era "Canais, cidades e pesquisas no Google").
- Redesenho da Home (05/11/2026, plano do Rafael §10–17):
  - **O caminho do material**: cada passo diz a posição, a quantidade e a **unidade** ("estações ligadas", "pastas", "lotes"; os números não se
    somam), uma linha do que é o passo e, quando for o caso, a marca em texto: **maior acúmulo** (amarelo), **próximo passo** (azul, o 1º passo
    de gente com algo esperando), **parado com erro** (vermelho), **atenção** (publicar com lote travado), **sem medida**; zero = "**nada
    esperando**" (não é problema). Link **O que é cada passo?**. Cada passo abre a lista filtrada.
  - **Folhas conferidas por dia — últimas 2 semanas**: **Total no período**, **Média por dia de trabalho** ("folhas ÷ N dias com conferência"),
    **Hoje, até agora**; "**Cada barra é um dia corrido** (inclui fins de semana e feriados)…"; dica "origem: conferências registradas no
    painel"; vazio: "**Nenhuma folha conferida no período selecionado**" (com **Ver o que falta conferir** / **Ver o material novo**); falha:
    "**Não foi possível carregar o ritmo**" com **Tentar de novo** (nunca zero no lugar do erro).
  - **Visitas ao site** na Home é só o resumo: "Resumo das visitas ao site público no período.", **Últimos 7/30/90 dias**, **Visitas no
    período**, **Média por dia**, **Variação vs. período anterior** ("sem base de comparação"), **Projetos mais visitados** ("os 5
    primeiros") e o botão **Ver análise completa de visitas →** (abre a tela Visitas ao site, com o módulo completo). Falha: "**Dados de
    audiência temporariamente indisponíveis**". Na tela completa, o ranking tem também **Todos os fundos** / **Todos os arquitetos** e, por
    projeto, "**sem comparação**" quando o período anterior não tem dados completos.
  - **Qualidade da base**: "índice geral" e a variação em **pontos percentuais** com o dia nomeado ("↓ caiu 0,8 ponto percentual frente a
    28/10 (73,6%)"); sem retrato antigo: "**Sem comparação**: ainda não há retrato de 7 dias atrás". Medida em 0%: chip **atenção**.
    **Como cada medida é calculada**; **Fundos que mais precisam de cuidado** (3) e **Ver todos os N fundos com folhas**.
  - **Melhorias de hoje**: "correções válidas, por pessoa", em ordem alfabética (não é ranking); "**Equipe:** N hoje · N nos últimos 7 dias";
    o que conta e o que não conta; quem só lê vê só o total da equipe. Vazio: "Nenhuma correção nos últimos 7 dias."
  - **Quanto do acervo já está no site**: "**N** de M folhas publicadas", "… projetos com página publicada", "… fundos com página publicada",
    a porcentagem e a barra; total zero = "**Não aplicável**"; a nota do denominador e os links **Ver projetos prontos para publicar** ·
    **Ver projetos não publicados** · **Ver fundos não publicados**.
- **N folhas publicadas sem lugar** (UX-25) fica no fim de **O que fazer agora**, porque pede uma ação (guardar).
- Fila de outro papel: aparece esmaecida e no fim, com "você acompanha; quem faz é um admin". Nunca se esconde o que a pessoa pode ver.
- O número de decisões só aparece com decisão pendente (nunca "0 decisões").
- UX-68 (03/11/2026): **decisão** é só o que está na fila de **Decisões** (projeto parecido, lote com números repetidos, dado diferente do
  cadastro, mesmo nome em outro fundo, verificar destino). O número do menu, a página Decisões e o "**N decisões pendentes sobre este projeto**"
  da página do projeto contam a mesma fila. No cartão **Dados do projeto**, a diferença entre o carimbo das folhas e o cadastro (e as obras
  distintas na pasta) é "**N a confirmar**", com o botão **Confirmar** e, em "O que falta", "**Confirmar N dados do projeto (carimbo × cadastro)**":
  é calculada das folhas e se resolve no próprio projeto (**Usar … no projeto** / **Manter o do projeto**); não é decisão. A diferença que
  também está na fila (o mesmo campo) conta uma vez só, como decisão ("1 decisão pendente · sobre este projeto, na fila de Decisões", **Ver em Decisões**).

## Home redesenhada: parte de cima (plano do Rafael de 03/11/2026, §5–§9)
- **Cabeçalho**: título só com a saudação ("**Boa noite, Rafael.**"); subtítulo "**N coisas pedem sua atenção hoje**" (1: "1 coisa pede…";
  0: "**Nada pede sua atenção agora.**"; quem só lê: "Veja como está o acervo hoje: você pode ver tudo, sem alterar."); a data com a hora numa
  linha discreta. O N é a fila REAL do servidor (`fila.pedem_atencao`): o que é da função da pessoa, fora **Melhorar a base**.
- **Entenda esta página** (antes "Como funciona esta página", só na Home): inteira na 1ª vez; depois do primeiro uso chega fechada numa linha e não
  reabre a cada visita; **Entendi** tira até a linha; o **?** traz inteira. Assuntos: **Os números do topo**, **O que fazer agora**,
  **Está tudo funcionando?**. Ajuda curta das seções: "**Como a fila é ordenada?**", "**O que significam as cores?**".
- **Indicadores**: **decisões pendentes** (só com decisão), **lotes para conferir** ("N folhas no total"), **lotes esperam um admin** (admin) ou
  **lotes para importar** (operador e leitura), **folhas conferidas hoje** ("média de N por dia de trabalho nas últimas 2 semanas"). Sem medida:
  "**Sem dados**" (nunca 0). Os que abrem lista têm a seta →.
- **O que fazer agora**: filtros **Todas · Decidir · Conferir · Publicar · Resolver · Responder · Melhorar a base** (com o total real; Decidir
  e Resolver só quando há); **Ordenar**: **Mais urgente primeiro** · **Mais antigo primeiro** · **Mais recente primeiro** · **Por tipo**.
  Regra do "mais urgente" (servidor, `pendencias.FILA_REGRA`): 1º o que é da sua função; 2º **Urgente** (o CAMP Vision parado esperando,
  problema que impede publicar ou já está no site, lote parado com erro, empréstimo vencido há 7 dias ou mais); 3º o resto; por último Melhorar
  a base; dentro de cada nível, quem espera há mais tempo. Cada linha: o tipo (**Decisão**, **Importar**, **Conferir**, **Verificar destino**,
  **Aprovar**, **Publicar**, **Problema**, **Leitura interrompida**, **Pedido**, **Empréstimo**, **Melhorar a base**), o selo **! Urgente** com o
  motivo, o código, "**esperando há N h**" / "**parado há N dias**" (lote) e o botão. "**Ver todos os itens da fila (N)**" / "**Mostrar só os
  primeiros**"; "**Mais N para melhorar a base · Ver quanto falta em cada fundo →**". Com o menu aberto a lista não se mexe: "**Há novidades na
  lista.**" + **Atualizar a lista**. Resultado na tela: "Escondido por 7 dias: <título>. Volta sozinho em dd/mm." / "Voltou para a lista: …".
  Erro ao ordenar: "Não consegui reordenar a lista: … **Tentar de novo**". Filtro vazio: "Nada em “Publicar” agora."
- **Está tudo funcionando?**: uma linha por sistema — **QNAP**, **CAMP Vision**, **Site público**, **Estações de captura**, **Cópias das
  imagens**, **Cópia de segurança do painel** (admin) — com ícone e o estado em texto: **normal** (✓ verde), **atenção** (! amarelo),
  **crítico** (✕ vermelho), **não medido** (? cinza) e, para estações desligadas fora do horário, **fora do expediente** (cinza). O que falha
  primeiro; "**medido hoje às HH:MM**"; **detalhes** / **esconder detalhes**; nada "em dia" sem "**Última cópia certa: …**". No título: "N com
  problema" / "N em atenção" / "N sem medida" / "tudo normal". Rodapé: "**Verificado às HH:MM**", **Verificar agora** (→ "Verificando…",
  "Verificado agora (HH:MM)") e **Ver detalhes dos sistemas →** (admin).

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
- Sincronização incremental (UX-46): **Sincronizar agora** lê só o que mudou; **Sincronizar tudo** (admin) relê o site inteiro. Texto
  abaixo dos botões: ""Sincronizar agora" lê só o que mudou no site desde a última conferência. "Sincronizar tudo" relê o site inteiro
  (leva vários minutos) e tira do painel o que saiu do site; o painel faz isso sozinho uma vez por dia." Em "Última conferência":
  "**só o que mudou: N itens**" quando a última foi incremental. Tarefas: "Sincronizar tudo com o site" / "Sincronizando tudo com o site";
  passo "Lendo do site o que mudou desde a última sincronização"; fim "Sincronizado só o que mudou: N itens do site, N divergências."
- No Histórico de ações: "{quem} mandou ao site as correções e escritas que estavam esperando" · "N enviadas, N falharam, N ainda na fila".

## Publicação paciente com o site lento (27/10/2026)
- No acompanhamento da publicação: "**Folha X: o site demorou (…). Tentando de novo em N s (tentativa 2 de 3)**"; quando o painel
  passa a mandar menos folhas juntas: "**O site está lento: enviando N de cada vez**"; quando volta: "**O site voltou a responder bem:
  enviando N de cada vez**". Folha que não subiu nem na 3ª: "**NÃO subiu (depois de 3 tentativas)**".
- No resultado: "**N folha(s) precisaram de nova tentativa (o site demorou)**". Falha de vez: "(o site não respondeu em 3 tentativas)" e
  "o próximo Publicar envia só as que faltam, sem duplicar as já enviadas".

## Fotos enviadas pelo painel vão ao QNAP e são lidas (28/10/2026)
- "+ Adicionar folhas (enviar imagens)": a folha entra **para conferir**. Logo depois o painel grava a foto na pasta do projeto no QNAP
  (<série>/<FORMATO>/) e pede ao CAMP Vision para ler e legendar (no Histórico: "folha gravada no QNAP", "releitura pedida" com o motivo
  "foto enviada pelo painel: ler e legendar", e "foto lida pelo CAMP Vision"). QNAP fora: tenta de novo sozinho.

## Mudar de fundo (28/10/2026)
- No "Mais ⋯" do projeto (admin): **Mudar de fundo** — "Para o projeto cadastrado no fundo errado (ex.: digitalizado como Convidado e é de
  um arquiteto)…". Escolhe o **Fundo certo**; a prévia diz "Vai virar F0xx-P00NN (N folhas)". Botão **Mudar de fundo**; aviso "Projeto mudou de
  fundo: X agora é Y" + "As etiquetas já impressas têm o código antigo: imprima de novo." Indisponível: "Já tem registro no site: não dá para mudar de fundo."

- Folha do **Convidado (F000)**, em "É de outro projeto…": "Projeto certo (código ou nome; de qualquer fundo: esta folha está no Convidado)";
  o projeto novo pede **Fundo (obrigatório)** ("— escolha o fundo —"; falta: "Escolha o fundo do projeto."). Dica: "O projeto inteiro é de
  outro fundo? Use Mais ⋯ → Mudar de fundo no projeto: ele e todas as folhas vão juntos."

## Apagar lote sem folhas (28/10/2026)
- Lote em Importar/Verificar destino SEM nenhuma folha no painel: no Ignorar ▾ da Home, **Apagar este lote (sem folhas)**; no Material novo,
  **Apagar lote** (só admin). Confirmação: "O lote não tem nenhuma folha no painel: sai de todas as listas e contagens, para todos. Os arquivos
  no QNAP não são tocados. Dá para desfazer logo depois." (+ "Atenção: o CAMP Vision achou N arquivos na pasta deste lote, que ainda não
  viraram folhas no painel." quando houver). Aviso: "**Lote apagado: saiu das listas e das contagens.**" com **Desfazer**.

## Mover e reter folha publicada (28/10/2026)
- Mover: a folha publicada pode ser marcada; ao lado dela, "**publicada: ao mover, sai do público no site (fica privada, nada é apagado)**".
- Reter ("Não publicar esta folha"): "Se ela já está publicada, sai do público no site (fica privada, nada é apagado)." Aviso depois de reter:
  "**· saiu do público no site (ficou privada)**". Se o site recusar: "Não consegui tirar a folha … do site (…). Nada foi mudado; tente de novo."

## Publicação sem duplicar (27/10/2026)
- Uma folha com erro não para a publicação: as demais seguem e o resultado diz "**N folha(s) enviada(s), N com erro**" (com a primeira
  folha e o erro) e "**As enviadas foram publicadas.**". Durante: "Enviadas N folha(s); faltam N. N com erro até agora."
- Em Divergências com o site: "**Item duplicado no site ao publicar**" (o painel ligou a folha no item mais antigo, ou no publicado, e
  não criou outro; "mande os itens que sobraram para a lixeira no site") e "**Folha com mais de um item no site**" (achado na sincronização).

## Recorte automático das imagens públicas (UX-44, 27/10/2026)
- Só a imagem que vai ao site (até 1.920 px) e o "**Ver como vai ao site**" são recortados na borda do papel. 28/10 (Rafael: "quero sempre
  igual o original"): a cor NÃO é mais ajustada (imagem.ajuste_cor = 0); no "Reprocessar imagens públicas", as que subiram clareadas aparecem
  como "**voltam à cor do original**". Em Máquinas → Catálogo local × site (admin): **Voltar à cor do original…** confere e, confirmando
  ("Reenviar com a cor do original"), reenvia SÓ essas; nenhuma: "Nenhuma imagem no site com a cor ajustada: todas já estão com a cor do original."
  O TIF e a prévia do CAMP Vision não mudam. O recorte feito à mão ("Recortar e alinhar") sempre vence.
- Na conferência, sobre a prévia: o retângulo tracejado e o selo **recorte automático** (com "o tracejado é o que vai ao site; o original
  não muda") ou **recorte automático incerto** (com o motivo: "Vai inteira ao site; se precisar, use “Recortar e alinhar” (K).").
- Botões: **Usar recorte inteiro (sem recorte)** e, depois dele, **Usar recorte automático**; o selo da escolha é
  **sem recorte (escolhido na conferência)**.
- Rotina de admin: **Reprocessar imagens públicas com recorte automático** (simula por padrão; só reenvia confirmando "REPROCESSAR").

## Sender.net: configuração enviada ao site (01/11/2026)
- Em Configurações → **E-mail e avisos**, o botão **Enviar a configuração do Sender ao site** (admin). Texto acima: "Manda ao site se ele
  usa o Sender.net nos e-mails dele, os IDs dos 6 e-mails transacionais e o token. Desligado, o site continua com o e-mail de sempre.
  O token não aparece aqui."
- Resultado: "**O site recebeu:** Sender.net ligado/desligado · token preenchido/sem token · N e-mails transacionais." Ligado sem token:
  "Sem o token, o site continua com o e-mail de sempre." Erro: "Não foi enviada: <motivo>"; site antigo: "O site ainda não recebe a
  configuração do Sender.net: atualize o site (plugin da CAMP 1.23.0 ou mais novo). Nada mudou no site." Com campo alterado sem salvar:
  "Salve as alterações desta seção antes de enviar ao site."
- No e-mail de entrega, a validade é por extenso: "15 de novembro de 2026, às 23h59" (horário de São Paulo).

## Objetivos do projeto (UX-73, 03/11/2026)
"Quero que possa publicar como está. Só precisa avisar que falta x ou h coisas serem feitas, como objetivos em uma gamificação" (Rafa).
- **Objetivos do projeto**: quadro no bloco "Próximo passo" com a barra **N de M objetivos** e a lista: ✓ no que está feito; no que falta,
  a frase começa com **Falta** ("Falta conferir 49 folhas", "Falta aprovar o lote (depois de conferir as folhas)", "Falta dizer o tipo da obra
  (programa / uso: residência, escola…)", "Falta dizer a natureza do trabalho (obra nova, reforma, restauro…)", "Falta dizer a modalidade
  (concurso, encomenda pública ou privada…)", "Falta dar um título de obra") e um botão que leva ao lugar: **Conferir as folhas**,
  **Aprovar o lote**, **Escolher o tipo**, **Escolher a natureza**, **Escolher a modalidade**, **Escolher a situação**, **Informar o ano**,
  **Informar a cidade**, **Corrigir o título**, **Ver os problemas**, **Publicar a página do arquiteto**. Rodapé: "Não impedem publicar: o projeto
  pode ir ao site como está e ser completado depois."
- **Tipo da obra** = o campo **Programa / uso** (coluna `tipologia`); **Natureza do trabalho** traz "Edificação (obra nova)", "Reforma / ampliação"…
- **Publicar como está**: o rótulo do Publicar enquanto houver objetivo aberto (cartão Site: "pronto: dá para publicar como está" e
  "objetivos: N de M"). Sem objetivo aberto, volta a ser **Publicar**.
- **Dados do projeto que faltam**: na Revisão do lote e no fim da conferência (aprovar o lote), só os dados do projeto que faltam, com o botão
  que abre a edição já no campo.
- Lista de Projetos: selo `objetivos N/M` (verde quando todos feitos).

## Estados de um bloco (redesenho §20, 04/11/2026)
Os textos do componente único de estados (`estadoHTML`, docs/UI.md "Estados"): **Carregando…**; **Nada por aqui ainda.** (vazio: diga o
período); **Não consegui carregar.** com **Serviço afetado:** (QNAP, CAMP Vision, site…) e **Última informação conhecida:**;
**Você não tem acesso a isto.** com **Quem pode autorizar:**; sucesso com o identificador real ("**Lote conferido:** F003-P9001");
**Dados desatualizados.** com **Última sincronização:** (no componente) ou **Última atualização às HH:MM** (na marca das listas); **Desfazer**.
Horas sempre no fuso de São Paulo: "às 14:05 (há 3 min)", "em 03/11 às 21:40".

## Topo: Estado dos sistemas (redesenho §4, 04/11/2026)
- Botão **Estado dos sistemas** (nome acessível "Estado dos sistemas: …"). O texto dele é o pior estado: **Sistemas funcionando** (só com
  tudo medido e normal; nunca "Sistemas operacionais"), **Atenção necessária** (+ a 1ª atenção), o nome da falha crítica ("**QNAP
  desconectado** +2") ou **Sistemas sem medida**. **desatualizado** quando o painel não verifica há 3 min.
- Painel: **Estado dos sistemas**, **Última verificação: às HH:MM (há N min)**, **informação desatualizada**; linhas **QNAP**, **Site público**,
  **CAMP Vision**, **Cópia das imagens**, **Cópia de segurança do painel**, **Estações de captura** ("N de M estações ligadas" — o número do
  UX-05 mora aqui agora), com o chip **normal**/**atenção**/**crítico**/**não medido** e uma frase do impacto; **Ver as máquinas (N)**,
  **Verificar agora**, **Abrir Máquinas**.
- Alerta que impede o trabalho: o texto de sempre ("QNAP não está conectado a este servidor: …"), sem **Fechar por hoje**.
- Busca do topo: "**Buscar projeto, fundo, arquiteto ou código**" (sem o exemplo de código no texto); no celular, onde não cabe, "**Buscar projeto ou código**".
- Conta: o menu do nome/avatar mostra o nome, o papel (**admin master**, **admin**, **operador**, **só leitura**) e o e-mail.

## Página do projeto (redesenho, 04/11/2026 — documento do Rafael §3–§9)
- **Cabeçalho**: o nome (h1) com a situação (as 5 do CAMP-146) e a linha "código · fundo (link) · autoria: … (se registrada) · ano · cidade ·
  N folhas". Ações: **Editar** (admin) e **Mais ⋯** (onde agora ficam **Etiquetas**, folha de contatos, duplicatas, relatar problema,
  exportar, mover e o vermelho de sempre).
- **Abas**: **Visão geral** · **Folhas (N)** · **Metadados** · **Problemas (N)** · **Histórico**. "Publicação" está em **Metadados**
  (quadro "Requisitos para publicar", junto de "Como aparece no site"); "Pedidos" está em **Histórico** ("Pedidos de material (N)").
  Em Histórico, o quadro principal se chama **Ações e alterações**.
- **Próximo passo** (o mesmo bloco do CAMP-147) traz a conferência: rótulo **Conferência**, "**N de M folhas conferidas**" com a barra e as
  etapas **Conferir folhas** → **Revisar metadados** → **Aprovar lote** → **Publicar no site** (orientação: "(feito)", "(você está aqui)",
  "(não se aplica)" para quem lê com leitor de tela). Sem lote: "Nenhuma folha deste projeto está num lote em conferência." O botão azul da
  conferência: **Iniciar conferência** (nenhuma conferida) ou **Continuar conferência**; ao lado, **Conferir só sem avisos (N)**.
  **Objetivos do projeto** ficam recolhidos (a barra e o "N de M" à vista).
- **Situação do projeto**: a coluna da direita da Visão geral (pendências + os cartões Folhas, Problemas, Dados do projeto, Site).
- **Cartão da folha**: **Folha NN** (ou o número D quando a folha não tem nº), o tipo, o selo `a conferir` / `conferida` / `corrigida` /
  `retida` (com ícone; "conferida" só com a revisão gravada) e o menu ⋯ (**Revisar folha**, **Abrir a página da folha**, **Relatar
  problema**). Filtros: os de sempre + **Tipo** ("Todos os tipos"); **Grade** / **Lista**.
- **Ordem das folhas** (06/11/2026, "organizar as fotos arrastando"): o select **Ordem** tem **código** · **nº de folha** · **tipo** ·
  **definida à mão**. Na "definida à mão" (operador e admin, sem filtro): a alça ⠿ ("Mudar a ordem: Folha NN. Setas movem para antes ou
  depois; ou arraste"), a dica "Arraste as folhas para mudar a ordem (ou use as setas na alça ⠿)." e, com ordem gravada, **Voltar à ordem
  do código** (pergunta "Voltar à ordem do código?"). Com filtro: "Para mudar a ordem, mostre **Todas** (sem filtro)." No ⋯ da folha:
  **Mover para antes** / **Mover para depois**. Ao soltar: "**Ordem salva**" com **Desfazer** ("Ordem desfeita"); erro: "A ordem não foi
  salva: … As folhas voltaram para onde estavam."; nas pontas: "Esta já é a primeira/última folha da série.". Nunca dizer "renumerar" nem
  "mudar o código": a ordem é só a posição na tela; o código D não muda. Histórico: "ordem das folhas mudada" ("N folhas mudaram de lugar
  (os códigos não mudam)") e "folhas de volta à ordem do código". No site (contrato 1.8), a ordem vale na página do projeto
  (e no anterior/próxima da folha): Histórico "ordem das folhas enviada ao site"; se o site recusar, fica a pendência "A ordem das
  folhas escolhida no painel ainda não chegou ao site" (ou "O site ainda não tem a rota da ordem das folhas…: atualize o site").
- **Revisar folha** (painel ao lado): **Folha NN** + selo + "por Nome" · código · projeto; **‹ Anterior** · "**N de M** · X conferidas" ·
  **Próxima ›**. Avisos em grupos: **Impede publicar** ("resolva antes de publicar") e **Aviso do CAMP Vision** ("confira; não impede
  publicar"); sem nada: "Nada apontado.". Barra: **Girar à esquerda**, **Girar 90°**, **Girar 180°**, **Espelhar**, **Recortar e alinhar**,
  **−** / **N%** / **+** (ampliação), **Tela cheia**, **? atalhos**. **Sugestões do CAMP Vision** ("Leitura automática: só vale se você usar e
  salvar."): **Título sugerido**, **Tipo sugerido**, **Orientação sugerida**, cada um com **Usar sugestão** (depois: "Sugestão no campo").
  **Dados da folha (editáveis)** (campo vazio: "· vazio"); **Identificado pelo CAMP Vision** (só leitura); **Outras ações desta folha** (Abrir a página da folha, Ler dados agora, Marcar duplicata, capa); **Não publicar esta folha** e **É de outro projeto…** (recolhidos).
  Rodapé: **Salvar e próxima folha** (na última: **Salvar e concluir**; tecla Enter; antes "Está certo e próxima" — e "Salvar correção",
  que fazia o mesmo com campo mudado) · **✓ Confirmar folha** (grava e fica na folha) · **Voltar para a conferir** (folha já conferida) ·
  **Relatar problema** · **Fechar**. Abrir a folha NÃO a confere.
- **Editar projeto** (painel ao lado): **Sobre a edição** (recolhível); **Informações públicas** (Nome do projeto, Ano "0 = sem data", Ano
  final, Cidade, Cliente "Só se estiver escrito num documento (carimbo, contrato, memorial). Não deduza.", Autoria do projeto, Papel do
  titular do fundo, Âmbito e conteúdo); **Programa / uso**; **Natureza do trabalho**; **Modalidade**; **Situação da obra** ("(escolha um)");
  cada lista com "Buscar em …", "Nenhum termo com essa busca." e o resumo do que está marcado ("nada marcado"); **Só no painel** ("não vai
  ao site"). Rodapé: **Cancelar** · **Salvar alterações** ("Salvando…"). Os termos são os da taxonomia do site (`/api/vocabulario/tipologia`),
  nunca os do protótipo.
