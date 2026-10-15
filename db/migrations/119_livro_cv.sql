-- CAMP-008: livro de registro do CAMP Vision (ACERVOS_CAMP/_campvision/registro/AAAA-MM.jsonl), lido de forma INCREMENTAL
-- (posição em bytes por arquivo) para o "Histórico" do projeto. O livro é append-only; o painel nunca escreve nele.
CREATE TABLE IF NOT EXISTS livro_posicao (
  arquivo   TEXT PRIMARY KEY,                    -- nome do arquivo do livro (ex.: 2026-10.jsonl)
  posicao   INTEGER NOT NULL DEFAULT 0,          -- bytes já lidos (só até a última linha completa)
  lido_em   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS livro_cv (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  arquivo           TEXT NOT NULL,
  inicio            INTEGER NOT NULL,            -- byte onde a linha começa (chave: ler de novo nunca duplica)
  quando            TEXT,
  acao              TEXT,
  projeto_codigo    TEXT,
  documento_codigo  TEXT,
  lote_id           TEXT,
  operador          TEXT,
  estacao           TEXT,
  nome_original     TEXT,
  detalhe           TEXT,
  UNIQUE (arquivo, inicio)
);
CREATE INDEX IF NOT EXISTS idx_livro_cv_projeto ON livro_cv(projeto_codigo, quando);
