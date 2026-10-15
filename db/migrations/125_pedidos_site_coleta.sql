-- CAMP-013: o painel BUSCA no site os pedidos (alta resolução, consulta aos originais) e as correções informadas (GET /wp-json/camp/v1/solicitacoes?marcar=1).
-- pedido_site guarda o que o site mandou (chave = id do post no site => idempotente) ANTES de virar solicitacao/erro: como o site marca como "importado" o que
-- devolve, nada se perde se o painel falhar no meio; o que ficou pendente é processado na próxima volta.
CREATE TABLE IF NOT EXISTS pedido_site (
  site_id      INTEGER PRIMARY KEY,           -- id do post (camp_solicitacao) no site
  tipo         TEXT,                          -- alta-resolucao | consulta | correcao
  codigo       TEXT,
  criado_no_site TEXT,
  payload      TEXT NOT NULL,                 -- JSON como veio
  destino      TEXT,                          -- solicitacao | erro | NULL (ainda não processado)
  destino_id   INTEGER,
  situacao     TEXT NOT NULL DEFAULT 'pendente',   -- pendente | importado | falhou
  erro         TEXT,
  recebido_em  TEXT NOT NULL DEFAULT (datetime('now')),
  importado_em TEXT
);
CREATE TABLE IF NOT EXISTS pedido_site_coleta (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  quando    TEXT NOT NULL DEFAULT (datetime('now')),
  lidas     INTEGER NOT NULL DEFAULT 0,
  novas     INTEGER NOT NULL DEFAULT 0,
  importadas INTEGER NOT NULL DEFAULT 0,
  erro      TEXT
);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('site.coleta_pedidos_min', '10', 'Minutos entre as buscas de pedidos e correções informados no site (0 desliga)', 0);
