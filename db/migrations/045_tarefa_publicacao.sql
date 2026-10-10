-- Publicar vira TAREFA em segundo plano: a tela acompanha (GET /api/tarefas/{id}), fechar a janela não para nada e o progresso real nunca se perde.
CREATE TABLE IF NOT EXISTS tarefa_publicacao (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_codigo TEXT NOT NULL,
  ator           TEXT NOT NULL,
  estado         TEXT NOT NULL DEFAULT 'rodando' CHECK (estado IN ('rodando','ok','falhou')),
  etapa          TEXT,
  folha_atual    TEXT,
  feitas         INTEGER NOT NULL DEFAULT 0,
  total          INTEGER NOT NULL DEFAULT 0,
  falhas         TEXT,
  log            TEXT,
  resultado      TEXT,
  iniciada_em    TEXT NOT NULL DEFAULT (datetime('now')),
  terminada_em   TEXT
);
CREATE INDEX IF NOT EXISTS idx_tarefa_pub_projeto ON tarefa_publicacao (projeto_codigo, id DESC);
