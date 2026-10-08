-- Uso do acervo: entradas do formulário de download do site (Fluent Forms) trazidas para o painel. Dados pessoais: só admin/master veem.
CREATE TABLE IF NOT EXISTS uso_download (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  form_id         INTEGER NOT NULL,
  origem_id       INTEGER NOT NULL,            -- id da entrada no Fluent Forms
  recebida_em     TEXT,                        -- quando a pessoa enviou o formulário
  nome            TEXT,
  email           TEXT,                        -- sempre em minúsculas
  telefone        TEXT,
  instituicao     TEXT,
  uso             TEXT,                        -- uso pretendido, como a pessoa escolheu ou escreveu (o uso é sempre o DECLARADO)
  material_codigo TEXT,                        -- código CAMP reconhecido (item ou projeto)
  material_origem TEXT,                        -- 'campo' (campo do formulário) | 'valor' (algum valor) | 'pagina' (endereço da ficha)
  projeto_codigo  TEXT,
  fundo_codigo    TEXT,
  pagina          TEXT,                        -- endereço da página onde o modal foi aberto
  resposta_json   TEXT,                        -- todas as respostas como vieram (permite reprocessar sem ir ao site)
  anonimizada     INTEGER NOT NULL DEFAULT 0,  -- 1 = dados pessoais apagados a pedido; a linha fica para as contagens e não é importada de novo
  importada_em    TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (form_id, origem_id)
);
CREATE INDEX IF NOT EXISTS idx_uso_email    ON uso_download(email);
CREATE INDEX IF NOT EXISTS idx_uso_material ON uso_download(material_codigo);
CREATE INDEX IF NOT EXISTS idx_uso_data     ON uso_download(recebida_em);
CREATE TABLE IF NOT EXISTS uso_coleta (        -- o que cada coleta fez (diagnóstico: a API do site pode responder diferente do esperado)
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  quando    TEXT NOT NULL DEFAULT (datetime('now')),
  form_id   INTEGER,
  endpoint  TEXT,
  lidas     INTEGER NOT NULL DEFAULT 0,
  novas     INTEGER NOT NULL DEFAULT 0,
  completo  INTEGER NOT NULL DEFAULT 0,
  erro      TEXT
);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('uso.form_id',    '',   'Id do formulário de download no Fluent Forms (vazio = procura "download" ou "material" no título)', 0),
 ('uso.coleta_min', '60', 'Minutos entre coletas automáticas das entradas do formulário de download (0 desliga)', 0);
