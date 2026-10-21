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
