-- Foto de perfil guardada no próprio banco (pequena: o navegador reduz para 256x256 JPEG antes de enviar).
-- Entra no backup junto com o resto; sem arquivos soltos nem caminhos para validar.
ALTER TABLE usuario ADD COLUMN foto BLOB;
ALTER TABLE usuario ADD COLUMN foto_tipo TEXT;
