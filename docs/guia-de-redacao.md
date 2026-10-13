# Guia de redação do painel

Vale para todo texto novo na tela (botões, avisos, caixas "Como funciona", erros). Base: Nielsen, heurísticas 2 e 6, e a escrita simples do GOV.UK.
As palavras do acervo estão explicadas no glossário (`#glossario`, constante `GLOSSARIO` em `frontend/index.html`) e em `docs/vocabulario.md`.

1. **Fale com a pessoa:** "Você pode…", "Falta você…". Nada de "o usuário".
2. **Botão = verbo + objeto:** "Importar folhas", "Publicar projeto", "Imprimir etiqueta". Nunca "OK", "Confirmar" ou "Executar" soltos.
3. **Frases de até 20 palavras.** Um assunto por frase.
4. **Diga o efeito, não o mecanismo:** "Fica visível para qualquer pessoa no site", e não "status publish no Tainacan".
5. **Mensagem de erro = o que aconteceu + por quê + o que fazer + botão para fazer.** Ex.: "Não deu para publicar: 14 folhas ainda não foram conferidas. [Conferir agora]".
6. **Sem "(s)":** use o plural certo. Sem nome técnico (snake_case, ids, URLs) na tela.
7. **Números com contexto:** "14 de 20 folhas conferidas", e não só "14".
8. **Datas em dd/mm/aaaa hh:mm**, horário de São Paulo; "há 5 min" quando for de hoje.
9. **Mesma coisa, mesmo nome em todo lugar** (os termos do glossário). Se trocar, troque em todas as telas, nos títulos, na trilha e nas caixas de ajuda.

O `scripts/check_ui.py` reprova parte disso sozinho (vocabulário proibido, códigos internos visíveis); o resto é revisão.
