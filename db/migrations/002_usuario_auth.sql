-- Autenticação: senha com hash, bloqueio por tentativas, sessões revogáveis, 2FA opcional
ALTER TABLE usuario ADD COLUMN senha_hash TEXT;
ALTER TABLE usuario ADD COLUMN tentativas_falhas INTEGER NOT NULL DEFAULT 0;
ALTER TABLE usuario ADD COLUMN bloqueado_ate TEXT;
ALTER TABLE usuario ADD COLUMN ultimo_login TEXT;
ALTER TABLE usuario ADD COLUMN totp_secret TEXT;           -- 2FA (TOTP), opcional por usuário
ALTER TABLE usuario ADD COLUMN precisa_trocar_senha INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS sessao (
  id          TEXT PRIMARY KEY,                 -- token aleatório (só o hash fica aqui)
  usuario_id  INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  criada_em   TEXT NOT NULL DEFAULT (datetime('now')),
  expira_em   TEXT NOT NULL,
  ip          TEXT,
  agente      TEXT,                             -- user-agent resumido
  revogada    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS sessao_usuario ON sessao(usuario_id, revogada);
