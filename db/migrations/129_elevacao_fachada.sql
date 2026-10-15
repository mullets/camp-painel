-- CAMP-051: "Elevação" e "Fachada" viram um tipo só: "Elevação/Fachada" (vocabulário do painel, itens e tabela). O tipo lido pelo CAMP Vision
-- (item.tipo_lido, lido_json) NÃO é mexido: é o registro do que ele leu.
INSERT OR IGNORE INTO tipo_documento (nome) VALUES ('Elevação/Fachada');
UPDATE item SET tipo_documento='Elevação/Fachada' WHERE tipo_documento IN ('Elevação', 'Elevacao', 'Fachada');
DELETE FROM tipo_documento WHERE nome IN ('Elevação', 'Elevacao', 'Fachada');
