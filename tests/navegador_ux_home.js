// Home ("Precisa de você") enxuta, no navegador de verdade (Playwright + Chromium):
//  - UX-18: o cartão "decisões" só aparece quando há decisão pendente (nunca "0 decisões — nenhuma esperando").
//  - UX-21: filas pelo papel: o operador vê "Decidir" (de admin) esmaecida e no fim, sem perder os dados; o admin e quem só lê
//    não têm nada esmaecido.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ag_k/home.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ag_k/home.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8951)
//   CAMP_DB_PATH=/tmp/ag_k/home.db CAMP_BASE=http://127.0.0.1:8951 node tests/navegador_ux_home.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8951', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

async function entrar(browser, email, senha, erros) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=/.test(u);
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(email + ': ' + m.text()); });
  page.on('pageerror', e => erros.push(email + ': pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, page };
}
async function abrirHome(page) {
  await page.evaluate(() => { nav('painel'); carregarPainel() });
  await page.waitForSelector('#v-painel .ini-grid #ini-tarefas', { timeout: 15000 });
  await page.waitForTimeout(600);
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const nDec = +py("print(con.execute(\"SELECT COUNT(*) FROM decisao WHERE situacao='pendente'\").fetchone()[0])");
    chk(nDec > 0, `a semente tem decisões pendentes (${nDec})`);
    const adm = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    const P = adm.page;

    // ---------- UX-18 ----------
    await abrirHome(P);
    const kDec = () => P.evaluate(() => { const b = document.querySelector('#v-painel .ini-kpi[data-ini-rota="decisoes"]'); return b ? b.textContent.replace(/\s+/g, ' ').trim() : null; });
    let k = await kDec();
    chk(!!k && new RegExp('^' + nDec + '\\s*decis').test(k), `UX-18: com ${nDec} decisões pendentes o cartão aparece: "${k}"`);
    const idsDec = py("ids=[r[0] for r in con.execute(\"SELECT id FROM decisao WHERE situacao='pendente'\")]\ncon.execute(\"UPDATE decisao SET situacao='resolvida' WHERE situacao='pendente'\")\nprint(','.join(map(str,ids)))");
    await abrirHome(P);
    k = await kDec();
    const kp = await P.evaluate(() => [...document.querySelectorAll('#v-painel .ini-kpi')].map(b => b.dataset.iniRota));
    const nKpis = await P.evaluate(() => getComputedStyle(document.querySelector('#v-painel .ini-kpis')).getPropertyValue('--n').trim());
    chk(k === null && !/nenhuma esperando/.test(await P.locator('#v-painel').innerText()), `UX-18: sem decisão pendente o cartão some (era "0 decisões — nenhuma esperando"): ${k}`);
    chk(kp.length >= 1 && !kp.includes('decisoes') && nKpis === String(kp.length), `UX-18: os outros números continuam e a grade se ajusta (${kp.join(', ')}; --n=${nKpis})`);
    py(`con.execute("UPDATE decisao SET situacao='pendente' WHERE id IN (${idsDec})")`);   // devolve a semente como estava
    // ---------- UX-21 ----------
    const grupos = pg => pg.evaluate(() => [...document.querySelectorAll('#ini-tarefas .ini-tg')].map(g => ({ id: g.dataset.iniGrupo, outro: g.classList.contains('ini-outro'), op: +getComputedStyle(g).opacity, linhas: g.querySelectorAll('.ini-task').length, txt: g.querySelector('.ini-tgh').textContent })));
    await abrirHome(P);
    const gA = await grupos(P);
    chk(gA.length > 1 && gA.every(g => !g.outro && g.op === 1), `UX-21: admin (master) executa todas as filas: nada esmaecido (${gA.map(g => g.id).join(', ')})`);
    chk(gA[0].id === 'decidir', `UX-21: para o admin, "Decidir" continua no topo (${gA[0].id})`);
    const op = await entrar(browser, 'operador@camp.arq.br', 'senha-operador-123', erros);
    await abrirHome(op.page);
    const api = await op.page.evaluate(async () => (await (await fetch('/api/painel', { credentials: 'same-origin' })).json()).tarefas.map(g => ({ id: g.id, quem: g.quem, n: g.itens.length })));
    const gO = await grupos(op.page);
    const dO = gO.find(g => g.id === 'decidir'), meusO = gO.filter(g => !g.outro);
    chk(!!dO && dO.outro && dO.op < 1 && /quem faz é um admin/.test(dO.txt), `UX-21: operador vê "Decidir" esmaecida e com "quem faz é um admin" (${JSON.stringify(dO)})`);
    chk(gO[gO.length - 1].id === 'decidir' && meusO.length >= 1 && meusO.every(g => g.op === 1 && api.find(a => a.id === g.id).quem !== 'admin'), `UX-21: as filas do operador vêm primeiro, sem esmaecer; a de admin, no fim (${gO.map(g => g.id + (g.outro ? '*' : '')).join(', ')})`);
    chk(gO.length === api.length && gO.every(g => g.linhas === api.find(a => a.id === g.id).n), `UX-21: nenhuma fila nem linha escondida: só esmaecida (${gO.length} grupos = servidor ${api.length})`);
    const kO = await op.page.evaluate(() => { const b = document.querySelector('#v-painel .ini-kpi[data-ini-rota="decisoes"]'); return b ? { outro: b.classList.contains('ini-outro'), op: +getComputedStyle(b).opacity } : null; });
    chk(!!kO && kO.outro && kO.op < 1, `UX-21: o número de decisões (de admin) esmaecido para o operador: ${JSON.stringify(kO)}`);
    await op.ctx.close();
    const le = await entrar(browser, 'leitor@camp.arq.br', 'senha-leitor-1234', erros);
    await abrirHome(le.page);
    const gL = await grupos(le.page);
    chk(gL.length >= 1 && gL.every(g => !g.outro), `UX-21: quem só lê não executa nenhuma fila: nada esmaecido, vê tudo (${gL.map(g => g.id).join(', ')})`);
    await le.ctx.close();
    await adm.ctx.close();
  } catch (e) { problemas.push('exceção: ' + (e && e.stack || e)); }
  finally { await browser.close(); }
  for (const e of erros) problemas.push('console: ' + e);
  console.log(linhas.join('\n'));
  if (problemas.length) { console.log('\nPROBLEMAS (' + problemas.length + '):\n- ' + problemas.join('\n- ')); process.exit(1); }
  console.log('\nTUDO OK (' + linhas.length + ' verificações)');
})();
