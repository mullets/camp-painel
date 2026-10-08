-- Fila de DECISÕES: o painel verifica antes de agir e, na dúvida, pergunta (hoje: "este projeto já existe no fundo? é o mesmo?").
-- Genérica de propósito: outras verificações entram na mesma fila (tipo + contexto JSON + candidatos + resolução).
CREATE TABLE IF NOT EXISTS decisao (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo           TEXT NOT NULL,                              -- 'projeto_parecido'
  chave          TEXT UNIQUE,                                -- chave_reserva da estação (idempotência): a mesma chave sempre volta à MESMA decisão
  fundo_codigo   TEXT NOT NULL,
  titulo         TEXT NOT NULL,                              -- o que chegou
  contexto       TEXT NOT NULL,                              -- JSON: o pedido original (titulo, ano, cidade, identificacao_original, operador...) e os candidatos com nota e motivos
  origem         TEXT NOT NULL,                              -- 'estacao' | 'painel'
  situacao       TEXT NOT NULL DEFAULT 'pendente' CHECK (situacao IN ('pendente','resolvida')),
  resolucao      TEXT CHECK (resolucao IN ('mesmo','novo')),
  projeto_codigo TEXT,                                       -- o resultado: o projeto existente escolhido, ou o novo criado
  criada_em      TEXT NOT NULL DEFAULT (datetime('now')),
  resolvida_em   TEXT,
  resolvida_por  TEXT
);
CREATE INDEX IF NOT EXISTS idx_decisao_situacao ON decisao(situacao, criada_em);
