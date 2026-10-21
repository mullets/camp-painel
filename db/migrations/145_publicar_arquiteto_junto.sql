-- 21/10/2026 (Rafa: "muito confuso publicar um arquiteto, ou deixar um público"): no site, projeto de fundo cuja página do arquiteto
-- não está publicada NÃO aparece, mesmo publicado no painel. Com 1, "Publicar" do projeto publica também a página do arquiteto
-- (se ela ainda não estiver pública). 0 = como antes (só avisa; a página do arquiteto se publica pelo quadro do fundo).
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('site.publicar_arquiteto_junto', '1', 'Ao publicar um projeto, publicar também a página do arquiteto quando ela ainda não está pública (sem ela o projeto não aparece no site). 1 = sim, 0 = não', 0);
