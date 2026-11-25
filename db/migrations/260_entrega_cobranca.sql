-- 260 · CAMP-ENTREGA (25/11/2026). Rafael: "caso alguém solicite acesso a algum, fazer uma resposta para download com link temporário e
-- uma cobrança, além de justificar o porquê da cobrança ou ausência dela."
-- O envio do pedido de alta resolução passa a guardar: com ou sem cobrança, o motivo (lista curta) e a justificativa escrita, o valor e a
-- cobrança do Mercado Pago ligada (cobranca_avulsa). O link pode ficar travado até o pagamento (liberar_apos_pagamento).
-- Idempotente: ADD COLUMN de coluna que já existe é ignorado pelo aplicador de migrações. Nada muda nos pedidos antigos (tudo NULL/0).
ALTER TABLE solicitacao ADD COLUMN cobranca_modo TEXT;            -- com | sem
ALTER TABLE solicitacao ADD COLUMN cobranca_motivo TEXT;          -- chave de entrega.MOTIVOS_COM / MOTIVOS_SEM
ALTER TABLE solicitacao ADD COLUMN cobranca_justificativa TEXT;   -- texto que vai no e-mail e na exportação
ALTER TABLE solicitacao ADD COLUMN cobranca_id INTEGER;           -- cobranca_avulsa.id
ALTER TABLE entrega_link ADD COLUMN cobranca_id INTEGER;
ALTER TABLE entrega_link ADD COLUMN liberar_apos_pagamento INTEGER NOT NULL DEFAULT 0;
ALTER TABLE entrega_link ADD COLUMN uso_comercial INTEGER NOT NULL DEFAULT 0;
ALTER TABLE cobranca_avulsa ADD COLUMN solicitacao_id INTEGER;
