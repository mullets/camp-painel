-- 240 · CAMP-DOA-AMIGO (21/11/2026). Rafael: "Não vi na lista também a Raquel, que doou acervo e virou amiga.."
-- O site (contrato 1.30) passa a dizer de qual doação de acervo veio o Amigo (doacao_id, doacao_protocolo) e de onde nasceu o cadastro
-- (fonte: site | painel | doacao_acervo). O painel guarda para mostrar "Origem: doação de acervo CAMP-AAAA-NNNNNN" com o link da doação.
-- Idempotente: ADD COLUMN repetido é ignorado por executar_script_idempotente.
ALTER TABLE amigo ADD COLUMN fonte TEXT;              -- de onde o cadastro nasceu no site (site | painel | doacao_acervo); NULL = site antigo
ALTER TABLE amigo ADD COLUMN doacao_site_id INTEGER;  -- id da intenção de doação de acervo no site que deu o Amigo (doacao_acervo.site_id)
ALTER TABLE amigo ADD COLUMN doacao_protocolo TEXT;   -- protocolo da doação (CAMP-AAAA-NNNNNN)
