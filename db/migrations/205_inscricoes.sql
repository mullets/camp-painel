-- Inscrições em cursos e "Avise-me da próxima turma" (02/11/2026, CAMP: "quero [as inscrições, com o currículo] no meu adm"; "o avise-me
-- também tem que ir para o painel, para quando tiver novos cursos avisar esse povo").
-- O site guarda cada inscrição (tipo camp_inscricao) e o painel busca na mesma volta da coleta de pedidos (contrato 1.6,
-- GET /wp-json/camp/v1/inscricoes + /cv + /confirmar; docs/CONTRATO_UNICO.md). O PDF do currículo fica numa pasta privada ao lado
-- do banco (inscricoes_cv/), nunca no site público. Tem dados pessoais: só admin e master veem; o apagar pessoa (LGPD) apaga também.
-- Idempotente.
CREATE TABLE IF NOT EXISTS inscricao (
  id             INTEGER PRIMARY KEY,
  site_id        INTEGER NOT NULL UNIQUE,         -- ID do registro no site (camp_inscricao)
  tipo           TEXT NOT NULL DEFAULT 'inscricao', -- inscricao | interesse ("Avise-me da próxima turma")
  curso_id       TEXT NOT NULL DEFAULT '',        -- slug estável do curso (ex.: residencia-acervos-arquitetura)
  curso          TEXT NOT NULL DEFAULT '',
  turma          TEXT NOT NULL DEFAULT '',
  nome           TEXT NOT NULL DEFAULT '',
  email          TEXT,
  telefone       TEXT,
  cidade         TEXT,
  formacao       TEXT,
  motivacao      TEXT,
  disponivel     TEXT,                            -- sim | parte | ''
  portfolio      TEXT,
  soube          TEXT,
  emkt           INTEGER NOT NULL DEFAULT 0,      -- marcou "Quero receber e-mails da CAMP"
  cv_arquivo     TEXT,                            -- nome do arquivo em inscricoes_cv/ (aleatório)
  cv_nome        TEXT,                            -- nome que a pessoa deu ao arquivo
  cv_tamanho     INTEGER,
  texto          TEXT,                            -- corpo completo vindo do site (reserva)
  situacao       TEXT NOT NULL DEFAULT 'nova',    -- inscrição: nova | em_analise | selecionada | nao_selecionada | desistiu; interesse: aguardando | avisado
  avisado_em     TEXT,                            -- interesse: quando a equipe marcou como avisado
  nota           TEXT,
  criado_no_site TEXT,
  importado_em   TEXT NOT NULL DEFAULT (datetime('now')),
  atualizado_em  TEXT
);
CREATE INDEX IF NOT EXISTS idx_inscricao_situacao ON inscricao (situacao);
CREATE INDEX IF NOT EXISTS idx_inscricao_tipo_curso ON inscricao (tipo, curso_id);
CREATE INDEX IF NOT EXISTS idx_inscricao_email ON inscricao (email);
CREATE TABLE IF NOT EXISTS inscricao_coleta (
  id         INTEGER PRIMARY KEY,
  quando     TEXT NOT NULL DEFAULT (datetime('now')),
  lidas      INTEGER NOT NULL DEFAULT 0,
  novas      INTEGER NOT NULL DEFAULT 0,
  confirmadas INTEGER NOT NULL DEFAULT 0,
  erro       TEXT
);
