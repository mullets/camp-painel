-- 236 · CAMP-AUTENTIQUE (20/11/2026). Rafael: assinatura eletrônica integrada. Em "Enviar contrato para assinatura" de uma doação de
-- acervo, o painel cria o documento na Autentique (plano grátis: 10 documentos por mês, API inclusa) a partir do PDF anexado; o link de
-- assinatura da pessoa vai no NOSSO e-mail TR30 (rota de sempre do site, contrato 1.25: nada muda no site). Quando todos assinam, o
-- painel passa a doação a "Contrato assinado pelas partes" com a data da última assinatura (POST /painel/doacoes-acervo/{id} de sempre).
-- Nasce DESLIGADO (autentique.ligado = 0) e sem token: nada muda até alguém colar o token e ligar. O token é sensível (nunca volta à tela).
-- Idempotente: CREATE ... IF NOT EXISTS, INSERT OR IGNORE.
CREATE TABLE IF NOT EXISTS doacao_autentique (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       INTEGER NOT NULL,                  -- doacao_acervo.site_id
  documento_id  TEXT NOT NULL,                     -- id do documento na Autentique
  link          TEXT,                              -- link de assinatura de quem doa (vai no TR30 como contrato_link)
  pdf_sha256    TEXT,                              -- para reaproveitar o documento se o envio do e-mail falhou (não gasta outro documento)
  assinantes    TEXT,                              -- JSON [{public_id, papel: doador|camp, assinado_em, recusado_em}] (sem nome nem e-mail)
  situacao      TEXT NOT NULL DEFAULT 'criado',    -- criado (e-mail ainda não saiu) | pendente | assinado | recusado
  assinado_em   TEXT,                              -- AAAA-MM-DD da última assinatura
  criado_em     TEXT NOT NULL DEFAULT (datetime('now')),
  criado_por    TEXT,
  conferido_em  TEXT,
  erro          TEXT                               -- último problema ao conferir (sem token)
);
CREATE INDEX IF NOT EXISTS idx_doacao_autentique_site ON doacao_autentique (site_id);
CREATE INDEX IF NOT EXISTS idx_doacao_autentique_sit ON doacao_autentique (situacao);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('autentique.token', '', 'Token da API da Autentique (assinatura eletrônica dos contratos de doação de acervo)', 1),
 ('autentique.ligado', '0', 'Assinatura eletrônica pela Autentique nos contratos de doação de acervo (1 liga, 0 desliga)', 0),
 ('autentique.assinante_camp', '', 'E-mail de quem assina pela CAMP na Autentique (opcional; a Autentique manda o link a esse e-mail)', 0);
