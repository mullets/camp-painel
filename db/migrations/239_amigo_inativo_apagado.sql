-- 239 · CAMP-AMIGO-APAGAR (21/11/2026). Rafael: "opção de desativar um amigo, apagar também por favor."
-- · Desativar (reversível com Reativar): inativo_em/inativo_motivo/inativo_por. A situação de pagamento NÃO muda (reativar volta ao que era).
--   Inativo: sem cobrança, lembretes nem e-mails automáticos; fora do "Enviar cobrança"; fora da lista padrão (filtro Inativos). O site
--   (contrato 1.28) cancela a assinatura mensal no Mercado Pago (sem reembolso) e para o código e os benefícios.
-- · Apagar (irreversível): apagado_em. Os dados pessoais saem (anonimizado=1); os pagamentos ficam, anônimos, para a contabilidade
--   (valor, data, meio, chave = referência do Mercado Pago ou do painel); o número de Amigo Fundador fica gasto.
-- Idempotente: ADD COLUMN repetido é ignorado por executar_script_idempotente.
ALTER TABLE amigo ADD COLUMN inativo_em TEXT;        -- datetime UTC em que foi desativado (NULL = ativo)
ALTER TABLE amigo ADD COLUMN inativo_motivo TEXT;    -- motivo opcional (apagado junto com o Amigo)
ALTER TABLE amigo ADD COLUMN inativo_por TEXT;       -- quem desativou (e-mail da equipe)
ALTER TABLE amigo ADD COLUMN apagado_em TEXT;        -- datetime UTC em que foi apagado (some do painel; pagamentos ficam)
CREATE INDEX IF NOT EXISTS idx_amigo_inativo ON amigo (inativo_em);
