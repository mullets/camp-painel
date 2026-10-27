-- UX-25 · Etiquetas: histórico "Impressas" com reimprimir. A tabela já existia (schema.sql) mas ninguém gravava nela;
-- agora cada clique em Imprimir registra o que saiu. Colunas novas, todas opcionais (NULL nas linhas antigas).
CREATE TABLE IF NOT EXISTS etiqueta_impressao (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo        TEXT NOT NULL CHECK (tipo IN ('projeto','documento','caixa','tubo','fundo')),
  codigo      TEXT NOT NULL,
  quantidade  INTEGER NOT NULL DEFAULT 1,
  formato_mm  TEXT NOT NULL DEFAULT '100x50',
  impressa_em TEXT NOT NULL DEFAULT (datetime('now')),
  usuario_id  INTEGER REFERENCES usuario(id)
);
ALTER TABLE etiqueta_impressao ADD COLUMN papel TEXT;     -- rolo | a4 | niimbot
ALTER TABLE etiqueta_impressao ADD COLUMN lote TEXT;      -- um | folhas | pastas | material
ALTER TABLE etiqueta_impressao ADD COLUMN config TEXT;    -- JSON: o que é preciso para reimprimir igual (material, volume, série, documento, local, cópias)
CREATE INDEX IF NOT EXISTS idx_etiqueta_impressao_em ON etiqueta_impressao (impressa_em);
