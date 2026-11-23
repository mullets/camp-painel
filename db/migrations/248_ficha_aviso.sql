-- 248 · CAMP-BLOQUEIO, 2ª parte (23/11/2026). Rafael: "só aviso". A ficha de documentação, a capa e os outros motivos que o CAMP Vision
-- escreve na folha nunca seguraram a publicação (publicacao.ELEGIVEL_LOCAL): viram AVISO. Os textos padrão dos modelos de decisão da
-- migração 246 diziam "bloqueio"; passam a dizer "aviso". Só troca o texto que ainda é o padrão de 246 (quem editou em Problemas › Modelos
-- de decisão fica com o seu). Idempotente: o WHERE exige o texto antigo exato; rodar de novo não acha nada.
UPDATE erro_modelo SET texto='Conferido na folha: é prancha do projeto, não ficha de documentação. O aviso do CAMP Vision saiu.'
 WHERE categoria='outro' AND titulo='É prancha do projeto'
   AND texto='Conferido na folha: é prancha do projeto, não ficha de documentação. O bloqueio do CAMP Vision saiu.';
UPDATE erro_modelo SET texto='Conferido na folha: o aviso do CAMP Vision não vale mais. A folha pode ir ao site.'
 WHERE categoria='outro' AND titulo='Pode ir ao site'
   AND texto='Conferido na folha: o motivo do bloqueio do CAMP Vision não vale mais. A folha pode ir ao site.';
UPDATE erro_modelo SET texto='Conferido na folha: o aviso do CAMP Vision está certo. A folha fica no painel e não vai ao site.'
 WHERE categoria='outro' AND titulo='Fica fora do site'
   AND texto='Conferido na folha: o bloqueio do CAMP Vision está certo. A folha fica no painel e não vai ao site.';
