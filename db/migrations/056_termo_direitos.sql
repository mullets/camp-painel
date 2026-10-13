-- H14: o PDF do termo assinado fica guardado junto dos direitos do fundo (quem conferir depois vê o documento, não só "Termo de doação…").
CREATE TABLE IF NOT EXISTS termo_direitos (
  fundo_codigo TEXT PRIMARY KEY REFERENCES fundo(codigo),
  arquivo      BLOB NOT NULL,
  nome         TEXT,
  tamanho      INTEGER NOT NULL,
  enviado_por  TEXT,
  enviado_em   TEXT NOT NULL DEFAULT (datetime('now'))
);
