-- CAMP-015: o que o painel mandou da última vez ao site para um fundo (hub + biografia + foto), para mostrar a divergência painel × site
-- (o painel não consegue LER os campos do hub no site: compara o que há agora no painel com o último envio).
CREATE TABLE IF NOT EXISTS fundo_envio_site (
  fundo_codigo TEXT PRIMARY KEY,
  enviado_em   TEXT NOT NULL DEFAULT (datetime('now')),
  enviado_por  TEXT,
  campos_json  TEXT NOT NULL,          -- {campo: texto (ou "retrato:<data>")} do último envio completo
  ok           INTEGER NOT NULL DEFAULT 1,
  erro         TEXT
);
