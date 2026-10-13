-- Consulta presencial e empréstimo de originais: quem levou (ou consultou) o quê, até quando, e quem recebeu de volta.
-- O "o quê" pode ser folhas soltas e/ou recipientes inteiros (caixa, tubo…), em emprestimo_item.
CREATE TABLE IF NOT EXISTS emprestimo (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo           TEXT NOT NULL CHECK (tipo IN ('consulta','emprestimo')),   -- consulta presencial (na CAMP) ou empréstimo (sai da CAMP)
  nome           TEXT NOT NULL,                                             -- quem consulta / leva
  contato        TEXT,                                                      -- e-mail ou telefone
  instituicao    TEXT,
  saida_em       TEXT NOT NULL,                                             -- data (AAAA-MM-DD)
  prazo          TEXT NOT NULL,                                             -- data combinada para devolver
  responsavel_id INTEGER REFERENCES usuario(id),                            -- quem da CAMP entregou e responde pelo material
  observacao     TEXT,
  devolvido_em   TEXT,                                                      -- data e hora em que voltou (NULL = ainda fora)
  devolvido_por  INTEGER REFERENCES usuario(id),
  criado_por     INTEGER REFERENCES usuario(id),
  criado_em      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_emprestimo_aberto ON emprestimo (devolvido_em, prazo);

CREATE TABLE IF NOT EXISTS emprestimo_item (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  emprestimo_id  INTEGER NOT NULL REFERENCES emprestimo(id) ON DELETE CASCADE,
  item_codigo    TEXT REFERENCES item(codigo),
  localizacao_id INTEGER REFERENCES localizacao_fisica(id),
  CHECK ((item_codigo IS NULL) <> (localizacao_id IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_emprestimo_item_emp ON emprestimo_item (emprestimo_id);
CREATE INDEX IF NOT EXISTS idx_emprestimo_item_item ON emprestimo_item (item_codigo);
CREATE INDEX IF NOT EXISTS idx_emprestimo_item_loc ON emprestimo_item (localizacao_id);
