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
- O painel conta as imagens do lote **em todas as subpastas**. Extensões contadas: `.jpg .jpeg .tif .tiff .dng .png`. **PDF não é contado** (ver seção 9).
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

## 5. Como o painel fica sabendo de um lote (hoje)
- **Varredura manual**: no painel, *Filas → Varrer QNAP* (`POST /api/filas/varrer-qnap`, exige login de **operador** ou acima). É o único jeito de criar/atualizar lotes.
- A cada 10 minutos o painel só **conta** lotes e mede espaço no QNAP (cartão do painel inicial); isso **não cria fila**.
- A varredura anda por **toda** a pasta final. Por isso a estrutura deve ser rasa e fixa (seção 2).

## 6. Chamadas HTTP (CV2 → painel)
Base: `http://192.168.15.60:8000`. **Só funcionam na rede local** (192.168.x.x ou 10.x.x.x), sem login.
- Fora da rede local, ou passando por proxy/túnel (cabeçalhos `X-Forwarded-For`, `CF-Connecting-IP`...): **403**.
- **Token:** se o painel tiver `estacao.token` configurado (Configurações; é um valor sensível, que só o administrador vê), o cabeçalho **`X-Camp-Token`** é **obrigatório**, inclusive dentro da rede local. Sem ele ou errado: **401**. Sem token configurado, vale só a rede local.
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

### 6.3 `POST /api/estacoes/heartbeat` — "estou vivo e fazendo isto"
**Serve para o CV2** (desde esta versão). Use:
| Campo | Valor para o CV2 |
|---|---|
| `estacao_id` | **`campvision2`** para a máquina `.40` (minúsculas, até 64 caracteres). A cópia do Mac, se existir, deve usar outro id (ex.: `campvision2-mac`): ela é aceita, mas só `campvision2` aparece em Estações |
| `tipo_estacao` | **`campvision`** |
| `app` | `campvision-new` |
| `estado` | `ocioso`, `processando` ou `erro` (também aceitos: `capturando`, `finalizando`, `backup`) |
| `versao`, `hostname`, `ip_local` | opcionais (`192.168.15.40`) |
| `fundo_codigo`, `projeto_codigo` | o que está processando agora (opcional) |
| `operador`, `ultimo_erro` | opcionais (`ultimo_erro` até 500 caracteres) |

- Envie **a cada 30 s** (ou no máximo a cada 60 s): **mais de 75 s sem heartbeat = "app offline"** em Estações. É o que mostra "o que está fazendo" no painel.
- Resposta: `{ "ok": true, "estacao_id": "campvision2", "estado": "processando" }`. `tipo_estacao` ou `estado` inválidos: **400**.
- O heartbeat nunca deve travar o CV2: use timeout curto (3–5 s) e ignore falhas.

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
- **Aviso automático de lote pronto.** Hoje o painel só descobre lotes na varredura manual. Proposta: `POST /api/estacoes/lote-pronto` (o CV2 avisa o código do projeto e o painel lê só aquela pasta, sem varrer tudo). **Não implementado.**
- **PDF** não entra na contagem de folhas (`folhas_encontradas`), embora o CV2 processe PDF. Lotes só de PDF aparecem com 0 folhas.
- O painel **não lê** `catalogacao.csv`, `contatos.jpg` nem `pacote_tainacan.json`. A revisão pós-CV2 (folha de contatos, girar, duplicatas) depende do formato real do CSV.
- Marcar o lote como `teste` só vale pelo `info_projeto.json`; o painel não sabe de testes que estejam só no nome da pasta além de `teste`, `asd` e `sei la`.
