-- Diagnóstico do QNAP no painel (por que "0" ou "não configurada") e limites de espaço (uma regra só, no servidor).
ALTER TABLE qnap_snapshot ADD COLUMN prontos_existe INTEGER;
ALTER TABLE qnap_snapshot ADD COLUMN prontos_pastas INTEGER;     -- pastas na raiz do material pronto (mesmo sem lote reconhecido)
ALTER TABLE qnap_snapshot ADD COLUMN entrada_existe INTEGER;
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('qnap.espaco_aviso_pct',   '15', 'Aviso quando o espaço livre do QNAP fica abaixo deste percentual', 0),
 ('qnap.espaco_critico_pct', '5',  'Crítico quando o espaço livre do QNAP fica abaixo deste percentual', 0),
 ('qnap.espaco_critico_gb',  '50', 'Crítico quando o espaço livre do QNAP fica abaixo deste valor em GB', 0);
