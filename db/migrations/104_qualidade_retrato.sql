-- Dashboard Tarefas de hoje: retrato diário do índice de qualidade por fundo (para a seta de tendência frente à semana anterior).
-- fundo_codigo='*' guarda o índice geral (todas as folhas). Um retrato por dia: o do dia é regravado até o dia virar.
CREATE TABLE IF NOT EXISTS qualidade_retrato (
  dia           TEXT NOT NULL,                 -- AAAA-MM-DD (horário local do servidor)
  fundo_codigo  TEXT NOT NULL,
  folhas        INTEGER NOT NULL DEFAULT 0,
  com_imagem    INTEGER NOT NULL DEFAULT 0,
  com_codigo    INTEGER NOT NULL DEFAULT 0,
  com_titulo    INTEGER NOT NULL DEFAULT 0,
  com_direitos  INTEGER NOT NULL DEFAULT 0,
  indice        REAL,                          -- média dos 4 percentuais (0 a 100); NULL quando o fundo não tem folhas
  gravado_em    TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (dia, fundo_codigo)
);
CREATE INDEX IF NOT EXISTS idx_qualidade_retrato_fundo ON qualidade_retrato (fundo_codigo, dia);
