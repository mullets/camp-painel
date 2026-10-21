-- 21/10/2026 (Rafa: "quem usa esse painel não usa o WordPress… preciso que ao alterar aí, já altere no WordPress automaticamente"):
-- correção numa folha já no site (título, tipo, nº, escala, ano, imagem girada/espelhada/recortada) vai sozinha ao site logo depois de salvar.
-- 0 = como antes (fica em "alteradas depois de publicar" até alguém clicar "Enviar ao site").
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('site.enviar_correcoes_sozinho', '1', 'Correção numa folha já publicada vai sozinha ao site logo depois de salvar. 1 = sim, 0 = não (fica na lista para enviar)', 0);
