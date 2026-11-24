-- 258 · CAMP-FIN (24/11/2026). O livro da conta do Mercado Pago: cada movimento do saldo com o SINAL que o próprio Mercado Pago dá.
-- Rafael: "a direção tem de vir do sistema, de forma confiável, pela documentação do Mercado Pago — não por palpite na descrição".
-- fonte 'relatorio': linha do relatório de liberações (NET_CREDIT_AMOUNT = entrada, NET_DEBIT_AMOUNT = saída; SOURCE_ID = id da operação).
-- fonte 'extrato': linha do Extrato baixado do Mercado Pago (TRANSACTION_NET_AMOUNT positivo = entrada, negativo = saída; REFERENCE_ID).
-- É a palavra final sobre entrada ou saída de um pagamento (vence o site e a heurística; só a escolha manual vence o livro) e dá o valor
-- exato que saiu (−472,24, não −482,24). Movimento de liberação (crédito de uma venda já contada) NUNCA vira receita nova: a receita continua
-- vindo do pagamento; o livro só confirma a direção. Só leitura do que o Mercado Pago mandou: nada aqui apaga ou muda outra tabela.
CREATE TABLE IF NOT EXISTS mp_movimento (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  fonte      TEXT NOT NULL,                 -- relatorio | extrato
  ref        TEXT NOT NULL,                 -- SOURCE_ID / REFERENCE_ID (pode ser alfanumérico: Pix pago com o saldo, ex. B33MMZEM0GVXCMCKZ)
  data       TEXT,
  credito    REAL NOT NULL DEFAULT 0,
  debito     REAL NOT NULL DEFAULT 0,
  descricao  TEXT,                          -- DESCRIPTION do relatório (payment, payout, tax_…) ou a descrição do Extrato
  chave      TEXT NOT NULL UNIQUE,          -- fonte:ref:data:crédito:débito:descrição (importar de novo não repete)
  criado_em  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mp_movimento_ref ON mp_movimento (ref);
