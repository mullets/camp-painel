// Home ("Precisa de você") enxuta, no navegador de verdade (Playwright + Chromium):
//  - UX-18: o cartão "decisões" só aparece quando há decisão pendente (nunca "0 decisões — nenhuma esperando").
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
    await adm.ctx.close();
  } catch (e) { problemas.push('exceção: ' + (e && e.stack || e)); }
  finally { await browser.close(); }
  for (const e of erros) problemas.push('console: ' + e);
  console.log(linhas.join('\n'));
  if (problemas.length) { console.log('\nPROBLEMAS (' + problemas.length + '):\n- ' + problemas.join('\n- ')); process.exit(1); }
  console.log('\nTUDO OK (' + linhas.length + ' verificações)');
})();
