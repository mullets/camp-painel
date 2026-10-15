-- CAMP-008: reconciliação noturna. O aviso do CAMP Vision (POST /api/campvision/aviso) lê uma pasta; se algum aviso se perder, a varredura da raiz
-- final (a mesma do botão "Varrer QNAP") recoloca na Fila o que faltar e lê erros.json de cada lote. Roda uma vez por noite, em segundo plano.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('qnap.reconciliacao_hora',   '3', 'Hora (0-23) da reconciliação noturna do QNAP com o painel; -1 desliga', 0),
 ('qnap.reconciliacao_ultima', '',  'Data (AAAA-MM-DD) da última reconciliação noturna concluída; o painel preenche', 0),
 ('qnap.reconciliacao_tentativa', '', 'Data e hora da última tentativa (para repetir só depois de 1 hora); o painel preenche', 0);
