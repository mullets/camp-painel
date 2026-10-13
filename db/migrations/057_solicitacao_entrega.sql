-- H17: ao marcar "entregue", o painel pergunta o que foi entregue (arquivos e tamanho) e guarda aqui (e no histórico do pedido).
ALTER TABLE solicitacao ADD COLUMN entrega TEXT;
