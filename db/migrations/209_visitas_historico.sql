-- Visitas ao site com histórico (03/11/2026, Rafael: "para colocar o analytics no nosso painel, adapte essa solução para nós":
-- Google Analytics / Search Console → coletor no servidor → banco → dashboard). O coletor (visitas_coletor.py) roda uma vez por dia
-- em segundo plano com a conta de serviço que o painel já usa (ga4.conta_servico), grava aqui, e a tela "Visitas ao site" lê só daqui.
-- Cada coleta fica registrada (período coberto, linhas, erro); os últimos dias são recoletados (o Google ainda ajusta os números).
CREATE TABLE IF NOT EXISTS visita_coleta (
  id          INTEGER PRIMARY KEY,
  inicio      TEXT NOT NULL DEFAULT (datetime('now')),
  fim         TEXT,
  fonte       TEXT NOT NULL,              -- ga4 | search_console
  de          TEXT, ate TEXT,             -- período coberto (AAAA-MM-DD)
  linhas      INTEGER NOT NULL DEFAULT 0,
  erro        TEXT,
  por         TEXT                        -- automático | e-mail de quem pediu
);
CREATE TABLE IF NOT EXISTS visita_dia (    -- GA4: totais do dia (site público, filtrado pelo domínio)
  dia            TEXT PRIMARY KEY,
  usuarios       INTEGER NOT NULL DEFAULT 0,
  sessoes        INTEGER NOT NULL DEFAULT 0,
  visualizacoes  INTEGER NOT NULL DEFAULT 0,
  coleta_id      INTEGER
);
CREATE TABLE IF NOT EXISTS visita_dimensao (   -- GA4: dia × canal | origem | pagina | cidade | dispositivo
  dia            TEXT NOT NULL,
  tipo           TEXT NOT NULL,
  valor          TEXT NOT NULL,
  extra          TEXT,                        -- página: o título
  usuarios       INTEGER NOT NULL DEFAULT 0,
  sessoes        INTEGER NOT NULL DEFAULT 0,
  visualizacoes  INTEGER NOT NULL DEFAULT 0,
  coleta_id      INTEGER,
  PRIMARY KEY (dia, tipo, valor)
);
CREATE INDEX IF NOT EXISTS ix_visita_dimensao_tipo ON visita_dimensao(tipo, dia);
CREATE TABLE IF NOT EXISTS visita_periodo (    -- GA4: pessoas (usuários únicos) não se somam dia a dia: os períodos da tela vêm prontos
  chave          TEXT PRIMARY KEY,            -- 7d | 28d | 90d | mes | mes_anterior
  de             TEXT NOT NULL, ate TEXT NOT NULL,
  usuarios       INTEGER NOT NULL DEFAULT 0,
  sessoes        INTEGER NOT NULL DEFAULT 0,
  visualizacoes  INTEGER NOT NULL DEFAULT 0,
  coleta_id      INTEGER
);
CREATE TABLE IF NOT EXISTS busca_google (      -- Search Console: dia × consulta | pagina
  dia         TEXT NOT NULL,
  tipo        TEXT NOT NULL,                    -- consulta | pagina
  valor       TEXT NOT NULL,
  cliques     INTEGER NOT NULL DEFAULT 0,
  impressoes  INTEGER NOT NULL DEFAULT 0,
  posicao     REAL,                             -- posição média no Google naquele dia
  coleta_id   INTEGER,
  PRIMARY KEY (dia, tipo, valor)
);
CREATE INDEX IF NOT EXISTS ix_busca_google_tipo ON busca_google(tipo, dia);

INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('ga4.dominio',          'camp.arq.br', 'Domínio do site público no Google Analytics (filtro hostName; www. entra junto). Vazio = sem filtro', 0),
 ('sc.site',              '',            'Propriedade do Search Console: sc-domain:camp.arq.br (domínio) ou https://camp.arq.br/ (prefixo). Vazio = não busca as pesquisas no Google', 0),
 ('visitas.coleta_hora',  '6',           'Hora do dia (0–23) em que o painel busca as visitas do dia anterior no Google. Vazio = não busca sozinho', 0),
 ('visitas.dias_iniciais','90',          'Na primeira coleta, quantos dias para trás buscar (até 480)', 0);
