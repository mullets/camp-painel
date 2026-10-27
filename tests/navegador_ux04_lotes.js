// UX-04 (P1) no navegador de verdade: lotes do mesmo projeto identificados e juntos; a contagem do lote é a das folhas reais.
// Caso do card (F009-P0092): "complemento de 19/10 (19 folhas)" mostrava 12 de 12 e "complemento de 20/10 (7 folhas)" 22 de 22, em duas
// linhas iguais na Home (parecia duplicata); "Rafael publicou F009-P0019" aparecia 2× às 16:16 no Hoje.
// Prova: na Home (Pronto para publicar) UMA linha "2 lotes prontos · complemento de 19/10 · complemento de 20/10" com "Publicar projeto";
// lote a conferir mostra o identificador abaixo do título; em Material novo UMA linha com os 2 lotes e a contagem real de cada um
// (12 e 22 folhas); na página do projeto o lote é "complemento de 19/10" com "12 de 12 conferidas" (sem "(19 folhas)"); no Hoje uma
// publicação pelo Próximo passo (site_publicar + publicacao_guiada) é UMA frase; nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux04.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux04.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8950)
//   CAMP_DB_PATH=/tmp/ux04.db CAMP_BASE=http://127.0.0.1:8950 node tests/navegador_ux04_lotes.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8950', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...args) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...args], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// F072-P0001: lote original publicado + 2 complementos aprovados (12 e 22 folhas reais; o nome antigo dizia 19 e 7).
// F072-P0002: 1 lote parcialmente conferido (2 de 5 a conferir). Os outros lotes da semente saem do caminho (descartados) para a Home caber.
py(`
con.execute("UPDATE lista_processamento SET descartado_em=datetime('now') WHERE projeto_codigo NOT LIKE 'F072-%' AND descartado_em IS NULL")
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F072','Fundo Lotes','FLO',1)")
for n, t in ((1, 'Residência Riviera'), (2, 'Casa do Lago'), (3, 'Escola Nova')):
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES ('F072',?)", (n,))
    con.execute("INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,autorizado_site) VALUES (?,'F072',?,?,1970,1)", ('F072-P%04d' % n, n, t))
con.execute("DELETE FROM item WHERE projeto_codigo LIKE 'F072-%'")
con.execute("DELETE FROM lista_processamento WHERE projeto_codigo LIKE 'F072-%'")
seq = [0]
def lote(P, nome, etapa, aprovado, criado, folhas, pend=0, res=None):
    lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, aprovado_em, aprovado_por, criado_em, atualizado_em, resultado) VALUES (?,?,?,?,?,?,?,?,?)",
                      (nome, P, '/x/' + P, etapa, '2026-10-20 10:00:00' if aprovado else None, 'rafael@camp.arq.br' if aprovado else None, criado, '2026-01-01 10:00:00', res)).lastrowid
    for k in range(folhas):
        seq[0] += 1
        con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, origem, lote_id, revisao, status_site, titulo) VALUES (?,?,'S01',?,'campvision',?,?,'nao_publicado','Planta')",
                    ('%s-1970-S01-D%05d' % (P, seq[0]), P, seq[0], lid, 'pendente' if k < pend else 'conferida'))
lote('F072-P0001', 'Residência Riviera', 'publicado', True, '2026-10-14 13:00:00', 0)
lote('F072-P0001', 'Residência Riviera — complemento de 19/10 (19 folhas)', 'revisao', True, '2026-10-19 13:00:00', 12, 0, '{"complemento": true}')
lote('F072-P0001', 'Residência Riviera — complemento de 20/10 (7 folhas)', 'revisao', True, '2026-10-20 13:00:00', 22, 0, '{"complemento": true}')
lote('F072-P0002', 'Casa do Lago', 'revisao', False, '2026-10-21 13:00:00', 5, 2)
con.execute("DELETE FROM evento WHERE entidade='projeto' AND codigo='F072-P0003'")   # rodar de novo no mesmo banco
for t in ('site_publicar', 'publicacao_guiada'):
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, quando) VALUES ('projeto','F072-P0003',?,'rafael@camp.arq.br',datetime('now','localtime','start of day','+12 hours','utc'))", (t,))
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  const so = t => String(t || '').replace(/\s+/g, ' ').trim();
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => nav('painel'));
    await page.waitForSelector('#ini-tarefas .ini-task', { timeout: 15000 }); await page.waitForTimeout(400);

    // ---- Home: Pronto para publicar ----
    const pub = page.locator('[data-ini-grupo="aprovar_publicar"] .ini-task').filter({ hasText: 'F072-P0001' });
    const nPub = await pub.count(), tPub = nPub ? so(await pub.first().textContent()) : '';
    chk(nPub === 1, `Home: os 2 lotes prontos do mesmo projeto são UMA linha (${nPub})`);
    chk(/2 lotes prontos · complemento de 19\/10 · complemento de 20\/10/.test(tPub) && (await pub.first().locator('.ini-lote').count()) === 1, 'Home: abaixo do título, "2 lotes prontos · complemento de 19/10 · complemento de 20/10": "' + tPub.slice(0, 160) + '"');
    chk(/Publicar projeto|Ver o que falta/.test(tPub), 'Home: o botão age no projeto ("Publicar projeto")');
    chk(!/\(19 folhas\)|\(7 folhas\)/.test(await page.textContent('#ini-tarefas')), 'Home: a contagem velha do nome ("(19 folhas)") não aparece');
    const conf = page.locator('[data-ini-grupo="conferir"] .ini-task').filter({ hasText: 'F072-P0002' });
    const tConf = (await conf.count()) ? so(await conf.first().textContent()) : '';
    chk(/lote de \d\d\/10/.test(tConf) && /2 de 5 folhas a conferir/.test(tConf), 'Home: o lote parcialmente conferido mostra o identificador e "2 de 5 folhas a conferir": "' + tConf.slice(0, 160) + '"');
    const hoje = await page.$$eval('#v-painel .ini-feed li', l => l.map(x => x.textContent.replace(/\s+/g, ' ').trim()).filter(t => /F072-P0003/.test(t)));
    chk(hoje.length === 1 && /publicou/.test(hoje[0]) && !/×/.test(hoje[0]), 'Hoje: uma publicação pelo Próximo passo é UMA frase (antes 2× no mesmo minuto): ' + JSON.stringify(hoje));

    // ---- Material novo ----
    await page.evaluate(() => { FILA_FILTRO = 'todas'; nav('filas'); });
    await page.waitForSelector('#filas-body tr[data-fila-grupo="F072-P0001"]', { timeout: 15000 }); await page.evaluate(() => { FILA_FILTRO = 'todas'; desenharFilas(); }); await page.waitForTimeout(300);
    const linhasA = await page.$$eval('#filas-body tr:not([data-fase="publicado"])', l => l.filter(r => /F072-P0001/.test(r.textContent)).length);   // o lote original, já publicado, é outra linha (No site)
    const g = page.locator('#filas-body tr[data-fila-grupo="F072-P0001"]'), tg = so(await g.textContent());
    chk(linhasA === 1 && /2 lotes prontos/.test(tg), `Material novo: os 2 lotes prontos do projeto são UMA linha "2 lotes prontos" (${linhasA} linha(s))`);
    const lis = await g.locator('.fila-lotes li').allTextContents();
    chk(lis.length === 2 && /complemento de 19\/10 · 12 folhas/.test(lis.join('|')) && /complemento de 20\/10 · 22 folhas/.test(lis.join('|')), 'Material novo: cada lote com o identificador e as folhas REAIS (12 e 22): ' + JSON.stringify(lis));
    chk((await g.locator('[data-fila-ir="publicar"]').count()) === 1 && /Publicar projeto/.test(tg), 'Material novo: um só botão "Publicar projeto"');
    chk(!/\(19 folhas\)|\(7 folhas\)/.test(await page.textContent('#filas-body')), 'Material novo: o "(19 folhas)" do nome não aparece');
    const lb = page.locator('#filas-body tr').filter({ hasText: 'F072-P0002' });
    chk(/lote de \d\d\/10/.test(await lb.locator('.fila-lote').textContent()), 'Material novo: o lote comum mostra "lote de dd/mm" abaixo do título');

    // ---- página do projeto ----
    await page.evaluate(() => nav('projeto/F072-P0001'));
    await page.waitForSelector('#pj-revisao details.rl-lote', { state: 'attached', timeout: 15000 }); await page.waitForTimeout(300);
    const sums = await page.$$eval('#pj-revisao details.rl-lote summary', l => l.map(s => s.textContent.replace(/\s+/g, ' ').trim()));
    chk(sums.some(s => /^complemento de 19\/10 /.test(s) && /12 de 12 conferidas/.test(s)) && sums.some(s => /^complemento de 20\/10 /.test(s) && /22 de 22 conferidas/.test(s)) && !sums.some(s => /folhas\)/.test(s)),
        'projeto: "complemento de 19/10 … 12 de 12 conferidas" (o nome não diz mais outro número): ' + JSON.stringify(sums));
  } catch (e) { chk(false, 'o teste quebrou: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma chamada da API falhou' + (falhas.length ? ': ' + falhas.slice(0, 4).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
