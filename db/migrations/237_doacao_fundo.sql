-- 237 · CAMP-DOA-FUNDO (21/11/2026). Rafael: "e precisa criar quando terminar o fundo e arquiteto automaticamente." Ao passar uma doação de
-- acervo a "Acervo recebido pela CAMP", o painel cria (ou usa, se a equipe escolher) o fundo e o arquiteto, e guarda AQUI o vínculo
-- doação → fundo: uma doação nunca ganha um segundo fundo (site_id é a chave), e se o site falhar depois de criar, tentar de novo usa o
-- mesmo fundo (códigos nunca se reusam). Sem dado pessoal (nem nome de quem doa, nem CPF, nem endereço). O site não muda (contrato igual:
-- vai etapa=recebido + fundo=<código> no POST /painel/doacoes-acervo/{id} de sempre).
-- Idempotente: CREATE ... IF NOT EXISTS.
CREATE TABLE IF NOT EXISTS doacao_fundo (
  site_id       INTEGER PRIMARY KEY,               -- doacao_acervo.site_id (uma doação → um fundo)
  fundo_codigo  TEXT NOT NULL REFERENCES fundo(codigo),
  agente_id     INTEGER REFERENCES agente(id),     -- o arquiteto (produtor do fundo)
  fundo_criado  INTEGER NOT NULL DEFAULT 0,        -- 1 = o painel criou o fundo por esta doação; 0 = a equipe escolheu um que já existia
  agente_criado INTEGER NOT NULL DEFAULT 0,        -- idem para o arquiteto
  criado_em     TEXT NOT NULL DEFAULT (datetime('now')),
  criado_por    TEXT,                              -- e-mail de quem confirmou
  site_ok_em    TEXT,                              -- quando o site aceitou etapa=recebido + fundo
  site_erro     TEXT                               -- último problema ao mandar ao site (o fundo fica; tentar de novo usa o mesmo)
);
CREATE INDEX IF NOT EXISTS idx_doacao_fundo_fundo ON doacao_fundo (fundo_codigo);
