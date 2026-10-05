-- Cópia extra opcional do backup diário do banco (ex.: pasta montada do QNAP). Vazio = só a cópia local.
-- NÃO use a pasta de acervos do QNAP: a varredura de filas lê tudo que está lá.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('backup.destino_extra','','Pasta extra para cópia do backup diário do banco (ex.: /mnt/qnap/backups). Vazio = somente cópia local em backend/backups. Não use a pasta de acervos.',0);
