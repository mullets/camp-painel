-- Alertas críticos por e-mail (cartão 151): o estado de cada assunto e o log de cada envio.
CREATE TABLE IF NOT EXISTS alerta_estado (
  assunto            TEXT PRIMARY KEY,                -- qnap | campvision | backup | site
  critico            INTEGER NOT NULL DEFAULT 0,
  desde              TEXT,
  texto              TEXT,
  critico_avisado    INTEGER NOT NULL DEFAULT 0,      -- já saiu e-mail deste episódio? (só então sai o 'resolvido')
  ultimo_critico_em  TEXT,                            -- limite: no máximo 1 e-mail de crítico a cada 6 h por assunto
  atualizado_em      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS alerta_envio (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  assunto     TEXT NOT NULL,
  tipo        TEXT NOT NULL CHECK (tipo IN ('critico','resolvido','suprimido')),
  para        TEXT,
  titulo      TEXT,
  ok          INTEGER NOT NULL DEFAULT 0,
  erro        TEXT,
  enviado_em  TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('avisos.intervalo_min', '5', 'De quantos em quantos minutos o painel confere os alertas críticos (0 desliga o envio por e-mail)', 0),
 ('painel.url', 'https://painel.camp.arq.br', 'Endereço do painel usado nos links dos e-mails', 0);
