# Contrato único dos sistemas CAMP (CAMP-001)

Este é o ponto de entrada de TODOS os contratos entre os sistemas CAMP. Cada repositório tem um `CLAUDE.md` que aponta para cá.
Regra de ouro: **mudou um campo, subiu a versão do contrato e atualizou os exemplos no mesmo commit.** Campo novo é sempre OPCIONAL
(a versão antiga do outro lado precisa continuar funcionando). Detalhes que ainda não foram promovidos para cá continuam nos documentos citados.

Versão deste documento: **1.3 (27/10/2026)**. Contrato CV2 ↔ painel: **2.5** (`backend/app/contrato.py`).
Board oficial para tickets transversais: **"Camp todos sistemas"** (Trello). Os boards "CAMP Vision 2", "CAMP Estações" e "CAMP Acervos — Painel" são históricos.

## 1. Mapa dos sistemas

| Sistema | Repositório | Onde roda | Papel |
|---|---|---|---|
| Estação Windows (Contex) | `camp-sistema-digitalizacao` | PC do scanner | captura, F9 reserva projeto, F12 envia lote |
| Estação Mac (fotografia) | `camp-sistema-digitalizacao-mac` | Mac da fotografia | idem, para fotos/negativos/slides |
| CAMP Vision 2 (CV2) | `campvision-new` (o `campvision2` é o app antigo: não usar) | Ubuntu `.40` | lê a ENTRADA, aplica EXIF, organiza, grava JSONs na pasta final |
| Painel | `camp-painel` (este) | Ubuntu `.60:8000` (`painel.camp.arq.br` por túnel) | fonte da verdade: fundos, projetos, códigos, revisão, publicação |
| Site | `camp-wordpress` | WordPress + Tainacan | acervo público |
| QNAP | — | `192.168.15.30` (`Server-Camp` no Mac) | disco comum |

```
estações ──(HTTP: contexto, reservar, heartbeat, eventos)──▶ painel
estações ──(arquivos)──▶ QNAP  Arquivos/100 - Scanners  (ENTRADA)
CV2 ◀── lê a ENTRADA;  CV2 ──(arquivos)──▶ QNAP  Fundos e Escritorios/ACERVOS_CAMP/<Fundo>/01 - Projetos/<Fxxx-Pxxxx - Nome>/  (PRONTO)
CV2 ──(HTTP: reservar, heartbeat, aviso, reidentificar)──▶ painel;  painel LÊ o PRONTO (nunca a ENTRADA, nunca grava no QNAP)
painel ──(REST + Application Password)──▶ site;  painel PUXA pedidos do site (pull a cada 10 min)
```

## 2. Quem produz e quem consome cada arquivo/chamada

| Artefato | Produz | Consome | Onde |
|---|---|---|---|
| `status.json` do **Windows** (`{"status":"enviado_windows","etapa":"enviado_windows"}`) | Windows | CV2 | pasta do lote em `100 - Scanners` |
| `status_mac.json` (`{"status":"enviado_mac","etapa":"enviado_mac"}`) | Mac | CV2 | idem |
| `manifesto.json` (marca de fim + SHA-256) | Windows e Mac (por último, atômico) | CV2 | idem |
| `info_projeto.json` da estação | Windows e Mac | CV2 | idem |
| `info_lote_*_mac.json` | Mac | CV2 (é só MARCADOR, mesclado em `dados`) | idem |
| `status.json` do **CV2** (`pronto`/`processando`/`erro`…) | CV2 | **painel** | pasta final em `ACERVOS_CAMP` |
| `info_projeto.json` do CV2, `pacote_tainacan.json`, `catalogacao/erros.json`, `_campvision/registro/*.jsonl` | CV2 | painel | pasta final |

Ou seja: o nome `status.json` existe nos DOIS lados com donos diferentes. Na ENTRADA quem escreve é a estação Windows e quem lê é o CV2;
na pasta FINAL quem escreve é o CV2 e quem lê é o painel. O painel nunca lê a ENTRADA.

## 3. Estações ↔ painel (HTTP, sem login)

Autorização (`backend/app/rede.py`, `exigir_estacao`): sem `estacao.token` no painel vale só a LAN verdadeira (192.168.x.x, 10.x.x.x, 127.0.0.1, sem cabeçalho de proxy).
Com `estacao.token`, o cabeçalho **`X-Camp-Token`** é obrigatório para todos, inclusive na LAN. 401 = token ausente/errado; 403 = fora da LAN ou via proxy sem token. Recusas aparecem em Estações (`estacao_negada`).
Estações e CV2 mandam o token quando houver (`painel_token`). 410 devolve `mensagem` para mostrar ao operador.

| Chamada | Quem chama | Resumo |
|---|---|---|
| `GET /api/estacoes/contexto` | estações, CV2 | fundos (`codigo_fundo`, `prefixo`, `nome`, `ultimo_projeto`, `proximo_projeto`, `autoridade{}`, `coautores[]`, `periodo_atuacao{de,ate}`) e `operadores[]` (só nomes) |
| `POST /api/estacoes/projetos/reservar` | estações, CV2 | cria/reutiliza projeto; idempotente por `chave_reserva` (32 hex); 202 `{pendente, decisao_id}` quando o painel pergunta a uma pessoa; 410 `{descartado}` lote descartado; 422 nome de subpasta |
| `POST /api/estacoes/heartbeat` | estações, CV2 | `estado` ∈ ocioso, capturando, finalizando, backup, processando, erro, vigiando, pasta indisponível; texto livre em `detalhe.situacao` |
| `POST /api/estacoes/eventos` | estações | `capturado` / `enviado`, idempotente por `chave` (uuid); nunca pode bloquear o operador |
| `GET /api/fundos.json` | Windows ANTIGO (legado) | aposentável por `legado.fundos_json` = 0 (ver §8) |

Exemplo de reserva (corpo):
```json
{"fundo_codigo":"F026","titulo":"Edificio Taruma","ano":1972,"cidade":"Santos","operador":"Beatriz",
 "chave_reserva":"0f3a9c1d5b7e4a2c8d6e1f0a9b8c7d6e","identificacao_original":"P0001 - Edificio Taruma 1972",
 "projeto_ja_existia":false,"numero_projeto":null,"p_estacao":"P0001"}
```
Resposta: `{"codigo":"F026-P0001","numero_projeto":"P0001","fundo_codigo":"F026","titulo":"Edificio Taruma","ano":1972,"cidade":"Santos","identificacao_original":"P0001 - Edificio Taruma 1972","outros_fundos":[]}`.
Regra do número P: o painel só reaproveita projeto com `projeto_ja_existia: true` + `numero_projeto` válido do fundo; o "P0001 - " na frente do nome é só pista (abre decisão).

## 4. Estações → `100 - Scanners` (arquivos)

Exemplos reais (campos novos são opcionais; as chaves antigas continuam):
```json
// status.json (Windows)  — gravado POR ÚLTIMO, de forma atômica
{"status":"enviado_windows","etapa":"enviado_windows","atualizado_em":"2026-10-15T09:00:00-03:00","atualizado_por":"WIN-01"}
// status_mac.json (Mac)
{"status":"enviado_mac","etapa":"enviado_mac","atualizado_em":"2026-10-15T09:00:00-03:00","atualizado_por":"MAC-01"}
// manifesto.json — por último, atômico
{"versao":1,"estacao_id":"WIN-01","tipo_estacao":"contex","operador":"Beatriz","fundo_codigo":"F026","projeto_codigo":"F026-P0001",
 "numero_projeto":"P0001","projeto_ja_existia":false,"identificacao_original":"P0001 - Edificio Taruma 1972","serie":"S01",
 "contagens":{"arquivos":24},"arquivos":[{"caminho":"01 - Desenhos e pranchas/a.tif","tamanho":123456,"sha256":"…"}],"gerado_em":"2026-10-15T09:00:00-03:00"}
// info_projeto.json (estação) — chaves antigas mantidas + as novas
{"codigo":"F026-P0001","fundo_codigo":"F026","estacao":"WIN-01","tipo_estacao":"contex","enviado_em":"2026-10-15T09:00:00-03:00"}
```
CV2 aceita `status` OU `etapa` ("enviado_windows"/"enviado_mac"), o manifesto e, por compatibilidade, o modo antigo. Mapeamentos do CV2: `estacao_id`→`estacao`, `estacao_tipo`→`tipo_estacao`, `finalizado_em`→`enviado_em`; `numero_projeto` NÃO vira `projeto`; `codigo_fundo` NÃO vira `escritorio`.

**Séries (tabela única):** S01 Desenhos e pranchas · S02 Documentos textuais · S03 Fotografias · S04 Negativos · S05 Slides · S06 Materiais e especificações · S07 Publicações · S08 Redesenhos · S99 Não identificado. Pasta no projeto = `NN - Nome` (ex.: `01 - Desenhos e pranchas`, `08 - Redesenhos`).

## 5. CV2 ↔ painel

Fonte única do contrato: `campvision-new/docs/contrato-painel.md` (**2.5**); cópia literal e exemplos reais em `tests/contrato/` deste repositório (`ORIGEM.txt` diz de qual commit). Resumo: o CV2 grava `info_projeto.json`, `status.json`, `pacote_tainacan.json`, `catalogacao/erros.json` e o livro `_campvision/`; avisa o painel em `POST /api/campvision/aviso` (202; o painel relê só aquela pasta). `autoria_divergente` é AVISO (a folha sobe com "Autoria não confirmada").

### 5.1 Corrigir o que entrou no projeto errado (CAMP-009)

As rotas administrativas de mover/mesclar exigem **login de admin**; o CV2 não tem login. Por isso existe a porta do CV2, que usa as MESMAS regras:

| Rota | Quem pode | Token | Idempotência |
|---|---|---|---|
| `POST /api/itens/mover` `{itens[], destino, motivo}` | admin logado | — | folha já no destino é ignorada |
| `POST /api/projetos/{origem}/mesclar-em` `{destino, motivo}` | admin logado | — | origem já mesclada = 409 |
| `POST /api/filas/{lid}/mover-para` `{projeto_codigo, motivo}` | admin logado | — | lote já no projeto = 400 |
| `POST /api/projetos/{codigo}/recodificar` `{novo, motivo}` | admin logado | — | mesmo fundo; antigo continua reservado |
| **`POST /api/campvision/reidentificar`** | **CV2** | `X-Camp-Token` ou LAN | sim (ver abaixo) |

`POST /api/campvision/reidentificar`:
```json
{"simular": true, "motivo": "reidentificar F026",
 "movimentos": [{"itens": ["F026-P0236-1980-S01-D00001"], "destino": "F026-P0002"}, {"lote_id": 41, "destino": "F026-P0002"}],
 "mesclar": [{"origem": "F026-P0240", "destino": "F026-P0002"}]}
```
- **`simular` é `true` por padrão** e só `false` aplica. Simular roda tudo numa transação e desfaz: o plano é exatamente o que aconteceria. Resposta: `{ok, simulado, aplicado, operacoes[], mapa{antigo:novo}, erros}`.
- **Aplicar exige `campvision.reidentificar_aplicar` = 1** no painel (nasce 0). Sem isso: 403 com `mensagem`.
- Tudo ou nada: com qualquer erro nada é gravado (409 com o plano e o erro de cada operação).
- Idempotente: folha já movida volta em `ja_movidos`; mesclar de novo no mesmo destino volta `ja_mesclado`. Folha pública no site é recusada (409): despublicar antes.
- Redirecionamentos antigo→novo entram na fila do site (CAMP-014) só ao aplicar. O `mapa` serve para o CV2 renomear/mover os arquivos no QNAP e refazer os pacotes.
- **Ordem do CV2** (a implementar no campvision-new): (1) `vigia.py --reidentificar` SEM `--sim` mostra o plano local; (2) chamar o painel com `simular: true` e conferir o plano; (3) admin liga `campvision.reidentificar_aplicar`; (4) `--sim` move os arquivos e chama o painel com `simular: false`; (5) `aviso` por projeto afetado. Ordem de deploy: **painel antes do CV2**; o CV2 antigo não chama a rota nova, então nada quebra.
- Aceite no F026 (precisa de máquina real e decisão do Rafa): folhas no QNAP e no painel batem, nada duplicado, redirecionamentos gravados.

### 5.2 Pastas que o painel decidiu que são de outro projeto (UX-43, NOVO 1.3)

`GET /api/campvision/destinos` (rede local ou `X-Camp-Token`; **só leitura**, rota nova e opcional: o CV2 antigo não chama e nada quebra) →
```json
{"destinos": [{"id": 3, "lote_id": 41, "pasta": "/mnt/qnap/.../F026-P0010 - Edifício Marambaia - 1970-1971", "nome_pasta": "Edifício Marambaia - 1970-1971",
  "de": "F026-P0010", "para": "F026-P0095", "para_titulo": "Marambaia", "criado": false, "desde": "2026-10-27 22:10:00",
  "comando": "vigia.py --reidentificar F026-P0010"}]}
```
- É a lista do "Verificar destino pelo painel" (`destino.automatico`, padrão `simular`: em simular a lista fica vazia). `criado: true` = o projeto de destino foi criado pelo painel (próximo P; já aparece em `/api/estacoes/contexto`).
- O painel NÃO muda o lote de projeto nem mexe no QNAP: o lote fica "movendo" no projeto antigo e não importa. Quem reorganiza a pasta é o CV2, pelo caminho que já existe (`--reidentificar <de>`: plano sem `--sim`, depois `--sim`; aviso por projeto).
- O item sai da lista sozinho quando o material chega ao projeto `para` (lote de outra pasta criado depois da decisão), quando o lote passa para `para` (`/api/campvision/reidentificar` com `lote_id`) ou quando uma pessoa usa Desfazer no painel.
- Até o CV2 ler esta rota (a implementar no campvision-new), uma pessoa roda o `comando` no servidor do CAMP Vision.

## 6. Painel ↔ site

Autenticação: Application Password do WordPress (painel → site). Rotas do site `/wp-json/camp/v1/…`:
- `GET /solicitacoes?limite=200` (sem `marcar`) — **somente leitura** dos pedidos ainda não confirmados, em ordem dos mais antigos; devolve array `[{id,tipo,codigo,nome,email,instituicao,finalidade,mensagem,criado_em}]`. O painel coleta a cada `site.coleta_pedidos_min` (padrão 10; 0 desliga). Salva em `pedido_site` (chave primária `site_id`) e confirma **após COMMIT**, nunca antes.
- **NOVO 1.1**: `POST /solicitacoes/confirmar` corpo `{"ids":[101,102]}` (até 500 IDs inteiros, auth `edit_pages`) → `{"confirmados":[101],"ja_confirmados":[102],"nao_encontrados":[],"falhas":[]}`. A operação é idempotente; ACK perdido permite reenviar sem duplicar `pedido_site`. Se o POST falhar, o coletor interrompe a paginação e deixa os IDs no site. O `GET ?marcar=1` permanece como legado durante transição; o novo coletor não o usa.
- Recuperação dos pedidos que já tinham sido marcados pela versão antiga: `GET /solicitacoes?todas=1&pagina=N&limite=200` com Application Password; importar novamente por `site_id` sem duplicar. A varredura histórica é procedimento administrativo separado, não roda automaticamente.
- `alta-resolucao`/`consulta` → `solicitacao` (origem "site"); `correcao` → `erro` (origem "site"). A fila local `pedido_site` permite reprocessar falhas de negócio após o ACK.
- **Ordem de implantação**: WordPress 1.5.89 primeiro (rotas antigas continuam), painel depois. Painel novo sobre WordPress antigo não perde dados, mas acumula erro de ACK até atualizar o site.
- `POST /painel/redirecionamentos` — mapa antigo→novo (`/acervo/projetos/<slug>`, `/acervo/documentos/<slug>`), com fila e reenvio; falha não desfaz o local.
- `POST /painel/hub` — cria/atualiza o fundo/arquiteto; campo vazio NÃO apaga; para limpar, mandar `"__limpar__"`.
- **NOVO 1.2** (UX-41, site plugin 1.6.3): datas do arquiteto no mesmo `{"meta": {...}}` do hub, OPCIONAIS: `_camp_arq_nascimento` e `_camp_arq_falecimento` (pessoa: ano, ex. `"1925"`) e `_camp_arq_atuacao` (escritório/família: `"1964–2010"`, `"desde 1964"`, `"até 2010"`), vindos de `agente.existencia_inicio/existencia_fim`. Só vai o preenchido; o painel nunca manda `"__limpar__"` para datas (não há como esvaziá-las no painel). O site mantém o texto escrito à mão quando ele já contém o valor (`"São Paulo, 1925"` × `"1925"`, resposta em `mantidos`, opcional) e, com um só ano no texto, troca só o ano. Site anterior a 1.6.3 devolve as chaves em `ignorados` (sem erro). Ordem: site primeiro, painel depois.
- `POST /painel/pessoa/apagar` `{"email": "..."}` — LGPD.
- `POST /api/pedidos/site` (painel recebe, `X-Camp-Token` = `pedidos.token`): caminho antigo/alternativo (push); ver `docs/pedidos-do-site.md`.
- Imagens públicas: JPEG q85 sRGB com lado maior ≤ 1920 px; o TIF e a prévia de 3000 px nunca vão ao site.

## 7. Versionamento e exemplos

1. Mudou campo ou rota de contrato → sobe a versão no documento dono (CV2↔painel: `contrato.py` + `tests/contrato/VERSAO`; este arquivo: cabeçalho) **no mesmo commit** e atualiza os exemplos.
2. Campo novo é opcional; remover/renomear exige período em que os dois nomes valem.
3. Teste novo deve falhar sem a correção.

## 8. Legado e como desligar (CAMP-024, lado do painel)

Chaves em Configurações (1 = ainda aceita, padrão). `GET /api/legado` (admin) mostra uso e se é seguro desligar; `POST /api/legado/{peca}` com `simular` (padrão) diz o efeito sem mudar nada.

| Peça | O que desliga | Alternativa correta |
|---|---|---|
| `legado.status_antigos` | `campvision_concluido`, `pronto_campvision2` viram "status desconhecido" (aviso) | `pronto` |
| `legado.nomes_de_teste` | pasta `asd` / `sei la` deixa de valer como teste | `"teste": true` no `info_projeto.json` |
| `legado.fundos_json` | `GET /api/fundos.json` responde 410 | `/api/estacoes/contexto` |

NÃO são legado (continuam): `enviado_windows`/`enviado_mac` (contrato §2), `etapa` no status das estações (até o manifesto substituir de verdade), `processando`.
Não feito no painel por depender de outros repositórios e de dados reais: remover `contadores_projeto.json` e `fundos.json` das estações, chaves `fase`/`campvision_concluido` e `pasta_vigiada` do CV2.
