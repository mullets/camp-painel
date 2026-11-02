-- Termo de uso no download do pedido (02/11/2026, Rafael: "na hora que ele receba o email com o link para download, ele tenha que dar OK
-- no termo de uso, e consentimento que não pode ser para uso comercial, e que tem um custo de 150 reais por folha para uso comercial, e
-- que implica leis e etc / dando o aceite aí sim abre o download").
-- O link abre o termo; os arquivos e o .zip só saem depois do aceite. O aceite fica guardado como prova: quando, nome digitado, IP e o
-- TEXTO exato que a pessoa aceitou (o termo pode mudar depois em Configurações; vale o que ela viu).
ALTER TABLE entrega_link ADD COLUMN aceite_em TEXT;
ALTER TABLE entrega_link ADD COLUMN aceite_nome TEXT;
ALTER TABLE entrega_link ADD COLUMN aceite_ip TEXT;
ALTER TABLE entrega_link ADD COLUMN aceite_termo TEXT;

INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('entrega.preco_comercial_folha', '150', 'Valor (R$) por folha para uso comercial, mostrado no termo de uso do download', 0),
 ('entrega.termo', '', 'Texto do termo de uso que a pessoa aceita antes de baixar (vazio = o termo padrão; {preco} vira o valor por folha)', 0);
