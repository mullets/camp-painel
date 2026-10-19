-- Recorte e alinhamento manual da folha na revisão (19/10). Só ADD COLUMN; nada é mexido no que já existe.
-- recorte: JSON {"x","y","w","h"} em frações (0–1) da imagem já girada/espelhada e endireitada; NULL = imagem inteira.
-- alinhamento: ângulo fino em graus (-10 a +10, positivo = horário); 0 = sem ajuste.
-- imagem_corrigida: o JPG corrigido que o painel gerou ao aplicar (relativo à pasta imagens_corrigidas do painel). O TIF e os
-- arquivos do CAMP Vision no QNAP nunca mudam; NULL = a folha usa a imagem do CAMP Vision como sempre.
ALTER TABLE item ADD COLUMN recorte TEXT;
ALTER TABLE item ADD COLUMN alinhamento REAL NOT NULL DEFAULT 0;
ALTER TABLE item ADD COLUMN imagem_corrigida TEXT;
