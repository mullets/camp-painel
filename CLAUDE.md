# CLAUDE.md — camp-painel

Painel de administração dos acervos da CAMP (FastAPI + SQLite + `frontend/index.html` de arquivo único, sem build). É o **núcleo**: fonte da verdade dos códigos
(F0xx, P000x, folhas) e dono dos contratos. Leia antes de mexer: `docs/CONTRATO_UNICO.md` (contratos entre os 5 sistemas), `docs/padroes.md` (decisões que não se refazem),
`docs/campvision.md` (CV2 ↔ painel), `docs/COMO_FUNCIONA.md` (guia completo).

## Os 5 repositórios
`camp-painel` (este) · `campvision-new` (CV2; o `campvision2` é o app antigo) · `camp-sistema-digitalizacao` (Windows) · `camp-sistema-digitalizacao-mac` · `camp-wordpress` (site).
Quem produz/consome o quê (ex.: `status.json`) está em `docs/CONTRATO_UNICO.md` §2. Board oficial para tickets transversais: **"Camp todos sistemas"** (Trello).

## Contratos que este repo produz e consome
- Produz: rotas das estações (`/api/estacoes/*`, `/api/campvision/aviso`, `/api/campvision/reidentificar`), mover/mesclar/recodificar, redirecionamentos para o site.
- Consome: arquivos do CV2 na pasta final (`status.json`, `info_projeto.json`, `pacote_tainacan.json`, `catalogacao/erros.json`, `_campvision/`), rotas `/wp-json/camp/v1/…` do site.
- Contrato CV2: fonte em `campvision-new/docs/contrato-painel.md`; cópia literal em `tests/contrato/` (carimbo em `ORIGEM.txt`); versão em `backend/app/contrato.py`.
- **Mudou campo/rota? Suba a versão do contrato e atualize os exemplos NO MESMO COMMIT. Todo campo novo é OPCIONAL** (o outro lado pode estar na versão antiga).

## Como testar
```
python tests/teste_backend.py --rapido      # o mesmo que o atualizar.sh roda; modos novos entram em MODOS_RAPIDOS
python tests/teste_backend.py               # pacote completo (~6 min)
python scripts/check_ui.py                  # estrutura/vocabulário da UI
bash tests/rodar_auditoria.sh [novas|xss]   # telas, funções, atalhos, XSS (mais de 5 min: por etapas)
bash tests/rodar_um.sh tests/ARQUIVO.js     # um teste de navegador
bash tests/rodar_fluxo_real.sh             # fluxo real de ponta a ponta: estação → CAMP Vision → conferir → aprovar → publicar (site falso), com prints
```
Dependências: `pip install -r backend/requirements.txt`. Um modo de teste isolado: `CAMP_DB_PATH=/tmp/x.db PYTHONPATH=backend python tests/teste_backend.py --filho <modo>`.
Todo ticket tem teste; **teste novo deve FALHAR sem a correção** (prove). Não afirmar o que não foi testado.

## Fluxo de trabalho
1. Trabalhe SEMPRE num branch (`claude/<nome>`); commit com o id do ticket no título (`CAMP-0xx: …`), um commit por ticket, explicando problema, causa e o que foi provado.
2. Rode a suíte (rápida + `check_ui`) antes de cada push; `git push -u origin <branch>`.
3. Quem abre PR e faz merge é o coordenador/Rafa. Trello: só atualize quando mandarem.
4. Migração nova = `db/migrations/NNN_nome.sql` (próximo número, idempotente, `INSERT OR IGNORE` para configuração). Config sensível: `sensivel=1`.
5. Operação destrutiva ou que depende de dado real entra **atrás de flag desligada por padrão ou em modo `simular`**, e compatível com o outro lado.

## Armadilhas de auto-deploy
- O servidor do painel roda `./atualizar.sh`: só aceita a branch `main`, baixa `origin/main`, testa a versão nova (`--rapido`) numa cópia, faz backup do banco, aplica migrações no restart. **Tudo que chega ao `main` vai para produção.**
- Os outros lados se atualizam sozinhos a partir do `main`: estações a cada ~5 min, CV2 a cada ~1 h, site no push. Um campo/rota que quebre a versão antiga derruba a operação real.
- Por isso: ordem de deploy importa (painel antes dos clientes novos; cliente antigo nunca pode ficar sem rota). Migração roda na base REAL: nada de `DROP`/`UPDATE` sem `WHERE` e sem teste com banco antigo (`antigo` na suíte).
- Rota nova usada pelas estações tem de funcionar na LAN sem token E com `X-Camp-Token` (ver `rede.py`).
- Nunca varrer o QNAP dentro de uma requisição (SMB lento trava o painel): use o coletor em segundo plano.

## NUNCA
- Commitar/pushar no `main`, abrir PR por conta própria, rodar `atualizar.sh`, reiniciar serviço ou tocar na base/QNAP reais.
- Usar script de commit compartilhado; confira `git rev-parse --show-toplevel` e use `git -C <repo>`.
- Reusar ou mudar código de fundo/projeto (imutáveis; recodificar cria redirecionamento 301). Código vem da tabela de autoridade, não do nome da pasta.
- Apagar dados ou legado em uso; reidentificar/mesclar de verdade sem simular antes; publicar/despublicar em produção em teste.
- Inventar biografia/fonte; renomear o que está decidido em `docs/padroes.md` sem pedido do Rafael; gravar token/senha em log, commit ou resposta.
- Colocar dados de pessoas dentro de `onclick` (só `data-*`); escrever texto de interface fora do `docs/vocabulario.md`.
- Escrever no Trello sem pedido; decidir o que é do Rafa (CAMP-045: ex.: renomear S07, Praça × Parque).
