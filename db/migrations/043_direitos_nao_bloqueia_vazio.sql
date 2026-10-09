-- Direitos do fundo NÃO PREENCHIDOS deixam de bloquear a publicação (ninguém decidiu isso; era uma inferência do caso de um fundo retirado do ar).
-- Uma restrição REGISTRADA de propósito (restrito, nao_autorizado) continua bloqueando. 1 = volta a exigir o preenchimento de todos os fundos.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('publicacao.exige_direitos','0','1 = o fundo sem direitos preenchidos também bloqueia a publicação. 0 (padrão) = só bloqueia quando alguém registrou uma restrição (restrito ou não autorizado).',0);
