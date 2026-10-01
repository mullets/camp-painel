-- Pipeline de captura -> QNAP -> CAMP Vision 2 -> pasta final.
-- As estações capturam; o CAMP Vision 2 interpreta/organiza; o painel só lê a pasta final.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('estacao.foto1.ip','', 'IP da Estação Foto 1 (Mac dedicado a fotos, negativos, slides e transparências)', 0),
('estacao.foto2.ip','', 'IP da Estação Foto 2 (Mac dedicado a fotos, negativos, slides e transparências)', 0),
('estacao.contex.ip','', 'IP da Estação Contex (materiais grandes: pranchas, croquis, desenhos etc.)', 0),
('estacao.universal1.ip','', 'IP da Estação Universal 1 (Mac para qualquer material, com tipo e metadados informados pelo operador)', 0),
('estacao.universal2.ip','', 'IP da Estação Universal 2 (Mac para qualquer material, com tipo e metadados informados pelo operador)', 0),
('campvision2.ip','', 'IP do computador CAMP Vision 2', 0),
('qnap.entrada_captura','', 'Raiz de entrada bruta onde as estações entregam digitalizações', 0),
('qnap.prontos_raiz','', 'Raiz final organizada pelo CAMP Vision 2; somente daqui surgem avisos de material pronto', 0);
