-- Fundo "sem legendas nas imagens do site" (10/11/2026, pedido do Rafael para o fundo da Chu Ming Silveira; contrato painel ↔ site 1.9).
-- Só ADD COLUMN; nada existente muda. NULL = nunca escolhido (nada vai ao site: o site segue com as legendas, como sempre);
-- 1 = ligado (vai "1" ao hub); 0 = desligado depois de ligado (vai "__limpar__"). Gravado pelo PATCH /api/fundos/{codigo}
-- (caixa "Sem legendas nas imagens do site") e pelo scripts/fundo_sem_legendas.py, que usa o mesmo caminho.
ALTER TABLE fundo ADD COLUMN sem_legendas INTEGER;
