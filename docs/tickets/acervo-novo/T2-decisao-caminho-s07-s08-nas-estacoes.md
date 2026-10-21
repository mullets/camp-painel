# CAMP-??? · DECISÃO: não existe caminho suportado para digitalizar S07 Publicações (revistas, matérias) e S08 Redesenhos

**Repo:** camp-sistema-digitalizacao, camp-sistema-digitalizacao-mac, campvision-new, camp-painel  
**Gravidade:** alta (decisão do Rafa)  
**Cenário do E2E:** TESTE-70 / TESTE-71

## Problema
- O Windows só produz **S01** (`SERIE_PADRAO = "01 - Desenhos e pranchas"`).
- O Mac, por padrão, só oferece Negativo, Slide e Fotografia (`MATERIAIS_PADRAO`: S04, S05, S03).
- Revistas, matérias e redesenhos só funcionaram no teste porque a configuração `materiais` do Mac foi preenchida à mão com os nomes exatos `07 - Publicações` e `08 - Redesenhos`. Quem usa o padrão não consegue escanear esses materiais.

## Decidir
- Qual estação escaneia S07 e S08.
- Se entram na lista de materiais padrão (Mac e/ou Windows) e com que nomes de pasta.
- Como o operador diferencia revista de matéria dentro de S07.

## Depende de
T3 (nomes das pastas do Mac).

## Teste quando decidido
`cenario_170`: projetos B e C do acervo novo, sem preencher `materiais` à mão.
