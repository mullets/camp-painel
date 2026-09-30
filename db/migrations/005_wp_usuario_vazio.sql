-- O valor padrão 'camp' em wp.usuario tinha prioridade sobre o .env e quebrava a autenticação.
-- Configuração só prevalece quando alguém preencher de propósito pelo painel.
UPDATE configuracao SET valor='' WHERE chave='wp.usuario' AND valor='camp' AND atualizado_por IS NULL;
UPDATE configuracao SET valor='' WHERE chave='wp.url' AND valor='https://camp.arq.br' AND atualizado_por IS NULL;
