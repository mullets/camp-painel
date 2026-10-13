-- O que uma PESSOA respondeu ao que o CAMP Vision entregou (cartão 148): usar/ignorar sugestão, aceitar/recusar proposta, devolver folha retirada.
-- Nada é aplicado sozinho; cada resposta guarda quem, quando e por quê.
CREATE TABLE IF NOT EXISTS cv_resposta (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  lote_id        INTEGER NOT NULL REFERENCES lista_processamento(id),
  projeto_codigo TEXT NOT NULL,
  tipo           TEXT NOT NULL CHECK (tipo IN ('sugestao','proposta','retirado')),
  chave          TEXT NOT NULL,          -- campo da sugestão; 'grupo:índice' da proposta; código da folha retirada
  acao           TEXT NOT NULL CHECK (acao IN ('usar','ignorar','aceitar','recusar','devolver')),
  valor          TEXT,
  motivo         TEXT,
  por            TEXT NOT NULL,
  em             TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (lote_id, tipo, chave)
);
