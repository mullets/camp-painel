# CAMP-??? · Pendência “pendente_criar_no_site” não fecha quando a criação dá certo depois

**Repo:** camp-painel  
**Gravidade:** média  
**Cenário do E2E:** TESTE-70

## Problema
Cadastrar um fundo quando a sincronização do site ainda não trouxe a taxonomia “Fundos” devolve 200 com `site.erro = "Taxonomia 'Fundos' não encontrada no espelho; rode a sincronização"` e abre a pendência `pendente_criar_no_site`.

Depois da sincronização, “criar no site” e “enviar ao site” funcionam (`site-status`: `no_site=true`, sem divergência), mas a pendência **continua aberta** (`divergencia_site.resolvida=0`). A tela segue dizendo “pendente” com o fundo já no ar.

## Esperado
Sucesso de `criar_fundo_no_site` (e do equivalente de projeto e item, `publicador.py:325` e `:864`, não testados) resolve a pendência anterior do mesmo código e campo.

## Como reproduzir
1. Criar fundo sem a taxonomia “Fundos” no espelho → pendência aberta.
2. Semear a taxonomia (ou sincronizar) → `POST /api/fundos/{F}/criar-no-site` → 200.
3. `divergencia_site` do fundo continua com `pendente_criar_no_site` e `resolvida=0`.

## Teste
Modo rápido novo: passos acima; deve falhar sem a correção. Harness: `cenario_170` (`e2e/cenarios_acervo_novo.py`) falha hoje só nesta checagem.

## Também
Ao cadastrar o fundo com o site sem sincronizar, a pessoa recebe só um texto de erro dentro de um 200. Avaliar aviso claro na tela e nova tentativa automática depois da sincronização.
