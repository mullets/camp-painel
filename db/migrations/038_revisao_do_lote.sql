-- Revisão pós-CAMP Vision: as folhas do lote entram no painel (a partir do pacote_tainacan.json), uma pessoa confere/corrige, o admin aprova o lote.
-- A aprovação é um REGISTRO (quem/quando) e NÃO muda a etapa: 'rascunho' já significa "foi para o site", com portões próprios.
ALTER TABLE item ADD COLUMN revisao TEXT NOT NULL DEFAULT 'pendente' CHECK (revisao IN ('pendente','conferida','corrigida'));
ALTER TABLE item ADD COLUMN revisado_por TEXT;
ALTER TABLE item ADD COLUMN revisado_em TEXT;
ALTER TABLE item ADD COLUMN tipo_lido TEXT;        -- o tipo como o CAMP Vision leu, mesmo que não exista no vocabulário do painel
ALTER TABLE item ADD COLUMN pendencias TEXT;       -- JSON: titulo_lido, bloqueios, ressalvas, sinais (orientação incerta...), confiança, prévia
ALTER TABLE item ADD COLUMN lote_id INTEGER REFERENCES lista_processamento(id);
ALTER TABLE lista_processamento ADD COLUMN aprovado_por TEXT;
ALTER TABLE lista_processamento ADD COLUMN aprovado_em TEXT;
CREATE INDEX IF NOT EXISTS idx_item_lote ON item(lote_id, revisao);
