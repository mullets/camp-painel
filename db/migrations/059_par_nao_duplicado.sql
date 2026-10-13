-- B7: pares de projetos que uma pessoa já disse que NÃO são o mesmo (a varredura de duplicados não volta a mostrar). a < b sempre.
CREATE TABLE IF NOT EXISTS par_nao_duplicado (
  a    TEXT NOT NULL,
  b    TEXT NOT NULL,
  por  TEXT,
  em   TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (a, b)
);
