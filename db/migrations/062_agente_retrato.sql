-- B9: retrato do arquiteto enviado pelo painel (fica fora da tabela agente para o SELECT a.* não carregar a imagem).
CREATE TABLE IF NOT EXISTS agente_retrato (
  agente_id     INTEGER PRIMARY KEY REFERENCES agente(id) ON DELETE CASCADE,
  imagem        BLOB NOT NULL,
  tipo          TEXT NOT NULL,                 -- image/jpeg | image/png
  media_id      INTEGER,                       -- anexo na biblioteca de mídia do site (vira _camp_foto_id da página-hub)
  atualizado_por TEXT,
  atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
