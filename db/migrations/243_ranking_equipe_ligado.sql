-- 243 · CAMP-HOME-UX (22/11/2026). Decisão do Rafael: o Ranking da equipe (mês) fica LIGADO (Home, coluna da direita, e Problemas).
-- Só vira '1' onde ainda está o padrão intocado da 241 ('0' e ninguém mexeu: atualizado_por IS NULL, como a 005). Se um admin já
-- desligou de propósito, fica desligado. Banco sem a chave: nasce ligada. Idempotente: INSERT OR IGNORE + UPDATE com WHERE.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('jogo.ranking_equipe', '1', 'Ranking da equipe (mês): pontos validados de cada pessoa no mês, na Home e em Problemas (1 = ligado, o padrão; 0 = desligado)', 0);
UPDATE configuracao SET valor='1' WHERE chave='jogo.ranking_equipe' AND valor='0' AND atualizado_por IS NULL;
-- o texto da chave (Configurações) passa a dizer mês e ligado, para todos (não muda o valor)
UPDATE configuracao SET descricao='Ranking da equipe (mês): pontos validados de cada pessoa no mês, na Home e em Problemas (1 = ligado, o padrão; 0 = desligado)'
 WHERE chave='jogo.ranking_equipe';
