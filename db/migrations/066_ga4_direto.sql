-- Google Analytics 4 direto (conta de serviço), sem depender da conexão do Site Kit. Ver backend/app/ga4_direto.py.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('ga4.propriedade',   '', 'Número da propriedade GA4 (Administrador → Detalhes da propriedade; ex.: 467114271). Com a conta de serviço, o painel lê o Analytics direto, sem o Site Kit', 0),
 ('ga4.conta_servico', '', 'Chave JSON da conta de serviço do Google (cole o arquivo inteiro). No GA4, adicione o e-mail dela como Leitor na propriedade', 1);
