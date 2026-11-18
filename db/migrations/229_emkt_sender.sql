-- CAMP-SENDER (18/11/2026, Rafael: "quem aceitou receber e-mails da CAMP… seria bom saber e conseguir filtrar. E cadastrar esses
-- no mailing: pelo site, aceitou → direto no Sender"). O site inscreve sozinho no grupo do Sender (plugin 1.25.15, contrato 1.14)
-- e conta ao painel pela rota GET /wp-json/camp/v1/painel/emkt: quem aceitou, de onde, quando, a versão do texto e a situação
-- no Sender (inscrito, pendente, erro, cancelou). Esta tabela é a cópia dessa lista (um registro do site por linha).
-- LGPD: "apagar esta pessoa" apaga as linhas dela aqui (lgpd.apagar_pessoa_local).
CREATE TABLE IF NOT EXISTS emkt_site (
  site_id     TEXT PRIMARY KEY,       -- "post-123" (formulário do site) ou "ff-45" (cadastro de download)
  email       TEXT NOT NULL,          -- minúsculas
  nome        TEXT,
  origem      TEXT,                   -- pedido, agendamento, contato, apoio, inscricao, interesse, equipamento, download, outro
  origem_nome TEXT,
  aceite_em   TEXT,
  versao      TEXT,                   -- versão do texto da caixa mostrada no formulário
  situacao    TEXT NOT NULL DEFAULT 'pendente',   -- inscrito | pendente | erro | cancelou
  sender_em   TEXT,
  erro        TEXT,
  visto_em    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_emkt_site_email ON emkt_site(email);

CREATE TABLE IF NOT EXISTS emkt_estado (   -- cursor "desde" e o resultado da última busca no site
  chave TEXT PRIMARY KEY,
  valor TEXT
);

INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('emkt.coleta_min', '60', 'Lista de e-mails da CAMP: minutos entre as buscas no site de quem aceitou receber e-mails e da situação no Sender; 0 desliga', 0);
