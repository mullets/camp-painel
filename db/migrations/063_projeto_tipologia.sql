-- B3: as 4 facetas de tipologia do site no projeto (programa/uso continua em projeto.tipologia).
-- Nomes dos termos do site separados por "; " (ver backend/app/tipologia.py).
ALTER TABLE projeto ADD COLUMN natureza TEXT;
ALTER TABLE projeto ADD COLUMN modalidade TEXT;
ALTER TABLE projeto ADD COLUMN situacao_obra TEXT;
