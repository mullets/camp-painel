-- 261 · CAMP-FICHA (25/11/2026). Decisão do Rafael: o tipo "Detalhe / Estrutura" entra na lista de tipos de documento do painel.
-- O CAMP Vision lê esse tipo em folhas de projeto complementar de estrutura e a ficha mostrava "não existe na lista do painel".
-- Só acrescenta ao vocabulário (idempotente). Nada existente muda: as folhas já lidas passam a casar com o tipo na conferência
-- ("Usar sugestão"); a releitura/importação nova grava o tipo direto. No agrupamento por disciplina, conta como Estrutura.
INSERT OR IGNORE INTO tipo_documento (nome) VALUES ('Detalhe / Estrutura');
