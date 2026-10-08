-- Heartbeat do CAMP Vision 2: guarda o que ele manda além do estado (progresso, fila, hoje, montagens), como JSON.
ALTER TABLE estacao_heartbeat ADD COLUMN detalhe TEXT;
