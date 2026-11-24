-- 259 · CAMP-PROJ (24/11/2026). Projetos da CAMP: os projetos institucionais (Lei Rouanet, editais, patrocínios, internos), com objetivos,
-- etapas e prazos, tarefas, orçamento, documentos e histórico, ligados ao Financeiro. Rafael: "vamos ter uma área de projetos no sistema,
-- interligados aos outros módulos dele, que vai ter os objetivos e prazos, e precisa sempre me avisar tudo." Modelo: a proposta do SALIC.
-- NÃO é o projeto do acervo (F0xx-P000x): esse continua "projeto" dentro do fundo; aqui é sempre "Projetos da CAMP".
-- O orçamento de um projeto incentivado NÃO é copiado: o projeto aponta para a conta (financeiro_conta, tipo projeto_incentivado) e usa a
-- planilha do SALIC que já está no Financeiro (migração 254). Nada aqui apaga ou muda dado antigo; colunas novas são opcionais (NULL).
-- Idempotente: CREATE ... IF NOT EXISTS, INSERT OR IGNORE, ADD COLUMN ignorado se já existe.
CREATE TABLE IF NOT EXISTS projeto_camp (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  nome             TEXT NOT NULL,
  tipo             TEXT NOT NULL DEFAULT 'interno',      -- rouanet | edital | patrocinio | interno
  codigo_externo   TEXT,                                 -- ex.: PRONAC 2613864, número do edital
  situacao         TEXT NOT NULL DEFAULT 'planejamento', -- planejamento | captacao | execucao | prestacao | concluido | arquivado
  responsavel      TEXT,
  objetivo_geral   TEXT,
  resumo           TEXT,
  inicio           TEXT,                                 -- AAAA-MM-DD
  fim              TEXT,
  prazo_captacao   TEXT,                                 -- prazos institucionais (SALIC/edital): data-limite
  prazo_execucao   TEXT,
  prazo_prestacao  TEXT,
  conta_id         INTEGER,                              -- financeiro_conta.id (conta do projeto; Rouanet: a do Banco do Brasil)
  criado_por       TEXT,
  criado_em        TEXT NOT NULL DEFAULT (datetime('now')),
  alterado_por     TEXT,
  alterado_em      TEXT,
  arquivado_em     TEXT,
  inicio_execucao  TEXT,                                 -- quando a execução começa (liberação da captação): só com ela as etapas com duração ganham datas
  fonte_recurso    TEXT,                                 -- ex.: Incentivo Fiscal Federal
  valor_proposta   REAL,
  locais           TEXT,                                 -- ex.: Presidente Prudente/SP e São Paulo/SP
  enquadramento    TEXT,
  observacao       TEXT,
  equipe           TEXT                                  -- ficha técnica: JSON [{papel, nome}] (nunca CPF, endereço, telefone ou e-mail)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_projeto_camp_codigo ON projeto_camp (codigo_externo) WHERE codigo_externo IS NOT NULL AND codigo_externo <> '';
CREATE TABLE IF NOT EXISTS projeto_camp_objetivo (      -- objetivos e metas (com indicador e meta numérica opcional)
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_id  INTEGER NOT NULL,
  texto       TEXT NOT NULL,
  indicador   TEXT,                                      -- ex.: "exemplares impressos"
  meta        REAL,                                      -- ex.: 1000
  atual       REAL,                                      -- o que já foi alcançado
  detalhe     TEXT,                                      -- ex.: a distribuição dos exemplares
  ordem       INTEGER NOT NULL DEFAULT 0,
  apagado_em  TEXT
);
CREATE TABLE IF NOT EXISTS projeto_camp_etapa (         -- etapas e marcos do cronograma
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_id  INTEGER NOT NULL,
  nome        TEXT NOT NULL,
  inicio      TEXT,
  prazo       TEXT,
  situacao    TEXT NOT NULL DEFAULT 'a_fazer',           -- a_fazer | fazendo | feita | nao_se_aplica
  marco       INTEGER NOT NULL DEFAULT 0,                -- 1 = marco (entrega, data institucional)
  duracao_texto TEXT,                                    -- a proposta dá DURAÇÃO, não data: "3 meses", "60 dias", "até 36 meses"
  duracao_dias INTEGER,                                  -- dias (60) …
  duracao_meses INTEGER,                                 -- … ou meses (3): com o início da execução, a etapa ganha datas em sequência
  comeca      TEXT,                                      -- "começa quando a captação for liberada", "depois da pré-produção"
  ordem       INTEGER NOT NULL DEFAULT 0,
  feita_em    TEXT,
  apagado_em  TEXT
);
CREATE TABLE IF NOT EXISTS projeto_camp_tarefa (        -- próximos passos (o mesmo vocabulário das tarefas da doação de acervo)
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_id  INTEGER NOT NULL,
  etapa_id    INTEGER,
  o_que       TEXT NOT NULL,
  responsavel TEXT,
  prazo       TEXT,
  situacao    TEXT NOT NULL DEFAULT 'a_fazer',           -- a_fazer | fazendo | feita | nao_se_aplica
  nota        TEXT,
  feita_em    TEXT,
  criado_por  TEXT,
  criado_em   TEXT NOT NULL DEFAULT (datetime('now')),
  apagado_em  TEXT
);
CREATE INDEX IF NOT EXISTS idx_projeto_camp_tarefa ON projeto_camp_tarefa (projeto_id, situacao);
CREATE TABLE IF NOT EXISTS projeto_camp_obrigacao (    -- obrigações assumidas na proposta (acessibilidade, democratização de acesso, direitos,
  id          INTEGER PRIMARY KEY AUTOINCREMENT,         -- documentos enviados): lista para a prestação de contas
  projeto_id  INTEGER NOT NULL,
  grupo       TEXT NOT NULL,
  texto       TEXT NOT NULL,
  situacao    TEXT NOT NULL DEFAULT 'a_fazer',           -- a_fazer | fazendo | feita | nao_se_aplica
  data        TEXT,                                      -- quando foi cumprida (documento enviado: a data de envio)
  nota        TEXT,
  ordem       INTEGER NOT NULL DEFAULT 0,
  feita_em    TEXT,
  apagado_em  TEXT
);
CREATE TABLE IF NOT EXISTS projeto_camp_item (          -- orçamento próprio (projeto SEM conta de projeto incentivado): previsto × realizado
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_id  INTEGER NOT NULL,
  descricao   TEXT NOT NULL,
  previsto    REAL NOT NULL DEFAULT 0,
  ordem       INTEGER NOT NULL DEFAULT 0,
  apagado_em  TEXT
);
CREATE TABLE IF NOT EXISTS projeto_camp_receita (       -- entradas do projeto lançadas pela equipe (captação, aporte, prêmio de edital)
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_id  INTEGER NOT NULL,
  data        TEXT NOT NULL,
  valor       REAL NOT NULL,
  origem      TEXT,                                      -- quem pagou / de onde veio
  descricao   TEXT,
  criado_por  TEXT,
  criado_em   TEXT NOT NULL DEFAULT (datetime('now')),
  apagado_em  TEXT
);
CREATE TABLE IF NOT EXISTS projeto_camp_arquivo (       -- documentos do projeto: o arquivo fica em projetos_camp_arquivos/<id>/ (ao lado do banco)
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_id  INTEGER NOT NULL,
  tipo        TEXT NOT NULL DEFAULT 'outro',             -- proposta | aprovacao | contrato | orcamento | relatorio | prestacao | outro
  nome        TEXT NOT NULL,
  arquivo     TEXT NOT NULL,
  mime        TEXT,
  tamanho     INTEGER,
  sha256      TEXT,
  criado_por  TEXT,
  criado_em   TEXT NOT NULL DEFAULT (datetime('now')),
  apagado_em  TEXT,
  apagado_por TEXT
);
CREATE TABLE IF NOT EXISTS projeto_camp_visto (         -- quando cada pessoa abriu o projeto pela última vez ("mudou desde a sua última visita")
  usuario     TEXT NOT NULL,
  projeto_id  INTEGER NOT NULL,
  visto_em    TEXT NOT NULL,
  PRIMARY KEY (usuario, projeto_id)
);
CREATE TABLE IF NOT EXISTS projeto_camp_email_envio (   -- resumo diário por e-mail (um por dia)
  dia         TEXT PRIMARY KEY,
  para        TEXT,
  ok          INTEGER NOT NULL DEFAULT 0,
  erro        TEXT,
  conteudo    TEXT,
  enviado_em  TEXT NOT NULL DEFAULT (datetime('now'))
);
ALTER TABLE despesa ADD COLUMN projeto_camp_id INTEGER;     -- despesa ligada a um projeto da CAMP (além das da conta do projeto)
ALTER TABLE despesa ADD COLUMN projeto_camp_item INTEGER;   -- item do orçamento próprio do projeto (projeto_camp_item.id)
ALTER TABLE patrocinio ADD COLUMN projeto_camp_id INTEGER;  -- patrocínio que financia um projeto da CAMP
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('projetos_camp.email_diario', '', 'Projetos da CAMP: quem recebe o resumo diário por e-mail (endereços separados por vírgula; vazio = desligado)', 0),
 ('projetos_camp.email_hora', '8', 'Projetos da CAMP: a partir de que hora sai o resumo diário (0 a 23, horário do servidor)', 0);
