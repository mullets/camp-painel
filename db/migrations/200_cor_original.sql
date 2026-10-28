-- 28/10/2026 (Rafael: "quero sempre igual o original"): a imagem que vai ao site NÃO tem mais ajuste de branco/contraste (UX-44).
-- O recorte da borda do scanner continua. Idempotente.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES ('imagem.ajuste_cor', '0', 'Imagem pública: ajustar branco e contraste pelo papel. Desligado: a imagem vai com a cor do original', 0);
UPDATE configuracao SET valor='0', descricao='Imagem pública: ajustar branco e contraste pelo papel. Desligado: a imagem vai com a cor do original' WHERE chave='imagem.ajuste_cor';
