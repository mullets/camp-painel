-- 05/11 (Rafael): "tire essa mensagem de imagens com uma cópia só do sistema".
-- Sem réplica configurada, o topo ("imagens com uma cópia só") e a lista "Está tudo funcionando?" deixam de avisar (0).
-- 1 = volta a avisar. O quadro Preservação, em Máquinas, continua mostrando a situação das cópias.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('replica.avisar_sem_copia', '0', 'Avisar no topo e no painel inicial quando as imagens têm uma cópia só (sem réplica configurada). 0=não avisa; 1=avisa.', 0);
