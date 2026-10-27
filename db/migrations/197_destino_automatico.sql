-- UX-43: "Verificar destino" resolvido pelo painel. O lote do CAMP Vision cuja pasta não parece do projeto (UX-01) ganha uma decisão
-- automática: mover para o projeto do mesmo fundo que combina com a pasta, ou criar o projeto (próximo P da tabela de autoridade).
-- desligado = nada; simular (PADRÃO) = o painel calcula e mostra o que faria, sem mudar nada; aplicar = o coletor aplica sozinho
-- (no máximo 10 lotes por rodada, simulando cada um antes; nunca o mesmo lote duas vezes).
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('destino.automatico', 'simular', 'Verificar destino pelo painel (UX-43): desligado | simular (mostra o que faria, sem mudar nada) | aplicar (move o lote para o projeto certo ou cria o projeto, sozinho, em segundo plano)', 0);

-- Uma linha por lote (UNIQUE): o painel nunca decide duas vezes o mesmo lote, nem depois do Desfazer.
-- O lote continua no projeto antigo (a pasta e o pacote no QNAP têm o código antigo) e não importa até o CAMP Vision reorganizar a pasta.
CREATE TABLE IF NOT EXISTS destino_auto (
  id              INTEGER PRIMARY KEY,
  lote_id         INTEGER NOT NULL UNIQUE REFERENCES lista_processamento(id),
  acao            TEXT NOT NULL CHECK (acao IN ('mover','criar')),
  projeto_antigo  TEXT NOT NULL,
  projeto_novo    TEXT NOT NULL,
  titulo_criado   TEXT,                       -- criar: o título que o painel deu (para o quadro "Projetos criados pelo painel")
  nota            REAL,                       -- nome da pasta × projeto escolhido (0..1); criar = a melhor nota de outro projeto
  segunda         REAL,                       -- a segunda melhor nota (a folga da escolha)
  nome_pasta      TEXT,
  pasta_qnap      TEXT,
  estado          TEXT NOT NULL DEFAULT 'movendo' CHECK (estado IN ('movendo','concluido','desfeito')),
  autor           TEXT NOT NULL DEFAULT 'painel (automático)',
  aplicado_por    TEXT,                       -- quem apertou "Aplicar estas N decisões" (admin) ou o coletor
  em              TEXT NOT NULL DEFAULT (datetime('now')),
  concluido_em    TEXT,
  desfeito_em     TEXT,
  desfeito_por    TEXT
);
CREATE INDEX IF NOT EXISTS ix_destino_auto_novo ON destino_auto(projeto_novo);

-- Projeto criado pelo painel (UX-43): origem = 'automatico'. NULL = criado por uma pessoa, pela estação ou importado.
ALTER TABLE projeto ADD COLUMN origem TEXT;
