-- 247 · CAMP-PAT-AUTENTIQUE (23/11/2026). Rafael: "sim, igual da doação no autentique, tem até lá já os dados salvos da api".
-- Contrato do patrocínio de empresas pela Autentique (mesmo token e mesma chave autentique.ligado da doação de acervo, migração 236):
-- o painel cria o documento a partir do PDF anexado, o link de assinatura vai no e-mail do site (POST /painel/patrocinios/{id}/enviar-contrato,
-- contrato 1.32) e, quando todos assinam, o patrocínio passa a "Contrato assinado". Mesma forma da tabela doacao_autentique.
-- Idempotente: CREATE ... IF NOT EXISTS.
CREATE TABLE IF NOT EXISTS patrocinio_autentique (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       INTEGER NOT NULL,                  -- patrocinio.site_id
  documento_id  TEXT NOT NULL,                     -- id do documento na Autentique
  link          TEXT,                              -- link de assinatura do responsável da empresa (vai no e-mail do site)
  pdf_sha256    TEXT,                              -- reaproveita o documento se o e-mail falhou (não gasta outro documento)
  assinantes    TEXT,                              -- JSON [{public_id, papel: empresa|camp, assinado_em, recusado_em}] (sem nome nem e-mail)
  situacao      TEXT NOT NULL DEFAULT 'criado',    -- criado (e-mail ainda não saiu) | pendente | assinado | recusado
  assinado_em   TEXT,                              -- AAAA-MM-DD da última assinatura
  criado_em     TEXT NOT NULL DEFAULT (datetime('now')),
  criado_por    TEXT,
  conferido_em  TEXT,
  erro          TEXT
);
CREATE INDEX IF NOT EXISTS idx_patrocinio_autentique_site ON patrocinio_autentique (site_id);
CREATE INDEX IF NOT EXISTS idx_patrocinio_autentique_sit ON patrocinio_autentique (situacao);
