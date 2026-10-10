-- Folha RETIDA na conferência: continua no painel (e conta como conferida), mas NUNCA vai ao site. Decisão de uma pessoa, com motivo opcional.
ALTER TABLE item ADD COLUMN retida INTEGER NOT NULL DEFAULT 0;
ALTER TABLE item ADD COLUMN retida_motivo TEXT;
ALTER TABLE item ADD COLUMN retida_por TEXT;
ALTER TABLE item ADD COLUMN retida_em TEXT;
