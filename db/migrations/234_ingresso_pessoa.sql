-- 234 · CAMP-INGRESSOS um ingresso por pessoa (20/11/2026, Rafael: "Nome e e-mail para enviar o ingresso dessa pessoa. E envia todos os
-- ingressos separados para quem comprou também"). Contrato 1.24 (site plugin 1.33.0), OPCIONAL: o registro de GET /painel/ingressos ganha
-- `ingressos` [{n, nome, email, tipo, motivo, codigo, link, entrou…}]. Compra antiga (ou site antigo): sem linhas aqui, a lista de presença
-- mostra "comprador + N". Dados pessoais (nome, e-mail): só admin/master veem; LGPD (apagar pessoa) anonimiza aqui também.
-- Idempotente (CREATE ... IF NOT EXISTS).
CREATE TABLE IF NOT EXISTS ingresso_pessoa (
    site_id     INTEGER NOT NULL,            -- a compra (ingresso.site_id)
    n           INTEGER NOT NULL,            -- 1..pessoas
    nome        TEXT,
    email       TEXT,
    tipo        TEXT NOT NULL DEFAULT 'inteira',   -- inteira | meia | amigo | gratuidade
    motivo      TEXT,                        -- só meia: estudante | professor | idoso | pcd | id_jovem | outro
    codigo      TEXT,
    link        TEXT,
    entrou      INTEGER NOT NULL DEFAULT 0,
    entrou_em   TEXT,
    eh_comprador INTEGER NOT NULL DEFAULT 0,
    envios      TEXT,                        -- JSON [{em, para: pessoa|comprador, via}] (sem endereço)
    anonimizado INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (site_id, n)
);
CREATE INDEX IF NOT EXISTS idx_ingresso_pessoa_email ON ingresso_pessoa (lower(email));
