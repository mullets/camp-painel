-- Projeto criado a partir de uma SUBPASTA do sistema ("01 - Arquivo Arquivístico (TIFF)", "JPG"…) e sem folhas: o admin descarta.
-- Nada é apagado: o projeto some das listas, o número P continua ocupado (numero_p não muda; nunca é reusado) e o evento fica no histórico.
ALTER TABLE projeto ADD COLUMN descartado_em TEXT;
ALTER TABLE projeto ADD COLUMN descartado_por TEXT;
ALTER TABLE projeto ADD COLUMN descartado_motivo TEXT;
