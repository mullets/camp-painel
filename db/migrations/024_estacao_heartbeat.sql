-- Heartbeat dos apps de captura. Máquina online (ping/porta) e app online são estados distintos.
CREATE TABLE IF NOT EXISTS estacao_heartbeat (
  estacao_id       TEXT PRIMARY KEY,
  tipo_estacao     TEXT NOT NULL,
  app              TEXT NOT NULL,
  versao           TEXT,
  hostname         TEXT,
  ip_local         TEXT,
  estado           TEXT NOT NULL DEFAULT 'ocioso',
  fundo_codigo     TEXT,
  projeto_codigo   TEXT,
  operador         TEXT,
  ultimo_erro      TEXT,
  recebido_de_ip   TEXT,
  atualizado_em    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_estacao_heartbeat_atualizado ON estacao_heartbeat(atualizado_em);
