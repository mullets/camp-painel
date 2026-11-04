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
  `--sp-1…--sp-8` (4…40 px), `--r-card` (raio do cartão, 8 px), `--linha-min` (52 px: altura mínima das linhas de tabela dentro de `.panel`), `--toque` (44 px), `--r-pill` (chip/pílula).
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

## Moldura, menu e topo (redesenho §3, §4, §19)

- **Menu** (`#nav`): grupos `.grp` Visão geral · Acervo · Público e processos · Administração · Ajuda. Item = `<button data-v="rota">` com
  ícone SVG 24×24 de traço (aparece com 18 px) + nome + `<span class="n">` **só** quando o item é demanda (fila, pedido, decisão).
  `.n.r` = demanda que bloqueia. Ativo: `.on` + `aria-current="page"` (fundo `--sel`, barra azul, texto 600). Item novo = linha em
  `NAV_ATALHOS`/`AJUDA_ATALHOS` (o `check_ui` confere) e, se for só de admin, `data-pode` ou a regra de papel no CSS.
- **Cores do menu** (redesenho Material novo §2–3): o menu é **azul-marinho escuro nos dois temas** (`--side-bg`), separado da área
  principal clara; texto `--side-ink`/`--side-ink2`, título de grupo `--side-grp`, hover `--side-hover`, item ativo **fundo azul**
  `--side-sel` com texto branco `--side-sel-ink` e a barra branca à esquerda. Não use `--surface`/`--ink` dentro de `.side`.
- **Marca**: `a#brand-home.brand` = logo (`.mark`) + `.brand-nome` "CAMP"; clique = `nav('painel')` (fecha a gaveta no celular).
- **Contadores**: o botão do menu é uma grade `ícone | rótulo | contador`; a pílula `.n` fica sempre na 3ª coluna (mesmo `right` em todos os
  itens, 22 px de altura, `min-width` 34 px, algarismos tabulares, `fmtN`). A tecla do atalho (`kbd`) não ocupa espaço: aparece por cima,
  só no item sem contador. Recolhido, o contador vira selo de 10 px no canto do ícone. Largura do menu aberto: `--side` 280 px (cabe
  "Pedidos de alta resolução" + "1.234" numa linha). `tests/navegador_menu_camp.js` confere.
- **Larguras**: ≥ 1280 px menu aberto; 721–1279 px menu recolhido por padrão (`camp.side` lembra a escolha da pessoa); ≤ 720 px gaveta
  (`gavetaMenu(true|false)`, botão `#nav-gaveta` no topo, fundo `#nav-fundo`; com ela aberta `.main` fica `inert`).
- **Home**: o contêiner `#v-painel .ini-grid` tem duas `.ini-col` — principal larga + secundária 300–360 px (400 px ≥ 1600). Abaixo de
  1280 px a secundária desce; de 900 a 1279 px ela usa duas colunas. Cartões novos entram numa das `.ini-col`, nunca com largura fixa.
- **Topo** (`.top`): ☰ (só celular) · busca (`#q`, centro, 44 px de altura) · onde estou (`#where`) · tarefas · **Estado dos sistemas**
  (`#machine-status`, só admin) · conta (`.who`: nome + avatar + ▾, menu `#who-menu` com nome, papel e e-mail no cabeçalho).
- **Estado dos sistemas** = `details.sis` > `summary.sis-btn.ms-resumo.{on|off|crit|sem}` (ícone ✓ ! ✕ ? + texto) e `.sis-painel`
  (`.sis-item.{ok|atencao|critico|sem}` com `data-sis`, chip `.tag.st`, frase de impacto em `SIS_IMPACTO`, `.sis-quando` com a
  última verificação, "Verificar agora" = `/api/estacoes?fresco=1`). Fonte única: `/api/estacoes.estado_geral` (mesma regra da Home).
  Verde só com todas as partes medidas e ok. Sem resposta há 3 min (`SIS_VELHO_MS`) = `.sis-velho` + "informação desatualizada".
- **Alerta do topo** (`#system-banner`): `.impede` (QNAP desconectado ou quase cheio, CAMP Vision sem sinal há 1 h, site sem resposta)
  é persistente: aparece em todas as telas, inclusive na Home e para o operador, com `role="alert"` e sem "Fechar por hoje".
  O resto (backup, conferência atrasada) continua com "Fechar por hoje" e fora da Home.

## Lista operacional (redesenho Material novo, 04/11/2026 — documento do Rafael §9)

Os componentes que a tela **Material novo** (`#v-filas`) usa e que a tela **Projetos** deve reutilizar (Fase 4). O compartilhamento é
visual e técnico: cada tela mantém os seus dados, as suas regras e as suas etapas (Projetos NÃO usa a barra de conferência de folhas como
progresso de catalogação). JS em `LST` (`frontend/index.html`); CSS no bloco "Redesenho Material novo §4–7, §9–10". `tests/navegador_material_novo.js` confere.

| # (§9) | Componente | Marcação / função | Regras |
| --- | --- | --- | --- |
| 1 | Cabeçalho de página | `.hdr` > `h1` + `p.sub` + `.act` (ações) | ações de entrada à direita; no máximo um `.btn.pri`; ação só com permissão (`data-pode`) |
| 2 | Cartão de indicador selecionável | `.ind-cards` > `LST.cards([{v,l,d,attr,sel,tom,titulo}])` → `button.ind-card[aria-pressed]` com `.metrica` | número real (carregando = `NUM_SKEL`; sem medida = "—" + "não consegui medir agora"); rótulo com a UNIDADE; clicar abre o conjunto (ou outra tela, dito no `.d`); `tom:'atencao'` só com texto que explique |
| 3 | Abas com contadores | `.lista-op>.abas-sit` > `LST.abas([{k,rot,n,titulo}],atual,'data-…')` | contagem = linhas que a aba mostra, da mesma regra do servidor (`contagens.py`); `titulo` explica o que conta; `b` com `NUM_SKEL` enquanto carrega |
| 4 | Busca e filtros combináveis | `.filterbar.lista-filtros` > `label.busca-local.filtro-sel` (input `type=search`) + `label.filtro-sel` (`span` + `select`) ; `LST.opcoes(el,[[valor,rótulo]],atual)` ; `LST.casa(campos,q)` | filtros somam (nunca zeram os outros); opções só com dados reais; `select.ativo` marca o filtro ligado; "Limpar filtros" aparece só com filtro; tecla F foca a busca; busca sem acento e com código parcial (zeros à esquerda: "0012", "F003P0012") |
| 5 | Tabela com colunas e ordenação | `table.lista-tab[data-sem-ordenar]` + `th[aria-sort]` > `button.th-ord` | ordenação sobre a lista INTEIRA (não só a página); `aria-sort` atualizado; cabeçalho fixo (`top:var(--top-h)`, medido do `.top`); colunas secundárias saem por `@container lista` (largura da lista, não da janela) |
| 6 | Célula de projeto com miniatura | `.proj-cel` > `button.exp-bt` + `LST.mini(codigoDaFolha)` + `.proj-txt` (`a.proj-tit` + `.proj-meta`) | miniatura só de imagem REAL do próprio registro (`/api/itens/{c}/previa?t=120`, `loading=lazy`, 56×42); sem imagem, quadro neutro; nunca foto genérica; o título é link (teclado) |
| 7 | Barra de progresso com legenda | `LST.progresso({rot,feito,total,texto,cls})` → `.prog` | `rot` diz O QUE mede ("Arquivos recebidos", "Importação", "Conferência", "Aprovação", "Publicação"); texto completo visível e no `aria-label`; 100% de um passo não é "pronto" |
| 8 | Etiqueta de situação | `situacaoTag(situacaoDe(fase))` (+ `.tag` auxiliares) | texto sempre; a cor só ajuda (as 5 situações do vocabulário) |
| 9 | Ação contextual + menu secundário | `.acao-cel` > um `.btn.sm.pri` (a etapa atual) + `LST.mais(rótulo,[botões role=menuitem])` (`details.mais-menu.lista-mais`, nome "Mais ações: …") | a ação depende da etapa e do papel; destrutivo em `.perigo-txt`, com a confirmação de sempre (`confirmar`) |
| 10 | Painel de detalhes expansível | `button.exp-bt[aria-expanded][aria-controls]` → `tr.fila-det-tr` > `.fila-det[role=region]` com `section`s | só desenhado quando aberto; o que precisa do servidor carrega na abertura (esqueleto → dado ou `estadoHTML('erro')`) |
| 11 | Paginação e densidade | `.lista-rodape` > `.pg-ctl` (`paginadorHTML({total,pagina,por,opcoes:[25,50,100]})`) + `.densidade` (`[data-…-dens="conf|comp"]`) | só a página fica no DOM; "Mostrando a–b de N" com números reais; Compacta esconde miniatura e frases secundárias; preferências em `LISTA_MEM` |
| 12 | Estados | `estadoHTML('vazio'|'erro'|'carregando',…)`, `vazioHTML`, `tabelaErro` | filtro sem resultado diz quantos registros a aba tem e oferece "Limpar filtros"; erro nunca vira zero |

- **Volta para a lista**: o estado (aba, busca, filtros, página) fica em `sessionStorage` (`LST.sessao`, com try/catch); voltando da página
  do registro pela MESMA rota, tudo volta; chegando por um link com filtro, começa limpo naquele filtro. Ordenação, itens por página e
  densidade são preferência da pessoa (`localStorage`).
- **Celular** (≤ 720 px): `thead` some e cada linha vira cartão (projeto → progresso → situação → tempo → ação); abas rolam na horizontal;
  filtros em duas colunas. Nada de rolagem lateral na página.
- **Projetos** (`#v-projetos`, redesenho Projetos 04/11/2026, §8): usa os MESMOS componentes 1–12 (`LST.cards` em `#proj-cards`,
  `LST.abas` em `#proj-chips`, `.lista-filtros`/`LST.opcoes`, `table.lista-tab.proj-tab` com `th[aria-sort]` > `button.th-ord[data-proj-ord]`,
  `.proj-cel` + `LST.mini(p.miniatura)`, `situacaoTag`, `.acao-cel` > "Abrir projeto" + `LST.mais`, `paginadorHTML` com `opcoes:[25,50,100]`,
  `.densidade`, `estadoHTML`), sem a barra de progresso (#7): o andamento é o selo "objetivos N/M" (UX-73). Filtro, ordenação e página vão
  ao SERVIDOR (`/api/projetos?…&autoria&periodo&material&pendencias`, todos opcionais); as opções vêm de `/api/projetos/filtros`; cartões e
  abas de `/api/projetos/resumo` (a mesma regra da lista). As linhas são `tr.lst-linha` (Material novo usa `tr[data-fase]`); as colunas saem
  por `@container lista` (1279 px: Fundo e Data; 980: Código; 880: Arquitetos; 700: cartão) e o que sai aparece embaixo do nome
  (`.pj-estreito > .pj-e-*`). Estado da volta: `LST.sessao` `camp.proj.estado` (rota + filtros + página); link de outra tela com filtro:
  `abrirProjetosCom({...})`. `tests/navegador_projetos_lista.js` confere.
- **Ferramentas avançadas**: função operacional sensível vai para `details.ferramentas-avancadas` (contorno tracejado, resumo com o
  estado atual, aviso `.fa-aviso`), recolhida por padrão; a confirmação de cada ação continua a mesma.
