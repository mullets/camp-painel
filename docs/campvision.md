# Contrato entre o painel e o CAMP Vision 2

Este documento é o contrato que o **CAMP Vision 2 (CV2)** segue para falar com o **painel**. Tudo que está aqui foi verificado por teste automático
(`tests/teste_backend.py`, bloco "Contrato com o CAMP Vision 2"). O que ainda **não** existe está na seção 9.
Repositório oficial do CV2: `github.com/mullets/campvision-new` (o `campvision2` é o app antigo, com YOLO/Tesseract: não usar).

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
```
/mnt/qnap/acervos/Fundos e Escritorios/ACERVOS_CAMP/
  <Fundo>/
    01 - Projetos/
      <Fxxx-Pxxxx - Nome>/          ← UM LOTE = esta pasta (tem info_projeto.json e status.json)
        info_projeto.json
        status.json
        <série>/                    ← Plantas, Fotografias, Documentos... (as imagens ficam aqui)
```
- **Um lote é a pasta do projeto** (a que contém `info_projeto.json` e/ou `status.json`). O painel não entra em outra pasta dentro dele.
- O painel conta **DOCUMENTOS**, não arquivos: a chave é (série, nome sem extensão), com a série sendo a primeira pasta abaixo da do projeto. Cada formato pode ficar numa subpasta própria dentro da série
  (`<série>/TIF/F026-P0006-1975-S01-D00001.tif` e `<série>/JPG/F026-P0006-1975-S01-D00001.jpg` são **um** documento, com dois formatos). Extensões: `.jpg .jpeg .tif .tiff .dng .png`. **PDF não é contado** (ver seção 9).
  Lixeira e ocultos do QNAP (`@Recycle`, `@eaDir`, `#recycle`, nomes com ponto) são ignorados.
- Na **página do projeto**, o painel "Encontradas no QNAP, ainda não catalogadas no painel" lista os documentos da pasta do lote que ainda não são folhas do painel (com prévia quando há JPG). A lista de folhas do projeto vem do
  banco (itens do site e itens locais); **importar o lote para virar folha é a revisão pós-CAMP Vision, que ainda não existe**.
- O nome da pasta do projeto **deve começar pelo código** (`F002-P0002 - Igreja...`): é o último recurso do painel para descobrir o projeto (seção 3).

## 3. `info_projeto.json` (na pasta do projeto)
```json
{
  "codigo": "F002-P0002",
  "nome": "Igreja Paróquia Mãe do Salvador",
  "folhas_esperadas": 19,
  "estacao": "contex1",
  "tipo_estacao": "contex",
  "operador": "Beatriz",
  "operador_email": "beatriz@camp.arq.br",
  "fundo_codigo": "F002",
  "teste": false
}
```
| Chave | Obrigatória | O que o painel faz |
|---|---|---|
| `codigo` | **sim** | Código do projeto (`Fxxx-Pxxxx`). Tem que existir no painel. Aceita também `projeto_codigo` |
| `nome` | não | Nome do lote nas Filas (aceita `titulo`; senão usa o nome da pasta) |
| `folhas_esperadas` | recomendada | Quantas folhas deveriam existir; o painel compara com as encontradas (aceita `itens_esperados` ou `quantidade`) |
| `estacao`, `tipo_estacao`, `operador`, `operador_email`, `fundo_codigo` | não | Guardados com o lote, para saber quem digitalizou |
| `teste` | não | **`true` = o lote é ignorado.** Também são ignoradas pastas chamadas `teste`, `asd` e `sei la` |

**Como o painel descobre o código do projeto** (usa o primeiro que achar): `codigo` / `projeto_codigo` do `info_projeto.json` → `codigo` do `status.json`
→ nome da pasta → nome da pasta-mãe + nome da pasta. **Se o código não existir no painel, o lote é ignorado** ("sem código de projeto reconhecido").

## 4. `status.json` (na pasta do projeto)
```json
{ "status": "pronto", "codigo": "F002-P0002", "fase": "organizado", "atualizado_em": "2026-10-07T18:30:00-03:00" }
```
Só `status` (e `codigo`) são lidos. Qualquer outra chave (`fase`, `mensagem`, `erro`, `campvision2_pranchas`...) é **guardada com o lote e mostrada, mas não interpretada**.

### Valores de `status` que o painel entende
| Valor | Etapa na fila do painel | Observação |
|---|---|---|
| **`processando`** | Processando | Aparece nas Filas; **não pede revisão** nem conta como pendência |
| **`pronto`** | **Revisão** | Pede revisão humana. Nada é publicado sozinho |
| **`erro`** | Erro | Aparece nas Filas com o erro |
| *(antigos)* `enviado_windows` | Processando | Aceito por compatibilidade |
| *(antigos)* `campvision_concluido`, `pronto_campvision2`, ou **sem status** | Revisão | Aceitos por compatibilidade |
| qualquer outro valor | Revisão **+ aviso** | A varredura devolve `avisos` com o valor desconhecido |

Regras:
- **Lote já publicado ou em rascunho nunca volta atrás**, mesmo que o CV2 grave `processando` de novo.
- Um lote pode mudar de etapa entre varreduras (`processando` → `pronto`); isso fica na auditoria.
- JSON inválido ou vazio: o lote é ignorado ("manifesto inválido").

## 5. Como o painel fica sabendo de um lote
- **Aviso do CV2 (o caminho normal):** `POST /api/campvision/aviso`, a cada troca de `status`. O painel relê **só aquela pasta**; a fila enche sozinha (seção 6.4).
- **Varredura completa**, no painel: *Filas → Varrer QNAP* (`POST /api/filas/varrer-qnap`, exige login de **operador** ou acima). Agora é **reconciliação**: pega o que um aviso perdeu.
- A cada 10 minutos o painel só **conta** lotes e mede espaço no QNAP (cartão do painel inicial); isso **não cria fila**.
- A varredura anda por **toda** a pasta final. Por isso a estrutura deve ser rasa e fixa (seção 2).

## 6. Chamadas HTTP (CV2 → painel)
Base: `http://192.168.15.60:8000`. Sem login. A regra (`app/rede.py`):
- **Sem `estacao.token` configurado:** só vale a rede local (192.168.x.x ou 10.x.x.x). De fora, ou passando por proxy/túnel (cabeçalhos `X-Forwarded-For`, `CF-Connecting-IP`...): **403**.
- **Com `estacao.token` configurado** (Configurações; valor sensível, que só o administrador vê): o cabeçalho **`X-Camp-Token`** é **obrigatório para todos**. Sem ele ou errado: **401**, mesmo de dentro da rede local. Um token válido vale **até de fora** da rede local (é para estações atrás de túnel).
  O CV2 deve ler o token de uma variável de ambiente (ex.: `CAMP_PAINEL_TOKEN`) e **nunca gravá-lo no repositório**.

### 6.1 `GET /api/estacoes/contexto` — fundos e próximo número de projeto
```json
{ "fundos": [ { "codigo_fundo": "F002", "prefixo": "AMA", "nome": "Arnaldo Martino", "ultimo_projeto": "P0002", "proximo_projeto": "P0003" } ] }
```
Com `?fundo=F002` a resposta inclui também `"projetos"`: lista de `{ codigo, numero_projeto, projeto, ano, cidade, identificacao_original }`. Fundo inexistente ou inativo: **404**. Só aparecem fundos ativos que têm sigla (`prefixo`).

### 6.2 `POST /api/estacoes/projetos/reservar` — cria o projeto com o contador oficial
Corpo: `fundo_codigo` e `titulo` (obrigatórios); `ano` (0 = sem data; 1800–2100), `cidade`, `identificacao_original`, `operador`, **`chave_reserva`** (uuid de 32 caracteres hexadecimais).
```json
{ "fundo_codigo": "F002", "titulo": "Igreja Paróquia Mãe do Salvador", "ano": 1977, "cidade": "São Paulo/SP", "operador": "Beatriz", "chave_reserva": "0f8e...32 hex" }
```
Resposta: `{ "codigo": "F002-P0003", "numero_projeto": "P0003", "fundo_codigo": "F002", "titulo": "...", "ano": 1977, "cidade": "...", "identificacao_original": null }`.
- **Idempotente:** repetir a chamada com a **mesma `chave_reserva`** devolve o **mesmo projeto**, sem criar outro. Use sempre uma chave e repita em caso de timeout. Chave diferente = próximo número.
- Erros: título vazio **400**; ano inválido **400**; fundo inexistente **400/404**.
- O **número P vem sempre daqui**: o CV2 nunca inventa número.
- **O painel verifica antes de criar.** Se já existe, no **mesmo fundo**, projeto com nome, identificação original, ano e cidade parecidos, ele **não cria**: abre uma **decisão** para uma pessoa ("é o mesmo? adiciono ao existente ou crio novo?") e responde **202**
  `{"pendente": true, "decisao_id": N, "mensagem": "..."}`, **sem `codigo`**. O CV2 trata como "sem número ainda": espera e **tenta de novo com a MESMA `chave_reserva`** (obrigatório mandar sempre a mesma chave).
  Depois da decisão, a mesma chamada devolve **200**: o código do projeto **existente** escolhido (com `"existente": true` e `decisao_id`: **adicione o material a esse projeto, não crie pasta nova**) ou o de um projeto **novo** criado.
- `confirmar_novo: true` (opcional) pula a verificação: use só se a pessoa na estação já viu a lista de projetos do fundo e escolheu criar um novo.
- Nome que só difere por número ou letra ("Casa 1" x "Casa 2", "Torre A" x "Torre B") **não** é considerado parecido.

### 6.3 `POST /api/estacoes/heartbeat` — "estou vivo e fazendo isto"
**Serve para o CV2** e aceita **o que o CV2 realmente manda** (`docs/contrato-painel.md` do campvision-new). Use:
| Campo | Valor para o CV2 |
|---|---|
| `estacao_id` | **`campvision2`** para a máquina `.40` (minúsculas, até 64 caracteres). A cópia do Mac, se existir, deve usar outro id (ex.: `campvision2-mac`): ela é aceita, mas só `campvision2` aparece em Estações |
| `tipo_estacao` | **`campvision`** |
| `app` | `campvision-new` |
| `estado` | **`vigiando`**, **`processando`**, **`pasta indisponível`** ou **`erro`** (os do CV2). Também aceitos: `ocioso`, `capturando`, `finalizando`, `backup` (estações de captura) |
| `versao`, `hostname`, `ip_local` | opcionais (`192.168.15.40`) |
| `projeto` (ou `projeto_codigo`), `fundo_codigo` | o que está processando agora (opcional) |
| `progresso` (`{feitos, total}`), `fila`, `hoje` (`{projetos, imagens, erros, custo_usd}`), `montagens` (`{entrada, acervo}`) | opcionais; ficam guardados e aparecem em Estações (`app_detalhe`) |
| `operador`, `ultimo_erro` | opcionais (`ultimo_erro` até 500 caracteres) |

- Envie **a cada 30 s** (ou no máximo a cada 60 s): **mais de 75 s sem heartbeat = "app offline"** em Estações. É o que mostra "o que está fazendo" no painel.
- Resposta: `{ "ok": true, "estacao_id": "campvision2", "estado": "processando" }`. `tipo_estacao` ou `estado` inválidos: **400**.
- O heartbeat nunca deve travar o CV2: use timeout curto (3–5 s) e ignore falhas.

### 6.4 `POST /api/campvision/aviso` — "acabei de mudar este projeto, olhe só ele"
Corpo: `{"codigo": "F002-P0002", "pasta": "F002 - BSG.../01 - Projetos/F002-P0002 - Residência X", "status": "pronto", "em": "..."}`. Responde **202**.
- `pasta`: relativa à raiz final do painel (`qnap.prontos_raiz`), ou absoluta **dentro** dela. A própria raiz, vazio e qualquer caminho que escape dela (`../`, `/etc`) são recusados com **400**.
- O painel lê o **`status.json` do disco**; o `status` do aviso é só uma dica (o aviso não manda no estado).
- `codigo` (opcional): se não bater com o projeto da pasta, **nada é importado** (`ok: false`).
- Resposta: `{ok, acao, etapa, codigo, folhas, pasta}` com `acao` = `nova` | `atualizada` | `igual` | `ignorada` (esta com `motivo`). Pasta ainda não visível pelo SMB: `ok: false` ("não encontrada (ainda?)"); o CV2 pode avisar de novo.
- Pasta da **entrada bruta** é recusada (`ok: false`): o painel só lê o material final.
- Mesma regra de rede e token da seção 6. Depois de uma queda do painel, o CV2 reenvia o aviso mais recente de cada projeto.

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
- **Do contrato do CV2 (`docs/contrato-painel.md`, §7), o painel ainda NÃO faz:** ler o `status.json` novo (`lote_atual`, contagens, `erros_bloqueantes`); ler `catalogacao/erros.json` em "Erros relatados"; ler `catalogacao.csv` e `contatos.jpg` (**revisão pós-CAMP Vision**: ver o que foi lido, corrigir e aprovar); ler `_campvision/registro/` no "Histórico"; reconciliação noturna; e um canal para **pedir releitura** de um projeto (hoje o painel só recebe, nunca manda nada ao CV2).
- **PDF** não entra na contagem de folhas (`folhas_encontradas`), embora o CV2 processe PDF. Lotes só de PDF aparecem com 0 folhas.
- O painel **não lê** `catalogacao.csv`, `contatos.jpg` nem `pacote_tainacan.json`. A revisão pós-CV2 (folha de contatos, girar, duplicatas) depende do formato real do CSV.
- Marcar o lote como `teste` só vale pelo `info_projeto.json`; o painel não sabe de testes que estejam só no nome da pasta além de `teste`, `asd` e `sei la`.

## 10. Revisão do lote (pós-CAMP Vision)
O CAMP Vision grava a catalogação e o painel **importa, uma pessoa confere/corrige e o admin aprova**. O painel não decide nada sozinho.

**Fonte:** `<pasta do lote>/catalogacao/pacote_tainacan.json` (versão 2). Entra só o que está em `documentos`; `retirados` (autoria divergente, retirada por decisão) **não entra** e é listado no resultado.
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
- **Ficam de fora:** duplicatas, autoria divergente e folhas **ainda não conferidas** na revisão (nunca vão ao site).
- **O que só uma pessoa resolve** e bloqueia: direitos do fundo, autoria divergente/erros bloqueantes, lote de teste, "nenhuma folha conferida ainda". Cada um traz o botão que resolve.

**"Publicar agora"** (`POST /api/projetos/{codigo}/publicar-tudo`, admin) faz a sequência: dossiê -> folhas (rascunho) -> autorizar -> publicar. Regras:
- **Idempotente:** clicar de novo continua de onde parou; o que já subiu não se repete.
- **Fatias de tempo:** cada chamada envia folhas por até ~40 s e devolve `parcial` com quantas faltam; a tela repete e mostra o progresso.
- **Falha numa folha:** para antes de autorizar e publicar, diz qual folha e por quê. Nada fica meio publicado.
- **Trava contra clique duplo:** 409 se o mesmo projeto já está sendo publicado.
- Todos os portões de `POST /publicar` continuam valendo: ele revalida no fim.

**Regra única de folha elegível** (`publicacao.ELEGIVEL_LOCAL`, antes repetida em 4 lugares): sem autoria divergente, não é duplicata e, se veio da revisão do CAMP Vision, já foi conferida/corrigida.
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
