-- Clima das salas do acervo: temperatura e umidade dos sensores Tuya (Wi-Fi), lidos da nuvem da Tuya em segundo plano.
-- Ver backend/app/clima.py. Nasce DESLIGADO (clima.coleta_min = 0): nada muda até alguém preencher as credenciais e ligar.
CREATE TABLE IF NOT EXISTS clima_sensor (
  id         TEXT PRIMARY KEY,                 -- id do aparelho na Tuya
  nome       TEXT NOT NULL,                    -- nome mostrado no painel (nasce igual ao do app; pode ser trocado aqui)
  nome_tuya  TEXT,                             -- nome no app da Tuya
  categoria  TEXT,
  online     INTEGER NOT NULL DEFAULT 1,
  escalas    TEXT,                             -- JSON {código: casas decimais}, lido uma vez da Tuya
  ativo      INTEGER NOT NULL DEFAULT 1,       -- 0 = não aparece nem guarda leitura
  criado_em  TEXT NOT NULL DEFAULT (datetime('now')),
  visto_em   TEXT
);
CREATE TABLE IF NOT EXISTS clima_leitura (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  sensor_id     TEXT NOT NULL,
  lido_em       TEXT NOT NULL DEFAULT (datetime('now')),
  temperatura_c REAL,
  umidade_pct   REAL,
  bateria_pct   REAL
);
CREATE INDEX IF NOT EXISTS ix_clima_leitura_sensor_quando ON clima_leitura(sensor_id, lido_em);
CREATE TABLE IF NOT EXISTS clima_coleta (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  quando     TEXT NOT NULL DEFAULT (datetime('now')),
  sensores   INTEGER NOT NULL DEFAULT 0,
  erro       TEXT,
  duracao_ms INTEGER
);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('clima.coleta_min',         '0',  'Minutos entre as leituras dos sensores de temperatura e umidade (Tuya); 0 desliga. Sugestão: 10', 0),
 ('clima.tuya_regiao',        'us', 'Região do projeto na nuvem da Tuya (us, us-e, eu, eu-w, in, cn). Contas do Brasil costumam ficar em us', 0),
 ('clima.tuya_access_id',     '',   'Access ID (Client ID) do projeto na nuvem da Tuya (iot.tuya.com, aba Overview do projeto)', 0),
 ('clima.tuya_access_secret', '',   'Access Secret (Client Secret) do mesmo projeto da Tuya', 1),
 ('clima.temp_min',           '18', 'Temperatura mínima desejada nas salas do acervo, em °C', 0),
 ('clima.temp_max',           '24', 'Temperatura máxima desejada nas salas do acervo, em °C', 0),
 ('clima.umid_min',           '40', 'Umidade relativa mínima desejada, em %', 0),
 ('clima.umid_max',           '60', 'Umidade relativa máxima desejada, em %', 0);

-- Tablet de parede (/clima): também mostra quantas pessoas estão no site agora (Google Analytics, últimos 30 min). Ver backend/app/site_agora.py.
CREATE TABLE IF NOT EXISTS site_agora (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  quando  TEXT NOT NULL DEFAULT (datetime('now')),
  pessoas INTEGER,
  erro    TEXT
);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('parede.site_agora_min', '0', 'Minutos entre as leituras de "pessoas no site agora" (Google Analytics) para o tablet de parede; 0 desliga. Sugestão: 2', 0);
