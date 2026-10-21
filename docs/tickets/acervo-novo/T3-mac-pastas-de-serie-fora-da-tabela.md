# CAMP-??? · Pastas de série do Mac não batem com a tabela de séries

**Repo:** camp-sistema-digitalizacao-mac  
**Gravidade:** média  
**Cenário do E2E:** TESTE-71

## Problema
`PASTAS_PROJETO` e o README do Mac usam `06 - Desenhos e pranchas`, `07 - Documentos textuais`, `08 - Materiais e especificações`, `09 - Publicações`. A tabela do CV2 e do painel é `01 Desenhos e pranchas … 07 Publicações, 08 Redesenhos, 99 Não identificado`.

Medido com 1 scan por pasta:

| Pasta do Mac | Código no nome do arquivo (Mac) | Série no painel (CV2) |
|---|---|---|
| `09 - Publicações` | S09 | S07 |
| `08 - Materiais e especificações` | S08 | **S06** |
| `07 - Documentos textuais` | S07 | **S02** |
| `06 - Desenhos e pranchas` | S06 | S01 |

Nenhuma pasta padrão do Mac chega em S08. O Mac nomeia o arquivo pelo número da pasta e o CV2 renomeia depois por nome: o nome no QNAP não é o do acervo.

## Correção da premissa
As pastas `06`–`09` do Mac são as pastas de **fundo** (a mesma lista do CV2, `estrutura.py`), não as séries do projeto; o Mac só as usaria como material se configurado à mão. O problema real: o Mac nomeia o arquivo pelo **número** da pasta, e o CV2 decide a série pelo **nome**; onde os números diferem da tabela de séries o código muda no acervo.

## Esperado
Nomes e numeração das pastas iguais à tabela de séries, e o código no nome do arquivo igual ao do acervo. Compatível com a versão antiga do CV2 (campo novo opcional, sem renomear S07).

## Teste
`cenario_171` (`e2e/cenarios_acervo_novo.py`) falha hoje. Teste novo em `tests/test_nucleo.py`: cada pasta de material vira o código de série da tabela.

## Resolução
Aplicado em `claude/melhorias-mac-series` (commit `04c660c`): `codigo_serie` usa a tabela de séries pelo nome da pasta (`09 - Publicações` → S07, `08 - Materiais e especificações` → S06…); nome fora da tabela mantém o número. Testes novos falham sem a correção; `cenario_171` passa (no `main` falha: S06→S01, S09→S07, S08→S06).
