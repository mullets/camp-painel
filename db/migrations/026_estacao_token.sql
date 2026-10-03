-- Token opcional das rotas sem login (estações). Vazio = só rede local verdadeira (sem proxy/túnel).
-- Preenchido = obrigatório no cabeçalho X-Camp-Token, inclusive dentro da LAN.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('estacao.token','','Token que as estações enviam no cabeçalho X-Camp-Token. Vazio = somente rede local (sem túnel). Obrigatório antes de abrir o painel pela internet.',1);
