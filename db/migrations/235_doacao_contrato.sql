-- 235 · CAMP-DOA-CONTRATO e CAMP-DOA-AVISOS (20/11/2026). Rafael: "No painel preciso poder pôr o link do contrato pra assinatura, e gerar a
-- cobrança no mercado livre quando enviar o contrato pra assinatura em e-mails separados" (contrato 1.25, site plugin 1.34.0, OPCIONAL).
-- - Cobranças avulsas: link do contrato para assinatura (opcional). Com ele, "Enviar por e-mail" manda ANTES o e-mail do contrato (TR30)
--   e depois o da cobrança (TR27), separados. contrato_email_link = o link que já saiu no TR30 (reenviar a cobrança não repete o contrato).
-- - doacao.avisar_pagamento: pagamento da contribuição confirmado pelo Mercado Pago avisa a pessoa (TR31 Andamento da doação), se o
--   modelo estiver no Sender. O painel manda o valor ao site junto de cada mudança na doação (o pagamento só vem depois de uma delas).
-- Idempotente: ADD COLUMN repetido é pulado pelo aplicador; INSERT OR IGNORE.
ALTER TABLE cobranca_avulsa ADD COLUMN contrato_link TEXT;
ALTER TABLE cobranca_avulsa ADD COLUMN contrato_email_link TEXT;
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('doacao.avisar_pagamento', '1', 'Avisar por e-mail (TR31, Sender) quem doa o acervo quando o pagamento da contribuição é confirmado (1 liga, 0 desliga)', 0);
