-- CAMP-034: a reserva de projeto da estação (chave_reserva) deixa de ser achada por LIKE no JSON de `evento`
-- (varredura da tabela inteira a cada chamada; e o evento aponta para o código ANTIGO depois de recodificar/mesclar).
CREATE TABLE IF NOT EXISTS reserva (
  chave_reserva  TEXT NOT NULL UNIQUE,
  projeto_codigo TEXT NOT NULL,
  criado_em      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_reserva_projeto ON reserva(projeto_codigo);
-- Backfill: as reservas que já criaram projeto (evento 'criado' com chave_reserva no detalhe).
INSERT OR IGNORE INTO reserva (chave_reserva, projeto_codigo, criado_em)
SELECT json_extract(e.detalhe, '$.chave_reserva'), e.codigo, e.quando
  FROM evento e
 WHERE e.entidade = 'projeto' AND e.tipo = 'criado' AND json_valid(e.detalhe)
   AND COALESCE(json_extract(e.detalhe, '$.chave_reserva'), '') <> ''
 ORDER BY e.id;
