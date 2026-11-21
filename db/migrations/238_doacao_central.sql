-- 238 · CAMP-DOA-CENTRAL (21/11/2026). Rafael: "seria o ideal lá no doações de acervo ter controle total sobre o acervo … Status, o que já
-- aconteceu, o que não aconteceu, informações internas e etc. Que nem agora esse do Cassol que foi assinado, eu preciso deixar claro que vamos
-- cotar frete, comprar insumo para embalar e etc."
-- Tudo INTERNO do painel (o site não sabe destas tabelas; o contrato com o site não muda):
-- · doacao_tarefa: os próximos passos de cada doação (logística: frete, embalagem, transporte…), com responsável, prazo, situação e valor.
-- · doacao_anexo: arquivos da doação (orçamento de frete, nota fiscal, fotos, contrato assinado baixado da Autentique). O arquivo fica na pasta
--   ao lado do banco (doacoes_anexos/<site_id>/), nunca no repositório; aqui só o nome, o tipo, o tamanho e o sha256.
-- Idempotente: CREATE ... IF NOT EXISTS.
CREATE TABLE IF NOT EXISTS doacao_tarefa (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id      INTEGER NOT NULL,                  -- doacao_acervo.site_id
  titulo       TEXT NOT NULL,
  responsavel  TEXT,                              -- texto livre (nome ou e-mail de quem cuida)
  prazo        TEXT,                              -- AAAA-MM-DD
  situacao     TEXT NOT NULL DEFAULT 'a_fazer',   -- a_fazer | fazendo | feita | nao_se_aplica
  valor        REAL,                              -- R$ (opcional: cotação do frete, compra de insumos…)
  nota         TEXT,
  ordem        INTEGER NOT NULL DEFAULT 0,
  criado_em    TEXT NOT NULL DEFAULT (datetime('now')),
  criado_por   TEXT,
  alterado_em  TEXT NOT NULL DEFAULT (datetime('now')),
  alterado_por TEXT
);
CREATE INDEX IF NOT EXISTS idx_doacao_tarefa_site ON doacao_tarefa (site_id);
CREATE TABLE IF NOT EXISTS doacao_anexo (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id     INTEGER NOT NULL,                   -- doacao_acervo.site_id
  tipo        TEXT NOT NULL DEFAULT 'documento',  -- contrato_assinado | contrato | orcamento | nota_fiscal | foto | documento
  nome        TEXT NOT NULL,                      -- nome para mostrar e baixar (limpo)
  arquivo     TEXT NOT NULL,                      -- caminho relativo à pasta dos anexos
  mime        TEXT,
  tamanho     INTEGER,
  sha256      TEXT,
  tarefa_id   INTEGER,                            -- doacao_tarefa.id (opcional)
  origem      TEXT,                               -- 'equipe' ou 'autentique:<documento_id>' (o contrato assinado baixado sozinho; idempotente)
  criado_em   TEXT NOT NULL DEFAULT (datetime('now')),
  criado_por  TEXT
);
CREATE INDEX IF NOT EXISTS idx_doacao_anexo_site ON doacao_anexo (site_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_doacao_anexo_origem ON doacao_anexo (origem) WHERE origem LIKE 'autentique:%';
