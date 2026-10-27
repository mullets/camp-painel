-- UX-20: "Desfazer" de verdade para as ações em massa em Problemas (resolver vários e mesclar mensagens repetidas).
-- Guarda como cada problema estava ANTES (situação, resolução, data); o Desfazer volta só os que ninguém mexeu depois.
CREATE TABLE IF NOT EXISTS erro_desfazer (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ator        TEXT NOT NULL,
  acao        TEXT NOT NULL,                    -- 'lote' | 'mesclar'
  situacao    TEXT NOT NULL,                    -- a situação que a ação gravou (o Desfazer só mexe em quem ainda está nela)
  antes       TEXT NOT NULL,                    -- JSON [{id, situacao, resolucao, resolvido_em}]
  criado_em   TEXT NOT NULL DEFAULT (datetime('now')),
  desfeito_em TEXT
);
