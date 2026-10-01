-- Conteúdo editorial completo da página pública de cada fundo/arquiteto.
-- Campos vazios são omitidos da saída pública.
CREATE TABLE IF NOT EXISTS fundo_perfil_publico (
  fundo_codigo TEXT PRIMARY KEY REFERENCES fundo(codigo) ON DELETE CASCADE,
  slug_publico TEXT,
  nome_publico TEXT,
  nomes_alternativos TEXT,
  imagem_url TEXT,
  texto_disponibilidade TEXT,
  periodo_atuacao TEXT,
  biografia TEXT,
  socios_colaboradores TEXT,
  obras_principais TEXT,
  bibliografia TEXT,
  fontes_biografia TEXT,
  descricao_acervo TEXT,
  autoria_procedencia TEXT,
  atualizado_por TEXT,
  atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
