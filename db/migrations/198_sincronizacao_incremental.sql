-- UX-46: sincronização incremental com o site. Cada rodada guarda se leu o site inteiro ('completa') ou só o que mudou
-- ('incremental', com os itens modificados a partir de `desde`, em UTC). Linhas antigas ficam com NULL = completa (era a única que havia).
-- A incremental não apaga nada do espelho; a completa continua 1×/dia (a automática) e no botão "Sincronizar tudo".
ALTER TABLE sincronizacao ADD COLUMN tipo TEXT;
ALTER TABLE sincronizacao ADD COLUMN desde TEXT;
