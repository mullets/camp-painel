-- Mesclar/mover folhas entre projetos e descartar lote duplicado: tudo deixa rastro (nada é apagado).
ALTER TABLE item ADD COLUMN codigo_anterior TEXT;                 -- código que a folha tinha antes de ser movida
ALTER TABLE projeto ADD COLUMN mesclado_em TEXT;                  -- código do projeto de destino; o projeto some das listas, mas continua guardado
ALTER TABLE projeto ADD COLUMN mesclado_por TEXT;
ALTER TABLE projeto ADD COLUMN mesclado_quando TEXT;
ALTER TABLE lista_processamento ADD COLUMN descartado_em TEXT;    -- lote que é subpasta/duplicata de outro: sai da Fila, não apaga nada no QNAP
ALTER TABLE lista_processamento ADD COLUMN descartado_por TEXT;
ALTER TABLE lista_processamento ADD COLUMN descartado_motivo TEXT;
ALTER TABLE lista_processamento ADD COLUMN descartado_duplicata_de INTEGER;
