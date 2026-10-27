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
- O painel é interno (só funcionários): publicar, despublicar e escrever no Tainacan podem ser feitos a qualquer horário. Publicar deixa o projeto visível no site na hora.

## 2. Vocabulário de publicação → `vocabulario.md`
Não publicado · Rascunho · Publicado · Despublicado; ações Publicar · Voltar para rascunho · Despublicar. Lint em `scripts/check_ui.py` e auditoria do texto visível.

## 3. Atalhos de teclado (UMA tabela: `NAV_ATALHOS` no `index.html`)
Ela gera as teclas, os rótulos do menu, a ajuda e a dica do painel. **Regra: os dígitos são as primeiras entradas do menu, NA ORDEM em que aparecem; depois, letras.** Desde o CAMP-154 (22/10/2026), 1–5 são os 5 destinos e o resto (no "Mais") vai por letra.
| Tecla | Tela | Tecla | Tela |
|---|---|---|---|
| 1 | Precisa de você (o Painel inicial) | D · N · P | Decisões · Material novo · Problemas |
| 2 | Projetos | I · W | Arquitetos · Onde está guardado |
| 3 | Fundos e arquitetos | X · T · O | Ler etiqueta · Etiquetas · Empréstimos |
| 4 | Pedidos do site | L · U · A | Relatórios · Downloads do site (admin) · Histórico de ações (admin) |
| 5 | Máquinas (admin) | Q · C · M · G | Qualidade do CAMP Vision · Configurações (admin) · Como o material anda · Glossário |
A tecla de um item do "Mais" funciona com o "Mais" fechado; só o papel esconde de verdade. Conferindo uma folha, as letras do menu não valem
(R gira, K recorta, Enter confere): por isso Arquitetos é I, não R.
Fixas: `⌘/Ctrl+K` busca · `⌘/Ctrl+B` barra lateral · `F` foca o filtro da tela · `?` ajuda · `Esc` fecha. Item novo no menu = nova linha na tabela (o `check_ui` reprova se esquecer ou fora de ordem, e `tests/auditoria_atalhos.js` aperta TODAS as teclas da tabela).

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
- **Teste:** toda verificação nova precisa de caso que DEVE pedir decisão e caso parecido que NÃO deve (falso alarme também é defeito).

## 10. Menu: 5 destinos + "Mais" (CAMP-154, 22/10/2026; antes: menu por trabalho, 09/10/2026)
- **Precisa de você** (1) — o Painel inicial: junta Decisões, Material novo e Problemas que bloqueiam (o número ao lado soma os três). É o CAMP-059.
- **Números do menu (UX-19, 27/10/2026): uma regra só, "itens que pedem ação de você"**, todos de `pendencias.pedem_acao` no servidor. Problemas conta só o que bloqueia ou pede correção; os avisos ficam na aba **Avisos** da tela Problemas e não entram no número.
- **Projetos** (2) · **Fundos e arquitetos** (3) · **Pedidos do site** (4) · **Máquinas** (5, só admin).
- **Mais**: Decisões (D), Material novo (N), Problemas (P), Arquitetos (I), Onde está guardado (W), Ler etiqueta (X), Etiquetas (T), Empréstimos (O),
  Relatórios (L), Downloads do site (U), Histórico de ações (A), Qualidade do CAMP Vision (Q), Configurações (C), Como o material anda (M), Glossário (G).
- No computador o "Mais" abre e fecha (e o navegador lembra); abre sozinho quando a tela atual é um item dele. No celular, como antes: barra de baixo
  com os destinos do papel + "Mais" (o menu inteiro numa folha).

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
