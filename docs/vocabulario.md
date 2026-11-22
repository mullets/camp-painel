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
**Amigos da CAMP** (18/11/2026, contrato 1.11): item do menu em Público e processos, tecla H, só admin e master (operador e leitura não veem o item e a API responde 403). Abas **Amigos** e **Adoções**. Situação do Amigo: **Pago**, **Pendente**, **Vencido**, **Recusado**, **Isento**, **Cancelado**; ao lado, "vence em N dias" e "cobrança enviada dd/mm". Situação do pedido (adoções e o pedido no site): **Novo**, **Em contato**, **Proposta enviada**, **Fechado**, **Arquivado**. Números do topo: **Amigos ativos**, **receita de AAAA (pago)**, **pendente**, **vencendo**. Botões: **Sincronizar agora**, **Registrar pagamento**, **Enviar e-mail**, **Enviar cobrança**, **Registrar Amigo**, **Valores e regras**, **Lembretes automáticos** (Desligados · Simular · Ligados). Modelos de e-mail: Pagamento confirmado: boas-vindas · Cobrança · Lembrete de renovação · Pagamento pendente · Recibo simples · Aviso de vencimento · Texto livre. E-mails "sempre pelo Sender" (18/11/2026): canal **Sender (pelo site)**; prévia "template **TRnn** (nome) no Sender. Variáveis que vão:" e "O texto e o layout finais são os do template no Sender. Texto de referência:"; aviso **não vai sair** com a mensagem do site; no histórico "enviado … pelo Sender" ou "não foi" + motivo ("não enviado: falta o template TR15 (Cobrança) do Sender no site. Crie no Sender e cole o ID na administração do site, Apoios → Mercado Pago → E-mails pelo Sender (avise quem cuida do site)", "… Atualize o site (plugin da CAMP 1.25.12 ou mais novo)", "o Sender está desligado no site (sem o token)…"). **Desativar, Reativar e Apagar** (CAMP-AMIGO-APAGAR, 21/11/2026, contrato 1.28; só admin): no detalhe, bloco **Desativar ou apagar** com **Desativar** (ou **Reativar**) e **Apagar**; na seleção, **Desativar** e, no filtro **Inativos**, **Reativar**. Chip **inativo**; filtro **Inativos** (fora da lista padrão). Confirmação **Desativar?**: "Fica inativo: sem cobranças, lembretes nem e-mails automáticos, fora do "Enviar cobrança" e da lista (filtro Inativos). O código e os benefícios de Amigo param de valer e a área do Amigo mostra "inativa". Dá para reativar."; com assinatura: "**A assinatura mensal no Mercado Pago será cancelada**: a pessoa para de ser cobrada. Nada é devolvido (sem reembolso)." e o botão **Desativar e cancelar a assinatura**; campo **Motivo (opcional, fica no histórico)**. Confirmação **Reativar?**: "A assinatura mensal cancelada no Mercado Pago não volta sozinha: a pessoa assina de novo pelo link de pagamento." Confirmação **Apagar este Amigo?**: listas **Sai, no painel e no site:** e **Fica, sem dados pessoais:**, "Não dá para desfazer.", campo **Para confirmar, digite o nome da pessoa ou APAGAR**, botão **Apagar** (**Apagando…**). Erros: "Nada foi apagado: …", "Não foi desativado: …". Toasts: "N Amigos desativados · N assinaturas canceladas no Mercado Pago", "Amigo apagado · N pagamentos mantidos para a contabilidade". Histórico: **desativado**, **reativado**. Dizer "desativar" (nunca "suspender" ou "bloquear") e "apagar" (nunca "excluir" ou "deletar"). **Juntar cadastros** (CAMP-AMIGO-DUP, 21/11/2026, contrato 1.29; só admin): etiqueta **e-mail repetido** na lista e filtro **Repetidos** (o mesmo e-mail em mais de um cadastro de Amigo); no detalhe, bloco **E-mail repetido** com o botão **Juntar cadastros** em cada outro cadastro. Confirmação **Juntar cadastros?**: "Fica um cadastro só. Passam para o que fica: N pagamentos, N e-mails, o histórico e as notas da equipe…", com assinatura "**A assinatura mensal no Mercado Pago do cadastro que sai será cancelada**: nada é devolvido (sem reembolso)."; escolha **Qual cadastro fica?** (o sugerido leva "(sugerido)"); "Para confirmar, digite JUNTAR"; botão **Juntar cadastros** (**Juntando…**). Erros: "Nada foi juntado: …", "Só dá para juntar cadastros com o mesmo e-mail. Nada foi mudado.", "Para juntar, digite JUNTAR. Nada foi mudado.". Toast: "Cadastros juntados · N pagamentos passaram para o que ficou". Histórico: **cadastro juntado a este**, **juntado a outro cadastro**. No site (plugin 1.39.1, LGPD), quem faz nova adesão com o e-mail de um Amigo ativo vê só a mensagem genérica "Se este e-mail já tiver um cadastro de Amigo ativo, enviamos para ele um link de acesso à Área do Amigo. Confira sua caixa de entrada." e o link de acesso (TR22) vai para o e-mail; nunca dizer na tela pública se um e-mail é de Amigo nem até quando. Dizer "juntar" para cadastros de Amigo (nunca "mesclar", que é dos projetos). **Amigo pela doação de acervo** (CAMP-DOA-AMIGO, 21/11/2026, contrato 1.30): na lista, origem **doação de acervo**; no detalhe, **Origem** "doação de acervo CAMP-AAAA-NNNNNN" (abre a doação).
**Cobranças avulsas** (CAMP-COB, 19/11/2026, contrato 1.19): item do menu em Público e processos, tecla R, só admin e master (operador e leitura não veem o item e a API responde 403). Cobrança pelo Mercado Pago fora do Amigos. Botões: **Nova cobrança**, **Criar cobrança**, **Sincronizar agora**, **Exportar CSV**, **Abrir**, **Copiar link**, **Copiar texto para WhatsApp**, **Abrir no WhatsApp**, **Enviar por e-mail**, **Gerar novo link**, **Consultar no Mercado Pago**, **Cancelar cobrança**. Finalidades: **Doação de acervo — tratamento/digitalização**, **Doação**, **Patrocínio**, **Serviço**, **Outro**. Situações: **Aberta**, **Pagamento em análise**, **Paga**, **Vencida**, **Cancelada**, **Recusada**, **Estornada**, **Sem link**. Números do topo: **abertas** (a receber), **pagas** (com o líquido), **vencidas**. Bloco **No extrato do Mercado Pago**: **Título do item**, **Referência** (CAMP-COB-n), **Na fatura do cartão** (CAMP DOACAO…), **ID do pagamento**; na criação, a prévia **Como vai aparecer no Mercado Pago**. E-mail só pelo Sender (template **TR27 · Cobrança avulsa**); sem template: "não enviado: falta o template TR27 (Cobrança avulsa) do Sender no site. Crie no Sender e cole o ID na administração do site, Apoios → Mercado Pago → E-mails pelo Sender (avise quem cuida do site)". Site antigo: "O site ainda não cria cobranças avulsas: avise quem cuida do site (plugin da CAMP 1.29.0 ou mais novo)." Campo opcional **Link do contrato para assinatura** (CAMP-DOA-CONTRATO, contrato 1.25): com ele, **Enviar por e-mail** manda antes o e-mail do contrato (TR30) e depois o da cobrança (TR27); toast "Enviados dois e-mails pelo Sender: o contrato (TR30) e a cobrança (TR27)".

**Doações de acervo** (CAMP-DOA-ACERVO, 20/11/2026, contrato 1.20): item do menu em Público e processos, tecla J, só admin e master. Intenções de doação de acervo enviadas pelo formulário do site **Intenção de doação de acervo**. Botões: **Sincronizar agora**, **Ver o formulário no site**, **Salvar**, **Gerar cobrança no Mercado Pago** / **Gerar novo link de pagamento**, **Copiar link**, **Consultar no Mercado Pago**. Filtro: **Pedem ação** (até o acervo chegar: só **Acervo recebido pela CAMP**, **Não aprovada** e **Arquivada** saem; CAMP-DOA-LISTA), **Todas as etapas** e cada etapa. Etapas: **Em análise**, **Aguardando informações do proponente**, **Visita agendada**, **Aprovada**, **Não aprovada**, **Contrato enviado para assinatura**, **Contrato assinado pelas partes**, **Cobrança enviada (Mercado Pago)** e **Contribuição paga · Amigo por 12 meses** (essas duas o sistema marca), **Acervo recebido pela CAMP**, **Arquivada (desistência ou sem retorno)**. Campos da equipe: **Link do contrato**, **Data em que as duas partes assinaram**, **Contribuição acordada no contrato** (mínimo R$ 1.000), **Caixas**, **Rolos**, **Volume físico estimado**, **Quantidade catalogada**, **Código do fundo**, **Nova nota interna**. A quantidade de quem oferece é **estimativa** (faixa), nunca contagem. Números do topo: **novas**, **pedem ação** ("até o acervo chegar"), **aguardando pagamento**, **contribuições pagas** (com "N acervos a receber"). Site antigo: "O site ainda não tem as intenções de doação de acervo: avise quem cuida do site (plugin da CAMP 1.30.0 ou mais novo)." **Contrato e avisos** (CAMP-DOA-CONTRATO/AVISOS, 20/11/2026, contrato 1.25): campo **Link do contrato para assinatura** (http/https; **Abrir o contrato**); botão **Enviar contrato para assinatura** abre a prévia: **Para:** (nome e e-mail), **E-mail 1 · Contrato para assinatura** (TR30, com o link, o valor combinado e **Assinar até (opcional)**), **E-mail 2 · Cobrança no Mercado Pago** (TR27, separado) com a caixa **Gerar a cobrança junto** (marcada com R$ 1.000 ou mais); botões **Enviar** e **Voltar**. Sem o TR30: "Nada foi enviado: falta o template TR30 (Contrato para assinatura) do Sender. Crie no Sender e cole o ID em E-mails → Modelos do Sender." Contrato enviado e cobrança com problema: "O contrato foi enviado, mas a cobrança não foi gerada: … Use Gerar cobrança no Mercado Pago para tentar de novo." A cobrança abre a partir de **Contrato enviado para assinatura** (decisão do Rafael). Ao mudar a etapa: caixa **Avisar a pessoa por e-mail** (TR31 · Andamento da doação; marcada em Aguardando informações, Visita agendada, Aprovada, Não aprovada, Contribuição paga e Acervo recebido; desmarcada em Arquivada; não aparece em Em análise, contrato e cobrança), **Texto do aviso** (pronto para a etapa, editável) e **Mensagem (opcional)**. Sem o TR31: "Etapa mudada, mas o aviso não saiu: falta o template TR31 (Andamento da doação) do Sender…". Bloco **E-mails desta doação**. Configuração `doacao.avisar_pagamento` (pagamento confirmado avisa sozinho). Site antigo: "O site ainda não manda o contrato para assinatura: avise quem cuida do site (plugin da CAMP 1.34.0 ou mais novo). Nada foi enviado." **Assinatura eletrônica (Autentique)** (CAMP-AUTENTIQUE, 20/11/2026; guia `docs/autentique.md`): bloco recolhível no fim da tela, com **Token da API da Autentique** (some depois de salvo: "configurado"), **E-mail de quem assina pela CAMP (opcional)**, caixa **Ligada** e botões **Salvar**, **Testar conexão**, **Apagar o token**; ao lado do título "· ligada" / "· desligada". Na prévia do envio, com ela ligada: **Anexar o PDF do contrato** (só PDF, até 5 MB) ou **Usar o link colado**. No detalhe, bloco **Assinatura eletrônica (Autentique)** com a situação (**Criado na Autentique (o e-mail ainda não saiu)**, **Aguardando assinaturas**, **Assinado por todos**, **Recusado na Autentique**), "N de M assinaram" e o botão **Conferir assinatura agora**. Frases: "Contrato criado na Autentique e e-mail com o link de assinatura enviado (TR30 pelo Sender).", "Todos assinaram na Autentique: a doação passou a Contrato assinado pelas partes.", "Acabaram os documentos do mês na Autentique (plano grátis: 10 por mês)…", "A Autentique recusou o token…"; erro da Autentique sempre termina em "Nada foi enviado." Dizer "Autentique" (nunca "API de assinatura") e "link de assinatura". **Dados para o contrato** (CAMP-DOA-TEXTO, 20/11/2026): no detalhe, botão **Copiar dados para o contrato** e caixa **Incluir notas internas** (desmarcada: as notas ficam fora); o texto simples também aparece na caixa **Texto para o contrato (se não colar, selecione aqui e copie)**. Seções do texto: "Intenção de doação de acervo — CAMP" (protocolo e **Recebida em**), **DADOS DA PESSOA**, **FORMULÁRIO (pergunta e resposta)** (as perguntas exatamente como no formulário do site), **DADOS COMBINADOS (equipe)** e, só com a caixa, **NOTAS INTERNAS**. Intenção com os dados apagados: "dados apagados (LGPD)". Frases: "Dados copiados: cole no e-mail ou no documento do contrato", "Não deu para copiar sozinho: o texto está selecionado na caixa abaixo; copie com Ctrl+C". **CPF/CNPJ, endereço e valor proposto** (CAMP-DOA-CPF, 20/11/2026, contrato 1.26): no detalhe, linhas **CPF ou CNPJ**, **Endereço** e **Valor proposto pela pessoa** (ao lado da **Contribuição acordada no contrato**; "A combinar com a equipe" quando a pessoa não escolheu valor); bloco recolhível **CPF/CNPJ e endereço (para o contrato)** com **CPF ou CNPJ**, **CEP**, **Rua, avenida (logradouro)**, **Número**, **Complemento**, **Bairro**, **Cidade**, **UF** (corrigir e **Salvar**). No texto para o contrato: "CPF: 123.456.789-09" ou "CNPJ: …" e "Endereço: Rua X, 123, apto 4 — Bairro — Cidade/UF — CEP 01234-567". Site antigo: "CPF/CNPJ e endereço não foram guardados: o site ainda não tem esses campos (plugin da CAMP 1.35.0 ou mais novo). Avise quem cuida do site." Nunca "RG", "documento de identidade" nem "dados cadastrais". **Importar ficha (CSV do Google Forms)** (CAMP-DOA-IMPORTAR, 20/11/2026, contrato 1.27): botão na tela Doações de acervo (só admin), para a antiga "Ficha de Doação de Acervo". Primeiro a **Simulação** (nada muda), com uma linha por resposta: **vai criar**, **vai completar (campos vazios)** ou **já igual**, a coluna **Etapa** (só nas que vão ser criadas; padrão Em análise) e os **Avisos**; botão **Importar**. Resultados: "criada (nenhum e-mail enviado)", "completada", "já estava importada". Toast: "Importado: N linhas. Nenhum e-mail foi enviado." No texto para o contrato, a seção **FICHA DE DOAÇÃO (Google Forms)** (com **Enviada em**). Site antigo: "O site ainda não importa a ficha: avise quem cuida do site (plugin da CAMP 1.36.0 ou mais novo)." Dizer "ficha" (a do Google Forms) e "formulário" (o do site). **Acervo recebido → fundo e arquiteto** (CAMP-DOA-FUNDO, 21/11/2026; sem mudar o contrato com o site): ao escolher a etapa **Acervo recebido pela CAMP**, o bloco com a caixa **Criar fundo e arquiteto agora** (marcada; desmarcada = o caminho de sempre, código digitado em **Código do fundo**) e a prévia "Vai criar o fundo F0xx · <nome> e o arquiteto <nome>" (ou "Vai usar o fundo F0xx · <nome> com o arquiteto <nome> (já cadastrado)"; doação que já tem fundo: "Esta doação já tem o fundo F0xx · <nome>: vai usar o mesmo."). Campos **Nome do arquiteto**, **Tipo** (as opções da tela de Fundos), **Nome do fundo**, **Sigla (3 letras; pode ficar para depois)**; com arquiteto ou fundo de mesmo nome: **Usar o existente: <nome>** ou **Criar novo**; botão **Atualizar a prévia**. Confirmação "Acervo recebido pela CAMP" com **Criar e salvar** e **Voltar**. Toast: "Criado o fundo F0xx · <nome> e o arquiteto <nome>. Acervo recebido: etapa enviada ao site." Site falhou: "O fundo F0xx ficou criado no painel, mas o site não recebeu a etapa: … Tente de novo: o mesmo fundo será usado." No detalhe: "Fundo: F0xx · <nome> · arquiteto <nome>" (com "o site ainda não recebeu: use Salvar de novo" se falhou); na página do fundo: "Origem: doação de acervo CAMP-AAAA-NNNNNN". Dizer "fundo" e "arquiteto" (nunca "agente" na tela). **Conferir Amigos das doações pagas** (CAMP-DOA-AMIGO, 21/11/2026, contrato 1.30; só admin): botão na tela; prévia com cada doação ("contribuição paga, sem cadastro de Amigo" ou "cobrança avulsa paga pelo mesmo e-mail (será ligada à doação)"; "vai criar o cadastro de Amigo" ou "já é Amigo (CAMP-…): +12 meses"); botão **Criar o Amigo** / **Criar os Amigos** (**Criando…**); sem nenhuma: "Nenhuma doação paga sem cadastro de Amigo. Nada a fazer."; toast "N Amigos criados ou estendidos pelas doações pagas". No detalhe da doação: "Amigo da CAMP até … · **ver o Amigo** CAMP-…", etiqueta **sem cadastro de Amigo** ("A contribuição foi paga, mas o Amigo não foi criado. Use Conferir Amigos das doações pagas.") ou "Vira Amigo da CAMP quando a contribuição for paga.". Site antigo: "O site ainda não confere os Amigos das doações pagas: avise quem cuida do site (plugin da CAMP 1.39.0 ou mais novo)." **Central da doação** (CAMP-DOA-CENTRAL, 21/11/2026; sem mudar o contrato com o site): a lista tem as abas **Em andamento** (padrão; até o acervo chegar), **Recebidos**, **Não aprovadas e arquivadas** e **Todas** (com o número de cada uma); o número do topo **em andamento** ("até o acervo chegar"); colunas **Recebida**, **Quem oferece**, **Acervo**, **Etapa** (com a situação do pagamento) e **Próximo passo** (com "N tarefas atrasadas" ou "N tarefas a fazer" e o fundo). No detalhe: a linha de etapas **Intenção recebida**, **Em análise**, **Visita**, **Aprovada**, **Contrato enviado**, **Contrato assinado**, **Cobrança enviada**, **Contribuição paga**, **Acervo recebido**, **Fundo criado** (cada uma com a data, ou **próximo passo**, **falta**, **não se aplica**) e a frase **Próximo passo:** (Analisar a proposta, Visitar o acervo, Decidir a aprovação, Enviar o contrato, Aguardar a assinatura do contrato, Gerar a cobrança, Aguardar o pagamento, Receber o acervo, Criar o fundo). Bloco **Próximos passos** (tarefas internas): aviso **Contrato assinado: defina os próximos passos (frete, embalagem…).**, botões **Usar roteiro de logística**, **Nova tarefa**, **Editar**, **Apagar** (confirmação **Apagar tarefa**), **Criar tarefa** / **Salvar tarefa** e **Voltar**; campos **O que fazer**, **Responsável**, **Prazo**, **Situação** (**A fazer**, **Fazendo**, **Feita**, **Não se aplica**), **Valor (R$, opcional)**, **Nota**; resumo "N de M feitas · N atrasadas · Custos: previstos … · feitos … · a fazer …". Roteiro de logística: **Cotar frete**, **Comprar insumos de embalagem**, **Agendar retirada/visita de embalagem**, **Embalar o acervo**, **Transporte**, **Receber e conferir na CAMP**, **Higienização/acondicionamento**, **Catalogação inicial**. Bloco **Nota interna** com **Salvar nota**. Bloco **Arquivos**: tipos **Contrato assinado**, **Contrato (minuta ou outro)**, **Orçamento**, **Nota fiscal ou recibo**, **Foto**, **Outro documento**; campos **Tipo**, **Da tarefa (opcional)**, **Arquivo (PDF, JPG, PNG, WEBP, XLSX ou DOCX; até 15 MB)**; botões **Anexar**, **Apagar** (confirmação **Apagar arquivo**) e **Baixar contrato assinado agora**; "baixado da Autentique". Frases: "O conteúdo do arquivo não é PDF de verdade (a extensão não bate com o arquivo).", "Contrato assinado baixado da Autentique e guardado nos arquivos.". Bloco **Histórico** (um só) com o filtro **Tudo**, **Notas**, **E-mails**, **Tarefas**. Na página do fundo: link **Contrato assinado** ao lado da origem. Dizer "próximos passos" e "tarefa" (nunca "checklist" ou "to-do" na tela) e "arquivo" (nunca "anexo" na tela).
**E-mails** (CAMP-EMAIL, 20/11/2026; Rafael: "Todos os e-mails num lugar só"): item do menu em Administração, sempre à vista (fora do "Mais"), logo abaixo de Máquinas, tecla E, só admin e master (operador e leitura não veem o item; as rotas da API respondem 403). Uma tela com três abas: **Enviados** (`#emails`), **Modelos do Sender** (`#emails/modelos`) e **Quem aceita e-mails** (`#emails/aceite`); ← → trocam de aba. Os endereços antigos `#emailsite` e `#emkt` abrem a aba certa. Ao citar um lugar: "E-mails → Modelos do Sender", "E-mails → Quem aceita e-mails". Não usar mais "E-mails enviados", "E-mails do site" nem "Quem aceita e-mails da CAMP" como nome de tela ou de menu.
**E-mails → Enviados** (CAMP-EMAIL, 18/11/2026, contrato 1.14; antes a tela "E-mails enviados"). Uma lista com todo e-mail que saiu do painel e do site. Colunas: **Data**, **Destinatário**, **Assunto / modelo** ("TRnn · nome do modelo"), **Canal**, **Origem**, **Situação**. Canais: **Sender**, **E-mail simples do site**, **SMTP do painel**. Origens: **Formulário do site**, **Visita**, **Inscrição**, **Amigos da CAMP**, **Entrega de material**, **Downloads (uso do acervo)**, **Alerta interno**, **Resumo do dia**, **Cobranças e doações**. Situações: **Enviado**, **Falhou** (com o motivo), **Não saiu pelo Sender** (foi o e-mail simples do site; com o motivo), **Na fila**. Números do topo: **enviados hoje**, **enviados em 7 dias**, **falhas em 7 dias**, **não saíram pelo Sender**. Filtros: período (Hoje · Últimos 7/30/90 dias · Tudo), canal, origem, modelo; busca por "e-mail, nome ou protocolo"; **Exportar CSV**; **Sincronizar agora**. No detalhe: **Variáveis enviadas**, **Texto**, e no Sender "entregue, aberto ou clicado: ver no Sender". Site antigo: "O site ainda não manda os e-mails dele: avise quem cuida do site (plugin da CAMP 1.25.14 ou mais novo)."
**E-mails → Modelos do Sender** (CAMP-SENDER, 20/11/2026, contrato 1.23; antes a tela "E-mails do site", `#emailsite`): aba da tela E-mails, também aberta pelo link em Configurações → E-mail e avisos; só admin e master (para os outros o link some e a API responde 403). Todos os modelos TR do Sender (TR04–TR31), agrupados por área: **Pedidos e visitas**, **Cursos e inscrições**, **Amigos da CAMP**, **Área do Amigo**, **Ingressos**, **Cobranças e doações**, **Acervo**. Colunas: **Modelo** ("TRnn · nome", quando sai, para quem), **Variáveis** (com **Copiar**), **ID no Sender** (com **Salvar**; vazio = deixar sem ID, com confirmação), **Situação**, **Último envio** (e falhas em 30 dias), **Enviar teste**. Situações: **Ativo**, **Sem ID — sai e-mail simples**, **Sem ID — não sai**, **Sem ID — login não abre**, **Sem ID — o painel manda**, **Sem ID — não usado**, **Sem chave do Sender**, **Sender desligado (emergência)**; etiqueta **crítico** (TR12, TR15, TR22, TR27, TR30 sem ID). Números do topo: **ativos**, **faltando**, **críticos**, **falhas em 30 dias**. Botões: **Baixar guia dos modelos (.md)** (um .md por modelo, num .zip), **Abrir no Sender**. "Enviar testes para" começa com o e-mail de quem está no painel.
**E-mails → Quem aceita e-mails** (18/11/2026, contrato 1.15; antes a tela "Quem aceita e-mails da CAMP", `#emkt`, tecla Y — a tecla Y ficou livre): aba da tela E-mails, só admin e master. Quem marcou a caixa opcional "Quero receber e-mails da CAMP" num formulário do site; o site põe cada pessoa sozinho no grupo do Sender. Situação no Sender: **No Sender** (`inscrito`), **Pendente** (`pendente`: na fila, sem grupo ou sem a chave do Sender no site), **Com erro** (`erro`), **Cancelou** (`cancelou`: descadastrou no Sender, foi apagada lá ou saiu da lista no painel), **Sem dado do site** (`sem`: o site ainda não contou). Números do topo: **aceitam e-mails**, **no Sender**, **ainda não entraram**, **cancelaram**. Filtros: busca, **De onde veio**, **aceitou de … até**, situação. Botões: **Sincronizar agora**, **Exportar CSV**, **Exportar selecionados**, **Limpar seleção**, **tirar da lista**, **devolver à lista**. Coluna **Texto aceito** = versão do texto da caixa. Na lista dos Amigos: coluna e filtro **Aceita e-mails** (aceita · cancelou · não).
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
- Mudar a publicação de um projeto ou fundo (Publicar, Voltar para rascunho, Despublicar) é tarefa (15/11): chip "⏳ Despublicando F002-P0147 · 37 de 120 folhas";
  o 2º clique diz "Já está rodando: o andamento fica no topo da página."; as que falharam ficam listadas com **Tentar de novo só estas N**.
  Escrita que passa de 1 min sem resposta nunca diz "Tente novamente": "O painel parou de esperar a resposta (mais de 1 min), mas a ação pode continuar no servidor. Não repita agora…".
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

## Central de Problemas (CAMP-PROB-UX, 22/11/2026 — documento do Rafael "Redesenho da Central de Problemas")
- O título da página continua **Problemas** (o nome do menu; o mockup dizia "Central de Problemas": a troca é decisão do Rafael). Subtítulo:
  "**N itens precisam de análise, conferência ou decisão.**"
- Cartões (como no mockup: número, ícone à direita, rótulo): **Problemas em aberto** (a dica diz "N pedem ação · N avisos"), **Críticos**,
  **Em análise**, **Aguardando conferência** (= fase Aguardando revisão), **Resolvidos (30 dias)**. Cada cartão abre a lista filtrada.
- Abas (pílulas, a ativa cheia de azul, com a contagem entre parênteses): **Prioridades** · **Minha fila** · **Todos** · **Concluídos**. Filtros rápidos: **Críticos**, **Sem responsável**, **Aguardando minha
  revisão**, **Mais antigos**, **Resolvíveis agora**, **Avisos**, **Podem já estar resolvidos**. Botões **Filtros** (gaveta no celular:
  **Fechar**, **Ver resultados**), **Limpar filtros**, **Salvar visão**, **Visões salvas (N)**, **Apagar esta visão**, **Ordenar por**
  (**Prioridade**, **Mais recentes**, **Mais antigos**, **Mexidos por último**), **Por página**, "**Mostrando X–Y de N problemas**", páginas numeradas com ← →.
- Severidade (sempre texto + cor + ícone): **Crítico** (!, vermelho; = "bloqueia"), **Médio** (▲, âmbar; = "corrigir"), **Baixo** (i, azul;
  = "aviso"). Severidade é o impacto; a **fase** é o andamento do trabalho — conceitos diferentes.
- Fases: **Novo** → **Em triagem** → **Em análise** → **Aguardando revisão** → **Resolvido**, e **Aguardando informação**, **Devolvido**,
  **Reaberto**, **Duplicado**, **Inválido**. Na linha: ícone de calendário com "há N dias", ícone de pessoa com o responsável ou **Sem responsável**, a pílula da severidade, **N problemas nesta folha** (UX-64), o motivo da prioridade ("Crítico: bloqueia a
  publicação · autoria conflitante", "aguardando revisão há N dias", "avisado por visitante do site", "projeto no site com este
  problema"), **resolução rápida**, **pelo sistema**. UMA ação: **Analisar** / **Continuar** / **Revisar** / **Ver**, e **⋯** (**Pegar para mim**,
  **Copiar link**, **Só este projeto**). O motivo é a frase da Home ("Prioridade alta porque impede a publicação e aguarda há N dias")
  mais o impacto ("· autoria conflitante").
- Títulos curtos (o que está errado): **Autoria não confirmada**, **Folha pode ser de outro projeto**, **Registro duplicado no acervo**,
  **Folha virada**, **Folha digitalizada pelo verso**, **Código errado**, **Informação errada ou faltando**, **Crédito errado ou faltando**,
  **Arquivo da imagem danificado**, **Problema relatado**, **Folha retirada pelo CAMP Vision**, **Folha recusada na importação**.
- Painel: **Contexto**, **Qual é o problema?**, **Fontes e hipóteses** (autoria: "O painel não sugere autoria nem fonte"), **Evidências**,
  **O que precisa ser decidido?** ("Para resolver: conclusão + evidência ou justificativa" / "+ fonte ou evidência"), **Resposta**
  (**Modelo de decisão**, **Salvar o texto como modelo**, **Conclusão / parecer**, **Evidência**, **Hipótese a que se refere**,
  **Justificativa ou motivo**, **Adicionar evidência**), botões **Resolver**, **Enviar para revisão**, **Aprovar e resolver**, **Devolver**,
  **Começar análise**, **Retomar a análise**, **Em triagem**, **Suspender: aguardando informação**, **Não é problema**, **Duplicado do nº**
  + **Juntar como duplicado**, **Reabrir** (com **Justificativa para reabrir**), **Pegar para mim**, **Devolver**, **Atribuir a…** (só
  admin; a regra da Home), **Histórico**. Confirmações
  discretas: "Resolução validada", "Problema enviado para revisão", "Devolvido para quem resolveu", "Problema reaberto", "Fechado: não é
  problema", "Juntado como duplicado". Rascunho: "O rascunho é salvo sozinho enquanto você escreve" / "Rascunho salvo às HH:MM (UTC)".
- **Mais ⋯**: **Contadores por fundo** ("A proporção é sobre as folhas já avaliadas…"; colunas **Abertos**, **Críticos**, **Folhas
  avaliadas**, **Avaliadas com problema**), **Modelos de decisão**, **Mensagens repetidas…**, **Limpeza geral…**. Lote: **Atribuir a**
  (**Ninguém (tirar)**) + **Atribuir**, **Selecionar os N desta página**.
- Coluna da direita (começa no topo, ao lado do título): **Seu progresso na resolução** (selo hexagonal, **Ver metas**; o nível e os pontos da **Home**, "N até o nível N"; **Ocultar minhas conquistas** /
  **Mostrar de novo**, a mesma preferência da Home), **Meta da semana** (da equipe, "N de M pontos validados", a mesma da Home),
  **Conquistas recentes** (**Ver todas**; selos coloridos; as de qualidade da Central, sem pontos: **Primeira resolução validada**, **Investigador documental**, **Colaborador**,
  **Revisor cuidadoso**, **Fundo organizado** — coletiva; e as da Home, "da Home"), **Ranking da equipe (mês)** (ligado por padrão,
  decisão do Rafael de 22/11/2026; o mesmo da Home: posição, nome e "N pontos" validados no mês) com o **?** que diz "Pontos validados de cada pessoa
  neste mês…" e "Reconhecimento, não avaliação: não serve para avaliar desempenho. Nunca use estes números para avaliar ninguém.",
  **Atividade recente** (ícones: resolvido, evidência, atribuído, registrado; **Ver histórico de atividades** só para admin). Gráficos: **Problemas por tipo** ("abertos agora") e **Evolução de resolução** ("últimas 4 semanas": resolvidos por
  pessoas, pelo sistema, novos).
- Nunca: "streak", "dias seguidos", medalha por velocidade, percentual sem base, ranking sem o aviso de que não serve para avaliar desempenho.

## Regras de texto
- Erro do CAMP Vision: primeiro o que aconteceu em linguagem de gente ("4 imagens têm o nome do autor longo demais no EXIF; ele foi cortado. Não impede publicar."), depois o que fazer; a mensagem técnica fica em **Ver detalhes técnicos** (fechado). UX-08.
- Chips de estado em minúsculas; botões, filtros e títulos com inicial maiúscula.
- **Nunca** usar: "no ar", "fora do ar", "colocar no ar", "tirar do ar", "retirar da publicação", "não pública".
- **Nunca** mandar a pessoa ao WordPress ("wp-admin", "corrija no WordPress"): quem usa o painel não entra no site. A ação é um botão do painel; o que só se resolve no site é "avise quem cuida do site" (padroes.md §15).
- "Desativar/Reativar" é só para **contas de usuário**, **2FA** e **Amigos da CAMP** (pedido do Rafael, 21/11/2026), nunca para conteúdo do acervo.
- Valores internos (`no_ar`, `fora_do_ar`, `tirar_do_ar` na API) ficam como estão por compatibilidade; só os rótulos mudam.
- Em português do Brasil, concordância normal: "projeto publicado", "folha publicada".

## Quem vê o quê (modo operador, 13/10/2026)
- Operador e leitura não veem nomes de sistema: nada de "Tainacan", "WordPress" ou "logado no WordPress" nos textos deles. Diga "o site", "a página pública", "só a equipe vê" (rascunho) e "retirado do público" (despublicado). O `check_ui` reprova "logado no WordPress".
- A tela "Máquinas e site" e o resumo de máquinas do topo (o botão **Estado dos sistemas**) são só para admin. O alerta que impede o trabalho (QNAP, CAMP Vision, site) aparece para todos (redesenho §4).
- Em texto novo, prefira "página pública" / "publicado" a "no site" quando falar do que o visitante vê (exceção: a situação **No site**, acima).
- Mover folhas, mover um lote ou mesclar (15/11/2026): o resultado diz "**N folhas retiradas do público no projeto antigo**" (o registro antigo fica privado no site; nada é apagado), "**N folhas saem do público no projeto antigo em segundo plano**" (lote grande) e "**N folhas ainda por retirar do público (o painel tenta de novo sozinho)**" (site sem resposta).

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

## Visualizador da folha (CAMP-VIEW, 21/11/2026)
- A mesma barra em toda tela que mostra uma folha grande (#item, gaveta **Revisar folha**, tela cheia, tela de conferir), sempre nesta ordem:
  **‹ Anterior** · "N de M" · **Próxima ›** | **↺ Girar à esquerda** · **↻ Girar 90°** · **✂ Recortar e alinhar** (e, na conferência, **Girar 180°**,
  **⇋ Espelhar**, **Desfazer recorte/alinhamento**) | **−** · **N%** · **+** · **Ajustar** | **Abrir a imagem numa aba nova ↗** (e, na conferência,
  **Tela cheia** e **? atalhos**). Girar e recortar só aparecem para quem pode (operador, admin) e quando há prévia do CAMP Vision; o TIF não muda.
- Rodapé da página da folha: "Atalhos: ← anterior · → próxima · R girar 90° · L girar à esquerda · C recortar e alinhar · + − 0 ampliar · E editar".

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
  aba "**Prioridades**" (antes "Abertos"; CAMP-PROB-UX: "Bloqueiam ou pedem correção, na ordem da prioridade (é o número do menu)"). No
  cartão **Em aberto** de Problemas: "**N pedem ação · N avisos**" (Em aberto = os dois juntos; o menu conta só os que pedem ação).
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
- **Indicadores**: **decisões pendentes** (só com decisão), **folhas para conferir** ("em N lotes"), **folhas esperam um admin** (admin; "em N
  lotes: N para aprovar, N para publicar"; decisão do Rafael, 22/11/2026: onde há as duas medidas, o número grande são as folhas) ou
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

## Home em três partes: Ação, Operação e Resultados (CAMP-HOME-UX, documento do Rafael de 22/11/2026)
- A barra do topo (busca, área da página, clima, tarefas, estado das máquinas, menu da pessoa) e a faixa do sistema **não mudam**; o menu lateral também não.
- **Cabeçalho**: a foto (ou as iniciais), a saudação, "N coisas pedem sua atenção hoje", a data e, na mesma linha à direita, o **?**. A
  **Meta da semana** fica na coluna da direita, no cartão do nível ("**Meta da semana · equipe**", "**N de M pontos validados**", "**N%**",
  barra com o valor em texto, "**Como conta?**"; admin: "**Nova meta (pontos)**" + **Salvar a meta**).
- **Indicadores**: os mesmos 4; todos são botões; o "**?**" e a dica "**Como conta:** …" dizem a regra da contagem. **folhas conferidas hoje**
  leva ao gráfico de Resultados.
- **O que fazer agora**: abas **Minha fila** (o que está com você: atribuído, pego por você, ou problema que você relatou) · **Todos** ·
  **Críticos** (nota 60 ou mais) · **Sem responsável**; embaixo, **Tipo**: **Todos os tipos · Decidir · Conferir · Publicar · Resolver ·
  Responder · Melhorar a base**. **Ordenar**: **Prioridade** (o padrão) · Mais urgente primeiro · Mais antigo primeiro · Mais recente primeiro ·
  Por tipo. No máximo 5 linhas e "**Ver todas as N tarefas**" (" da minha fila", " críticas", " sem responsável") / "**Mostrar só as 5 primeiras**".
- **Prioridade** (selo na linha): **Crítico** · **Alto** · **Médio** · **Baixo**, com a frase "**Prioridade alta porque impede a publicação e
  aguarda há 19 dias**" (crítica, alta, média, baixa). Nota de 0 a 100: gravidade (até 40), tempo parado (até 20, para de somar em 14 dias),
  segura a etapa seguinte (até 20), prazo vencido ou risco público (até 20). A linha urgente mantém o **!** no selo.
- **Responsável**: nome curto (ou "**Você**") com as iniciais; sem dono: "**Sem responsável**". No **⋯**: **Pegar para mim** · **Devolver (tirar
  meu nome)** · **Atribuir a…** (admin) · **Tirar o responsável** (admin). Resultado: "Você ficou com: <título>." / "Atribuída a <nome>: …" /
  "Sem responsável agora: …". Minha fila vazia: "**Nada está com você agora.** Pegue uma tarefa da fila: no “⋯” da linha, Pegar para mim." +
  **Ver todas as N tarefas**. Críticos vazio: "Nenhuma tarefa crítica agora." Sem responsável vazio: "Todas as tarefas têm responsável."
- **O caminho do material**: **gargalo** (amarelo) = o passo onde os lotes esperam há mais tempo, somando as horas de todos — selo
  "**gargalo: espera há mais tempo**" e "**N lotes aguardando há até X dias**"; o passo com mais lotes, se não é o gargalo, diz "**maior volume**".
  Passo zerado mostra **✓**.
- **Resultados**: período **7 dias · 14 dias · 30 dias · 90 dias** para o ritmo (14 = "últimas 2 semanas") e as visitas (7, 30 e 90);
  "**Frente aos N dias anteriores**" só quando o período anterior teve alguma folha conferida; **Ver relatório completo**.
- **Seu progresso**: "**Nível N · <nome>**" (Primeiros passos · Olhar atento · Mão firme · Guardião do Acervo · Memória viva · Referência do
  acervo), "**N / M XP**", **Suas conquistas** (marcos pessoais, nunca comparação), "**Próxima: …**", "N dias seguidos com trabalho validado"
  (fato neutro, sem cobrança), **Como os pontos são contados?**, **Ocultar conquistas** / **Mostrar de novo**. **Ranking da equipe (mês)**
  (ligado por padrão; "N pontos" validados no mês por pessoa, com a posição; o **?** diz que não serve para avaliar desempenho e que "Um admin desliga
  o ranking em Configurações"; vazio: "Ninguém pontuou neste mês ainda."). Em **Configurações › Progresso e ranking**: a caixa "**Mostrar o Ranking
  da equipe (mês) na Home e em Problemas**" (qualquer admin; avisos "Ranking da equipe ligado" / "Ranking da equipe desligado"). **Pontos validados**: só ações que continuam valendo (desfez, o ponto some); descartar decisão e "não era problema" não contam.
- **Qualidade da base**: "**O que mais baixa o índice**" com as duas medidas mais baixas, "faltam N folhas" e o caminho (**Registrar os direitos
  nos fundos →**, **Dar título às folhas →**, **Ver os projetos →**).
- **Está tudo funcionando?**: tudo normal = "**Tudo funcionando · N sistemas normais**" (e "· N sem medida") com "**Ver cada sistema (…)**"
  recolhido; com falha, só o que falha aberto e "**Ver N outros sistemas (…)**".

## Home no desenho da maquete (CAMP-HOME-UX, maquete do Rafael de 22/11/2026)
- Barra do topo e menu lateral **não mudam**. **Entenda esta página** chega sempre fechada numa linha (o **?** abre a caixa inteira).
- **Cabeçalho**: foto grande (ou as iniciais), a saudação, "N coisas pedem sua atenção hoje", a data e o **?** na mesma linha (sem cartão de meta).
- **Indicadores**: ícone colorido (pasta · camadas · triângulo · ✓), número grande, rótulo e a linha cinza; a seta e o "?" aparecem ao passar o mouse.
- **O que fazer agora**: abas com o número em selo e, à direita, "**Ordenar:**"; cada linha = barra colorida, miniatura, nome, linha cinza
  ("Tipo · lote · código · fundo · responsável"), selo **Crítico** / **Alto** / **Médio** / **Baixo**, "**Há N dias**" / "**Há N h**" /
  "**Há menos de 1 h**" (a frase inteira na dica), UM botão e **⋯**. A frase "Prioridade … porque …" fica na dica da linha e do selo.
- **O caminho do material**: 7 cartões lado a lado (número, nome, subtítulo curto — **Estações de captura**, **Pastas enviadas**, **Leitura das
  folhas**, **Trazer para o painel**, **Folha por folha**, **Um admin confirma**, **Enviar ao site** —, a quantidade com a unidade e ✓ verde
  quando nada espera); o gargalo em amarelo. Ajuda: "**Como funciona o fluxo?**" (as cores e as unidades).
- **Folhas conferidas por dia**: período numa caixa de escolha (**7 dias · 14 dias · 30 dias · 90 dias**); 4 números (Total no período, Média
  por dia de trabalho, Hoje, até agora, e a variação "**Frente aos N dias anteriores**" com seta); "Cada barra é um dia corrido…" em **Ver os números**.
- **Visitas ao site**: à esquerda **Visitas no período**, **Média por dia** e a variação "**vs. período anterior**"; à direita o gráfico.
  Sem dados: "**Dados de audiência temporariamente indisponíveis**" numa caixa compacta, com **Tentar de novo**. **Projetos mais visitados**
  é outro cartão ("os 5 primeiros", **Ver análise completa de visitas →**).
- **Coluna da direita**: cartão azul-marinho "**Nível N · <nome>**", "N / M XP", "**Faltam N XP para o nível N+1**" e, abaixo de uma linha, a
  2ª seção "**Meta da semana · equipe**" com o alvo, "**N de M pontos validados**", o **N%** e a barra verde, **Como conta?** (leitura e
  conquistas ocultas: o mesmo cartão só com a meta; jogo desligado: some tudo); **Suas conquistas** com 3
  selos (**N folhas conferidas** · **N lotes aprovados** · **N dias de sequência**; cinza quando zero) e **Ver todas →** (os marcos, Próxima,
  Como os pontos são contados?, **Ocultar conquistas**). **Está tudo funcionando?**: uma linha por sistema, ✓ e "**Online**" (cópias:
  "**Em dia**"); o que falha vem primeiro com o selo e a frase; **Ver detalhes e histórico →**. **Qualidade da base**: o índice, "**↓ −N p.p.**"
  só com comparação ("sem comparação ainda"), 4 barras, **Como o índice é calculado? →** e **O que mais baixa o índice →**. **Quanto do acervo
  já está no site**: donut com o % e "N de M folhas publicadas"; legenda **No site** · **Em preparo** (ainda não conferida) · **A publicar**
  (conferida, fora do site); embaixo Projetos e Fundos com página. **Melhorias de hoje**: linhas com ✓ ("+N edições na base", "N folhas
  conferidas", "N lotes aprovados", "N decisões respondidas", "N problemas corrigidos"); vazio: "Nenhuma melhoria registrada hoje ainda.";
  por pessoa em **Ver histórico de melhorias →**.

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
  tentativa**" (não sai de novo no clique seguinte).
- CAMP-FIX (15/11/2026): folha em que o painel não vê diferença para o site **não é falha**: a correção fecha e sai da fila. Resultado:
  "**Enviadas** · **já estavam iguais no site** · **falharam** · **ainda na fila**"; no andamento, "{código}: **já estava igual no site**";
  na mensagem, "N já estavam iguais no site". "ainda na fila" explica o resto: "(N esperam a próxima tentativa; N podem sair já: no
  máximo 50 por rodada, envie de novo)". No Histórico da folha: "**correção fechada: já estava igual no site**".
- Termo que o site não tem (CAMP-FIX 15/11/2026): "**O arquiteto “Nome” não existe no site: envie o fundo F0xx ao site primeiro
  (Fundos → F0xx → Enviar fundo ao site)**" (o mesmo para o fundo). O painel procura o termo pelo nome no site antes de dizer isso.
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
- No Histórico de ações: "{quem} mandou ao site as correções e escritas que estavam esperando" · "N enviadas, N já estavam iguais no site, N falharam, N ainda na fila" (a parte "iguais" só quando há).

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
- **Cópias** (10/11/2026, Rafael: "fotos repetidas 2–3 vezes: JPG, DNG e TIF. Deixe só uma."): a folha marcada como cópia de outra
  (duplicata) não aparece na grade/lista nem entra nas contas da página (**Folhas (N)**, "N folhas", "**Conferidas X de N**", a barra da
  conferência, "**N de M**" da revisão). O cartão da folha que fica mostra **+N cópias (DNG, JPG)** (os formatos quando o painel sabe; âmbar
  quando alguma cópia ainda espera conferência), que abre **Conferir as duplicatas lado a lado**. O filtro **Cópias (N)** mostra só as
  cópias, cada uma com o selo **cópia de Dxxxxx**. Nada é apagado: a cópia só não vai ao site. Nunca "excluída" nem "apagada".
  A cópia sem conferir não impede **Aprovar lote** nem conta em "Faltam conferir" (projeto, Fila, Material novo); no resumo do lote
  aparece à parte: "**N cópias sem conferir** (não impedem aprovar)". Na lista de Projetos, "N folhas" também não conta as cópias.
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

## Fundo sem legendas no site (10/11/2026, contrato painel ↔ site 1.9)
- Caixa no "Editar" do fundo, grupo "Aparece na página pública": **Sem legendas nas imagens do site** — "As fotos e desenhos deste fundo
  aparecem no site sem o texto embaixo da imagem (título, ano). A ficha de cada folha e o crédito da foto continuam."
- Ao salvar: "· as legendas do site mudam em seguida" (fundo no site) ou "· vale no site quando o fundo for enviado ao site".
- Histórico: **"sem legendas nas imagens" enviado ao site**; divergência do "Enviar fundo ao site": **Sem legendas nas imagens do site**.
- Site antigo: "O site ainda não conhece "sem legendas" (plugin da CAMP 1.23.24): atualize o site; vai quando ele tiver".
- "Legenda" aqui é só o texto embaixo da imagem no site. Não confundir com "ler e legendar" do CAMP Vision (dados lidos da folha).

## Copiar folhas e seleção de folhas (15/11/2026)
- Ações (Mais ⋯ do projeto): **Copiar folhas para outro projeto** e **Copiar um lote para outro projeto**; botões **Copiar as folhas marcadas** / **Copiar o lote**; confirmação **Copiar as folhas?** / **Criar o projeto e copiar?** (botões **Copiar** / **Criar e copiar**). Resultado: "**N folhas copiadas de F0xx-P0zzz para F0xx-P0yyy**" (+ "(projeto novo)") e "As de F0xx-P0zzz não mudam.", com **Abrir o destino**. Sempre dizer que "as folhas daqui não mudam".
- Cópias visíveis nos dois projetos (15/11/2026, Rafael: "dizendo que tal projeto foi copiado para x projeto"): na Visão geral, coluna da direita, **Folhas copiadas de outros projetos** ("**6 folhas de** Casa de praia Yves E. Josquim (F010-P0735)") no destino e **Folhas copiadas para outros projetos** ("**6 folhas copiadas para** Memorial Residências (F010-P0732)") na origem, cada projeto com link. No cartão da folha: selo **cópia de F0xx-P0yyy · Dnnnnn** (a cópia, com link para a original; o projeto no selo a distingue do **cópia de Dxxxxx** das duplicatas) e **copiada para F0xx-P0yyy** (a original). No **Revisar folha**: "Cópia de F0xx-P0yyy · Dnnnnn (a original continua lá)" / "Copiada para …". Histórico: "**Recebeu N folhas copiadas de F0xx-P0yyy**" (destino) e "**Copiou N folhas para F0xx-P0yyy**" (origem).
- Destino: **Novo projeto… (o destino ainda não existe)**, com **Fundo (arquiteto)** só no copiar (mover é só no mesmo fundo). Parecido no fundo: **Usar este** / **É outro projeto mesmo: criar novo**.
- Toda lista de folhas com caixa usa o mesmo componente: miniatura, código (D) e título, **Selecionar todos** · **Limpar** e "**N de M folhas marcadas**"; Shift+clique marca o intervalo. Não usar "Marcar todas"/"Desmarcar" em lista nova.

## Clima das salas do acervo (16/11/2026)
Temperatura e umidade dos sensores Tuya (Wi-Fi), lidas da nuvem da Tuya em segundo plano (`clima.py`). Nasce desligado (`clima.coleta_min` = 0).
| Valor interno (NÃO muda) | Texto na tela | O que significa |
|---|---|---|
| `ok` | **Dentro da faixa** | temperatura e umidade dentro da faixa desejada (`clima.temp_min`/`temp_max`, `clima.umid_min`/`umid_max`) |
| `aviso` | **Fora da faixa** | passou do limite |
| `critico` | **Muito fora da faixa** | passou do limite por mais de 3 °C ou 10 pontos de umidade |
| (sem nível) | **Sem leitura recente** | a última leitura tem mais de 3 horas: a tela não diz que está tudo bem |
- Nome da página de parede (tablet): **Clima do acervo** (`/clima`, sem login, só na rede do escritório).
- "Faixa desejada: 18 a 24 °C · 40 a 60 % de umidade"; "Lido há 3 min"; "bateria fraca" (20 % ou menos); "Sem conexão com o painel".
- Nunca "Tuya" na página de parede: quem olha o tablet quer saber da sala, não do fabricante. Em Configurações o nome aparece (é onde entram as credenciais).
- Faixa do site na mesma página: "N pessoas no site agora" (Google Analytics, últimos 30 min; traço quando não há leitura de menos de 20 min),
  "visitantes em 7 dias" (as pessoas da coleta diária das Visitas ao site), "N acervos no site" (fundos publicados) e "N folhas em M projetos"
  (a mesma conta do painel, `contagens.no_site`).
- **Clima na barra do topo** (CAMP-HOME-CLIMA, 21/11/2026): pílula ao lado do estado dos sistemas com a **média** dos sensores com leitura recente
  ("23,1° · 58%"; no celular só "23,1°"), na cor do **pior** sensor (verde, âmbar, vermelho) e cinza com "sem leitura há 4 h" quando todos
  estão sem leitura recente. Desligado ou sem sensor: não aparece. O painel que abre se chama **Clima das salas** e tem uma frase curta:
  **Tudo dentro da faixa**, ou "<sala>: umidade um pouco alta (66%)" / "umidade alta demais", "umidade um pouco baixa" / "umidade baixa demais",
  "temperatura um pouco alta (25,1°)" / "temperatura alta demais", "temperatura um pouco baixa" / "temperatura baixa demais" (o nome da sala
  vem antes dos dois-pontos para não errar o gênero); "Sem leitura há 4 h"; "Média de 2 sensores · lido há 5 min" (+ "1 sem leitura recente,
  fora da média"); a faixa desejada e o botão **Abrir Clima do acervo**.

**Ingressos · lista de presença por pessoa** (CAMP-INGRESSOS, 20/11/2026, contrato 1.24): na aba **Por data · lista de presença**, uma linha por pessoa (colunas **Nome**, **Tipo**, **Amigo da CAMP**, **Pagamento**, **Código · pedido**, **E-mail**, **Entrou**, **Presença**). Quem comprou leva a etiqueta **comprador**; as outras pessoas mostram "comprou: <nome>". Compra antiga (sem os dados de cada pessoa) = uma linha com o comprador e "+ N". Meia-entrada mostra "motivo: …"; pessoa sem e-mail mostra "sem e-mail: só o comprador recebe". Botões: **Reenviar ingresso (a esta pessoa)**, **Reenviar ao comprador** e, uma vez por pedido, **Reenviar todos ao comprador** (um e-mail por ingresso). Ficam no menu **⋯** de cada linha, com **Histórico** e **Abrir ingresso**. Tela (redesenho de 20/11/2026): faixa recolhível **Avisos à equipe** ("vão para …", com **Mudar e-mail** e **Mandar aviso de teste**); cinco números numa linha (**pessoas no mês**, **recebido** com a divisão por meio, **por tipo** em etiquetas, **entraram**, **descontos de Amigo**); tabela de turmas com **Ocupação** ("5/15" e barra), **Pagos**, **Aguardando**, **Entraram**, **Recebido** — a linha inteira abre a lista ("sáb 28/11 · 10:00 — 1 pessoa"); Amigo sem adesão em dia: **Amigo · pagamento pendente**, **Amigo · adesão vencida**, **Amigo · pagamento recusado**, **Amigo · adesão cancelada**. A nota da referência do Mercado Pago fica no **?** ao lado do título.
