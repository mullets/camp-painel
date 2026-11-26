-- 267 · CAMP-ENTREGA (26/11/2026). Reenviar um pedido (novo link, nova cobrança) deixava o link ANTIGO de pé, mostrando
-- "Aguardando pagamento" com o link de pagamento da cobrança já cancelada. Agora o reenvio encerra os links anteriores do pedido e
-- marca quando foram substituídos; a página do link antigo diz "Este link foi substituído por um novo enviado por e-mail em <data>.
-- Use o link mais recente." (sem botão de pagar). Idempotente: ADD COLUMN de coluna que já existe é ignorado pelo aplicador.
ALTER TABLE entrega_link ADD COLUMN substituido_em TEXT;
ALTER TABLE entrega_link ADD COLUMN substituido_por INTEGER;
