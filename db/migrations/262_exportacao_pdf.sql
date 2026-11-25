-- 262 · CAMP-PROJETO (25/11/2026). Rafael: "exportar um pdf feito em cima dos tifs em alta qualidade, seleciono quais quero e exporto,
-- ou escolho a categoria (desenho, fotos, estrutura) e exporto em pdf no máximo possível em cima do tiff original".
-- Cada PDF montado no painel (em segundo plano) fica registrado aqui: o arquivo mora em <pasta do banco>/exportacoes_pdf/ e é apagado
-- sozinho depois da validade (`exportacao_pdf.validade_dias`). O QNAP nunca é alterado. Idempotente.
CREATE TABLE IF NOT EXISTS exportacao_pdf (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_codigo TEXT NOT NULL,
  arquivo        TEXT NOT NULL,                 -- nome do arquivo dentro de exportacoes_pdf/ (nunca um caminho)
  rotulo         TEXT,                          -- "Estrutura", "3 folhas escolhidas", "Projeto inteiro"
  folhas         TEXT,                          -- JSON: códigos que entraram, na ordem das páginas
  puladas        TEXT,                          -- JSON: [{codigo, motivo}] das que ficaram de fora
  paginas        INTEGER NOT NULL DEFAULT 0,
  bytes          INTEGER NOT NULL DEFAULT 0,
  ator           TEXT,
  criado_em      TEXT NOT NULL DEFAULT (datetime('now')),
  expira_em      TEXT NOT NULL,
  apagado_em     TEXT
);
CREATE INDEX IF NOT EXISTS idx_exportacao_pdf_projeto ON exportacao_pdf (projeto_codigo, criado_em);
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
  ('exportacao_pdf.validade_dias', '7', 'Dias que o PDF exportado de um projeto fica guardado no painel para baixar (depois é apagado sozinho)', 0);
