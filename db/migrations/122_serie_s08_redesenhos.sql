-- CAMP-047 (decisão do Rafa): S07 passa a ser só "Publicações" e nasce S08 "Redesenhos" (pasta 08 - Redesenhos, dentro do projeto).
-- Só a TABELA de séries muda aqui. Mover as folhas que hoje são S07/Redesenhos para S08 (o código delas muda) é um ROTEIRO à parte,
-- com modo simular: scripts/migrar_serie_s08.py (nunca roda sozinho, nem em produção).
INSERT OR IGNORE INTO serie (codigo, nome, pasta) VALUES ('S08', 'Redesenhos', '08 - Redesenhos');
UPDATE serie SET nome='Publicações', pasta='09 - Publicações' WHERE codigo='S07' AND nome='Redesenhos';
