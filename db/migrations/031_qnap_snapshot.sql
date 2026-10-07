-- Coleta periódica de informações do QNAP (feita em segundo plano; a tela só lê o que foi guardado).
CREATE TABLE IF NOT EXISTS qnap_snapshot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  coletado_em TEXT NOT NULL DEFAULT (datetime('now')),
  montado INTEGER NOT NULL DEFAULT 0,
  motivo TEXT,                    -- nao_existe | vazia (quando não montado)
  latencia_ms INTEGER,            -- tempo para o QNAP responder à checagem da pasta
  total_gb REAL, livre_gb REAL,
  entrada_bruta INTEGER, parados INTEGER,
  prontos INTEGER, prontos_parcial INTEGER NOT NULL DEFAULT 0,   -- parcial = a varredura parou no limite de tempo
  ultimo_material_em TEXT, ultimo_material_nome TEXT,
  duracao_ms INTEGER, erro TEXT
);
CREATE INDEX IF NOT EXISTS ix_qnap_snapshot_quando ON qnap_snapshot(coletado_em);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('qnap.coleta_min', '10', 'Intervalo (minutos) da coleta de informações do QNAP; 0 desliga', 0),
 ('qnap.dias_parado', '3', 'Dias sem alteração para uma pasta da entrada bruta contar como parada', 0);
