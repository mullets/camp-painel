-- A mesma decisão pode ser pedida por várias chaves de estação ("Golombeck 3", "Golombeck_3"...): cada chave extra aponta para a decisão que já existe.
CREATE TABLE IF NOT EXISTS decisao_chave (
  chave      TEXT PRIMARY KEY,
  decisao_id INTEGER NOT NULL REFERENCES decisao(id),
  criada_em  TEXT NOT NULL DEFAULT (datetime('now'))
);
