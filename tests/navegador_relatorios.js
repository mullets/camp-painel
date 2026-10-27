// UX-14 · Relatórios (prestação de contas) no navegador de verdade (Playwright + Chromium).
// Prova: o primeiro cartão é "Digitalizadas no período" (só CAMP Vision); as folhas migradas do site aparecem num cartão separado,
// "Migradas/importadas do site", com a nota da migração como evento único; "Publicadas no período"; sem erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/rel.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/rel.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8947)
//   CAMP_DB_PATH=/tmp/rel.db CAMP_BASE=http://127.0.0.1:8947 node tests/navegador_relatorios.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8947', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// 7 folhas migradas do site neste ano, num projeto que não é lote de teste
const ano = new Date().getFullYear();
py(`
pc = con.execute("SELECT codigo FROM projeto WHERE lote_teste=0 ORDER BY codigo LIMIT 1").fetchone()[0]
for n in range(1, 8):
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,origem,criado_em) VALUES (?,?,?,?,?,?)", (pc + '-0000-S01-D%05d' % (80000 + n), pc, 'S01', 80000 + n, 'importado', '${ano}-01-02 10:00:00'))
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$/.test(u);
  const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => nav('relatorios'));
    await page.waitForSelector('#rel-corpo .rel-kpis .hoje-kpi', { timeout: 15000 });
    const r = await page.evaluate(async () => (await (await fetch('/api/relatorios', { credentials: 'same-origin' })).json()).folhas);
    const prim = await page.locator('#rel-corpo .rel-kpis').first().locator('.hoje-kpi').first();
    chk(/Digitalizadas no período/.test(await prim.textContent()) && (await prim.locator('.v').textContent()).trim() === String(r.digitalizadas), 'primeiro cartão = "Digitalizadas no período" com o número do CAMP Vision (' + r.digitalizadas + ')');
    chk(!/digitalizadas ou importadas/i.test(await page.textContent('#rel-corpo')), 'o rótulo "digitalizadas ou importadas" sumiu da tela');
    const mig = page.locator('#rel-corpo .rel-migradas');
    const mt = (await mig.textContent()).replace(/\s+/g, ' ');
    chk(r.importadas >= 7 && /Migradas\/importadas do site/.test(mt) && mt.includes(String(r.importadas)) && /evento único/.test(mt) && /migração/.test(mt), 'cartão separado de migradas com a nota da migração: "' + mt.slice(0, 160) + '"');
    chk(/Publicadas no período/.test(await page.textContent('#rel-corpo .rel-kpis')), 'cartão "Publicadas no período"');
    chk(erros.length === 0, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  } catch (e) { chk(false, 'erro no roteiro: ' + e.message); }
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
