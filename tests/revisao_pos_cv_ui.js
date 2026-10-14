// Checagens de tela (Playwright, Chromium de verdade) do cartão "Revisão pós-CAMP Vision no painel":
// folha de contatos (2), marcar/desfazer duplicata (3), e de quebra o botão Espelhar (1) e o consenso do lote (4).
// Uso (servidor PRÓPRIO, nunca a porta 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8861)
//   CAMP_DB_PATH=/tmp/x.db CAMP_BASE=http://127.0.0.1:8861 node tests/revisao_pos_cv_ui.js
// O navegador só fala com o servidor de teste; prévias e imagens do site viram um JPEG branco (o QNAP de teste não existe).
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8861', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const JPG = Buffer.from('/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAeACgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigAooooAKKKKACiiigAooooAKKKKAP//Z', 'base64');
const problemas = [], linhas = [], ERROS = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F003-P9001', D = n => `${P}-1972-S01-D0000${n}`;
const dup = c => py(`print(con.execute("SELECT duplicata_de FROM item WHERE codigo=?",("${c}",)).fetchone()[0])`);

(async () => {
  py(`
cs=[r[0] for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo='${P}' ORDER BY sequencial")]
for c,(e,a) in zip(cs,[('Rua A, 10',1968),('Rua A, 10',1968),('Av. B, 5',1972)]): con.execute("UPDATE item SET endereco_folha=?, ano_folha=?, duplicata_de=NULL, espelho_manual=NULL WHERE codigo=?",(e,a,c))
f=[r[0] for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo='F023-P0011' ORDER BY sequencial LIMIT 3")]
for c in f: con.execute("UPDATE item SET ano_folha=1960 WHERE codigo=?",(c,))`);
  const browser = await chromium.launch({ executablePath: CHROME });
  const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
  await ctx.route('**/*', rt => { const u = rt.request().url();
    if (u.startsWith(BASE) && !/\/previa\?/.test(u)) return rt.continue();
    return rt.fulfill({ status: 200, contentType: 'image/jpeg', body: JPG }) });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error') ERROS.push(m.text()) }); page.on('pageerror', e => ERROS.push('pageerror: ' + e.message));
  const r = await ctx.request.post(BASE + '/api/auth/login', { data: { email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' } });
  chk(r.ok(), 'login do usuário semeado');

  // ---------- (4) consenso do lote ----------
  await page.goto(BASE + '/#projeto/' + P); await page.waitForSelector('#pj-consenso .cs-panel', { timeout: 15000 });
  const cs = await page.textContent('#pj-consenso');
  chk(/Consenso do lote/.test(cs) && /Rua A, 10/.test(cs) && /1968/.test(cs), 'o painel mostra o consenso (endereço "Rua A, 10", ano 1968): ' + cs.slice(0, 200));
  chk(await page.$$eval('#pj-consenso .cs-div', l => l.length) === 2, 'destaca a folha que diverge no ano e no endereço (D00003, duas linhas)');
  await page.click('#pj-consenso [data-cs-usar="endereco"]');
  await page.waitForFunction(() => !document.querySelector('#pj-consenso [data-cs-usar="endereco"]'), null, { timeout: 8000 });
  chk(py(`print(con.execute("SELECT endereco_folha FROM item WHERE codigo=?",("${D(3)}",)).fetchone()[0])`) === 'Rua A, 10', '"Usar o valor do consenso" troca o endereço da folha D00003');

  // ---------- (1) espelhar na revisão ----------
  await page.click(`.thumb[data-rev-abrir="${D(2)}"]`); await page.waitForSelector('#d-body [data-rev-espelhar]', { timeout: 8000 });
  await page.click('#d-body [data-rev-espelhar]'); await page.waitForFunction(() => document.querySelector('#d-body [data-rev-espelhar]').getAttribute('aria-pressed') === 'true', null, { timeout: 8000 });
  chk(/e=1/.test(await page.getAttribute('#rv-img', 'src')) && py(`print(con.execute("SELECT espelho_manual FROM item WHERE codigo=?",("${D(2)}",)).fetchone()[0])`) === '1', 'o botão Espelhar (ao lado do Girar) espelha a folha e troca a prévia');

  // ---------- (3) duplicata na revisão: escolher a original por busca e dizer qual publica ----------
  await page.click('#d-body [data-dup-marcar]'); await page.waitForSelector('#conf-ov #dup-busca');
  chk(await page.$$eval('#dup-lista .dup-op', l => l.length) === 2, 'a busca lista as outras folhas do projeto (2)');
  await page.fill('#dup-busca', 'D00001'); await page.waitForTimeout(150);
  chk(await page.$$eval('#dup-lista .dup-op', l => l.length) === 1, 'buscar "D00001" deixa só uma folha na lista');
  await page.check('#dup-lista input[name="dup-alvo"]'); await page.check('input[name="dup-qual"][value="esta_publica"]');
  await page.click('#conf-ov [data-conf="sim"]'); await page.waitForSelector('#conf-ov', { state: 'detached', timeout: 8000 });
  chk(dup(D(1)) === D(2) && dup(D(2)) === 'None', '"Esta folha é a que publica": a OUTRA (D00001) vira a duplicata de D00002');
  await page.evaluate(c => abrirRevisaoItem(c), D(1)); await page.waitForSelector('#d-body [data-dup-desfazer]', { timeout: 8000 });
  chk(/duplicata de/.test(await page.textContent('#d-body .dup-estado')), 'na revisão de D00001 aparece "duplicata de D00002" com "Não é duplicata"');
  await page.click('#d-body [data-dup-desfazer]'); await page.waitForSelector('#d-body [data-dup-marcar]', { timeout: 8000 });
  chk(dup(D(1)) === 'None', '"Não é duplicata" desfaz a marcação');

  // ---------- (2) folha de contatos ----------
  await page.evaluate(() => closeDrawer(true));
  await page.click('#pd [data-contatos]'); await page.waitForSelector('#ct-ov .ct-folha');
  const nums = await page.$$eval('#ct-ov .ct-num', l => l.map(x => x.textContent));
  chk(JSON.stringify(nums) === '["1","2","3"]', 'a folha de contatos mostra todas as folhas numeradas 1..3: ' + JSON.stringify(nums));
  chk(await page.$$eval('#ct-ov .ct-img img', l => l.length) === 3, 'cada folha com a sua miniatura');
  chk(/espelhada/.test(await page.textContent('#ct-ov .ct-folha:nth-child(2)')), 'a folha espelhada aparece marcada na grade');
  await page.emulateMedia({ media: 'print' });
  const imp = await page.evaluate(() => ({ ov: getComputedStyle(document.getElementById('ct-ov')).position, app: [...document.body.children].filter(e => e.id !== 'ct-ov' && getComputedStyle(e).display !== 'none').length, acoes: getComputedStyle(document.querySelector('.ct-acoes')).display }));
  chk(imp.ov === 'static' && imp.app === 0 && imp.acoes === 'none', 'impressão: só a grade sai no papel (sem menu, sem botões): ' + JSON.stringify(imp));
  await page.emulateMedia({ media: 'screen' });
  await page.click('#ct-ov .ct-folha:nth-child(3)'); await page.waitForSelector('#d-title', { timeout: 8000 });
  await page.waitForFunction(c => (document.getElementById('d-sub') || {}).textContent === c, D(3), { timeout: 8000 });
  chk(!(await page.$('#ct-ov')), 'clicar na folha 3 fecha a grade e abre a folha D00003 na revisão');
  await page.evaluate(() => closeDrawer(true));

  // ---------- (3) na página da folha ----------
  await page.goto(BASE + '/#item/' + D(3)); await page.waitForSelector('#idet [data-dup-marcar]', { timeout: 15000 });
  await page.click('#idet [data-dup-marcar]'); await page.waitForSelector('#conf-ov #dup-busca');
  await page.fill('#dup-busca', 'D00001'); await page.waitForTimeout(150); await page.check('#dup-lista input[name="dup-alvo"]');
  await page.click('#conf-ov [data-conf="sim"]'); await page.waitForSelector('#idet [data-dup-desfazer]', { timeout: 8000 });
  chk(dup(D(3)) === D(1), 'na página da folha: "Esta folha é a cópia" marca D00003 como duplicata de D00001');
  await page.click('#idet [data-dup-desfazer]'); await page.waitForSelector('#idet [data-dup-marcar]', { timeout: 8000 });
  chk(dup(D(3)) === 'None', 'na página da folha: "Não é duplicata" desfaz');

  // ---------- (4) "em todas", num projeto sem lote (consenso do projeto) ----------
  await page.goto(BASE + '/#projeto/F023-P0011'); await page.waitForSelector('#pj-consenso [data-cs-todas="ano"]', { timeout: 15000 });
  chk(/em todas \(3\)/.test(await page.textContent('#pj-consenso [data-cs-todas="ano"]')), 'o botão "Usar o valor do consenso em todas (3)" aparece');
  await page.click('#pj-consenso [data-cs-todas="ano"]'); await page.click('#conf-ov [data-conf="sim"]');
  await page.waitForSelector('#pj-consenso [data-cs-todas="ano"]', { state: 'detached', timeout: 8000 });
  chk(py(`print(con.execute("SELECT COUNT(*) FROM item WHERE projeto_codigo='F023-P0011' AND ano_folha<>1959").fetchone()[0])`) === '0', '"em todas" deixa as 3 folhas com o ano do consenso (1959)');
  await page.click('#pd [data-contatos]'); await page.waitForSelector('#ct-ov .ct-folha');
  chk(await page.$$eval('#ct-ov .ct-folha', l => l.length) === await page.evaluate(() => (window.ITENS_PJ || []).length), 'a folha de contatos de um projeto grande mostra todas as folhas');
  await page.keyboard.press('Escape'); chk(!(await page.$('#ct-ov')), 'Esc fecha a folha de contatos');

  chk(ERROS.length === 0, 'nenhum erro no console: ' + JSON.stringify(ERROS.slice(0, 5)));
  await browser.close();
  console.log(linhas.join('\n')); console.log(`\n=== REVISÃO PÓS-CV: ${problemas.length} problema(s) ===`); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); console.log(linhas.join('\n')); process.exit(1) });
