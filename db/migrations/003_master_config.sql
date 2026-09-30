-- Papel "master" (admin master) acima de admin; e configurações editáveis pelo painel
CREATE TABLE usuario_novo (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  nome   TEXT NOT NULL,
  email  TEXT UNIQUE,
  papel  TEXT NOT NULL CHECK (papel IN ('master','admin','operador','leitura')),
  ativo  INTEGER NOT NULL DEFAULT 1,
  senha_hash TEXT,
  tentativas_falhas INTEGER NOT NULL DEFAULT 0,
  bloqueado_ate TEXT,
  ultimo_login TEXT,
  totp_secret TEXT,
  precisa_trocar_senha INTEGER NOT NULL DEFAULT 0
);
INSERT INTO usuario_novo SELECT id,nome,email,papel,ativo,senha_hash,tentativas_falhas,bloqueado_ate,ultimo_login,totp_secret,precisa_trocar_senha FROM usuario;
DROP TABLE usuario;
ALTER TABLE usuario_novo RENAME TO usuario;

-- Configurações de infraestrutura e integração, editáveis só pelo master
CREATE TABLE configuracao (
  chave        TEXT PRIMARY KEY,
  valor        TEXT,
  descricao    TEXT,
  sensivel     INTEGER NOT NULL DEFAULT 0,     -- não devolve o valor pela API, só se está preenchido
  atualizado_em TEXT NOT NULL DEFAULT (datetime('now')),
  atualizado_por TEXT
);
INSERT INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('qnap.ip',            '',                    'IP do QNAP TS-932PX na rede local', 0),
 ('qnap.raiz',          '/mnt/qnap/acervos',   'Pasta onde o acervo está montado nesta máquina', 0),
 ('qnap.backup_ip',     '',                    'IP do QNAP TS-231P (backup frio)', 0),
 ('contex.ip',          '',                    'IP da estação Windows do scanner Contex', 0),
 ('vuescan.ip',         '',                    'IP do Mac do VueScan', 0),
 ('campvision.pasta_saida', '',                'Pasta onde o CAMP Vision 2 grava a catalogação', 0),
 ('wp.url',             '',                    'Endereço do site (vazio = usa o .env)', 0),
 ('wp.usuario',         '',                    'Usuário WordPress da API (vazio = usa o .env)', 0),
 ('wp.app_password',    '',                    'Application Password do WordPress', 1),
 ('smtp.host',          '',                    'Servidor SMTP para avisos', 0),
 ('smtp.usuario',       '',                    'Usuário SMTP', 0),
 ('smtp.senha',         '',                    'Senha SMTP', 1),
 ('avisos.email',       'rafael@camp.arq.br',  'Quem recebe avisos do sistema', 0),
 ('site.credito_padrao','Acervo {agente}/CAMP - Casa da Arquitetura Moderna Paulista','Crédito padrão dos itens', 0);
