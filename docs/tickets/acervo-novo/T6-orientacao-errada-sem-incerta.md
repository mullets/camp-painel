# CAMP-??? · Orientação errada sem “incerta” só é pega por olho humano

**Repo:** campvision-new, camp-painel  
**Gravidade:** baixa (melhoria)  
**Cenário do E2E:** TESTE-60

## Problema
Com o CV2 errando a orientação de 5 de 8 folhas, só a que veio marcada “incerta” ganhou aviso. As outras 4 chegaram sem aviso nenhum. A correção pelo painel (girar e espelhar) funcionou e a imagem publicada no site saiu certa em todas.

## Sugestão
Na conferência, destacar a prévia de folhas cuja orientação o CV2 mudou (rotação diferente de 0 ou espelhada), mesmo sem “incerta”.

## Teste
`cenario_160` (CV2 forçado a errar 90°, 180°, espelho, 270° e 90° incerta).

## Resolução
Aplicado em `claude/melhorias-acervo-novo` (commit `c2cfb48`): folha que o CV2 girou (90/180/270) sem marcar incerteza ganha o sinal “orientação girada pelo CAMP Vision: confira a prévia”; “Aprovar todas” a deixa para conferir uma a uma (regra do CAMP-094). Atenção: toda folha girada pelo CV2, certa ou errada, agora precisa de conferência individual.
