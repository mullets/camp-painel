-- Separa explicitamente a coleção de dossiês/projetos da coleção de documentos/itens.
-- Valores atuais da instalação CAMP; podem ser alterados em Configurações sem mudar código.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('tainacan.projetos_collection_id','8007','ID da coleção Tainacan que representa os dossiês/projetos',0),
('tainacan.itens_collection_id','8013','ID da coleção Tainacan que representa folhas, fotografias e demais documentos',0);
