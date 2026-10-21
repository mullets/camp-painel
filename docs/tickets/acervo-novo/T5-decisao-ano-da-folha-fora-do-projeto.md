# CAMP-??? · DECISÃO: ano da folha fora do ano do projeto passa sem aviso

**Repo:** camp-painel  
**Gravidade:** baixa  
**Cenário do E2E:** TESTE-60

## Problema
Folha lida com ano 1917 num projeto de 1971 (código `-1971-`) foi conferida e publicada com `Ano = 1917` no site, sem alerta.

## Decidir
Avisar na conferência quando o ano da folha foge do ano do projeto por mais de N anos (qual N?) e se isso bloqueia ou só avisa.

## Teste quando decidido
`cenario_160`, folha D4.
