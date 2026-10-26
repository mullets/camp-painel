-- 26/10 (Rafael): "o sistema responde que um projeto com nome semelhante é o mesmo projeto, mas não é: tira isso".
-- A pergunta por NOME parecido no F9 da estação fica desligada (0). 1 = volta a perguntar em Decisões (a estação espera).
-- ("mesmo nome em outro fundo" já está desligada desde 14/10: similaridade.buscar_em_outros_fundos.)
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('decisoes.parecido_estacao', '0', 'Estação (F9): perguntar em Decisões quando já existe projeto de nome parecido no fundo. 0=cria direto; 1=pergunta (a estação espera).', 0);
