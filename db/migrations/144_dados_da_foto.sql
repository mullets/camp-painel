-- Fotos separadas por ano da foto, estágio e fotógrafo (21/10/2026, Rafa: "fotos precisa por ano da foto, estagio, fotografo").
-- Só ADD COLUMN; nada existente muda (NULL = não informado). Valem para qualquer folha, mas a tela oferece nas séries de foto
-- (S03 Fotografias, S04 Negativos, S05 Slides). Coluna na própria folha: mover/recodificar/mudar a série copiam a linha e levam junto.
-- foto_ano é texto ("1992", "c. 1992", "década de 1990"): a ordem dos blocos usa o primeiro ano de 4 dígitos. Regras em backend/app/dados_foto.py.
ALTER TABLE item ADD COLUMN foto_ano TEXT;
ALTER TABLE item ADD COLUMN foto_estagio TEXT;
ALTER TABLE item ADD COLUMN foto_fotografo TEXT;
