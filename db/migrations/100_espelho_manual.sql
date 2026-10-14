-- Revisão pós-CAMP Vision: espelhar a folha (digitalizada pelo verso). NULL = ninguém decidiu: vale o que o CAMP Vision apontou (item.espelhado).
-- 0/1 = decisão de uma pessoa na revisão, que não é desfeita por uma nova importação. Vale para a prévia e para a imagem enviada ao site.
ALTER TABLE item ADD COLUMN espelho_manual INTEGER CHECK (espelho_manual IN (0, 1));
