-- B5: séries iguais às do site (taxonomia padronizada em 26/09): S06 passa a se chamar "Materiais" e nasce S07 "Redesenhos"
-- (os 9 redesenhos ComoVer da Casa Tapera, F029-P0001-1969-S07-*). A pasta de S06 não muda: é o nome que o CAMP Vision procura.
UPDATE serie SET nome='Materiais' WHERE codigo='S06';
INSERT OR IGNORE INTO serie (codigo, nome, pasta) VALUES ('S07', 'Redesenhos', '09 - Redesenhos');
