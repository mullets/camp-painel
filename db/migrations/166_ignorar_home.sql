-- UX-03: "Ignorar ▾" em todo item do Precisa de você.
-- "Esconder por 7 dias" usa a tarefa_adiada (por pessoa, volta sozinho); o título guardado aparece em Problemas › Ignorados.
ALTER TABLE tarefa_adiada ADD COLUMN titulo TEXT;
-- "Não mostrar mais (não era problema)": quem fechou o problema (a data é resolvido_em; a justificativa, resolucao).
ALTER TABLE erro ADD COLUMN fechado_por TEXT;
