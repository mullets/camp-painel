-- Entrega de pedido de alta resolução por e-mail (01/11/2026, Rafael: "quando recebemos uma solicitação de envio de material em alta,
-- poder aprovar pelo sistema e já enviar o que ele pediu pelo próprio sistema").
-- O painel aprova o pedido, cria um link de download com prazo e manda o e-mail à pessoa (Sender.net com o layout pronto, ou o e-mail
-- do site). Os arquivos NÃO vão anexados: o link serve os arquivos do QNAP pelo próprio painel (rota pública /entrega/<token>).
-- O token só existe no e-mail: aqui fica o hash (sha256). Nada é apagado do QNAP; o JPG reduzido (3000 px) é gerado na pasta do painel.
CREATE TABLE IF NOT EXISTS entrega_link (
  id                 INTEGER PRIMARY KEY,
  solicitacao_id     INTEGER NOT NULL,
  token_hash         TEXT NOT NULL UNIQUE,
  arquivos           TEXT NOT NULL,                       -- JSON [{n, codigo, titulo, formato, nome, caminho, tamanho}]
  para               TEXT,
  canal              TEXT,                                -- sender | site
  teste              INTEGER NOT NULL DEFAULT 0,          -- 1 = envio de teste para quem aprovou (não marca o pedido)
  criado_por         TEXT,
  criado_em          TEXT NOT NULL DEFAULT (datetime('now')),
  expira_em          TEXT NOT NULL,
  revogado_em        TEXT,
  downloads          INTEGER NOT NULL DEFAULT 0,
  ultimo_download_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_entrega_link_solicitacao ON entrega_link(solicitacao_id);

INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('entrega.canal',           'sender', 'Por onde sai o e-mail de entrega dos pedidos: sender (Sender.net, com o layout pronto) ou site (o e-mail do site)', 0),
 ('entrega.validade_dias',   '14',     'Por quantos dias o link de download do pedido funciona', 0),
 ('entrega.responder_para',  '',       'Quem recebe as respostas do e-mail de entrega (vazio = o e-mail de pedidos do site)', 0),
 ('sender.token',            '',       'Token da API do Sender.net (no Sender: Settings → API access tokens)', 1),
 ('sender.campanha_entrega', '',       'ID do e-mail transacional do Sender.net usado na entrega (o layout pronto; no Sender: Transactional → o e-mail → API)', 0);
