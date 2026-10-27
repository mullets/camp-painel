-- UX-13: a senha temporária (gerada pelo administrador em "Novo usuário" ou "Nova senha") vale 72 h.
-- Guarda QUANDO ela foi gerada. Contas que já existiam ficam com NULL = data desconhecida = não vencem por esta regra
-- (não tranca ninguém que hoje entra com senha temporária, inclusive o admin de produção). Só senha gerada depois desta versão vence.
ALTER TABLE usuario ADD COLUMN senha_temporaria_em TEXT;
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('usuarios.senha_temporaria_horas', '72', 'Validade (em horas) da senha temporária gerada pelo administrador. Vencida, a pessoa não entra: o administrador gera outra em Usuários › Nova senha. 0 = não vence.', 0);
