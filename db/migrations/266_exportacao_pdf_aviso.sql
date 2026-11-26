-- 266 · CAMP-PROJETO (26/11/2026). Rafael (quiz da revisão de usabilidade): "Avisar acima de 2 GB" no PDF montado a partir dos TIFF.
-- Antes de começar, se o tamanho estimado passar deste limite, a tela mostra a estimativa e pede confirmação (continua podendo gerar).
-- Idempotente: INSERT OR IGNORE nunca troca um valor já preenchido.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
  ('exportacao_pdf.aviso_gb', '2', 'Acima deste tamanho estimado (em GB), o PDF dos TIFF de um projeto pede confirmação antes de começar', 0);
