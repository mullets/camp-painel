-- Configuração do pipeline de fotografia: 2 Macs -> QNAP -> CAMP Vision 2 -> pasta final.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('foto.estacao1_ip','', 'IP da Estação Foto 1 (Mac dedicado a fotos/negativos/slides/transparências)', 0),
('foto.estacao2_ip','', 'IP da Estação Foto 2 (Mac dedicado a fotos/negativos/slides/transparências)', 0),
('campvision2.ip','', 'IP do computador CAMP Vision 2 no QNAP', 0),
('qnap.entrada_foto','', 'Pasta de entrada onde as estações de foto entregam os arquivos brutos', 0),
('qnap.prontos_raiz','', 'Raiz final organizada pelo CAMP Vision 2; somente daqui surgem avisos de material pronto', 0);
