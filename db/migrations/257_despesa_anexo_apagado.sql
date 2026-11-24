-- 257 · CAMP-FIN (24/11/2026). Comprovante anexado por engano numa despesa (Rafael: "subi a nota errada").
-- "Tirar este comprovante" não apaga o arquivo nem a linha: marca apagado_em/apagado_por (some da despesa, das contagens, do ZIP e do
-- leitor automático; fica no histórico da despesa e no disco). "Trocar" = tirar + anexar o certo.
-- Idempotente: ADD COLUMN de coluna que já existe é ignorado pelo aplicador de migrações.
ALTER TABLE despesa_anexo ADD COLUMN apagado_em TEXT;
ALTER TABLE despesa_anexo ADD COLUMN apagado_por TEXT;
CREATE INDEX IF NOT EXISTS idx_despesa_anexo_sha ON despesa_anexo (sha256);
