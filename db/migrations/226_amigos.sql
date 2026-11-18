-- Amigos da CAMP no painel (18/11/2026, Rafael: "Amigos da CAMP, podemos pôr no painel? Aí teremos um valor x por ano já programado,
-- e conseguiria controlar quem já pagou ou não, alterar status etc. Disparar e-mail etc.").
-- O site continua com o formulário e o Mercado Pago; o painel busca os apoios (Amigos, Adote um projeto, Adote um arquiteto) pela rota
-- GET /wp-json/camp/v1/painel/apoios (contrato 1.11, docs/CONTRATO_UNICO.md §6) e devolve as mudanças por POST /painel/apoios/{id}.
-- Ver backend/app/amigos.py. Tem dados pessoais: só admin e master veem. Lembretes automáticos nascem DESLIGADOS. Idempotente.
CREATE TABLE IF NOT EXISTS amigo (
  id               INTEGER PRIMARY KEY,
  site_id          INTEGER UNIQUE,                  -- ID do registro no site (camp_apoio); NULL = registrado só no painel
  tipo             TEXT NOT NULL DEFAULT 'amigo',   -- amigo | projeto | arquiteto
  protocolo        TEXT,
  categoria        TEXT,                            -- estudante | amigo | guardiao | patrono (Amigos)
  modalidade       TEXT,                            -- anual | mensal
  perfil           TEXT,
  nome             TEXT NOT NULL DEFAULT '',
  empresa          TEXT,
  cargo            TEXT,
  email            TEXT,
  telefone         TEXT,
  vinculo          TEXT,
  nome_publico     INTEGER NOT NULL DEFAULT 0,
  emkt             INTEGER NOT NULL DEFAULT 0,
  faixa            TEXT,
  area             TEXT,
  mensagem         TEXT,
  origem_pagina    TEXT,
  status_pedido    TEXT NOT NULL DEFAULT 'novo',    -- situação do pedido no site: novo | em_contato | proposta | fechado | arquivado
  notas            TEXT,
  situacao         TEXT,                            -- Amigos: pago | pendente | vencido | recusado | isento | cancelado (adoções: NULL)
  situacao_site    TEXT,                            -- valor cru do site (_camp_mp_situacao)
  valor_cobrado    REAL,                            -- valor da categoria no site no momento da adesão
  inicio           TEXT,
  validade         TEXT,                            -- AAAA-MM-DD (dia de São Paulo) em que deixa de valer
  codigo           TEXT,                            -- código do Amigo (o site gera)
  fundador         INTEGER,                         -- número de Amigo Fundador (o site gera, 1 a 100)
  renova           INTEGER NOT NULL DEFAULT 0,
  pago_em          TEXT,                            -- data do último pagamento aprovado
  ultimo_valor     REAL,
  origem_pagamento TEXT,                            -- site (Mercado Pago) | manual (registrado no painel)
  origem           TEXT NOT NULL DEFAULT 'site',    -- site | painel
  criado_no_site   TEXT,
  alterado_no_site TEXT,
  importado_em     TEXT NOT NULL DEFAULT (datetime('now')),
  atualizado_em    TEXT,
  cobranca_em      TEXT,                            -- última cobrança enviada pelo painel (datetime UTC)
  cobranca_tipo    TEXT,                            -- mp (link do Mercado Pago criado pelo site) | manual (instruções de Pix do painel)
  cobranca_link    TEXT,
  cobranca_vence   TEXT,                            -- AAAA-MM-DD: data limite escrita na cobrança
  pendente_site    TEXT,                            -- JSON com o que ainda falta mandar ao site (POST /painel/apoios/{id})
  erro_site        TEXT,
  anonimizado      INTEGER NOT NULL DEFAULT 0       -- LGPD: dados pessoais apagados no painel (a coleta não os traz de volta)
);
CREATE INDEX IF NOT EXISTS idx_amigo_tipo_situacao ON amigo (tipo, situacao);
CREATE INDEX IF NOT EXISTS idx_amigo_email ON amigo (email);
CREATE INDEX IF NOT EXISTS idx_amigo_validade ON amigo (validade);
CREATE TABLE IF NOT EXISTS amigo_pagamento (
  id         INTEGER PRIMARY KEY,
  amigo_id   INTEGER NOT NULL,
  chave      TEXT NOT NULL UNIQUE,                  -- mp-<id do pagamento> | painel-<aleatório> (o mesmo vai ao site)
  data       TEXT NOT NULL,                         -- AAAA-MM-DD
  valor      REAL NOT NULL DEFAULT 0,
  meio       TEXT,                                  -- pix | transferencia | dinheiro | cartao | outro (ou o do Mercado Pago)
  nota       TEXT,
  origem     TEXT NOT NULL DEFAULT 'manual',        -- manual | mp
  status     TEXT NOT NULL DEFAULT 'approved',      -- approved conta na receita; o resto (rejected, refunded…) não
  criado_por TEXT,
  criado_em  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_amigo_pagamento_amigo ON amigo_pagamento (amigo_id, data);
CREATE TABLE IF NOT EXISTS amigo_email (
  id          INTEGER PRIMARY KEY,
  amigo_id    INTEGER NOT NULL,
  modelo      TEXT NOT NULL,                        -- boas_vindas | lembrete_renovacao | cobranca_pendente | recibo | livre
  assunto     TEXT,
  corpo       TEXT,
  para        TEXT,
  situacao    TEXT NOT NULL DEFAULT 'na_fila',      -- na_fila | enviado | falhou
  canal       TEXT,                                 -- smtp | site
  erro        TEXT,
  chave       TEXT,                                 -- lembrete automático: modelo:amigo:validade:marco (nunca repete)
  criado_por  TEXT,
  criado_em   TEXT NOT NULL DEFAULT (datetime('now')),
  enviado_em  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_amigo_email_chave ON amigo_email (chave) WHERE chave IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_amigo_email_fila ON amigo_email (situacao, id);
CREATE TABLE IF NOT EXISTS amigo_preco (
  ano       INTEGER NOT NULL,
  categoria TEXT NOT NULL,
  nome      TEXT NOT NULL,
  anual     REAL NOT NULL DEFAULT 0,
  mensal    REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (ano, categoria)
);
-- Valores propostos para 2027 (os mesmos do site, class-apoio.php). Outros anos: "Adicionar ano" na tela copia o ano anterior.
INSERT OR IGNORE INTO amigo_preco (ano, categoria, nome, anual, mensal) VALUES
 (2027, 'estudante', 'Estudante / Professor', 200, 20),
 (2027, 'amigo',     'Amigo',                 450, 45),
 (2027, 'guardiao',  'Guardião',              1500, 150),
 (2027, 'patrono',   'Patrono',               6000, 600);
CREATE TABLE IF NOT EXISTS amigo_coleta (
  id          INTEGER PRIMARY KEY,
  quando      TEXT NOT NULL DEFAULT (datetime('now')),
  lidos       INTEGER NOT NULL DEFAULT 0,
  novos       INTEGER NOT NULL DEFAULT 0,
  enviados    INTEGER NOT NULL DEFAULT 0,
  erro        TEXT
);
CREATE TABLE IF NOT EXISTS amigo_estado (            -- estado interno da coleta (cursor "desde", valores vindos do site)
  chave TEXT PRIMARY KEY,
  valor TEXT
);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('amigos.coleta_min',      '10',        'Amigos da CAMP: minutos entre as buscas dos apoios no site (e o envio das mudanças); 0 desliga', 0),
 ('amigos.validade_regra',  '12_meses',  'Amigos da CAMP: validade de um pagamento registrado no painel. 12_meses = 12 meses a partir do pagamento (ou do fim da validade atual, se ainda vale); fim_do_ano = até 31/12', 0),
 ('amigos.lembretes_auto',  'desligado', 'Amigos da CAMP: lembretes automáticos por e-mail (renovação antes de vencer e aviso de vencido). desligado | simular (mostra quem receberia, não envia) | ligado', 0),
 ('amigos.lembrete_dias',   '30,7',      'Amigos da CAMP: com quantos dias antes de vencer vai o lembrete de renovação (separados por vírgula)', 0),
 ('amigos.responder_para',  '',          'Amigos da CAMP: endereço de resposta dos e-mails aos Amigos (vazio = o remetente)', 0),
 ('amigos.link_pagina',     'https://camp.arq.br/amigos/', 'Amigos da CAMP: endereço da página dos Amigos no site, usado nos e-mails', 0),
 ('amigos.cobranca_pix',    '',          'Amigos da CAMP: instruções de pagamento manual (chave Pix, banco…) usadas na cobrança quando o Mercado Pago do site está desligado. Vazio = sem cobrança manual', 0),
 ('amigos.cobranca_prazo_dias', '7',     'Amigos da CAMP: prazo para pagar, em dias, escrito na cobrança', 0),
 ('amigos.cobranca_intervalo_dias', '3', 'Amigos da CAMP: a mesma pessoa não recebe outra cobrança antes de tantos dias sem uma confirmação explícita', 0);
