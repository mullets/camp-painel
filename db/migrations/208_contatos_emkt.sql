-- Lista de quem aceitou receber e-mails da CAMP, para exportar ao Sender.net (03/11/2026, Rafael: "mostrar no painel quem aceitou
-- receber e-mails da CAMP, para exportar a lista para o Sender.net").
-- A lista é montada na hora a partir das inscrições (emkt = 1) e dos cadastros de download com o aceite "consentimento_base".
-- Esta tabela guarda só quem pediu para SAIR (ou foi tirado pela equipe): essa pessoa não volta para a lista exportada,
-- mesmo que se cadastre de novo, até alguém devolvê-la.
CREATE TABLE IF NOT EXISTS contato_descadastro (
  email      TEXT PRIMARY KEY,                -- minúsculas
  quando     TEXT NOT NULL DEFAULT (datetime('now')),
  motivo     TEXT,
  por        TEXT
);
