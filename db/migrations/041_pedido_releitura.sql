-- "Ler dados agora": pedido de releitura ao CAMP Vision. O painel NÃO chama o CAMP Vision (ele não escuta; o fluxo é de mão única): registra o PEDIDO e o CV2 pergunta,
-- avisa que começou e que terminou (GET/POST /api/estacoes/pedidos-releitura). item_codigo NULL = o projeto inteiro.
CREATE TABLE IF NOT EXISTS pedido_releitura (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_codigo TEXT NOT NULL REFERENCES projeto(codigo),
  item_codigo    TEXT REFERENCES item(codigo),
  motivo         TEXT,
  pedido_por     TEXT NOT NULL,
  pedido_em      TEXT NOT NULL DEFAULT (datetime('now')),
  estado         TEXT NOT NULL DEFAULT 'pedido' CHECK (estado IN ('pedido','em_andamento','concluido','falhou','cancelado')),
  estacao        TEXT,
  iniciado_em    TEXT,
  concluido_em   TEXT,
  mensagem       TEXT,                 -- o que o CAMP Vision respondeu
  resultado      TEXT                  -- JSON: o que o painel fez ao importar de novo
);
-- no máximo UM pedido aberto por alvo (projeto inteiro ou uma folha): clicar de novo devolve o que já está aberto
CREATE UNIQUE INDEX IF NOT EXISTS uq_releitura_aberta ON pedido_releitura(projeto_codigo, COALESCE(item_codigo, '')) WHERE estado IN ('pedido','em_andamento');
CREATE INDEX IF NOT EXISTS idx_releitura_estado ON pedido_releitura(estado, pedido_em);
-- quando o CAMP Vision consultou os pedidos pela última vez (para o painel dizer a verdade: "ele ainda não consulta pedidos")
CREATE TABLE IF NOT EXISTS releitura_consulta (
  id           INTEGER PRIMARY KEY CHECK (id = 1),
  consultado_em TEXT NOT NULL,
  estacao      TEXT,
  ip           TEXT
);
