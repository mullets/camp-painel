-- E-mails transacionais do Sender.net (01/11/2026). A CAMP criou 6 e-mails transacionais no Sender.net (domínio camp.arq.br
-- verificado). Os IDs não são segredo. A configuração fica aqui (Configurações → E-mail e avisos) e o painel a envia ao site
-- (POST /wp-json/camp/v1/painel/sender, contrato 1.5, docs/CONTRATO_UNICO.md §6). O TR09 é o e-mail da entrega em alta resolução
-- que o próprio painel manda (entrega.py).
-- Idempotente: INSERT OR IGNORE nunca troca um valor já preenchido; o UPDATE só preenche sender.campanha_entrega se estiver vazio.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('sender.tr04_solicitacao_recebida', 'egx4Z6', 'ID do e-mail transacional do Sender.net "Pedido recebido" (TR04), que o site manda a quem faz um pedido', 0),
 ('sender.tr05_pdf_disponivel',       'ejv4Z5', 'ID do e-mail transacional do Sender.net "PDF disponível" (TR05), que o site manda com o link do PDF do projeto', 0),
 ('sender.tr06_visita_solicitada',    'bkw48X', 'ID do e-mail transacional do Sender.net "Visita solicitada" (TR06), que o site manda a quem pede uma visita', 0),
 ('sender.tr07_visita_confirmada',    'elv4x6', 'ID do e-mail transacional do Sender.net "Visita confirmada" (TR07), com data e horário da visita', 0),
 ('sender.tr08_inscricao_recebida',   'bm24O0', 'ID do e-mail transacional do Sender.net "Inscrição recebida" (TR08), que o site manda a quem se inscreve num curso', 0),
 ('sender.tr09_material_download',    'bov4VK', 'ID do e-mail transacional do Sender.net "Material para download" (TR09), com o link do material com prazo', 0),
 ('sender.site_ativo',                '0',      'O site manda os e-mails dele pelo Sender.net? 1 = sim; 0 = não, o site continua com o e-mail de sempre (vale depois de enviar a configuração ao site)', 0);

UPDATE configuracao SET valor = 'bov4VK'
 WHERE chave = 'sender.campanha_entrega' AND (valor IS NULL OR valor = '');
