-- 255 · CAMP-CLIMA (24/11/2026). Gerenciar os sensores do clima pelo painel (nome, "Usar no clima", tirar da lista).
-- Rafael: "adicionei outros sensores de temperatura na sala, e vamos tirar aqueles 2 que já existiam."
-- removido = 1: o admin tirou o sensor da lista (some do clima, da parede e da tela de sensores; ativo vai junto para 0).
-- NADA é apagado: as leituras (clima_leitura) ficam, o histórico continua. "Devolver à lista" volta removido a 0.
-- alterado_em: a última vez que um admin mexeu no sensor (o selo "novo" some depois disso).
-- Idempotente: ADD COLUMN de coluna que já existe é ignorado pelo aplicador de migrações.
ALTER TABLE clima_sensor ADD COLUMN removido INTEGER NOT NULL DEFAULT 0;
ALTER TABLE clima_sensor ADD COLUMN removido_em TEXT;
ALTER TABLE clima_sensor ADD COLUMN alterado_em TEXT;
ALTER TABLE clima_sensor ADD COLUMN alterado_por TEXT;
