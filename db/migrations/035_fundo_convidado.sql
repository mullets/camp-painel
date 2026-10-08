-- Decisão 08/10/2026: fundo F000 · CNV · Convidado — material de TERCEIROS que a CAMP
-- digitaliza (empréstimo, pesquisador, família...). Cada pessoa/origem vira um projeto P
-- dentro do F000. Nada dele vai ao site. v_proximo_fundo usa MAX()+1, então o F000
-- não muda o próximo código de fundo.
INSERT OR IGNORE INTO fundo (codigo, sigla, titulo, nivel_descricao, procedencia, condicoes_acesso,
                             condicoes_reproducao, credito_padrao)
VALUES ('F000', 'CNV', 'Convidado', 'coleção',
        'Material de terceiros trazido para digitalização na CAMP; não pertence ao acervo da CAMP.',
        'Uso interno. O material e os arquivos digitais pertencem a quem trouxe.',
        'Reprodução só com autorização de quem trouxe o material.',
        'Acervo de terceiros, digitalizado na CAMP - Casa da Arquitetura Moderna Paulista');

-- Trava no banco: nem o fundo nem os projetos do F000 podem ser marcados para o site
CREATE TRIGGER IF NOT EXISTS trg_f000_fundo_fora_do_site
BEFORE UPDATE OF status_site ON fundo
WHEN NEW.codigo = 'F000' AND NEW.status_site <> 'nao_publicado'
BEGIN
  SELECT RAISE(ABORT, 'F000 Convidado e material de terceiros: nao vai ao site');
END;

CREATE TRIGGER IF NOT EXISTS trg_f000_projeto_insert_fora_do_site
BEFORE INSERT ON projeto
WHEN NEW.fundo_codigo = 'F000' AND (NEW.autorizado_site <> 0 OR NEW.status_site NOT IN ('nao_publicado', 'bloqueado'))
BEGIN
  SELECT RAISE(ABORT, 'F000 Convidado e material de terceiros: nao vai ao site');
END;

CREATE TRIGGER IF NOT EXISTS trg_f000_projeto_update_fora_do_site
BEFORE UPDATE OF autorizado_site, status_site ON projeto
WHEN NEW.fundo_codigo = 'F000' AND (NEW.autorizado_site <> 0 OR NEW.status_site NOT IN ('nao_publicado', 'bloqueado'))
BEGIN
  SELECT RAISE(ABORT, 'F000 Convidado e material de terceiros: nao vai ao site');
END;
