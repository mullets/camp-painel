-- Sobras #12: pedidos de material que chegam sozinhos do formulário do site (rota pública com token), aviso por e-mail ao admin
-- e o "pacote de entrega" (o que foi entregue fica na própria linha do pedido).
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('pedidos.token', '', 'Senha que o formulário de pedido de material do site manda no cabeçalho X-Camp-Token. Vazio = o site não consegue registrar pedidos (ver docs/pedidos-do-site.md)', 1),
 ('avisos.pedido_novo', '1', 'Mandar e-mail para avisos.email quando chega um pedido de material pelo site (1 = sim, 0 = não)', 0);

-- O registro de envio dos alertas passa a aceitar o aviso de pedido novo (tipo 'novo'). O SQLite não muda um CHECK: recria a tabela.
CREATE TABLE IF NOT EXISTS alerta_envio_075 (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  assunto     TEXT NOT NULL,
  tipo        TEXT NOT NULL CHECK (tipo IN ('critico','resolvido','suprimido','novo')),
  para        TEXT,
  titulo      TEXT,
  ok          INTEGER NOT NULL DEFAULT 0,
  erro        TEXT,
  enviado_em  TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT INTO alerta_envio_075 (id, assunto, tipo, para, titulo, ok, erro, enviado_em)
  SELECT id, assunto, tipo, para, titulo, ok, erro, enviado_em FROM alerta_envio;
DROP TABLE alerta_envio;
ALTER TABLE alerta_envio_075 RENAME TO alerta_envio;
