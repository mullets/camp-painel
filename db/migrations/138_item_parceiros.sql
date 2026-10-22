-- Escritórios parceiros / projetos complementares da folha (19/10/2026): calculista, instalações, paisagismo etc.
-- Só ADD COLUMN; nada existente muda. JSON: [{"escritorio": "Escritório X", "disciplina": "Estrutura"}, ...]; NULL = nenhum informado.
-- Coluna (e não tabela própria) como recorte, pendencias e outlier_campos: a lista vive e é salva junto com a folha (PATCH /api/itens/{c}),
-- e mover/recodificar folha (que copia a linha inteira) leva os parceiros junto sem código a mais. Regras em backend/app/parceiros.py.
ALTER TABLE item ADD COLUMN parceiros TEXT;
