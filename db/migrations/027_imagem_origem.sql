-- De onde vem a imagem mostrada para cada item do site: 'miniatura' (do Tainacan), 'documento' (o próprio anexo) ou '' (nenhuma).
ALTER TABLE wp_item ADD COLUMN imagem_origem TEXT;
