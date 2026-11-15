-- 15/11/2026 (Rafael: "Movi um lote inteiro de um projeto para outro; no antigo ficaram as imagens no site, e no painel ficam como
-- 'só no site'. Devia tirar de ambos."). Ao mover/mesclar, a folha perde o vínculo com o registro que tinha no site (o código muda; ao
-- publicar o destino, ela sobe com o código novo). Esse registro ANTIGO precisa sair do público (privado no site; nada é apagado) e
-- nunca pode voltar ao painel como folha "só no site". Esta tabela é o mapa explícito dos registros antigos (app.mover_site):
--   - entra na MESMA transação do mover (todo caminho: mover folhas, mover lote, mesclar, CAMP Vision);
--   - escondido_em NULL = ainda falta deixar privado no site (pendência; o coletor de 10 min e a rodada de reenvio tentam de novo);
--   - a importação do site (importador_site) não recria folha a partir destes ids.
CREATE TABLE IF NOT EXISTS site_registro_antigo (
  wp_id           INTEGER PRIMARY KEY,      -- id do item no site (o tainacan_item_id que a folha tinha)
  codigo_antigo   TEXT NOT NULL,            -- o código da folha quando tinha este registro
  codigo_novo     TEXT,                     -- para onde a folha foi
  motivo          TEXT,
  ator            TEXT,
  criado_em       TEXT NOT NULL DEFAULT (datetime('now')),
  tentativas      INTEGER NOT NULL DEFAULT 0,
  ultimo_erro     TEXT,
  proxima_em      TEXT,
  escondido_em    TEXT                      -- quando o site confirmou 'private'
);
CREATE INDEX IF NOT EXISTS idx_site_registro_antigo_pendente ON site_registro_antigo (escondido_em, proxima_em);
CREATE INDEX IF NOT EXISTS idx_site_registro_antigo_codigo ON site_registro_antigo (codigo_antigo);
