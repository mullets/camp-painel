// UX-29 (27/10) no navegador de verdade: possível duplicata ao criar ou editar projeto, e o relatório em Problemas.
// Prova: em "Novo projeto", ao DIGITAR o nome (antes de clicar Criar) aparece a lista de parecidos do mesmo fundo com "Abrir este";
// em "Editar", mudar o nome para um parecido avisa com "Abrir este" e "Não é duplicata"; em Problemas há "Possíveis projetos
// duplicados (N)"; "Não é duplicata" tira o par e o número diminui; recarregar não traz o par de volta; nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux29.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux29.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8941)
//   CAMP_DB_PATH=/tmp/ux29.db CAMP_BASE=http://127.0.0.1:8941 node tests/navegador_ux29_duplicata.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8941', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

py(`
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F072','Fundo Duplicatas','FDU',1)")
for n, t in ((92, 'Jockey Club'), (233, 'Edifício Jockey Club São Paulo'), (1, 'Residência James Francis King'), (2, 'Residência James Franics King - SP')):
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES ('F072',?)", (n,))
    con.execute("INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES (?,'F072',?,?,1960,'São Paulo')", ('F072-P%04d' % n, n, t))
con.execute("DELETE FROM par_nao_duplicado WHERE a LIKE 'F072-%'")
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?/.test(u);
  const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });

    // ---- Novo projeto: enquanto digita ----
    await page.evaluate(async () => { if (!FUNDOS.some(f => f[0] === 'F072')) await carregarFundosAPI(); abrirNovoProjeto('F072'); });
    await page.waitForSelector('#m-proj.on', { timeout: 10000 });
    await page.fill('#np-titulo', 'Jockey Club SP');
    await page.waitForSelector('#np-sugestoes .dup-par', { timeout: 10000 });
    const sug = await page.textContent('#np-sugestoes');
    chk(/F072-P0092/.test(sug) && /F072-P0233/.test(sug) && /São Paulo/.test(sug), 'Novo projeto: ao digitar "Jockey Club SP", antes de clicar Criar, aparecem F072-P0092 e F072-P0233 (com ano e cidade)');
    chk((await page.locator('#np-sugestoes [data-np-abrir="F072-P0092"]').count()) === 1, 'Novo projeto: cada parecido tem "Abrir este"');
    chk(!(await page.evaluate(() => !!document.querySelector('#m-proj .modal-erro, #np-err:not(:empty)'))), 'Novo projeto: nada foi salvo nem pedido (só a sugestão)');
    await page.fill('#np-titulo', 'Xq'); await page.waitForTimeout(900);
    chk(!(await page.$('#np-sugestoes .dup-par')), 'apagar o nome tira a sugestão');
    await page.evaluate(() => closeModal());

    // ---- Editar projeto: mudar o nome para um parecido ----
    await page.evaluate(() => nav('projeto/F072-P0001')); await page.waitForTimeout(1500);
    await page.evaluate(() => editarProjeto('F072-P0001'));
    await page.waitForSelector('#ep-titulo', { timeout: 10000 });
    await page.fill('#ep-titulo', 'Residência James Franics King');
    await page.waitForSelector('#ep-parecidos .dup-par', { timeout: 10000 });
    const ep = await page.textContent('#ep-parecidos');
    chk(/F072-P0002/.test(ep) && !/F072-P0001/.test(ep), 'Editar: o nome digitado avisa que fica parecido com F072-P0002 (e não lista o próprio projeto)');
    chk((await page.locator('#ep-parecidos [data-dup-nao]').count()) === 1, 'Editar: "Não é duplicata" ao lado do parecido');
    await page.evaluate(() => { limparAlteracoes('drawer'); closeDrawer(true); });

    // ---- Problemas ----
    await page.reload(); await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => nav('erros'));
    await page.waitForSelector('#err-dup-proj:not([hidden]) details', { timeout: 15000 });
    const n0 = +(await page.textContent('#err-dup-n'));
    await page.click('#err-dup-proj summary');
    const rel = await page.textContent('#err-dup-proj');
    chk(n0 >= 2 && /Jockey Club/.test(rel) && /Franics/.test(rel), `Problemas: "Possíveis projetos duplicados (${n0})" com Jockey Club e James Franics King`);
    const par = page.locator('#err-dup-proj .dup-par').filter({ hasText: 'Franics' });
    await par.locator('[data-dup-nao]').click(); await page.waitForTimeout(800);
    chk((await page.locator('#err-dup-proj .dup-par').filter({ hasText: 'Franics' }).count()) === 0 && +(await page.textContent('#err-dup-n')) === n0 - 1, '"Não é duplicata" tira o par e o número diminui');
    const gravado = py(`print(con.execute("SELECT COUNT(*) FROM par_nao_duplicado WHERE a='F072-P0001' AND b='F072-P0002'").fetchone()[0])`);
    chk(gravado === '1', 'o par fica gravado como "não são o mesmo" (par_nao_duplicado)');
    await page.reload(); await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => nav('erros')); await page.waitForSelector('#err-dup-proj details', { timeout: 15000 }); await page.waitForTimeout(500);
    chk(!/Franics/.test(await page.textContent('#err-dup-proj')), 'recarregar não traz o par de volta');
  } catch (e) { chk(false, 'o teste quebrou: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma chamada da API falhou' + (falhas.length ? ': ' + falhas.slice(0, 4).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
