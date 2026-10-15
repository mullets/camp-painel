-- CAMP-050 (LGPD, retenção de 24 meses). Padrão SIMULAR: a rotina diária só conta e registra; só anonimiza com lgpd.modo = aplicar.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('lgpd.modo',  'simular', 'LGPD: simular (só conta e registra o que seria anonimizado) ou aplicar (anonimiza de verdade os dados pessoais com mais de lgpd.meses)', 0),
 ('lgpd.meses', '24',      'LGPD: meses de guarda dos dados pessoais de pedidos, downloads e relatos do site', 0),
 ('lgpd.ultima_execucao', '', 'LGPD: data (AAAA-MM-DD) da última rotina diária; o painel preenche', 0);
-- pedido (solicitacao) já anonimizado: a linha fica para as contagens
ALTER TABLE solicitacao ADD COLUMN anonimizada INTEGER NOT NULL DEFAULT 0;
-- pedido de apagar uma pessoa que o site ainda não confirmou: o painel repete até dar certo (o e-mail sai da linha quando o site responde)
CREATE TABLE IF NOT EXISTS lgpd_pendente_site (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  email        TEXT NOT NULL,
  criado_em    TEXT NOT NULL DEFAULT (datetime('now')),
  tentativas   INTEGER NOT NULL DEFAULT 0,
  ultimo_erro  TEXT,
  ultima_em    TEXT
);
