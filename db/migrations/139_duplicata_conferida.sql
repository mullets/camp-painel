-- Conferência de duplicatas (19/10/2026, "tá complexo quando tem 50 folhas e 25 são duplicatas"): a tela "Duplicatas" do projeto
-- registra que uma PESSOA olhou a marcação. Só ADD COLUMN, opcionais; nada existente muda. Regras em backend/app/duplicatas.py.
--   duplicata_conferida_em/por: quando e quem conferiu.
--   duplicata_conferida_de: a original que a pessoa viu ao conferir. A marcação só conta como conferida enquanto
--   duplicata_de = duplicata_conferida_de: se o CAMP Vision reimportar e apontar para outra folha, volta a pedir conferência.
--   Com duplicata_de NULL e duplicata_conferida_em preenchido: a pessoa disse "Não é duplicata" (não volta como sugestão).
ALTER TABLE item ADD COLUMN duplicata_conferida_em TEXT;
ALTER TABLE item ADD COLUMN duplicata_conferida_por TEXT;
ALTER TABLE item ADD COLUMN duplicata_conferida_de TEXT;
