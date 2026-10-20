-- UF do projeto (20/10/2026, CAMP-125, F026-P0009): o CAMP Vision sugere "UF: SP" no bloco projeto do pacote e o painel
-- não tinha onde guardar (a sugestão aparecia para sempre, sem o botão "Usar"). Só ADD COLUMN, opcional; nada existente muda.
ALTER TABLE projeto ADD COLUMN uf TEXT;
