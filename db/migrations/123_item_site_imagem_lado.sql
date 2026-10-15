-- CAMP-048: lado maior (px) da imagem que subiu ao site, para o reprocessamento achar o que passa de 1920 px. NULL = subiu antes do limite (tamanho desconhecido).
ALTER TABLE item ADD COLUMN site_imagem_lado INTEGER;
