-- "Mais inteligência": a fila de Decisões passa a ter vários tipos (projeto_parecido, lote_colide, divergencia, projeto_outro_fundo).
-- `resolucao` continua só para projeto_parecido ('mesmo'|'novo', por causa do CHECK antigo); a escolha de QUALQUER tipo fica em `escolha`
-- (e o valor escolhido, quando há, em `escolha_valor`). Assim não é preciso recriar a tabela.
ALTER TABLE decisao ADD COLUMN escolha TEXT;
ALTER TABLE decisao ADD COLUMN escolha_valor TEXT;
UPDATE decisao SET escolha=resolucao WHERE resolucao IS NOT NULL AND escolha IS NULL;
CREATE INDEX IF NOT EXISTS idx_decisao_tipo ON decisao(tipo, situacao);
