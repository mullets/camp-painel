# Padrão de tela — toda página funciona do mesmo jeito

Pedido do Rafael (09/10): "cada página faz uma coisa e tá difícil de entender". Vale para todas as telas, sem exceção.
O `scripts/check_ui.py` reprova se uma variante antiga voltar (`.backbar`, `.fila-chips`, `.fundos-filtros`, select de situação nos Erros).

## 1. Cabeçalho
- Título, **uma frase** dizendo para que a tela serve e **UMA ação principal** (`.btn.pri`) à direita.
- As demais ações vão para o menu **Mais ⋯**: `menuMaisHTML([{html}, {perigo:true, html}])` (`frontend/index.html`).
  As que apagam ou despublicam ficam **só no menu**, em vermelho (`.btn.perigo-txt`), separadas por uma linha e sempre com a janela `confirmar()` (P2-18).
- Exemplo: página do fundo = `Editar` · **`Novo projeto`** · `Mais ⋯` (Etiqueta do fundo, Publicar o fundo / Voltar para rascunho, Despublicar o fundo…).

## 2. Abas de situação
- Uma fileira de abas com contagem, logo abaixo do cabeçalho (ou no topo do quadro da lista): `Abertos 3 · Corrigidos 12 · Todos 15`.
- Componente único: contêiner `.abas-sit` (com `role="group"` e `aria-label`), botões `.btn.sm` com `aria-pressed` (ou `.on`) e a contagem em `<b>`.
- Usado em: Decisões, Filas, Projetos, Fundos, Erros (`GET /api/erros/contagem`) e Solicitações.
- Abas que mudam a **visão** (Uso do acervo: Pedidos · Pessoas · Materiais; abas do projeto) continuam `.tabs`.

## 3. Barra de busca
Campo de busca + filtros extras + contagem "x de y" + Exportar, nesta ordem (`.filterbar`).

## 4. Tabela
- Clicar na linha abre o detalhe **real**: `<tr data-abrir="tipo:id">` (o despachante único fica no `index.html`: decisão, pedido, erro, agente, localização, auditoria) ou `<tr data-nav="rota">`.
- Toda linha clicável mostra **›** no fim (CSS de `tr[data-abrir]`, `tr[data-nav]`, `tr.us-row[data-uso-acao]`).
- No máximo **um** botão de ação na linha, e só quando é o próximo passo.

## 5. Detalhe (fundo, projeto, folha)
- Trilha (`Fundos / F026 Sami Bussab / F026-P0233 · Casa…`) + **um só Voltar**, o do topo. No celular o topo esconde o resto e fica só o Voltar.
- Logo abaixo do título, o bloco **Próximo passo** com **UM** botão azul (o único da página). O resto em seções recolhidas ou abas (#95).
- Título sempre limpo: `tituloExibicao()` tira o prefixo da pasta (`T102_`) e os `_`; o banco não muda.

## 6. Retorno das ações (H4)
- Rápida: o botão trava; o aviso diz o objeto ("Pedido de Fulana marcado como entregue").
- Média: passado 1 s o botão diz "Trabalhando…"; o resultado fica **na tela** por 10 s com o próximo passo (`avisoNoLugar`).
- Longa: vira **tarefa** no servidor (`rodarTarefa`), com o chip no topo e o aviso de conclusão.
- Reversível e frequente: sem pergunta, com **Desfazer** por 8 s. Irreversível ou público: `confirmar()` com alvo e consequência.

## 7. Textos
Nada de códigos internos (`releitura_concluida`), palavras sem acento (`decisao`) ou termos fora do `vocabulario.md`. Prefira singular/plural certo a "(s)" nos textos novos.
