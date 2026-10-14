-- Sobras #9: mudar o código de um projeto (ex.: número P errado). A tabela redirecionamento já existe no schema
-- (codigo_antigo → codigo_novo); passa a ser preenchida pelo painel e guarda também quem fez. O site lê em
-- GET /api/redirecionamentos para responder 301 do endereço antigo.
CREATE TABLE IF NOT EXISTS redirecionamento (
  codigo_antigo TEXT PRIMARY KEY,
  codigo_novo   TEXT NOT NULL,
  entidade      TEXT NOT NULL CHECK (entidade IN ('fundo','projeto','item')),
  motivo        TEXT NOT NULL,
  criado_em     TEXT NOT NULL DEFAULT (datetime('now')),
  aplicado_no_site INTEGER NOT NULL DEFAULT 0
);
ALTER TABLE redirecionamento ADD COLUMN criado_por TEXT;
CREATE INDEX IF NOT EXISTS idx_redirecionamento_novo ON redirecionamento(codigo_novo);
