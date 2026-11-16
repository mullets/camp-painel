-- Clima: escolher QUAIS sensores entram (a conta do app da Tuya pode ter aparelhos de outros lugares). Ver backend/app/clima.py.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('clima.sensores', '', 'Só estes sensores entram no clima: nomes (como no app da Tuya) separados por vírgula, ex.: Arquivo, Servidor. Vazio = todos os que têm leitura', 0);
