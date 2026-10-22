-- REF-006: fila escrita na mesma transação que altera folha publicada.
CREATE TABLE IF NOT EXISTS fila_correcao_site (
  item_codigo TEXT PRIMARY KEY,
  versao INTEGER NOT NULL DEFAULT 1,
  estado TEXT NOT NULL DEFAULT 'pendente' CHECK (estado IN ('pendente','executando')),
  tentativas INTEGER NOT NULL DEFAULT 0,
  proxima_em TEXT NOT NULL DEFAULT (datetime('now')),
  reservado_ate TEXT,
  ultimo_erro TEXT,
  atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_fila_correcao_pendente ON fila_correcao_site(estado, proxima_em);
CREATE TRIGGER IF NOT EXISTS trg_fila_correcao_item
AFTER UPDATE OF titulo, tipo_documento, tipos_documento, folha, escala, ano_folha,
                endereco_folha, cliente_folha, suporte, giro_manual, espelho_manual,
                recorte, alinhamento, imagem_corrigida ON item
WHEN NEW.tainacan_item_id IS NOT NULL AND NEW.status_site IN ('no_ar','rascunho') AND (
     OLD.titulo IS NOT NEW.titulo OR OLD.tipo_documento IS NOT NEW.tipo_documento OR
     OLD.tipos_documento IS NOT NEW.tipos_documento OR OLD.folha IS NOT NEW.folha OR
     OLD.escala IS NOT NEW.escala OR OLD.ano_folha IS NOT NEW.ano_folha OR
     OLD.endereco_folha IS NOT NEW.endereco_folha OR OLD.cliente_folha IS NOT NEW.cliente_folha OR
     OLD.suporte IS NOT NEW.suporte OR OLD.giro_manual IS NOT NEW.giro_manual OR
     OLD.espelho_manual IS NOT NEW.espelho_manual OR OLD.recorte IS NOT NEW.recorte OR
     OLD.alinhamento IS NOT NEW.alinhamento OR OLD.imagem_corrigida IS NOT NEW.imagem_corrigida
)
BEGIN
 INSERT INTO fila_correcao_site (item_codigo) VALUES (NEW.codigo)
 ON CONFLICT(item_codigo) DO UPDATE SET
   versao = versao + 1, estado='pendente', tentativas=0,
   proxima_em=datetime('now'), reservado_ate=NULL, ultimo_erro=NULL,
   atualizado_em=datetime('now');
END;
