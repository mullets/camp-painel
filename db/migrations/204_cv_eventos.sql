-- Relatório do CAMP Vision e gasto por fundo no painel (02/11/2026, Rafael: "esses relatórios do campvision, consigo acessar no meu
-- painel? / seria bom saber tudo que ele fez resumidamente e o valor gasto / no painel de um fundo, o quanto já gastamos com ele").
-- O CV2 (contrato 2.6) copia o diário de eventos para ACERVOS_CAMP/_campvision/eventos.jsonl; o coletor do QNAP (segundo plano) traz
-- cada linha para cá. Uma linha = um projeto processado. Mesma linha (quando + projeto + pasta) não entra duas vezes.
CREATE TABLE IF NOT EXISTS cv_evento (
  id               INTEGER PRIMARY KEY,
  quando           TEXT NOT NULL,                 -- hora local do servidor do CV2 (ISO, sem fuso)
  dia              TEXT NOT NULL,                 -- AAAA-MM-DD de `quando`
  projeto          TEXT NOT NULL,                 -- "F001-P9003 - Auditório…" (pode ser o provisório P9xxx)
  fundo            TEXT,                          -- F001 (do começo de `projeto`)
  pasta            TEXT NOT NULL DEFAULT '',
  pranchas         INTEGER NOT NULL DEFAULT 0,
  com_carimbo      INTEGER NOT NULL DEFAULT 0,
  erros            INTEGER NOT NULL DEFAULT 0,
  campos_a_revisar INTEGER NOT NULL DEFAULT 0,
  custo_usd        REAL NOT NULL DEFAULT 0,
  duracao_s        INTEGER NOT NULL DEFAULT 0,
  falha            TEXT,
  UNIQUE (quando, projeto, pasta)
);
CREATE INDEX IF NOT EXISTS ix_cv_evento_dia ON cv_evento(dia);
CREATE INDEX IF NOT EXISTS ix_cv_evento_fundo ON cv_evento(fundo);

CREATE TABLE IF NOT EXISTS cv_evento_leitura (
  id        INTEGER PRIMARY KEY CHECK (id = 1),
  mtime     REAL,
  tamanho   INTEGER,
  linhas    INTEGER,
  lido_em   TEXT
);

INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('custos.cotacao_dolar', '', 'Cotação do dólar para mostrar o gasto do CAMP Vision também em reais (vazio = só em US$)', 0);
