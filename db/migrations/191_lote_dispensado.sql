-- UX-35: "Dispensar este lote" — lote com erro do CAMP Vision que ninguém consegue resolver sai das listas e das contagens para todos.
-- Não apaga nada nem muda a etapa/status.json: só anota quem dispensou, quando, o motivo (opcional) e a ASSINATURA do erro
-- (etapa + desde quando + mensagem do CAMP Vision). Se o CAMP Vision reler e a etapa ou a mensagem mudarem, a dispensa deixa de valer
-- sozinha (dispensa_lote.validas). "Voltar a mostrar" apaga a linha (o Histórico guarda as duas ações).
CREATE TABLE IF NOT EXISTS lote_dispensado (
  lote_id     INTEGER PRIMARY KEY REFERENCES lista_processamento(id),
  assinatura  TEXT NOT NULL,
  etapa       TEXT,
  erro_cv     TEXT,
  motivo      TEXT,
  por         TEXT,
  em          TEXT NOT NULL DEFAULT (datetime('now'))
);
