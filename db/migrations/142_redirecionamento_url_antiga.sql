-- CAMP-017 (E2E 137): ao recodificar, o painel troca o código em wp_item (espelho do site) e perdia o endereço público do código ANTIGO;
-- sem ele o redirecionamento da folha nunca saía ('sem_url'). Guarda o endereço que o espelho conhecia antes da troca.
ALTER TABLE redirecionamento ADD COLUMN url_antiga TEXT;
