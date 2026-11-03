-- UX-73 (03/11/2026, pedido do Rafa: "Quero que possa publicar como está. Só precisa avisar que falta x ou h coisas serem feitas,
-- como objetivos em uma gamificação"): conferir as folhas e aprovar o lote viram METAS do projeto, não trava de publicação.
-- 0 (padrão) = publica como está: folhas ainda não conferidas também vão ao site (duplicata, retida e folha com problema que bloqueia
-- continuam de fora); a tela mostra o que falta como objetivos. 1 = como antes (UX-62): projeto com folha a conferir não publica.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('publicacao.exige_conferencia', '0', 'Exigir a conferência antes de publicar: 1 = só publica com todas as folhas conferidas e o lote aprovado (folha não conferida fica fora do site); 0 = publica como está (folhas não conferidas também vão ao site) e o que falta aparece como objetivos do projeto', 0);
