// UX-16 · Downloads do site (Uso do acervo) no navegador de verdade (Playwright + Chromium).
// Prova: os registros de teste (finalidade "Teste QA automatizado", e-mail de QA) não entram nas métricas nem na lista; a tela diz
// "N registros de teste ocultos" e o "Ver" mostra só eles (e "Voltar às métricas" volta); o "uso mais declarado" é a categoria
// (pesquisa acadêmica…), não o texto de teste; sem erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/dl.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/dl.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8947)
//   CAMP_DB_PATH=/tmp/dl.db CAMP_BASE=http://127.0.0.1:8947 node tests/navegador_downloads.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8947', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// 30 registros do robô de QA (mais que todos os reais juntos: antes viravam o "uso mais declarado") e um e-mail de QA
const reais = Number(py(`
for k in range(30):
    con.execute("INSERT INTO uso_download (form_id,origem_id,recebida_em,nome,email,uso) VALUES (99,?,datetime('now','-2 days'),'Robô QA',?, 'Teste QA automatizado')", (9000 + k, 'robo%d@x.com' % k))
con.execute("INSERT INTO uso_download (form_id,origem_id,recebida_em,nome,email,uso) VALUES (99,9100,datetime('now','-2 days'),'Juca','qa+dl@camp.arq.br','pesquisa acadêmica')")
print(con.execute("SELECT COUNT(*) FROM uso_download WHERE apagada=0").fetchone()[0] - 31)
`));

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$/.test(u);
  const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  const linhasTabela = () => page.locator('#us-body tr.us-row').count();
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => nav('uso'));
    await page.waitForSelector('#us-kpis .hoje-kpi', { timeout: 15000 }); await page.waitForSelector('#us-body tr.us-row', { timeout: 15000 }); await page.waitForTimeout(400);
    const k1 = (await page.locator('#us-kpis .hoje-kpi').first().locator('.v').textContent()).trim();
    chk(k1 === String(reais), `métrica "pedidos de download" sem os testes: ${k1} (reais: ${reais}, ocultos 31)`);
    const kUso = (await page.locator('#us-kpis .hoje-kpi').nth(3).textContent()).replace(/\s+/g, ' ');
    chk(!/teste/i.test(kUso) && /variações de texto agrupadas/.test(kUso), '"uso mais declarado" é uma categoria, não "Teste QA automatizado": "' + kUso + '"');
    const fr = await page.textContent('#us-frase');
    chk(/31 registros de teste ocultos/.test(fr), 'a tela diz "31 registros de teste ocultos"');
    chk(!/Teste QA|qa\+dl@/.test(await page.textContent('#us-body')) && (await linhasTabela()) === Math.min(reais, 50), 'lista sem os registros de teste');
    await page.click('#us-frase [data-uso-testes="so"]');
    await page.waitForFunction(() => /Mostrando só os/.test(document.getElementById('us-frase').textContent), null, { timeout: 5000 }); await page.waitForTimeout(600);
    chk((await linhasTabela()) === 31 && /Teste QA automatizado/.test(await page.textContent('#us-body')) && /qa\+dl@camp\.arq\.br/.test(await page.textContent('#us-body')), '"Ver" mostra só os 31 de teste (inclusive o e-mail de QA)');
    await page.click('#us-frase [data-uso-testes=""]');
    await page.waitForFunction(() => /registros de teste ocultos/.test(document.getElementById('us-frase').textContent), null, { timeout: 5000 }); await page.waitForTimeout(600);
    chk(!/Teste QA/.test(await page.textContent('#us-body')), '"Voltar às métricas" esconde de novo');
    chk(erros.length === 0, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  } catch (e) { chk(false, 'erro no roteiro: ' + e.message); }
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
