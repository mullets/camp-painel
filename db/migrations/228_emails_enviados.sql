-- 228 · CAMP-EMAIL (18/11/2026, Rafael: "temos um painel no admin de e-mails enviados? com log e tudo?"): tela E-mails enviados (só admin
-- e master). Junta o que o painel já guarda (uso_email, amigo_email, entrega_link, alerta_envio, resumo_diario_envio, avisos de inscrição
-- no evento) e o que o SITE mandou, buscado pela rota GET /wp-json/camp/v1/painel/emails (contrato 1.14, opcional: site antigo = 404, a
-- tela mostra só o que saiu do painel). Tem dados pessoais (e-mail e nome de quem recebeu): o apagar pessoa (LGPD) limpa estas linhas.
-- Idempotente: CREATE ... IF NOT EXISTS, INSERT OR IGNORE; ADD COLUMN repetido é ignorado pelo aplicador de migrações.
CREATE TABLE IF NOT EXISTS email_site (
  id           INTEGER PRIMARY KEY,
  chave        TEXT NOT NULL UNIQUE,              -- chave estável do site: <id do registro>:<tipo>
  registro_id  INTEGER,                           -- ID do registro no site (pedido, visita, inscrição, contato, apoio)
  registro     TEXT,                              -- tipo do registro no site (camp_solicitacao, camp_agendamento…)
  protocolo    TEXT,
  tipo         TEXT,                              -- chave do e-mail no site (solicitacao_recebida, amigo_adesao, aviso_equipe…)
  template     TEXT,                              -- TR04…TR21 (vazio = sem template)
  para         TEXT,                              -- e-mail de quem recebeu (LGPD: apagado no apagar pessoa)
  nome         TEXT,
  canal        TEXT,                              -- sender | simples
  situacao     TEXT,                              -- enviado | falhou | nao_sender
  motivo       TEXT,                              -- por que falhou ou por que não saiu pelo Sender (nunca o token)
  sender_id    TEXT,                              -- id do e-mail no Sender (emailId), quando o Sender aceitou
  tentativas   INTEGER,
  enviado_em   TEXT,                              -- UTC, AAAA-MM-DD HH:MM:SS
  coletado_em  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_email_site_em ON email_site (enviado_em);
CREATE INDEX IF NOT EXISTS idx_email_site_para ON email_site (para);
CREATE TABLE IF NOT EXISTS email_estado (           -- estado da busca no site (cursor "desde", última busca, último erro)
  chave TEXT PRIMARY KEY,
  valor TEXT
);
-- Entrega de material: o motivo da falha passa a ficar guardado (antes só o link era cancelado, sem o porquê).
ALTER TABLE entrega_link ADD COLUMN erro TEXT;
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('emails.coleta_min', '15', 'De quantos em quantos minutos o painel busca no site os e-mails que o site mandou, para a tela E-mails enviados (0 desliga)', 0);
