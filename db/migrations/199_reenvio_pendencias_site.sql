-- UX-47: escritas pendentes de fundo, projeto e arquiteto (divergencia_site 'pendente_*') também saem na rodada de envio ao site
-- (o botão "Enviar as N agora" e o reenvio automático). Esta tabela só guarda a espera entre as tentativas de cada pendência, como a
-- fila de correções de folhas faz: a que falhou espera a próxima tentativa (não martela o site). Nada é apagado de divergencia_site.
CREATE TABLE IF NOT EXISTS reenvio_pendencia_site (
  divergencia_id INTEGER PRIMARY KEY,                    -- divergencia_site.id
  tentativas     INTEGER NOT NULL DEFAULT 0,
  proxima_em     TEXT NOT NULL DEFAULT (datetime('now')),
  ultimo_erro    TEXT,
  atualizado_em  TEXT NOT NULL DEFAULT (datetime('now'))
);
