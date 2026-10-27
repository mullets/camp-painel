-- UX-07: o estado de cada alerta guarda o NÍVEL (ok | atencao | critico | nao_medido) e, quando não foi possível medir, o porquê.
-- Só acrescenta colunas (idempotente: o executor pula a coluna que já existe). 'critico' continua sendo a regra do e-mail.
ALTER TABLE alerta_estado ADD COLUMN nivel TEXT;
ALTER TABLE alerta_estado ADD COLUMN motivo TEXT;
