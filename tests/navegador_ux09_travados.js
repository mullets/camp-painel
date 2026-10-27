// UX-09 (P1) no navegador de verdade: estados travados e idade do lote.
// Caso do card: F009-P0092 "sendo lido pelo CAMP Vision há 177 h" (estado impossível) e lotes "esperando a revisão há 392 h" sem idade na Home.
// Prova: na Home, "Leitura interrompida: …" com "Ler de novo" (1 clique: o botão apaga enquanto pede, o pedido é o de releitura que já existe
// e depois a linha diz "releitura pedida"); "parado há 16 dias" na linha do lote; "mais parado primeiro" sobe o mais antigo; em Material novo,
// a etiqueta "leitura interrompida" com "Ler de novo", a coluna "Parado há" pela etapa e o clique no cabeçalho ordena pelo mais parado;
// nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux09.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux09.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8950)
//   CAMP_DB_PATH=/tmp/ux09.db CAMP_BASE=http://127.0.0.1:8950 node tests/navegador_ux09_travados.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8950', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...args) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...args], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// F073-P0001 "sendo lido" há 177 h sem sinal; F073-P0002 a conferir, grande e novo; F073-P0003 a conferir, pequeno e parado há 16 dias.
// Os outros lotes da semente saem do caminho (descartados) para a Home caber; nenhum heartbeat de "processando".
py(`
con.execute("UPDATE lista_processamento SET descartado_em=datetime('now') WHERE projeto_codigo NOT LIKE 'F073-%' AND descartado_em IS NULL")
con.execute("DELETE FROM estacao_heartbeat WHERE estado='processando'")
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F073','Fundo Travados','FTR',1)")
for n, t in ((1, 'Edifício Lido'), (2, 'Casa Grande Nova'), (3, 'Casa Pequena Antiga')):
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES ('F073',?)", (n,))
    con.execute("INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,ano) VALUES (?,'F073',?,?,1970)", ('F073-P%04d' % n, n, t))
con.execute("DELETE FROM item WHERE projeto_codigo LIKE 'F073-%'")
con.execute("DELETE FROM pedido_releitura WHERE projeto_codigo LIKE 'F073-%'")
con.execute("DELETE FROM lista_processamento WHERE projeto_codigo LIKE 'F073-%'")
seq = [0]
def lote(n, etapa, horas, folhas=0):
    P = 'F073-P%04d' % n
    lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, criado_em) VALUES (?,?,?,?,datetime('now',?))", (P, P, '/x/' + P, etapa, '-%d hours' % horas)).lastrowid
    con.execute("UPDATE lista_processamento SET etapa_desde=datetime('now',?), atualizado_em=datetime('now') WHERE id=?", ('-%d hours' % horas, lid))
    for k in range(folhas):
        seq[0] += 1
        con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, origem, lote_id, revisao, status_site, titulo) VALUES (?,?,'S01',?,'campvision',?,'pendente','nao_publicado','Planta')",
                    ('%s-1970-S01-D%05d' % (P, seq[0]), P, seq[0], lid))
lote(1, 'processando', 177)
lote(2, 'revisao', 2, 9)
lote(3, 'revisao', 16 * 24, 2)
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
  let posts = 0;
  page.on('request', r => { if (r.method() === 'POST' && /\/api\/projetos\/F073-P0001\/releitura$/.test(r.url())) posts++; });
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'operador@camp.arq.br'); await page.fill('#lg-senha', 'senha-operador-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => { try { localStorage.removeItem('camp.ini.ordem'); localStorage.removeItem('camp.fila.ordem'); } catch (_) {} nav('painel'); });
    await page.waitForSelector('#ini-tarefas .ini-task', { timeout: 15000 }); await page.waitForTimeout(400);

    // ---- Home ----
    const li = page.locator('#ini-tarefas .ini-task').filter({ hasText: 'Leitura interrompida: Edifício Lido' });
    const tli = (await li.count()) ? so(await li.first().textContent()) : '';
    chk(/não dá sinal deste lote há mais de 2 h/.test(tli) && /parado há 7 dias/.test(tli), 'Home: "Leitura interrompida: Edifício Lido" com o porquê e "parado há 7 dias": "' + tli.slice(0, 200) + '"');
    const bt = li.first().locator('[data-ini-acao]');
    chk((await bt.count()) === 1 && /Ler de novo/.test(await bt.textContent()), 'Home: o botão é "Ler de novo"');
    const conf = await page.$$eval('[data-ini-grupo="conferir"] .ini-task', l => l.map(x => x.textContent.replace(/\s+/g, ' ')));
    chk(conf.some(t => /F073-P0003/.test(t) && /parado há 16 dias/.test(t)), 'Home: a linha do lote mostra "parado há 16 dias" (idade da etapa): ' + JSON.stringify(conf.map(t => t.slice(0, 90))));
    const ordem0 = await page.$$eval('[data-ini-grupo="conferir"] .ini-task .code', l => l.map(x => x.textContent));
    await page.click('[data-ini-grupo="conferir"] [data-ini-ordem]'); await page.waitForTimeout(1200);
    const ordem1 = await page.$$eval('[data-ini-grupo="conferir"] .ini-task .code', l => l.map(x => x.textContent));
    chk(ordem0.indexOf('F073-P0002') < ordem0.indexOf('F073-P0003') && ordem1.indexOf('F073-P0003') < ordem1.indexOf('F073-P0002')
        && (await page.getAttribute('[data-ini-grupo="conferir"] [data-ini-ordem]', 'aria-pressed')) === 'true', `Home: "mais parado primeiro" sobe o lote de 16 dias (${ordem0.join(',')} → ${ordem1.join(',')})`);
    await page.click('[data-ini-grupo="conferir"] [data-ini-ordem]'); await page.waitForTimeout(800);
    // 1 clique: dois cliques seguidos fazem UM pedido (o botão apaga enquanto pede)
    const bt2 = page.locator('#ini-tarefas .ini-task').filter({ hasText: 'Leitura interrompida: Edifício Lido' }).first().locator('[data-ini-acao]');
    await bt2.evaluate(b => { b.click(); b.click(); });
    await page.waitForTimeout(1500);
    const nPed = +py(`print(con.execute("SELECT COUNT(*) FROM pedido_releitura WHERE projeto_codigo='F073-P0001' AND estado='pedido'").fetchone()[0])`);
    chk(nPed === 1 && posts === 1, `"Ler de novo": um clique, um pedido de releitura (pedidos ${nPed}, chamadas ${posts})`);
    const tli2 = so(await page.locator('#ini-tarefas .ini-task').filter({ hasText: 'Leitura interrompida: Edifício Lido' }).first().textContent());
    chk(/releitura pedida agora/.test(tli2) && /Ver na Fila/.test(tli2), 'Home: depois do pedido a linha diz "releitura pedida agora" e o botão vira "Ver na Fila": "' + tli2.slice(0, 200) + '"');

    // ---- Material novo ----
    py(`con.execute("DELETE FROM pedido_releitura WHERE projeto_codigo='F073-P0001'")`);
    await page.evaluate(() => { FILA_FILTRO = 'todas'; nav('filas'); });
    await page.waitForSelector('#filas-body tr[data-fase="processando"]', { timeout: 15000 }); await page.evaluate(() => { FILA_FILTRO = 'todas'; desenharFilas(); }); await page.waitForTimeout(300);
    const lr = page.locator('#filas-body tr').filter({ hasText: 'F073-P0001' }), tlr = so(await lr.textContent());
    chk(/leitura interrompida/.test(tlr) && (await lr.locator('[data-ler-de-novo]').count()) === 1 && /parado há 7 dias/.test(tlr), 'Material novo: etiqueta "leitura interrompida", "Ler de novo" e "parado há 7 dias": "' + tlr.slice(0, 220) + '"');
    const cods = async () => (await page.$$eval('#filas-body tr td:first-child .code', l => l.map(x => x.textContent))).filter(c => /^F073-/.test(c));
    await page.click('[data-fila-ordem]'); await page.waitForTimeout(300);
    const o = await cods();
    chk(o[0] === 'F073-P0003' && o[1] === 'F073-P0001' && o[2] === 'F073-P0002' && (await page.getAttribute('[data-fila-ordem]', 'aria-pressed')) === 'true', 'Material novo: clicar em "Parado há" ordena do mais parado (16 dias, 7 dias, 2 h): ' + o.join(','));
    await page.evaluate(() => { FILA_FILTRO = 'gente'; desenharFilas(); }); await page.waitForTimeout(200);
    chk((await page.locator('#filas-body tr').filter({ hasText: 'F073-P0001' }).count()) === 1, 'Material novo: a leitura interrompida aparece em "Precisam de você"');
    await page.locator('#filas-body tr').filter({ hasText: 'F073-P0001' }).locator('[data-ler-de-novo]').click(); await page.waitForTimeout(1500);
    const nPed2 = +py(`print(con.execute("SELECT COUNT(*) FROM pedido_releitura WHERE projeto_codigo='F073-P0001' AND estado='pedido'").fetchone()[0])`);
    const tlr2 = so(await page.locator('#filas-body tr').filter({ hasText: 'F073-P0001' }).textContent());
    chk(nPed2 === 1 && /Releitura pedida/.test(tlr2) && (await page.locator('#filas-body tr').filter({ hasText: 'F073-P0001' }).locator('[data-ler-de-novo]').count()) === 0, 'Material novo: "Ler de novo" pede a releitura e a linha passa a dizer "Releitura pedida": "' + tlr2.slice(0, 200) + '"');
  } catch (e) { chk(false, 'o teste quebrou: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma chamada da API falhou' + (falhas.length ? ': ' + falhas.slice(0, 4).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
