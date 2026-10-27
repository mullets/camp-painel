-- UX-44: recorte automático na borda do papel e ajuste de branco/contraste, SÓ nas imagens derivadas (pública e "como vai ao site").
-- O TIF e a prévia do CAMP Vision nunca mudam. Recorte manual (item.recorte) sempre vence.
-- sem_recorte_auto: 1 = a pessoa escolheu "Usar recorte inteiro (sem recorte)" na conferência.
ALTER TABLE item ADD COLUMN sem_recorte_auto INTEGER NOT NULL DEFAULT 0;
-- site_imagem_recorte: versão do recorte automático com que a imagem do site foi gerada (NULL = subiu antes; o reprocessamento lista essas).
ALTER TABLE item ADD COLUMN site_imagem_recorte TEXT;
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('imagem.recorte_automatico', '1', 'Imagem pública: recortar sozinho o fundo do scanner em volta do papel (só na imagem que vai ao site; o original não muda). Recorte incerto não recorta e fica para conferir. 0 desliga', 0),
('imagem.ajuste_cor', '1', 'Imagem pública: ajustar branco e contraste pelo papel (só na imagem que vai ao site; o original não muda). 0 desliga', 0);
