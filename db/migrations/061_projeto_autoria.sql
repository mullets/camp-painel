-- B4: autoria do projeto diferente do titular do fundo (terceiros, coautoria, consultoria).
-- Espelha os campos do site "Autoria do projeto" (62564) e "Papel no projeto" (62566).
ALTER TABLE projeto ADD COLUMN autoria TEXT;            -- quem projetou, separado por ";" (ex.: 8 autores do IAB)
ALTER TABLE projeto ADD COLUMN papel_no_projeto TEXT;   -- papel do titular do fundo: autor, coautor, consultor, colaborador, terceiros
