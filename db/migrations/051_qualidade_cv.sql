-- Qualidade e custo do CAMP Vision (cartão 152): o que o CV2 leu de cada folha, com que versão, e o que a revisão fez com cada campo.
ALTER TABLE item ADD COLUMN versao_cv2 TEXT;
ALTER TABLE item ADD COLUMN versao_prompt TEXT;
ALTER TABLE item ADD COLUMN modelo_cv TEXT;
ALTER TABLE item ADD COLUMN lido_json TEXT;                  -- {titulo, tipo_documento, folha, escala, ano_folha} como o CV2 leu
ALTER TABLE lista_processamento ADD COLUMN execucao_json TEXT;  -- bloco "execucao" do pacote: versão, modelo, chamadas, tokens, custo_usd, tempo_s
CREATE TABLE IF NOT EXISTS revisao_campo (
  item_codigo TEXT NOT NULL,
  campo       TEXT NOT NULL,
  valor_lido  TEXT,
  valor_final TEXT,
  resultado   TEXT NOT NULL CHECK (resultado IN ('igual','corrigido','preenchido')),
  versao_cv2  TEXT,
  por         TEXT NOT NULL,
  em          TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (item_codigo, campo)
);
