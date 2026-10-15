-- CAMP-051: amostra de 10% (estratificada por fundo) dos lotes "inferidos" para a revisão do Rafa. Só registra a amostra e as decisões; NÃO libera nada.
CREATE TABLE IF NOT EXISTS amostra_lote_inferido (
  lote_id      INTEGER PRIMARY KEY REFERENCES lista_processamento(id),
  fundo_codigo TEXT,
  sorteado_em  TEXT NOT NULL DEFAULT (datetime('now')),
  semente      TEXT,
  decisao      TEXT CHECK (decisao IN ('aprovado','reprovado')),
  motivo       TEXT,
  decidido_por TEXT,
  decidido_em  TEXT
);
