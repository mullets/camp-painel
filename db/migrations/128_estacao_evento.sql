-- CAMP-017: as estações (Windows/Mac) avisam o painel quando CAPTURAM e quando ENVIAM um lote (POST /api/estacoes/eventos).
-- chave = uuid que a estação gera (projeto+evento+lote): o mesmo aviso repetido não duplica. Serve para achar lote enviado e nunca processado.
CREATE TABLE IF NOT EXISTS estacao_evento (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  chave            TEXT NOT NULL UNIQUE,
  estacao_id       TEXT,
  tipo_estacao     TEXT,
  operador         TEXT,
  projeto_codigo   TEXT,
  evento           TEXT NOT NULL CHECK (evento IN ('capturado','enviado')),
  total_arquivos   INTEGER,
  pasta_entrada    TEXT,
  sha256_manifesto TEXT,                      -- pode ser NULL (no "capturado" ainda não há manifesto)
  recebido_em      TEXT NOT NULL DEFAULT (datetime('now')),
  conferido_em     TEXT,                      -- quando o lote chegou ao painel e a contagem foi comparada
  lote_id          INTEGER,
  folhas_entregues INTEGER,
  divergente       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_estacao_evento_proj ON estacao_evento(projeto_codigo, evento);
