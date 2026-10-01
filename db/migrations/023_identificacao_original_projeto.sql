-- Preserva a referência física/legada anterior ao código CAMP.
-- Exemplos: CX039, Caixa 12, Tubo 07, Pasta 03, Rolo 22.
ALTER TABLE projeto ADD COLUMN identificacao_original TEXT;
