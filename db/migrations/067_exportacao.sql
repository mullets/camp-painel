-- Exportação EAD/CSV e BagIt: onde os pacotes BagIt são gravados. Vazio = pasta 'exportacoes' ao lado do banco do painel.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('exportacao.pasta', '', 'Pasta onde o painel grava os pacotes BagIt dos projetos (vazio = pasta exportacoes ao lado do banco)', 0);
