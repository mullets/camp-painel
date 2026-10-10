-- Preferências por PESSOA (valem em qualquer computador): hoje, qual versão da caixa "Como funciona esta página" cada um já viu (chave 'ajuda.<página>').
CREATE TABLE IF NOT EXISTS usuario_preferencia (
  usuario_id    INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  chave         TEXT NOT NULL,
  valor         TEXT NOT NULL,
  atualizado_em TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (usuario_id, chave)
);
