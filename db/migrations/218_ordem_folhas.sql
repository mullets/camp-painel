-- Ordem das folhas escolhida à mão na página do projeto (06/11/2026: "queria poder organizar as fotos arrastando pra nova ordem").
-- Só ADD COLUMN; nada existente muda. NULL = sem ordem escolhida: a folha segue a ordem do código (série, D). O código (D0xxxx) NUNCA muda:
-- esta coluna é só a posição de exibição dentro do projeto (0, 1, 2…). Gravada por PUT /api/projetos/{codigo}/ordem-folhas;
-- DELETE na mesma rota volta todas a NULL. Folha movida para outro projeto perde a posição (vai para o fim da ordem de lá).
ALTER TABLE item ADD COLUMN ordem_manual INTEGER;
