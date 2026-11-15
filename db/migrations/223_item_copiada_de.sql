-- 15/11/2026 (Rafael: "copiar para outro lote, e ter a opção de criar esse lote, seja no mesmo arquiteto ou em outro"): folha COPIADA
-- para outro projeto (POST /api/itens/copiar). Só ADD COLUMN (opcional); nada existente muda. NULL = folha comum.
-- Valor = o código da folha de onde a cópia saiu, no momento da cópia. Serve para: (1) a imagem — a cópia usa a mesma imagem da original
-- (o painel nunca copia arquivo no QNAP) e a prévia do CAMP Vision tem o nome do código da original; (2) não copiar duas vezes a mesma folha
-- para o mesmo projeto; (3) a sugestão de duplicatas não junta a cópia com a original; (4) a cópia nunca é gravada no QNAP pelo painel.
ALTER TABLE item ADD COLUMN copiada_de TEXT;
CREATE INDEX IF NOT EXISTS idx_item_copiada_de ON item(copiada_de);
