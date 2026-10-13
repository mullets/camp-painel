-- Cartão 13: problemas registrados SOZINHOS (origem automática). A importação de um lote do CAMP Vision grava
-- em `erro` cada folha que o CV2 retirou (ou que o painel recusou); `chave` identifica o achado para que
-- reimportar o mesmo lote não duplique o registro (nem reabra um que alguém já resolveu).
ALTER TABLE erro ADD COLUMN chave TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_erro_chave ON erro(chave) WHERE chave IS NOT NULL;
