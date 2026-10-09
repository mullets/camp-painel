-- Endereço da página pública do projeto CONFIRMADO no site (o painel só presumia, e errava o slug).
ALTER TABLE projeto ADD COLUMN url_publica_confirmada TEXT;
ALTER TABLE projeto ADD COLUMN url_publica_em TEXT;
