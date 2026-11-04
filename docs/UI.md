# CAMP Painel — padrões de UI

Este arquivo define o padrão mínimo para novas telas e alterações visuais.

## Princípios

1. **Uma tarefa por bloco.** Use `.panel` para conteúdo delimitado e evite criar variações locais sem necessidade.
2. **Layout estrutural usa classes.** Não use `style=""` para grid, flex, espaçamento, largura ou posicionamento de novos componentes.
3. **Estados têm significado estável.** Verde = ok; âmbar = atenção; vermelho = falha/bloqueio; cinza = neutro/não configurado.
4. **Ação principal é única.** Em um mesmo bloco, no máximo uma ação `.btn.pri`.
5. **Feedback sempre visível.** Loading, erro, vazio, salvo e não salvo não podem depender apenas de toast.
6. **Operador vê tarefa, não infraestrutura.** IDs internos e nomes de implementação ficam restritos a telas administrativas.
7. **Acessibilidade é requisito.** Todo controle precisa de nome acessível, foco visível e operação por teclado.

## Primitivas

- `.stack`: pilha vertical com espaçamento padrão.
- `.cluster`: itens em linha, quebrando quando necessário.
- `.toolbar`: ações e filtros; use `.spacer` para empurrar ações secundárias.
- `.surface`: superfície padrão com fundo/borda/radius.
- `.status-dot.ok|warn|bad`: indicador de estado.
- `.panel .ph/.pb`: cabeçalho e corpo de painéis.
- `.filterbar`: busca/filtros de tabelas.
- `.bulkbar`: ações sobre seleção múltipla.
- `.field`: campo de formulário; erros usam `.invalid` + `.field-error`.
- `.modal` e `.drawer`: sobreposições; não crie outro padrão paralelo.

## Regressões

Antes de reiniciar produção, `scripts/check_ui.py` verifica estruturas e seletores essenciais.
O updater deve abortar se essa checagem falhar.

O orçamento de estilos inline é controlado. Para aumentar o limite é obrigatório justificar no PR; preferencialmente reduza o total.

## Telas críticas

Qualquer mudança nestas áreas exige revisão visual: Painel, Fundos, Projeto, Etiquetas e Configurações.

## Sistema de design (redesenho §18, 04/11/2026)

Tokens no `:root` de `frontend/index.html`. Cor sempre por token, e todo token de cor existe nos dois temas (claro e escuro).

### Superfícies e cores
| Token | Para quê |
| --- | --- |
| `--bg` | fundo da página (o mais escuro no tema escuro) |
| `--surface` | cartão / painel (`.panel`) |
| `--surface2` | área secundária dentro do cartão (cabeçalho de grupo, campo somente leitura) |
| `--hover` | linha ou item com o mouse em cima |
| `--sel` + `--sel-ink` | item selecionado / ativo (menu, linha marcada); `--sel-ink` é o texto sobre ele |
| `--line` · `--line2` · `--line-forte` | contorno do cartão · divisória interna · contorno do botão no hover e de estado neutro |
| `--blue` | ação e dado informativo (botão primário, link) |
| `--amber` | atenção e destaque pontual — **não** use para o 1º colocado de ranking nem para enfeite |
| `--green` | sucesso real (só depois que a ação foi confirmada) |
| `--red` | erro, bloqueio, perda; texto sobre ele: `--on-red` |
| `--sombra-pop` | só em sobreposição (menu, painel flutuante); cartão não tem sombra |

Status nunca só por cor: use o chip `<span class="tag st ok|atencao|critico|sem">normal|atenção|crítico|não medido</span>` (ícone ✓ ! ✕ ? + texto + cor).

### Tipografia
| Token | Valor | Uso |
| --- | --- | --- |
| `--fs-page` | 28 px (24 no celular) | `h1`, título da página |
| `--fs-sec` | 18 px (17 no celular) | `h2`, título de seção / cartão |
| `--fs-sub` | 16 px | subtítulo, título de estado |
| `--fs-body` | 15 px | texto principal (`body`) |
| `--fs-tab` | 14 px | linhas de tabela e de lista, rótulo de métrica |
| `--fs-2nd` | 13 px | texto secundário (nunca menor que isto em frase) |
| `--fs-metric` · `--fs-metric-lg` | 28 · 32 px | número principal de cartão (`.metrica .v`, `.metrica.grande .v`) |
| `--fs-xs` / `--fs-2xs` | 12 px | só chip, etiqueta e contador — nunca frase |

Os tokens antigos continuam e valem: `--fs-sm` e `--fs-sm2` passaram a 13 px; `--fs-md` 13, `--fs-base` 14, `--fs-lg` 17, `--fs-xl` 20.
Fonte em px cru é reprovada pelo `check_ui` (teto); use o token mais próximo.

### Espaçamento e componentes
- `--gutter` (margem lateral da página: 26 px; 40 px ≥ 1500 px; 14 px no celular), `--gap-card` (16/20 px entre cartões), `--pad-card` (18 px),
  `--sp-1…--sp-8` (4…40 px), `--r-card` (raio do cartão, 8 px), `--linha-min` (52 px, linha de lista confortável), `--toque` (44 px).
- **Cartão** = `.panel`: `.ph` (título → resumo → ação) com `<div class="ph-txt"><h2>…</h2><p class="ph-resumo">…</p></div>`, `.pb` (conteúdo)
  e `.pf` (ações no rodapé). Contorno sutil, sem sombra.
- **Métrica** = `<div class="metrica"><span class="v">123</span><span class="l">rótulo</span><span class="d">detalhe</span></div>` (números tabulares).
- **Botões**: `.btn.pri` (primário, um por bloco) · `.btn` (secundário) · `.btn.perigo` (destrutivo, cheio, na janela de confirmação) ·
  `.btn.perigo-contorno` (destrutivo fora do menu) · `.btn.perigo-txt` (destrutivo dentro do "Mais ⋯"). `.btn.sm` para linha de lista.
- **Links**: sublinhados (mais grossos no mouse/foco); `.lnk` para botão que é link.
- **Foco**: anel azul de 2 px em tudo o que recebe foco pelo teclado (`:focus-visible`); não tire o `outline` sem pôr outro.
- Movimento: com `prefers-reduced-motion` as animações (esqueleto, giro do botão) param.

## Estados (redesenho §20)

Um componente só, `estadoHTML(tipo, o)` (CSS `.estado`), para tudo o que depende do servidor, do QNAP, do CAMP Vision ou do site:

| tipo | Quando | Campos |
| --- | --- | --- |
| `carregando` | esperando a resposta | `linhas` (esqueleto; o contêiner reserva a altura com `--esq-h` no CSS dele, sem pulo) |
| `vazio` | a consulta deu certo e não há registros no período | `titulo`, `texto` (diga o período; nunca preencha com números) |
| `erro` | a integração falhou | `servico` (o sistema afetado), `ultima` (a última informação conhecida), `acoes` (diagnóstico / tentar de novo), `detalhe` |
| `sem-permissao` | o papel não abre | `titulo` (o porquê), `quem` (quem pode autorizar) |
| `sucesso` | ação concluída | `titulo` + `id` (o identificador REAL: "Lote conferido: F003-P9001") |
| `desatualizado` | o dado na tela é velho | `ultima` (a última sincronização) |

Todos aceitam `acoes` (HTML de botões já escapado), `desfazer: {rotulo, attr}` (ex.: `{attr:'data-x-desfazer="F003-P9001"'}`; o
clique é tratado por quem chamou) e `solto: true` (dentro de um cartão, sem borda). `esqueletoHTML(n)` dá só as linhas cinzas.
Já usam o componente: `estadoErroHTML` (todas as listas), a página "Sem acesso" e a marca **Dados desatualizados** das listas
(`.stale-note`, agora com "Última atualização às HH:MM"). Ação reversível frequente continua com o **Desfazer** do aviso rápido
(`toast(msg,{acao:{rotulo:'Desfazer',fn}})`, 8 s) e o resultado no lugar com `avisoNoLugar` (padrao-de-tela.md §6).
**Erro nunca vira zero**: sem resposta, mostre `erro` com o serviço; carregando, `carregando` ou `NUM_SKEL`.
