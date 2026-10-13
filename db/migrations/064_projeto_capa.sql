-- B12: capa do projeto escolhida no painel (vira a miniatura do dossiê no site, que é a capa e o og:image).
ALTER TABLE projeto ADD COLUMN capa_item TEXT;          -- código da folha escolhida
ALTER TABLE item ADD COLUMN site_media_id INTEGER;      -- anexo da imagem da folha na biblioteca de mídia do site
