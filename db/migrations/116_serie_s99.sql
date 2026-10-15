-- CAMP-031 (contrato C6): série S99 "Não identificado" para folhas que o CAMP Vision não soube classificar.
-- O código GLOB 'S[0-9][0-9]' da tabela já a aceita. S07 NÃO é renomeada (decisão do Rafa, CAMP-045 #3).
INSERT OR IGNORE INTO serie (codigo, nome, pasta) VALUES ('S99', 'Não identificado', '99 - Não identificado');
