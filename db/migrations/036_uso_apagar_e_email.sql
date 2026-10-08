-- Uso do acervo: apagar entradas (marca invisível que impede a reimportação) e e-mail para uma pessoa.
ALTER TABLE uso_download ADD COLUMN apagada INTEGER NOT NULL DEFAULT 0;   -- 1 = apagada: some de listas, contagens e exportações; só resta a marca (form_id, origem_id)
ALTER TABLE uso_download ADD COLUMN apagada_em TEXT;
CREATE INDEX IF NOT EXISTS idx_uso_apagada ON uso_download(apagada);
CREATE TABLE IF NOT EXISTS uso_email (          -- cada envio (ou tentativa) de e-mail para uma pessoa do Uso do acervo
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  uso_id      INTEGER NOT NULL,
  enviado_em  TEXT NOT NULL DEFAULT (datetime('now')),
  enviado_por TEXT NOT NULL,
  assunto     TEXT NOT NULL,
  ok          INTEGER NOT NULL,
  erro        TEXT
);
CREATE INDEX IF NOT EXISTS idx_uso_email_uso ON uso_email(uso_id);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('smtp.porta',        '587',      'Porta do SMTP (587 = STARTTLS, 465 = SSL)', 0),
 ('smtp.seguranca',    'starttls', 'Segurança do SMTP: starttls | ssl | nenhuma', 0),
 ('smtp.remetente',    '',         'Endereço que aparece como remetente (vazio = o usuário SMTP, se for um e-mail)', 0),
 ('uso.email_assunto', 'CAMP: sobre o seu pedido de material', 'Assunto padrão do e-mail para quem pediu material ({nome}, {material}, {data})', 0),
 ('uso.email_corpo',   'Olá, {nome}.\n\nVocê pediu o material {material} no site do acervo da CAMP em {data}.\n\n\n\nAtenciosamente,\nCAMP - Casa da Arquitetura Moderna Paulista', 'Texto padrão do e-mail para quem pediu material ({nome}, {material}, {data})', 0);
