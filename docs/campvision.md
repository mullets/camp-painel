# Contrato entre o painel e o CAMP Vision 2

Este documento é o contrato que o **CAMP Vision 2 (CV2)** segue para falar com o **painel**. Tudo que está aqui foi verificado por teste automático
(`tests/teste_backend.py`, bloco "Contrato com o CAMP Vision 2"). O que ainda **não** existe está na seção 9.
Repositório oficial do CV2: `github.com/mullets/campvision-new` (o `campvision2` é o app antigo, com YOLO/Tesseract: não usar).

> **Contrato com o CAMP Vision 2:** a fonte única é `campvision-new/docs/contrato-painel.md`. Este painel implementa o **Contrato 2.4** (autoria divergente vira aviso; base 2.2 de 13/10/2026) (constante `CONTRATO_PAINEL` em `backend/app/contrato.py`; exemplos reais copiados em `tests/contrato/`, origem em `tests/contrato/ORIGEM.txt`). Se o CV2 mandar outra versão no heartbeat, a tela Estações avisa. Este arquivo descreve só o que o PAINEL faz com o que recebe.

## 1. Visão geral
```
estações de captura ─▶ QNAP: Arquivos/100 - Scanners  ─▶  CV2 (Ubuntu .40)  ─▶  QNAP: Fundos e Escritorios/ACERVOS_CAMP  ─▶  painel (.60)
        │                       ENTRADA                    lê, aplica EXIF,           PRONTO (só o painel LÊ daqui)
        └─ painel: reservar nº de projeto (HTTP)           organiza, grava JSON
```
- **Mão única.** O painel só **lê** a pasta final e responde a chamadas HTTP. Ele **não grava** no QNAP e **não chama** o CV2.
- O painel **nunca lê a ENTRADA** (`Arquivos/100 - Scanners`): material ali nunca vira lote, mesmo que tenha `status.json`.
- QNAP: `192.168.15.30` (o Mac mostra como `Server-Camp`), compartilhamento **`Backup Servidor CAMP`**. No painel e no CV2 ele é montado em `/mnt/qnap/acervos`.
- Painel: `http://192.168.15.60:8000`.

## 2. Estrutura da pasta final (fixa e rasa)

Este trecho é CONTRATO e não é mais descrito aqui: a fonte única é `campvision-new/docs/contrato-painel.md` (Contrato 2.1 — 10/10/2026, commit f8c8a69 do campvision-new). Cópia literal e exemplos reais em `tests/contrato/` (ver `tests/contrato/ORIGEM.txt`); os testes do painel usam esses arquivos.

## 3. `info_projeto.json` (na pasta do projeto)

Este trecho é CONTRATO e não é mais descrito aqui: a fonte única é `campvision-new/docs/contrato-painel.md` (Contrato 2.1 — 10/10/2026, commit f8c8a69 do campvision-new). Cópia literal e exemplos reais em `tests/contrato/` (ver `tests/contrato/ORIGEM.txt`); os testes do painel usam esses arquivos.

## 4. `status.json` (na pasta do projeto)

Este trecho é CONTRATO e não é mais descrito aqui: a fonte única é `campvision-new/docs/contrato-painel.md` (Contrato 2.1 — 10/10/2026, commit f8c8a69 do campvision-new). Cópia literal e exemplos reais em `tests/contrato/` (ver `tests/contrato/ORIGEM.txt`); os testes do painel usam esses arquivos.

## 5. Como o painel fica sabendo de um lote
- **Aviso do CV2 (o caminho normal):** `POST /api/campvision/aviso`, a cada troca de `status`. O painel relê **só aquela pasta**; a fila enche sozinha (seção 6.4).
- **Varredura completa**, no painel: *Filas → Varrer QNAP* (`POST /api/filas/varrer-qnap`, exige login de **operador** ou acima). Agora é **reconciliação**: pega o que um aviso perdeu.
- A cada 10 minutos o painel só **conta** lotes e mede espaço no QNAP (cartão do painel inicial); isso **não cria fila**.
- A varredura anda por **toda** a pasta final. Por isso a estrutura deve ser rasa e fixa (seção 2).

## 6. Chamadas HTTP (CV2 → painel)

Este trecho é CONTRATO e não é mais descrito aqui: a fonte única é `campvision-new/docs/contrato-painel.md` (Contrato 2.1 — 10/10/2026, commit f8c8a69 do campvision-new). Cópia literal e exemplos reais em `tests/contrato/` (ver `tests/contrato/ORIGEM.txt`); os testes do painel usam esses arquivos.

## 7. O que o CV2 deve fazer, em ordem
1. Ao iniciar: ler `GET /contexto` (fundos e próximos números) e começar o heartbeat (`ocioso`).
2. Para cada projeto novo da ENTRADA: obter o número com `POST /reservar` (com `chave_reserva`) e criar `…/01 - Projetos/<Fxxx-Pxxxx - Nome>/`.
3. Gravar `info_projeto.json` e `status.json` com `status: "processando"` **antes** de mexer nas imagens.
4. Processar; heartbeat com `estado: "processando"` e `projeto_codigo`.
5. Terminando: atualizar `status.json` para **`pronto`** (ou **`erro`** com a causa em `mensagem`). Gravar o `status.json` **por último**, depois que as imagens estiverem completas.
6. Lotes de teste: `"teste": true` no `info_projeto.json`.

## 8. Como conferir que funcionou
No painel, depois que o CV2 gravar um lote: *Filas → Varrer QNAP*. O lote deve aparecer em **Revisão** (ou **Processando**/**Erro**), com o nome, a contagem de folhas e a estação/operador.
Em *Estações*, o card do **CAMP Vision 2** mostra o app online, a versão e o projeto em andamento. Exemplo de teste de rede (do `.40`):
```
curl -s -H "X-Camp-Token: $CAMP_PAINEL_TOKEN" http://192.168.15.60:8000/api/estacoes/contexto
```

## 9. Ainda não existe (decisões pendentes)
**Passou a existir (integração de 15/10/2026):**
- `catalogacao/erros.json` entra em **Erros relatados** (origem "CAMP Vision"); gravidade `bloqueia` impede publicar; a chave nasce do conteúdo, então ler de novo não duplica nem reabre o que alguém resolveu.
- O livro `_campvision/registro/AAAA-MM.jsonl` é lido de forma **incremental** (posição em bytes por arquivo, só linhas completas) pelo coletor do QNAP e aparece em "Registro do CAMP Vision" no Histórico do projeto. `_campvision/` é ignorado na varredura de lotes.
- **PDF conta como folha** (`folhas_encontradas`); o TIF/JPG do mesmo código continua sendo um documento só.
- O painel lê o contrato 2.2: motivo do erro em `resultado.status.motivo`; endereço da folha em `carimbo.local` / `lido.endereco`; retirados com `decisao.por` e `decisao.motivo`; `fotografo` (em `lido_json`) e `programa_sugerido`, `natureza_sugerida`, `lacunas` do projeto (no resultado da importação); TIF achado em `<série>/TIF/<codigo>.tif` quando `arquivos[]` traz só o JPG e o arquivo existe; `concluido` de releitura guarda `custo_usd`, `relidos` e afins.
- Reserva de projeto: o "P0060 - " do nome da pasta (ou `p_estacao`) é só **pista**; só `projeto_ja_existia: true` com `numero_projeto` válido reaproveita o projeto. Repetir a `chave_reserva` usa a tabela `reserva`.
- Heartbeat: texto livre em `detalhe.situacao`; `/api/estacoes/contexto` traz `coautores` e `periodo_atuacao` por fundo; série `S99` "Não identificado" aceita no importador; Estações avisa quando uma máquina é recusada por falta de token.

**Ainda NÃO existe:**
- **Reconciliação noturna** (comparar o livro com o que o painel tem) e um canal de volta do painel para o CV2 além dos pedidos de releitura.
- O painel **não lê** `catalogacao.csv` nem `contatos.jpg`; a revisão usa o `pacote_tainacan.json`.
- Marcar o lote como `teste` só vale pelo `info_projeto.json`; o painel não sabe de testes que estejam só no nome da pasta além de `teste`, `asd` e `sei la`.
- Os campos `fotografo`, `programa_sugerido`, `natureza_sugerida` e `lacunas` ainda não têm coluna nem tela própria.

## 10. Revisão do lote (pós-CAMP Vision)
O CAMP Vision grava a catalogação e o painel **importa, uma pessoa confere/corrige e o admin aprova**. O painel não decide nada sozinho.

**Fonte:** `<pasta do lote>/catalogacao/pacote_tainacan.json` (versão 2). Entra só o que está em `documentos` (inclusive folha com autoria divergente, que vem com `publicavel=true`, `autoria_divergente=true` e a ressalva "autoria não confirmada": contrato 2.4); `retirados` (projeto divergente, capa, retirada por decisão) **não entra** e é listado no resultado.
Os caminhos de `arquivos` e `preview` vêm **relativos à raiz `ACERVOS_CAMP`** (`qnap.prontos_raiz`); a prévia fica em `_campvision/preview/<projeto>/<código>.jpg`.

**Fluxo (botões na página do projeto, painel "Revisão do lote"):**
1. **Importar as folhas do lote** (operador+): `POST /api/lotes/{id}/importar`. Cria uma folha por documento, `revisao = pendente`, ligada ao lote. Idempotente.
   **Nunca sobrescreve** o que uma pessoa já revisou nem o que já está no site; reimportar só atualiza as ainda pendentes.
2. **Conferir / corrigir** cada folha (janela "Revisar": o que o CAMP Vision leu e apontou ao lado dos campos). Corrigir usa o editor que já existe (`PATCH /api/itens/{codigo}`, com histórico antes/depois) e marca `corrigida`; "está certo" marca `conferida`.
   "Conferir as folhas sem pendência" marca em lote **só** a folha sem nenhum bloqueio, ressalva ou sinal do CAMP Vision e com título. O resto fica para olho humano.
3. **Aprovar o lote** (admin): só com **todas** as folhas revisadas. É um **registro** (quem e quando) e **não muda a etapa**: `rascunho` já significa "foi para o site", com portões próprios.
   Esse portão (`PATCH /api/filas/{id}` para `rascunho`) agora **exige a aprovação** quando o lote tem folhas importadas. Lote aprovado fica protegido (revisar/importar dão 409) até **Reabrir** (admin, e só se ainda não foi ao site).

**O que vira o quê:** `bloqueios`/`publicavel=false` -> `status_site = bloqueado`; `duplicata_de` e `tipo_duplicata` são mantidos; `tipo_de_desenho` só vira o tipo do painel se existir no vocabulário (o lido fica em `tipo_lido`);
título lido, ressalvas, orientação/série incerta e a prévia ficam em `pendencias` para a pessoa ver ao revisar.
**Página do projeto:** mostra as folhas do site **somadas** às importadas que ainda não estão no site (antes, se o projeto já tinha folha no site, as locais ficavam escondidas).
**Ainda não faz:** ler `erros.json` e o aceite do lote (`catalogacao/lotes/*.json`), e enviar a folha ao site (continua sendo o fluxo de publicação que já existe).

## 11. Publicar com um clique
Antes, publicar exigia cinco passos soltos, na ordem certa e conhecidos de cabeça: dossiê no site, folhas no site, autorizar o projeto, direitos do fundo, publicar. Agora o painel conhece a receita.

**Na página do projeto, o botão Publicar está sempre ativo e abre o plano** (`GET /api/projetos/{codigo}/publicar/plano`, não muda nada):
- **O que vou fazer:** dossiê, folhas, autorizar, publicar (cada passo mostra se já foi feito).
- **Ficam de fora:** duplicatas e folhas **ainda não conferidas** na revisão (nunca vão ao site).
- **O que só uma pessoa resolve** e bloqueia: direitos do fundo, erros bloqueantes (autoria divergente é só aviso desde o contrato 2.4), lote de teste, "nenhuma folha conferida ainda". Cada um traz o botão que resolve.

**"Publicar agora"** (`POST /api/projetos/{codigo}/publicar-tudo`, admin) faz a sequência: dossiê -> folhas (rascunho) -> autorizar -> publicar. Regras:
- **Idempotente:** clicar de novo continua de onde parou; o que já subiu não se repete.
- **Fatias de tempo:** cada chamada envia folhas por até ~40 s e devolve `parcial` com quantas faltam; a tela repete e mostra o progresso.
- **Falha numa folha:** para antes de autorizar e publicar, diz qual folha e por quê. Nada fica meio publicado.
- **Trava contra clique duplo:** 409 se o mesmo projeto já está sendo publicado.
- Todos os portões de `POST /publicar` continuam valendo: ele revalida no fim.

**Regra única de folha elegível** (`publicacao.ELEGIVEL_LOCAL`, antes repetida em 4 lugares): não é duplicata e, se veio da revisão do CAMP Vision, já foi conferida/corrigida.
**Imagem que sobe ao site** (`imagem_site.py`): a **prévia do CAMP Vision** (`_campvision/preview/`, ~3000 px, já girada); senão o arquivo da folha, absoluto ou relativo à raiz dos prontos. Antes tratava o caminho como local, e uma folha vinda da revisão subia **sem imagem**.
**Nunca testado contra o WordPress de verdade**: os testes usam substitutos do dossiê, das folhas e do status do site.

## 12. Revisão mais simples: aprovar todas, virar a folha, próxima
- **Aprovar todas** (`POST /api/lotes/{id}/conferir-todas`, operador+): marca TODAS as folhas pendentes do lote como conferidas, inclusive as com algo apontado pelo CAMP Vision. A tela pergunta antes e diz quantas têm algo apontado.
  As bloqueadas (duplicata, autoria) continuam sem ir ao site. **Aprovar o lote** continua sendo do admin e só aparece quando não resta nenhuma pendente.
- **Clicar no cartão** abre a revisão da folha (sem botão repetido em cada cartão). Depois de "Está certo" ou "Salvar correção" a janela passa **sozinha para a próxima** pendente, sem recarregar a página; o selo do cartão e os contadores se atualizam na hora.
- **Virar a folha** (`POST /api/itens/{codigo}/girar`, graus 90, -90 ou 180, operador+): guarda `item.giro_manual` (0/90/180/270, somado ao que o CAMP Vision já aplicou). A prévia é entregue já virada (`GET /api/itens/{codigo}/previa`), **e é a imagem virada que sobe ao site**.
  O arquivo original no QNAP não é tocado. Não vale para folha que já está no site nem para lote aprovado (409). Precisa do **Pillow** (`requirements.txt`; o `./atualizar.sh` instala): sem ele, girar responde 503 dizendo isso.
- **Miniaturas leves:** `previa?t=480` entrega a prévia reduzida (lado maior de 120 a 1600 px; fora disso é ignorado), com **cache em disco** (`cache_previas/`, por arquivo, data, tamanho, giro e lado). Antes cada cartão baixava a prévia inteira de ~3000 px.
- **Orientação automática é do CAMP Vision** (ticket #25 dele, ainda no backlog): o painel não adivinha o lado certo; corrige em um clique quando a leitura erra.
- **Painel "Encontradas no QNAP"** não lista mais a pasta `catalogacao/` (folha de contatos e saídas do CAMP Vision) nem as folhas **retiradas** pelo CAMP Vision (autoria divergente): essas aparecem em "retiradas" na Revisão do lote. A contagem da Fila também deixou de contar a folha de contatos como documento.
- O aviso amarelo "divergência" da fonte visual só aparece quando o site já tem folhas e o número difere; projeto ainda fora do site não é divergência.

## 13. Endereço da página pública do projeto
O botão "Ver página pública" antes **presumia** o endereço e errava (caso F026-P0005: levava a `.../f026-p0005-clube-ipe-social-rua-estado-de-israel/`, que dá 404; o real é `.../f026-p0005-clube-ipe-social/`).
- **Regra do slug do site** (conferida contra 30 projetos reais): o título é cortado na **primeira vírgula** (o resto é local/endereço) e o slug guarda só as **6 primeiras palavras**: `f026-p0005-` + `clube-ipe-social`.
- **Confirmação no site** (`POST /api/projetos/{codigo}/pagina-publica/confirmar`): como a regra é um palpite, o painel pergunta ao site. (1) o palpite abre? (2) senão, a busca pública `https://camp.arq.br/acervo/projetos/?q=<código>` devolve o endereço real
  (só vale link do próprio site e do próprio código). Achou: grava em `projeto.url_publica_confirmada` e o botão passa a usar esse endereço. Não achou: o botão vira "Procurar no site" e leva à busca pública por código, que sempre abre. Nunca um link morto. Sem rede: não quebra.
- **Publicado no painel não quer dizer "com folhas no site"**: a página pode existir como **registro de inventário** (0 documentos) quando só o dossiê do projeto foi publicado. As estatísticas do fundo na página do arquiteto também podem ficar em cache no site.

## 14. "Ler dados agora": pedido de releitura ao CAMP Vision

Este trecho é CONTRATO e não é mais descrito aqui: a fonte única é `campvision-new/docs/contrato-painel.md` (Contrato 2.1 — 10/10/2026, commit f8c8a69 do campvision-new). Cópia literal e exemplos reais em `tests/contrato/` (ver `tests/contrato/ORIGEM.txt`); os testes do painel usam esses arquivos.

## 15. Número P nunca reusado (CV-27) e arquivo de origem (CV-01)
- **CV-27:** o próximo P de um fundo (`projetos_novos.proximo_numero`) é o MAIOR entre:
  - o contador do painel (`numero_p`);
  - os códigos que o espelho do site já viu (`wp_item.codigo_detectado`);
  - o `proximo_p_local` que o CV2 manda no `/reservar` (maior P nas pastas do acervo + 1).

  Um código que já existe em `projeto` é pulado. Vale para a estação, o painel e a resolução de decisão.
- **CV-01:** `item.arquivo_origem` (migração 042) recebe `documentos[].arquivo_origem` do pacote: pasta + nome original, várias versões separadas por ` | `. Ao subir a folha, vai para o metadado de texto "Arquivo de origem" da coleção Acervo CAMP (8013).
  - Se o metadado não existir, o painel o cria uma vez, oculto ao público (`display: no`).
  - Se o site recusar a criação, fica pendência e a folha sobe sem ele.
- Tipo de duplicata `quase` (nome novo no CV2) é gravado como `perceptual` no painel.

## Séries (CAMP-047, segunda leva)
S01 Desenhos e pranchas · S02 Documentos textuais · S03 Fotografias · S04 Negativos · S05 Slides · S06 Materiais · **S07 Publicações** · **S08 Redesenhos** (pasta `08 - Redesenhos`, dentro do projeto) · S99 Não identificado. O importador aceita S01–S08 e S99.
A migração 122 só ajusta a tabela `serie`. Mover as folhas que eram S07 "Redesenhos" para S08 (o código muda, o antigo vira redirecionamento) é o roteiro `scripts/migrar_serie_s08.py`: `--simular` (padrão) só lista; `--aplicar` troca as que não estão no site; `--incluir-no-site` também as que estão (passam pelo fluxo de redirecionamento do site). Nunca roda sozinho.

## Imagem pública no site: até 1920 px (CAMP-048)
Ao enviar a folha ao site (`publicador.imagem_pronta_para_o_site`, também usada no giro de folha já publicada), o painel gera um **derivado JPEG q85, sRGB, lado maior ≤ 1920 px** a partir da prévia do CAMP Vision (`_campvision/preview`, já girada), com o giro/espelho escolhido na revisão. Fica em cache em disco (arquivo + data + tamanho + giro + espelho + lado). O TIF e a prévia de ~3000 px **nunca** vão ao site; caminho `.tif` nunca é escolhido; sem Pillow o envio falha com mensagem (melhor não subir do que subir a grande). Fundo com limite menor (jpg_1200) continua valendo. `item.site_imagem_lado` guarda o lado enviado (NULL = enviado antes do limite).
`python scripts/reprocessar_imagens_publicas.py --simular` (ou `--sim`) lista as folhas com imagem acima de 1920 px ou de tamanho desconhecido; `--aplicar [--limite N] [--fundo F] [--projeto P]` troca o arquivo do anexo no site (mesmo ID).

## Eventos das estações: capturado / enviado (CAMP-017)
`POST /api/estacoes/eventos` (rede local + `X-Camp-Token`) recebe `{chave (uuid5 de projeto|evento|lote, lote = finalizado_em), estacao_id, tipo_estacao, operador, projeto_codigo, evento: "capturado"|"enviado", total_arquivos, pasta_entrada, sha256_manifesto}`. **Idempotente pela `chave`**; `sha256_manifesto` e `total_arquivos` podem ser `null` (no "capturado" ainda não há manifesto). Grava em `estacao_evento` e no histórico do projeto (`evento`).
- **Fila / painel inicial:** "Enviados pela estação e ainda sem processar": evento `enviado` há mais de 1 h sem lote do projeto criado depois (`GET /api/estacoes/eventos/pendentes`).
- **Contagem:** ao importar o lote, compara o total enviado com as folhas que chegaram (criadas + atualizadas + ignoradas + retiradas). Só abre **aviso** (gravidade `aviso`, nunca bloqueia) quando chegaram **menos** folhas que arquivos enviados; folhas a mais não é divergência (a estação Windows pode mandar total menor que o manifesto mesclado com lote anterior ainda não consumido), e total `null` nunca diverge.
- Heartbeat do CV2 2.4: `detalhe.alerta` (lote incompleto, estado `erro`) aparece em Estações e em "Problemas que bloqueiam" do painel inicial.
