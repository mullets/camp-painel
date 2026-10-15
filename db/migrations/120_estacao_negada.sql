-- CAMP-027 (lado do painel): o painel lembra das chamadas de estações RECUSADAS por falta de token, para a tela Estações avisar
-- ("uma máquina está tentando falar com o painel sem o token"). Uma linha por IP e motivo; só os últimos dias contam.
CREATE TABLE IF NOT EXISTS estacao_negada (
  ip            TEXT NOT NULL,
  motivo        TEXT NOT NULL,                 -- token_ausente_ou_invalido | via_proxy_sem_token
  enviou_token  INTEGER NOT NULL DEFAULT 0,    -- 1 = mandou um token, mas errado
  rota          TEXT,
  vezes         INTEGER NOT NULL DEFAULT 1,
  primeira_em   TEXT NOT NULL DEFAULT (datetime('now')),
  ultima_em     TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (ip, motivo)
);
