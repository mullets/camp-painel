-- 230 · CAMP-INGRESSOS (19/11/2026, Rafael: "Não esquece de preparar nosso painel adm também"): ingressos da visita guiada à
-- Residência João Marino, vendidos no site (plugin 1.28.0/1.28.1, contrato 1.18). O painel guarda uma cópia, buscada pela rota
-- GET /wp-json/camp/v1/painel/ingressos?desde=…&todas=1 (só leitura; site antigo = 404: a tela avisa e fica vazia), de N em N
-- minutos (ingressos.coleta_min) ou em "Sincronizar agora". Tela Ingressos (só admin e master: tem dados pessoais).
-- LGPD: "apagar esta pessoa" anonimiza as linhas dela aqui (os valores pagos ficam para a receita).
-- Idempotente: CREATE ... IF NOT EXISTS, INSERT OR IGNORE.
CREATE TABLE IF NOT EXISTS ingresso (
  site_id       INTEGER PRIMARY KEY,               -- ID do ingresso no site (camp_ingresso)
  ref           TEXT,                              -- referência do Mercado Pago: CAMP-INGRESSO-JM-AAAAMMDD-HHMM-n
  casa          TEXT,                              -- sigla da casa (JM = Residência João Marino)
  visita        TEXT,
  data          TEXT,                              -- AAAA-MM-DD da turma (São Paulo)
  hora          TEXT,                              -- HH:MM da turma
  nome          TEXT,
  email         TEXT,                              -- minúsculas (LGPD: apagado no apagar pessoa)
  telefone      TEXT,
  pessoas       INTEGER NOT NULL DEFAULT 0,
  entraram      INTEGER NOT NULL DEFAULT 0,
  preco         REAL,
  total         REAL,                              -- pago pelo visitante (sem a tarifa do Mercado Pago)
  situacao      TEXT,                              -- pago | gratuito | reservado | processando | recusado | cancelado
  amigo_site_id INTEGER,                           -- Amigo que teve o desconto (ID do apoio no site)
  desconto      TEXT,                              -- JSON {categoria, pct, qtd, valor, via} ou NULL
  pagamentos    TEXT,                              -- JSON [{id, valor, meio, data}]
  codigo        TEXT,                              -- código curto do ingresso (o mesmo do e-mail)
  link          TEXT,                              -- endereço do ingresso no site (o QR leva a ele)
  modo          TEXT,                              -- teste | producao (do Mercado Pago, na compra)
  criado_em     TEXT,                              -- UTC, AAAA-MM-DD HH:MM:SS
  confirmado_em TEXT,
  alterado_em   TEXT,
  anonimizado   INTEGER NOT NULL DEFAULT 0,
  visto_em      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ingresso_data ON ingresso (data, hora);
CREATE INDEX IF NOT EXISTS idx_ingresso_email ON ingresso (email);
CREATE TABLE IF NOT EXISTS ingresso_turma (       -- turmas à venda e vagas (cópia da última busca)
  chave    TEXT PRIMARY KEY,                       -- AAAA-MM-DD|HH:MM
  data     TEXT,
  hora     TEXT,
  vagas    INTEGER,
  ocupadas INTEGER,
  livres   INTEGER,
  visto_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS ingresso_estado (       -- estado da busca (desde, última busca, último erro, configuração do site)
  chave TEXT PRIMARY KEY,
  valor TEXT
);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('ingressos.coleta_min', '10', 'De quantos em quantos minutos o painel busca no site os ingressos da visita guiada à Residência João Marino (0 desliga)', 0);
