-- 227 · CAMP-APOIO (18/11/2026, Rafael: "sempre Sender"): os e-mails do Amigos da CAMP saem só pelo Sender, pela rota do site
-- POST /wp-json/camp/v1/painel/apoios/{id}/email (contrato 1.12). A fila guarda o template do site e as variáveis que vão
-- (o que a prévia mostrou é o que sai) e o id que o Sender devolveu. Só colunas novas, opcionais (linhas antigas na fila são
-- remontadas no envio). ADD COLUMN repetido é ignorado pelo aplicador de migrações (idempotente).
ALTER TABLE amigo_email ADD COLUMN modelo_site TEXT;   -- amigo_cobranca, amigo_lembrete_7… (chave do template no site)
ALTER TABLE amigo_email ADD COLUMN variaveis TEXT;     -- JSON com as variáveis mandadas ao Sender
ALTER TABLE amigo_email ADD COLUMN sender_id TEXT;     -- id do e-mail no Sender (emailId), quando enviado
