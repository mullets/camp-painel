-- Aviso por e-mail quando muda a situação de uma inscrição em curso (02/11/2026, Rafael: "quando coloco uma pessoa que se inscreveu no
-- nosso painel, e mudo o status dela, devia mandar um e-mail para ela avisando que status está").
-- Em análise, selecionada e não selecionada avisam a pessoa (dá para desmarcar na hora). Canal: o e-mail transacional do Sender.net
-- abaixo, se preenchido (variáveis {{nome}}, {{curso}}, {{turma}}, {{situacao}}, {{texto}}, {{mensagem}}); senão, o e-mail do site.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
 ('sender.tr10_inscricao_situacao', '', 'ID do e-mail transacional do Sender.net "Situação da inscrição" (TR10): avisa a pessoa quando a inscrição fica em análise, selecionada ou não selecionada. Vazio = sai pelo e-mail do site', 0);
