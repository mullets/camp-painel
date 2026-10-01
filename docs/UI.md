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
