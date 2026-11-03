-- UX-67 (03/11/2026): títulos de projeto que vieram do nome da pasta ("Teatro Piracicaba - 12 Folhas", "F000 - CNV - Convidado").
-- A correção em vários projetos de uma vez é feita por um admin na tela (prévia primeiro; nada muda sozinho). Cada aplicação é um
-- "lote" aqui, com o título de antes e o de depois, para o histórico e para o Desfazer. Só o título muda: o código F/P é imutável.
CREATE TABLE IF NOT EXISTS titulo_correcao (
  id              INTEGER PRIMARY KEY,
  lote            TEXT NOT NULL,                       -- uma aplicação (vários projetos)
  projeto_codigo  TEXT NOT NULL,
  titulo_antes    TEXT,
  titulo_depois   TEXT NOT NULL,
  fonte           TEXT,                                -- carimbo | pasta | manual
  ator            TEXT,
  em              TEXT NOT NULL DEFAULT (datetime('now')),
  desfeito_em     TEXT,
  desfeito_por    TEXT
);
CREATE INDEX IF NOT EXISTS ix_titulo_correcao_lote ON titulo_correcao(lote);
CREATE INDEX IF NOT EXISTS ix_titulo_correcao_projeto ON titulo_correcao(projeto_codigo);
