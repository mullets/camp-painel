-- 264 · CAMP-ESTANTE (25/11/2026). Rafael: "TB001-01" (nome dos tubos). TB + grupo de tubos (3 dígitos, sequência geral) + "-" + parte
-- (2 dígitos): o mesmo lote em vários tubos continua o grupo (TB001-01, TB001-02…); outro projeto abre o grupo seguinte (TB002-01).
-- O padrão fica configurável. Idempotente; não renomeia nada (os tubos antigos TB-<projeto>.<n> só mudam pela simulação + aplicar).
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
  ('estante.padrao_tubo', 'TB{grupo:03d}-{parte:02d}', 'Nome dos tubos novos: {grupo} = número do grupo de tubos (sequência geral), {parte} = parte dentro do grupo. Ex.: TB001-01, TB001-02.', 0);
