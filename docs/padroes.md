# Padrões do projeto — decididos; seguir, não refazer

Este é o registro único do que já foi decidido. Antes de mexer em algo daqui, leia a seção. Só se muda um padrão quando o Rafael pedir.

## 1. Infraestrutura (fatos)
- **Painel**: servidor Ubuntu `camp@camp`, `192.168.15.60:8000` (na LAN também `http://painel.local`, ver `scripts/instalar_nome_local.sh`), serviço `camp-painel`, repositório `~/camp-painel`. Atualiza com `./atualizar.sh` (faz backup antes).
- **QNAP TS-932PX**: `192.168.15.30`. **O nome que o Mac mostra é `Server-Camp`** (mesma máquina). Compartilhamento `Backup Servidor CAMP`; usuário do painel `camp-panel`; montado neste servidor em `/mnt/qnap/acervos` (raiz do compartilhamento). Ver `qnap.md`.
  - **ENTRADA** (`qnap.entrada_captura`): `Arquivos/100 - Scanners`. Os scanners gravam aqui e o CAMP Vision 2 lê. O painel não lê lotes daqui.
  - **PRONTO** (`qnap.prontos_raiz`): `Fundos e Escritorios/ACERVOS_CAMP`, no padrão `<Fundo>/01 - Projetos/<Fxxx-Pxxxx - Nome>/<série>`. O CAMP Vision 2 grava aqui e **o painel lê os lotes só daqui**.
- **CAMP Vision 2** (repositório oficial `github.com/mullets/campvision-new`; o `campvision2` é o app antigo): roda num Ubuntu dedicado (`.40`). O **contrato** com o painel (arquivos, valores de `status`, heartbeat, token, reserva de projeto) está em `campvision.md`; quem mexer em um lado confere o outro.
- **Uso do acervo (quem pediu para baixar o quê)**: fases 0 e 1 prontas (coleta do formulário de download do site, tela só para admin/master, CSV, apagar pessoa); ver `uso-do-acervo.md`. "Pediu para baixar" é diferente de "baixou de verdade"; o uso é sempre o declarado. Dados de pessoas nunca dentro de `onclick` (só `data-*`). A coleta automática tem `uso.coleta_min` (a semente de teste a desliga, como a do QNAP: teste não depende de relógio).
- **Informações do QNAP no painel** (espaço, tendência, último material, entrada bruta, paradas, lotes prontos, resposta) vêm do **coletor em segundo plano** (`qnap_coletor.py`, a cada 10 min, limite de 25 s, histórico de 90 dias). **Nunca varrer o QNAP dentro de uma requisição**: por SMB é lento e, com a montagem presa, trava o painel. A tela só lê o guardado (`GET /api/qnap`; admin pede `POST /api/qnap/coletar`). Configurações: `qnap.coleta_min`, `qnap.dias_parado`.
- **Clima das salas** (16/11/2026): temperatura e umidade dos sensores Tuya Wi-Fi vêm da nuvem da Tuya pelo **coletor em segundo plano** (`clima.py`; `clima.coleta_min`, **0 = desligado, o padrão**; histórico de 400 dias). A tela só lê o guardado (`GET /api/clima`; admin pede `POST /api/clima/coletar`). `clima.sensores` (nomes do app separados por vírgula; vazio = todos) escolhe quais sensores entram; sensor que nunca leu ou está sem leitura há mais de 7 dias não aparece. Credenciais em Configurações (`clima.tuya_access_id`, `clima.tuya_access_secret` sensível, `clima.tuya_regiao`). O tablet de parede abre `/clima` (página leve, JavaScript antigo de propósito) e lê `GET /api/clima/parede`: sem login, **só na rede local, nunca pelo túnel**, e sem id de aparelho nem configuração na resposta. A mesma página mostra o site: pessoas agora (`site_agora.py`, Google Analytics em segundo plano; `parede.site_agora_min`, **0 = desligado, o padrão**), visitantes em 7 dias (coleta diária das Visitas) e fundos, projetos e folhas no site (`contagens.no_site`).
- O painel é interno (só funcionários): publicar, despublicar e escrever no Tainacan podem ser feitos a qualquer horário. Publicar deixa o projeto visível no site na hora.

- **Amigos da CAMP** (18/11/2026, pedido do Rafael): o painel trabalha os apoios que vêm do site (contrato 1.11; `amigos.py`). Valores por ano em `amigo_preco` (2027 = os do site; "Adicionar ano" copia o anterior). Pagamento registrado no painel: validade pela regra `amigos.validade_regra` (padrão **12 meses a partir do pagamento**, ou do fim da validade atual se ainda vale; `fim_do_ano` = 31/12). E-mails **sempre pelo Sender** (Rafael, 18/11/2026), pela rota do site `POST /painel/apoios/{id}/email` (contrato 1.12, templates TR12 e TR15–TR21); nunca pelo SMTP do painel nem pelo `wp_mail`: template sem ID, Sender sem token ou site antigo = nada sai e o histórico diz o que configurar. Cobrança: link do Mercado Pago criado pelo site; com o pagamento online desligado, as instruções de Pix (`amigos.cobranca_pix`); a mesma pessoa não é cobrada de novo antes de `amigos.cobranca_intervalo_dias` (3) sem confirmar. Lembretes automáticos `amigos.lembretes_auto` **nascem desligados** (`simular` só lista). Só admin e master. Coleta `amigos.coleta_min` (10; a semente de teste desliga).

## 2. Vocabulário de publicação → `vocabulario.md`
Não publicado · Rascunho · Publicado · Despublicado; ações Publicar · Voltar para rascunho · Despublicar. Lint em `scripts/check_ui.py` e auditoria do texto visível.

## 3. Atalhos de teclado (UMA tabela: `NAV_ATALHOS` no `index.html`)
Ela gera as teclas, os rótulos do menu, a ajuda e a dica do painel. **Regra: os dígitos seguem a ordem do menu (1, 2, 3… de cima para baixo) e só ficam em item sempre à vista; o resto vai por letra.** Desde o UX-28 (27/10/2026) o menu segue a ordem do trabalho e as letras ficam entre os dígitos, mas **nenhuma tecla mudou** (antes, CAMP-154: os dígitos eram as 5 primeiras entradas).
| Tecla | Tela | Tecla | Tela |
|---|---|---|---|
| 1 | Precisa de você (o Painel inicial) | N · P · D | Material novo · Problemas · Decisões |
| 2 | Projetos | I · W · X | Arquitetos · Onde está guardado · Ler etiqueta |
| 3 | Fundos | T · O | Etiquetas · Empréstimos |
| 4 | Pedidos de alta resolução | U · L · A | Downloads (admin) · Relatórios · Histórico de ações (admin) |
| 5 · 6 | Máquinas · Financeiro (admin) | Q · C · M · G | Qualidade do CAMP Vision · Configurações (admin) · Como o material anda · Glossário |
A tecla de um item do "Mais" funciona com o "Mais" fechado; só o papel esconde de verdade. Conferindo uma folha, as letras do menu não valem
(R gira, K recorta, Enter confere): por isso Arquitetos é I, não R.
**Visualizador da folha (CAMP-VIEW, 21/11/2026, pedido do Rafael: "mantenha as views meio padronizadas"):** a MESMA barra (`visorBarraHTML`) e as mesmas teclas (`VISOR_TECLAS`) na página da folha (#item), na gaveta "Revisar folha", na tela cheia e na tela de conferir: ← → anterior/próxima, R gira à direita, L à esquerda, C (ou K, fora da tela cheia) recorta, + − 0 ampliam. Nessas telas as letras do menu não valem (R não vai para Cobranças, C não vai para Configurações, L não vai para Relatórios); Shift+letra continua indo para as telas.
**Duplicatas (lado a lado, CAMP-VIEW 22/11/2026):** cada lado da comparação tem a mesma barra; ‹ Anterior · grupo N de M · Próxima › andam entre os grupos (← →, como J/K). Girar e recortar só para operador, admin e master e só com a prévia do CAMP Vision (as mesmas rotas). As teclas do visualizador (R L C/K + − 0) valem para o lado **com o foco ou sob o mouse**; fora das folhas continuam as da tela (J/K grupo, C confirmar, N não é duplicata). Num lado sem a ferramenta (sem prévia, só leitura), a tecla não faz nada (não confirma nem vai ao menu).
Nas listas do Precisa de você e de Problemas (UX-32): `J`/`K` descem/sobem, `Enter` abre e `I` ignora o item escolhido (esconder por 7 dias); sem item escolhido com J/K, o `I` continua sendo Arquitetos.
Fixas: `⌘/Ctrl+K` busca · `[` ou `⌘/Ctrl+B` recolhe/expande o menu (recolhido = só ícones, nome e tecla na dica) · `F` foca o filtro da tela · `?` ajuda · `Esc` fecha. Item novo no menu = nova linha na tabela (o `check_ui` reprova se esquecer ou fora de ordem, e `tests/auditoria_atalhos.js` aperta TODAS as teclas da tabela).

## 4. Listas e paginação
- Listas grandes de verdade (Projetos, Auditoria): paginação **no servidor** (`pagina`/`por_pagina`), "Mostrando X–Y de N", seletor de tamanho.
- Demais listas: paginador genérico (`ativarPaginacao`), aparece acima de 50 linhas; grades de folhas usam "Mostrar mais".
- **Exportar sempre exporta TUDO** do filtro atual, nunca só a página na tela.

## 5. Publicação
- Uma regra só (`publicacao.condicoes_projeto`) para projeto, lote e fundo inteiro; o painel mostra o checklist antes de clicar e o erro fica na tela.
- O painel **não publica arquiteto** no site: o "Status" do arquiteto é marcador interno; foto, biografia e ativar são feitos no WordPress. Guia: `como-publicar.md`.

## 6. Usuários
Papéis: master > admin > operador > leitura. Conta nova entra com senha temporária e é obrigada a trocar (a troca recusa a mesma senha e padrões óbvios). Foto de perfil fica no banco.

## 7. Como o trabalho é feito (vale para quem for mexer, inclusive o Claude)
1. Ler este arquivo e o que já existe antes de propor algo. **Não renomear, recriar nem trocar o que está decidido** sem pedido.
2. Toda mudança tem teste. Pacote: `tests/teste_backend.py` + `bash tests/rodar_auditoria.sh` (telas, funções, atalhos, XSS; passa de 5 min: rode por etapas, ex. `bash tests/rodar_auditoria.sh novas`, `... xss`) + `python3 scripts/check_ui.py`. Teste isolado: `bash tests/rodar_um.sh tests/ARQUIVO.js`.
3. Só envia ao `main` com tudo verde; o commit explica o problema, a causa e o que foi provado. Depois atualiza o Trello e marca como feito o que está concluído.
4. Não afirmar o que não foi testado; dizer o que ficou sem teste.

## 9. O painel verifica antes de agir e, na dúvida, PERGUNTA (Decisões)
Regra de projeto (pedido do Rafael, 08/10/2026): o painel não obedece cegamente. Antes de criar ou mudar algo que pode duplicar ou contradizer o que já existe, ele **confere** e, havendo dúvida, **abre uma decisão** para uma pessoa em vez de escolher sozinho.
- **Fila única:** tabela `decisao` (tipo, chave, fundo, pedido e candidatos em JSON, situação, resolução, projeto resultante). Aparece no "Precisa de atenção" (topo) e conta nas pendências do "Por onde começar". Ler: operador; decidir: admin.
- **Nunca decide sozinho** que dois projetos são o mesmo. Mostra a **nota e os motivos** (nome, identificação original, ano, cidade) e os dois caminhos: "é o mesmo: adicionar a este" ou "é outro: criar novo". Decisão resolvida fica só para leitura.
- **Idempotente:** a mesma `chave_reserva` volta sempre à mesma decisão; depois de decidida, devolve sempre o mesmo projeto.
- **Hoje:** `projeto_parecido` (reserva da estação e "Novo projeto" à mão). Motor em `similaridade.py` (puro e testado: palavras genéricas, nome contido, erro de OCR; número ou letra de designação distingue projetos). Novas verificações entram na mesma fila (ver o cartão "Mais inteligência").
- **Lote que chegou na pasta errada (UX-01):** antes de importar, nome da pasta × título do projeto (`similaridade.compatibilidade_pasta`, `destino_lote.py`); abaixo de 0,5 ou pasta só com código = "Verificar destino": não importa (botão, "Importar todas", automática) até uma pessoa dizer "É deste projeto" (com justificativa, no Histórico) ou abrir a decisão `lote_destino`. O painel não move a pasta sozinho (o pacote tem o código antigo: o CAMP Vision reidentifica).
- **Verificar destino resolvido pelo painel (UX-43, 27/10/2026, pedido do Rafael):** `destino_auto.py`, configuração `destino.automatico` = `desligado` | `simular` (PADRÃO: mostra "O painel faria" e não muda nada) | `aplicar`. Para cada lote do CAMP Vision em "Verificar destino" (sem folhas, em revisão, não complemento, sem decisão humana): **(a) mover** quando um projeto do MESMO fundo tem nota ≥ 0,8 e ≥ 0,15 acima do segundo; **(b) criar** o projeto quando nenhum chega a 0,5 — próximo P do contador do painel (`projetos_novos.criar_projeto`, nunca reusa número), título = nome da pasta limpo pelas regras do UX-15, ano da pasta ("1970-1971" → 1970 até 1971), `projeto.origem='automatico'`; **(c) pessoa** no resto (só código, empate, zona cinzenta, nome que não serve de título). Para decidir sozinho, palavra fraca (clube, garagem, apartamentos…) sozinha não conta como parecida. O lote **não muda de projeto no painel**: fica "movendo para F0xx-P0yyy" (não importa no antigo) até o CAMP Vision reorganizar a pasta (`vigia.py --reidentificar <antigo>`; lista em `GET /api/campvision/destinos`). Aplicar só em segundo plano (coletor ou a tarefa do botão "Aplicar estas N decisões"), simulando cada lote antes, no máximo 10 por rodada, nunca o mesmo lote duas vezes (nem depois do Desfazer). **Desfazer** (admin) enquanto o CAMP Vision não reorganizou: o lote volta a "Verificar destino" e o projeto criado, se vazio, é descartado (o número continua gasto).
- **Teste:** toda verificação nova precisa de caso que DEVE pedir decisão e caso parecido que NÃO deve (falso alarme também é defeito).

## 10. Menu pela ordem do trabalho (redesenho §3/§19, 04/11/2026; UX-28, 27/10/2026; antes: 5 destinos + "Mais", CAMP-154, 22/10/2026; menu por trabalho, 09/10/2026)
- **Redesenho §3 (plano do Rafael, 04/11/2026):** os grupos passam a ser **Principal** (as filas do dia, abaixo) · **Acervo** · **Público e processos**
  (Pedidos de alta resolução, Inscrições, Downloads, Visitas ao site, Relatórios; antes "Público" + "Acompanhamento") · **Administração** (Máquinas,
  Configurações e, saídos de "Acompanhamento", Histórico de ações e Qualidade do CAMP Vision, que já eram só de admin) · **Ajuda** (no fim, dentro do "Mais").
  Teclas iguais. Item ativo: fundo `--sel`, barra azul à esquerda e texto mais forte; contador só em item que é demanda (pill à direita; vermelho
  quando bloqueia). Setas ↑ ↓ andam pelo menu. **Celular (§19): gaveta à esquerda aberta pelo ☰ do cabeçalho** (fecha com Esc, no fundo ou ao escolher;
  substitui a barra de baixo). **Notebook/tablet (721–1279 px): o menu começa recolhido** (só ícones) até a pessoa escolher; a escolha fica lembrada.
- **Topo, sempre à vista** (as filas do dia nunca ficam no "Mais"): **Precisa de você** (1, o Painel inicial: junta Decisões, Material novo e Problemas
  que bloqueiam; é o CAMP-059) · **Material novo** (N) · **Problemas** (P) · **Decisões** (D) · **Projetos** (2) · **Busca** (a mesma do ⌘/Ctrl+K).
  O nome da Home continua **Precisa de você** (decisão do CAMP-154/CAMP-059; o card UX-28 sugeria "Hoje" — não renomeado, cabe ao Rafael).
- **Números do menu (UX-19, 27/10/2026): uma regra só, "itens que pedem ação de você"**, todos de `pendencias.pedem_acao` no servidor. Problemas conta só o que bloqueia ou pede correção; os avisos ficam na aba **Avisos** da tela Problemas e não entram no número.
- **Acervo**: Fundos (3) · Arquitetos (I) · Onde está guardado (W) · Ler etiqueta (X) · Etiquetas (T) · Empréstimos (O).
- **Público**: Pedidos de alta resolução (4) · Downloads (U, só admin).
- **Acompanhamento**: Relatórios (L) · Histórico de ações (A, só admin) · Qualidade do CAMP Vision (Q, só admin).
- **Administração** (só admin; o título do grupo some para os outros): Máquinas (5) · Financeiro (6, CAMP-FIN: não sobrou letra livre) · Configurações (C).
- **Ajuda**: Como o material anda (M) · Glossário (G).
- Sempre à vista no computador: o Topo, Fundos, Arquitetos, Pedidos de alta resolução e Máquinas; o resto aparece ao abrir o **"Mais"** (que abre e
  fecha, o navegador lembra, e abre sozinho quando a tela atual é um item dele). No celular: a gaveta do ☰ com o menu inteiro (redesenho §19).
- **Nome do menu = título da página** (h1, aba do navegador, trilha). Fundos e Arquitetos são itens separados, cada um com a sua página.
- **Trilha do projeto** (e da folha, Conferir folhas, Duplicatas) respeita por onde se entrou: veio de Projetos → "Projetos / projeto"; veio de
  Fundos (ou link direto) → "Fundos / fundo / projeto". As outras telas mostram o grupo do menu ("Acervo / Arquitetos").

**Todo projeto mostra o PRÓXIMO PASSO no topo** (`GET /api/projetos/{c}/proximo-passo`, a mesma fase da Fila): Importar, Conferir, Aprovar, Publicar, com UM botão para o passo atual. A Fila e o projeto dizem a mesma coisa porque usam `filas_fase.py`.
Princípio: cada tela diz **o que falta** e oferece **um** botão principal que faz o passo de verdade; nada de rótulo que só troca de lugar. Texto de interface em português de gente ("37 folhas no painel · 0 no site"), nunca o nome interno.

## 11. Padrão das LISTAS (Projetos primeiro; as demais seguem)
Uma lista existe para responder "o que eu preciso fazer?" e "onde está aquilo que procuro?", não para despejar colunas.
- **Situação em chips com contagem**, acima da lista, dentro do fundo e da busca escolhidos (`GET /api/projetos/resumo`): Todos, **Precisam de você**, Publicados, Não publicados, Sem folhas. O chip ativo fica marcado.
- **Filtros combináveis**: busca por texto, **fundo** e **ordem** (código, mais recentes, nome, mais folhas). "Limpar filtros" só aparece quando há filtro, e volta tudo ao padrão.
- **Poucas colunas, as que decidem**: Projeto (código + nome + ano e cidade embaixo), Fundo, Folhas, **Situação**, Atualizado. Séries, ano e "última atividade" saíram da lista (ficam no projeto).
- **Situação diz o que falta**, na mesma fase da Fila (`filas_fase.py`): "Conferir 12", "Importar folhas", "Aprovar lote", "Pronto para publicar", "Em leitura", "Erro no CAMP Vision"; sem lista ativa, a situação no site (publicado, rascunho, despublicado, não publicado) e "sem folhas".
- **A seleção em massa respeita os filtros** ("Selecionar todos os resultados" usa fundo e situação, não só o texto).
- O servidor é a fonte única: `situacao`, `ordem` e `fundo` são parâmetros de `GET /api/projetos`, `/api/projetos/codigos` e `/resumo`, sempre com a mesma regra (`_filtro_projetos`).

## 12. Direitos do fundo: preencher NÃO é exigido por padrão (09/10/2026)
O painel não bloqueia a publicação só porque os direitos de um fundo estão em branco. Ninguém decidiu isso: foi uma regra tirada do caso de um fundo retirado do ar (a família reclamou de uma biografia publicada) e aplicada a todos os 33 fundos, e acabou mandando na tela inicial ("travados por direitos", "Definir os direitos de BSG").
- **Bloqueia** quando alguém **registrou** uma restrição de propósito (`restrito` ou `nao_autorizado`): é uma decisão de pessoa, e continua valendo. Foi o que protegeria um fundo como o do Chu Ming.
- **Não bloqueia** quando os direitos estão `nao_definida` (nunca preenchidos).
- Para voltar a exigir o preenchimento de todos os fundos: configuração `publicacao.exige_direitos` = `1` (Configurações). Padrão `0`.
- É uma única função, `rotas_gestao.direitos_permitem_publicar`, usada pela publicação do projeto, pela do fundo, pela autorização, pelo guia e pela tela inicial; por isso o interruptor vale para todos.
- Na lista de Fundos, só aparece a etiqueta (e o filtro "Com restrição de direitos") para restrição registrada.
- Testes: os de backend e de navegador antigos ligam a exigência (continuam provando o bloqueio); o bloco `direitos_opcional` prova o padrão.

## 13. Topo do projeto e janela de revisão (09/10/2026, depois de olhar as telas num navegador)
- **Topo do projeto = um painel só**: os 4 passos, a frase do que falta e os botões do passo atual (Começar a conferir, Aprovar todas). O painel "Revisão do lote" ficou só com o andamento e o que foi retirado; as ações raras (Só as sem pendência, Importar de novo, Ler de novo no CAMP Vision) ficam em "Mais ações do lote".
- **Janela de revisão da folha**: a imagem, o que o CAMP Vision apontou e, no fim, os botões **fixos** (Está certo e próxima, Salvar correção); os campos de edição ficam recolhidos em "Corrigir os dados da folha" e abrem sozinhos quando a folha está sem título. A ação mais comum é a mais à mão.
- **22/10/2026 (CAMP-147, Trello):** o topo virou o bloco **"Próximo passo"** (`#pj-status`): a situação (uma das 5), UMA frase e UM botão azul.
  Antes da publicação (importar, conferir, aprovar, erro) a frase e o botão vêm do `/proximo-passo` (`#pj-proximo`, dentro do bloco); depois, do plano de publicação.
  O caminho de 7 passos saiu da página do projeto (fica na Fila e no quadro do fim da conferência). `umBotaoAzul()` tira o azul de qualquer botão da página
  fora desse bloco (cartões, quadros que chegam depois). Lote com erro do CAMP Vision: "Ver o erro" abre a mensagem com o único "Pedir releitura" (CAMP-128).
  Os 4 cartões e a barra "O que falta" continuam abaixo; virar abas é a segunda parte do CAMP-147.
- Textos: "agora" (não "agora há pouco"), "1 coisa pede / N coisas pedem você hoje", caminho de navegação com os mesmos nomes dos grupos do menu.

## 14. Padrão único de tela → `padrao-de-tela.md` (13/10/2026)
- Cabeçalho com UMA ação principal e o resto em "Mais ⋯" (`menuMaisHTML`); abas de situação únicas (`.abas-sit`); linha clicável com › (`data-abrir`/`data-nav`); detalhe com um só Voltar (o do topo), trilha e "Próximo passo" com o único botão azul.
- `scripts/check_ui.py` reprova `.backbar`, `.fila-chips`, `.fundos-filtros` e o select de situação dos Erros se voltarem.

## 15. Tudo se faz no painel; o site acompanha sozinho (21/10/2026, Rafa)
- "Quem usa esse painel não usa o painel do WordPress, nem tem acesso direto. É tudo feito NESSE painel somente, nunca mande alguém para o WordPress."
- "Ao alterar aí, já altere no WordPress automaticamente."
- Nenhum texto da tela manda ninguém ao WordPress, ao wp-admin ou a "corrigir no site". Se algo só pode ser resolvido dentro do site (ex.: permissão do Site Kit), a frase é "avise quem cuida do site", com o detalhe para essa pessoa.
- O que precisa mudar no site tem botão no painel:
  - publicar ou tirar a página do arquiteto (CAMP-141);
  - corrigir o fundo de um item no site;
  - tirar do público item sem código.
- Correção numa folha ou projeto já publicado vai ao site sozinha, logo depois de salvar. A lista "alteradas depois de publicar" só aparece quando o site recusou, para tentar de novo.
- `scripts/check_ui.py` reprova "wp-admin" e "no/pelo/ao WordPress" no HTML e no backend.


## 16. Publicar no site em um passo (CAMP-148, decidido pelo Rafa em 22/10/2026)
- Configuração `publicacao.publicar_um_passo` (migração 147). **Nasce desligada (0)**: tudo como antes (um admin aprova o lote e publica).
- Ligada (1): com as folhas conferidas, o Próximo passo já é "Publicar N folhas"; o MESMO clique aprova o lote (evento `revisao_aprovada`
  com `junto_com_publicar`), autoriza e publica. Sem confirmação; o resultado fica no bloco, com Desfazer (quem pode despublicar).
- Ligada, o **operador também publica** (decisão do Rafa). Os outros botões da aba Publicação continuam de admin (`pode_agir`); o Publicar
  usa `eu_publico` em /publicacao e `pode_agir` no plano (`publicacao_guiada.pode_publicar`). Cuidado: `pode_publicar` em /publicacao é outra coisa (as condições).
- Continua travando: folha ainda a conferir ("Falta conferir N folhas"), bloqueio registrado por pessoa, direitos com restrição, projeto
  sem título, lote de teste. Nesses casos o lote NÃO é aprovado.
- Some o "Autorizar" da barra em lote de Projetos (o Publicar já autoriza). Fila e Painel inicial trocam "Aprovar" por "Publicar no site".
- **CAMP-149:** as abas de Projetos são as situações (Precisa de você · Pronto para publicar · No site · Com problema · Todos; "Não publicados"
  e "Sem folhas" só aparecem quando vêm de um link, como os números do fundo). Na aba Pronto, marcar → "N projetos selecionados · X folhas" →
  "Publicar os N no site" (o mesmo caminho do Publicar do projeto). Com o um passo ligado, o operador também publica em lote (só publicar).

## 17. Conferir só as folhas com aviso (CAMP-150, decidido pelo Rafa em 22/10/2026)
- Configuração `revisao.conferir_so_avisos` (migração 148). **Nasce desligada (0)**: todas as folhas esperam alguém conferir.
- Ligada (1): ao importar, a folha SEM aviso (a regra do "Aprovar todas", CAMP-094: bloqueio, duplicata, autoria, espelho a confirmar,
  ressalva/sinal do CAMP Vision ou problema aberto) entra conferida por `painel (sem aviso: conferida sozinha)`, com o evento
  `conferida_automaticamente` (lista das folhas). As com aviso esperam.
- Tela: o modo conferir abre no filtro "A conferir" (só as com aviso) e diz "Folha 1 de N com aviso (M sem aviso já conferidas)"; a folha
  começa por "Por que você está vendo esta folha" (inclusive a ressalva do CAMP Vision); some "Aprovar todas". "Todas" mostra qualquer folha,
  e uma conferida sozinha pode voltar para "a conferir".

## 18. Importar sozinho quando o CAMP Vision termina (CAMP-151, decidido pelo Rafa em 22/10/2026)
- Configuração `importacao.automatica` (migração 149). **Nasce desligada (0)**: alguém clica "Importar folhas" (o aviso do CAMP Vision já
  importa quando chega; isto cobre o lote que ficou esperando).
- Ligada (1): a cada coleta do QNAP (laço em segundo plano de `main._coleta_qnap_periodica`, NUNCA numa requisição), `importar_sozinho`
  importa o lote em "revisao", sem folhas, não aprovado, pelo mesmo importador e com as mesmas condições do botão. Evento `importado_sozinho`.
- Não importa: decisão pendente de números que colidem; CAMP Vision ainda lendo. Não deu (QNAP fora, pacote faltando ou de outro projeto):
  um problema do projeto com o motivo (chave `importar_sozinho:<lote>`, um só), que fecha sozinho quando a importação der certo.

## 15. Home em Ação, Operação e Resultados (CAMP-HOME-UX, 22/11/2026, documento do Rafael)
- O menu superior (dados do usuário, estado das coisas, temperatura) e o menu lateral **não mudam** (pedido explícito do Rafael); o teste compara a marcação do topo.
- Prioridade da fila = nota 0–100 explicável (pesos do §8: gravidade 40, tempo 20 com teto de 14 dias, bloqueio 20, prazo/risco 20); fórmula em `COMO_FUNCIONA.md` D.2.1.3.
- **Tom sério, nada infantil** (Rafael, 22/11/2026: "não quero que fique infantil o sistema, tá? é algo bem sério"): o painel é ferramenta interna de um acervo de patrimônio. Sem nível, XP, título de nível, medalha, selo, troféu, estrela, cor de jogo, emoji, confete ou comemoração ("Parabéns", exclamação). A coluna da direita mostra **Seu trabalho** (pontos validados na semana e no mês + a meta da equipe na barra padrão), **Marcos** (texto com data) e o ranking em tabela. O nível continua calculado em `home_trabalho.nivel_xp` (compatibilidade da API), mas não aparece. `check_ui.py` impede a volta.
  - **Marcos é a única exceção: pode ter ícones e emojis (decisão do Rafael 22/11)** ("aqui sim pode ficar gamificado como estava antes, com ícones e emojis"): selos grandes coloridos nos totais (folhas, lotes, decisões, problemas corrigidos), um emoji por marco e 🎯 com barra no próximo marco, na Home e em Problemas. Os textos continuam sérios (sem nível, XP, "Parabéns" ou exclamação). A exceção é estreita: o `check_ui.py` aceita emoji e selo só no trecho `MARCOS-ICONES-INICIO … MARCOS-ICONES-FIM` do `index.html` (uma vez só, curto, só funções `marco*`/`MARCOS_*`); "Seu trabalho", o ranking e o resto seguem sóbrios.
- Gamificação só com eventos validados e recontados do estado atual (desfez, o ponto some); meta coletiva; conquistas não competitivas e ocultáveis; **Ranking da equipe (mês) LIGADO por padrão** (decisão do Rafael, 22/11/2026: `jogo.ranking_equipe` = 1, migração 243; qualquer admin desliga em Configurações; só pontos validados; o "?" sempre diz que não serve para avaliar desempenho); nada de cobrança por sequência.
- Cartões da Home com as duas medidas (Para conferir, Esperam um admin): o número grande são as **folhas**, a linha de baixo "em N lotes" (decisão do Rafael, 22/11/2026). Decisões continuam decisões; "folhas conferidas hoje" continua folhas.

## 20. Central de Problemas (CAMP-PROB-UX, 22/11/2026, documento do Rafael)
- O topo (usuário, situação, temperatura), a faixa do sistema e o menu não mudam. O título continua **Problemas** (nome do menu).
- A coluna `erro.situacao` continua a regra de todo o resto; a `fase` (Novo → … → Resolvido) só detalha o trabalho e cai sempre numa situação antiga (`central_problemas.FASE_SITUACAO`). Fase NULL ou mexida por rota antiga = deduzida da situação.
- Resolver exige conclusão + evidência ou justificativa; **autoria e crédito exigem fonte** (o painel nunca sugere autoria nem fonte).
- **Revisão por outra pessoa** (`problemas.revisao_outra_pessoa`) nasce **desligada**.
- Reusa a Home (§15): responsável em `tarefa_responsavel` (`erro:<id>`, mesmas regras de "Pegar para mim"/admin "Atribuir a…"), a nota de prioridade de `home_trabalho.prioridade` e UM sistema de pontos (`home_trabalho.eventos_validados`, recontado do estado; meta `meta.semana`; Ranking da equipe do mês `jogo.ranking_equipe`, ligado por padrão). Detalhe: `COMO_FUNCIONA.md` D.2.4 e D.4.3b.

## 19. Financeiro (CAMP-FIN, 24/11/2026, pedido do Rafael: "relatório de receitas para o contador"; "Temos como interligar com o Mercado Pago?")
- Tela **Financeiro** em Administração (tecla 6; só admin e master; `financeiro.py`). Junta num livro só cada pagamento confirmado: Amigos da CAMP,
  cobranças avulsas (pela finalidade), doação de acervo, ingressos, patrocínios e a **conta inteira do Mercado Pago** (pelo site, contrato 1.33:
  a chave fica no site e nunca vem ao painel; `mp_pagamento`, único pelo id do pagamento). Um pagamento conta uma vez (id do Mercado Pago).
- Natureza no espírito da ITG 2002 (R1), num mapa editável (`financeiro.naturezas`): Doações · Doações com restrição · Contribuições de associados ·
  Patrocínios · Receitas de serviços e ingressos · Outras. Texto sempre cauteloso: **a classificação final é do contador**.
- Sem referência da CAMP (Pix, link ou QR direto na conta) = "Recebido direto no Mercado Pago", Doações por padrão, com "Classificar como…" que fica lembrado.
- Estorno/contestação = linha negativa na data do estorno. Sem a tarifa lida: "a conferir no extrato". Nenhum CPF/CNPJ no relatório (só `documento=1`).
- Contas (`financeiro_conta`): Mercado Pago (operacional) e, já cadastrada e desativada, a do Banco do Brasil do projeto Rouanet (PRONAC 2613864 ·
  Livro Karazawa), com restrição. Conta com restrição aparece SEMPRE separada da operacional. Sem rubricas/SALIC por enquanto.
- A leitura da conta do Mercado Pago roda em segundo plano (`financeiro.mp_coleta_min`, 60; 0 desliga) e no botão, também em segundo plano.
- **DRE gerencial** (CAMP-FIN, pedido do Rafael: "Já podemos fazer DRE nisso tudo?"; `dre.py`): "Demonstração do resultado do período" com superávit ou
  déficit (nunca "lucro"), só com o livro do Financeiro, **por regime de caixa**; o aviso "Não substitui a demonstração oficial do contador (regime de
  competência, ITG 2002)" vai na tela e na exportação. Mapa `dre.mapa` (natureza/categoria → linha); fora do mapa = "Outras" com aviso. Visões:
  Consolidado, Operacional e cada conta com restrição separada. Colunas: período, anterior e acumulado do ano; e a visão mensal.
- **Inteligência do Financeiro** (pedido do Rafael: "Capriche na inteligência do sistema"; `financeiro_ia.py`): toda sugestão diz o porquê e nada é
  aplicado sem um clique. Categoria sugerida (regra da equipe → o que a equipe escolheu antes para a mesma contraparte/CNPJ → palavras da descrição),
  com confiança; regra "Sempre classificar X como Y" sugerida quando a mesma escolha se repete 3 vezes (com histórico). Justificativa sugerida
  (despesas parecidas e tarefas de doação com valor e data perto). Alertas (cobrança repetida, valor fora do usual, recorrente com a próxima data,
  sem comprovante há N dias, doadores, orçamento de conta de projeto) no Destaques e na Home do admin (prioridade baixa). Projeção de 3 meses
  rotulada como estimativa. Busca natural ("frete outubro", "doações acima de 500", "sem nota"). Leitura automática do comprovante só com um
  leitor configurado e `financeiro.leitura_comprovante` = 1 (desligada; o painel não tem cliente de IA hoje).

## Tipos de documento

- **Rafael, 25/11/2026: tipo Detalhe / Estrutura.** Entra na lista de tipos de documento do painel (migração 261), como está escrito,
  com a barra e os espaços. É o tipo que o CAMP Vision lê nas folhas de projeto complementar de estrutura; antes a ficha dizia "não existe
  na lista do painel". O importador casa o nome inteiro antes de separar por " / " (que continua valendo para "Planta / Corte"). No
  agrupamento por disciplina conta como **Estrutura**. Para o site é só o texto do "Tipo de desenho" (nenhum contrato muda); o CAMP Vision
  não recebe a lista.

