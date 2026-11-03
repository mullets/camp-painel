// UX-67 (P2): títulos de projeto com texto da pasta ("Teatro Piracicaba - 12 Folhas"). Playwright + Chromium, servidor PRÓPRIO (porta 8971).
// Na tela Projetos (admin): o aviso tem "Corrigir vários títulos"; a lista mostra a sugestão do carimbo e a da pasta; "Ver o que muda"
// não grava nada (simular); "Aplicar" pede confirmação e grava; o histórico tem "Desfazer", que volta o título de antes.
// Uso:
//   CAMP_DB_PATH=/tmp/ux67.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux67.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8971)
//   CAMP_DB_PATH=/tmp/ux67.db CAMP_BASE=http://127.0.0.1:8971 node tests/navegador_ux67_titulos.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8971', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const A = 'F003-P9671', B = 'F003-P9672';
py(`
for cod, n, t in (('${A}', 9671, 'Teatro Piracicaba - 12 Folhas'), ('${B}', 9672, 'Sede do Conselho Regional - 08 Folhas')):
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F003', ?)", (n,))
    con.execute("INSERT INTO projeto (codigo, fundo_codigo, numero, titulo) VALUES (?, 'F003', ?, ?)", (cod, n, t))
for k in range(1, 4):
    con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, titulo, origem, projeto_carimbo) VALUES (?,?,?,?,?,'campvision',?)",
                ('${A}-1975-S01-D%05d' % k, '${A}', 'S01', k, 'Planta %d' % k, 'TEATRO MUNICIPAL DE PIRACICABA'))
`);
const titulo = c => py(`print(con.execute("SELECT titulo FROM projeto WHERE codigo='${c}'").fetchone()[0])`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|\/previa\?|\/miniatura|exemplo\.test/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO((m.location() || {}).url || '')) erros.push(m.text() + ' @' + ((m.location() || {}).url || '')); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  const txt = async s => ((await page.$(s)) ? (await page.textContent(s)).replace(/\s+/g, ' ').trim() : '');
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    for (const sel of ['.ajuda-caixa [data-ajuda-fechar]', '[data-faixa-fechar]']) { const b = await page.$(sel); if (b && await b.isVisible()) { await b.click(); await page.waitForTimeout(300) } }
    await page.evaluate(() => nav('projetos'));
    await page.waitForSelector('#proj-nome-pasta [data-tp-abrir]', { timeout: 15000 });
    chk(true, 'o aviso da tela Projetos tem "Corrigir vários títulos"');
    await page.click('#proj-nome-pasta [data-tp-abrir]');
    await page.waitForSelector(`#d-body .tp-it[data-tp="${A}"]`, { timeout: 10000 });
    const va = await page.inputValue(`#d-body .tp-it[data-tp="${A}"] [data-tp-novo]`), vb = await page.inputValue(`#d-body .tp-it[data-tp="${B}"] [data-tp-novo]`);
    chk(va === 'Teatro Municipal de Piracicaba', `${A}: o título novo vem do carimbo ("${va}")`);
    chk(vb === 'Sede do Conselho Regional', `${B}: sem carimbo, vem da pasta sem "- 08 Folhas" ("${vb}")`);
    const la = await txt(`#d-body .tp-it[data-tp="${A}"]`);
    chk(/no carimbo: Teatro Municipal de Piracicaba \(3 de 3 folhas\)/.test(la) && /da pasta: Teatro Piracicaba/.test(la), `${A}: mostra as duas sugestões ("${la}")`);
    // usar a da pasta no A (clique no texto da sugestão)
    await page.click(`#d-body .tp-it[data-tp="${A}"] [data-tp-usar][data-tp-fonte="pasta"]`);
    chk(await page.inputValue(`#d-body .tp-it[data-tp="${A}"] [data-tp-novo]`) === 'Teatro Piracicaba', 'clicar na sugestão da pasta troca o título novo');
    // desmarcar todos os outros (o semear pode ter outros títulos técnicos) e deixar A e B
    await page.evaluate(([a, b]) => document.querySelectorAll('#d-body .tp-it').forEach(li => { li.querySelector('[data-tp-ok]').checked = [a, b].includes(li.dataset.tp) }), [A, B]);
    await page.click('#d-body [data-tp-simular]');
    await page.waitForSelector('#tp-res [data-tp-aplicar]', { timeout: 10000 });
    const sim = await txt('#tp-res');
    chk(/2 títulos mudam/.test(sim) && /nada foi gravado ainda/.test(sim) && titulo(A) === 'Teatro Piracicaba - 12 Folhas', 'Ver o que muda: "2 títulos mudam (nada foi gravado ainda)" e nada muda no banco: "' + sim.slice(0, 160) + '"');
    await page.click('#tp-res [data-tp-aplicar]');
    await page.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 5000 });
    await page.click('#conf-ov [data-conf="sim"]');
    await page.waitForFunction(a => !document.querySelector(`#d-body .tp-it[data-tp="${a}"]`) && document.querySelector('#d-body .tp-hist'), A, { timeout: 10000 });
    chk(titulo(A) === 'Teatro Piracicaba' && titulo(B) === 'Sede do Conselho Regional', `Aplicar grava os títulos novos (${titulo(A)} · ${titulo(B)})`);
    await page.click('#d-body .tp-hist summary');
    const h = await txt('#d-body .tp-hist');
    chk(/2 títulos/.test(h) && !!(await page.$('#d-body .tp-hist [data-tp-desfazer]')), 'o histórico mostra a correção com Desfazer: "' + h.slice(0, 160) + '"');
    await page.click('#d-body .tp-hist [data-tp-desfazer]');
    await page.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 5000 });
    await page.click('#conf-ov [data-conf="sim"]');
    await page.waitForFunction(a => !!document.querySelector(`#d-body .tp-it[data-tp="${a}"]`), A, { timeout: 10000 });
    chk(titulo(A) === 'Teatro Piracicaba - 12 Folhas' && titulo(B) === 'Sede do Conselho Regional - 08 Folhas', 'Desfazer volta os títulos de antes');
    // celular
    await page.setViewportSize({ width: 390, height: 844 }); await page.waitForTimeout(300);
    chk(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'no celular (390px) não há rolagem lateral');
  } catch (e) { problemas.push('exceção: ' + e.message); linhas.push('FALHA exceção: ' + e.message) }
  chk(!erros.length, 'nenhum erro no console: ' + erros.slice(0, 3).join(' | '));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
