-- CAMP-014: o painel ENVIA o mapa antigo→novo ao site (POST /wp-json/camp/v1/painel/redirecionamentos). A própria linha da tabela é a fila de reenvio
-- (aplicado_no_site=0 = falta enviar). Estas colunas guardam o andamento; falha do site nunca desfaz o que mudou no painel.
ALTER TABLE redirecionamento ADD COLUMN tentativas INTEGER NOT NULL DEFAULT 0;
ALTER TABLE redirecionamento ADD COLUMN ultimo_erro TEXT;
ALTER TABLE redirecionamento ADD COLUMN ultima_tentativa TEXT;
ALTER TABLE redirecionamento ADD COLUMN aplicado_em TEXT;
ALTER TABLE redirecionamento ADD COLUMN sem_site INTEGER NOT NULL DEFAULT 0;   -- 1 = não havia nada publicado/registrado no site com este código: nada a enviar
