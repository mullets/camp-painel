-- H4: toda ação longa vira TAREFA (não só publicar): varrer QNAP, backup, sincronizar, buscar pedidos de uso, enviar folhas.
-- projeto_codigo passa a ser o ALVO da tarefa (o código do projeto, ou 'qnap', 'site', 'uso', 'backup').
ALTER TABLE tarefa_publicacao ADD COLUMN tipo TEXT NOT NULL DEFAULT 'publicar';
ALTER TABLE tarefa_publicacao ADD COLUMN titulo TEXT;
CREATE INDEX IF NOT EXISTS idx_tarefa_estado ON tarefa_publicacao (estado, id DESC);
