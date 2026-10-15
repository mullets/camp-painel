// Projetos com nome de pasta do sistema (Playwright, Chromium de verdade). Servidor PRÓPRIO (porta 8920-8929), nunca a 8765:
//   CAMP_DB_PATH=/tmp/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8923)
//   CAMP_DB_PATH=/tmp/x.db CAMP_BASE=http://127.0.0.1:8923 node tests/nome_de_pasta_ui.js
// Cria no banco semeado dois projetos com nome de subpasta (F026-P0114 sem folhas, F026-P0237 com 1 folha), descarta um e junta o outro.
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8923', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
execFileSync('python3', ['-c', `import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
A='/mnt/qnap/acervos/F026 - X'
for n,t in ((114,'01 - Arquivo Arquivístico (TIFF)'),(237,'JPG')):
    c.execute('INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES (?,?)',('F026',n))
    c.execute('INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo) VALUES (?,?,?,?)',(f'F026-P{n:04d}','F026',n,t))
c.execute('INSERT INTO lista_processamento (nome,projeto_codigo,pasta_qnap,etapa) VALUES (?,?,?,?)',('01','F026-P0114',A+'/P0001 - Casa Tarumã - 1968/01 - Arquivo Arquivístico (TIFF)','revisao'))
c.execute('INSERT INTO lista_processamento (nome,projeto_codigo,pasta_qnap,etapa) VALUES (?,?,?,?)',('JPG','F026-P0237',A+'/Edifício Paulista - 1970/JPG','revisao'))
c.execute("INSERT OR IGNORE INTO item (codigo,projeto_codigo,serie_codigo,sequencial,origem) VALUES ('F026-P0237-0000-S03-D00001','F026-P0237','S03',1,'importado')")
c.commit()`, DB], { stdio: 'inherit' });
const linhas = [], prob = [], erros = [];
const chk = (ok, m) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + m); if (!ok) prob.push(m) };
(async () => {
  const b = await chromium.launch({ executablePath: CHROME });
  async function sessao(email, senha) {
    const ctx = await b.newContext({ viewport: { width: 1280, height: 900 } });
    await ctx.route('**/*', rt => rt.request().url().startsWith(BASE) ? rt.continue() : rt.abort());
    const r = await ctx.request.post(BASE + '/api/auth/login', { data: { email, senha } });
    chk(r.ok(), 'login ' + email);
    const page = await ctx.newPage();
    page.on('console', m => { if (m.type() === 'error' && !/net::ERR_FAILED|Failed to load resource/.test(m.text())) erros.push(email + ': ' + m.text()) });
    page.on('pageerror', e => erros.push(email + ' pageerror: ' + e.message));
    return page;
  }
  const page = await sessao('rafael@camp.arq.br', 'senha-bem-longa-123');
  await page.goto(BASE + '/#projetos');
  await page.waitForSelector('#proj-nome-pasta .aviso-pasta', { timeout: 15000 });
  const txt = await page.textContent('#proj-nome-pasta');
  chk(/2 projetos com nome de pasta do sistema/.test(txt), 'aviso na tela Projetos: ' + txt.trim().slice(0, 90));
  chk(/não uma obra/.test(txt), 'texto simples "não uma obra"');
  await page.click('[data-np-abrir]');
  await page.waitForSelector('#d-body .np-card');
  const cards = await page.$$eval('#d-body .np-card', cs => cs.map(c => ({ cod: c.dataset.np, t: c.textContent, desc: !!c.querySelector('[data-np-descartar]'), capa: c.querySelector('.np-capa').tagName })));
  chk(cards.length === 2, 'janela lista 2 projetos');
  const c114 = cards.find(c => c.cod === 'F026-P0114'), c237 = cards.find(c => c.cod === 'F026-P0237');
  chk(c114 && /F026-P0001/.test(c114.t) && c114.desc, 'P0114: sugestão F026-P0001 (pelo P na pasta-mãe) e botão Descartar');
  chk(c237 && /F026-P0002/.test(c237.t) && !c237.desc, 'P0237 (1 folha): sugestão F026-P0002 pelo nome, sem Descartar');
  // descartar P0114
  await page.click('[data-np-descartar="F026-P0114"]');
  await page.waitForSelector('#conf-ov');
  await page.click('#conf-ov [data-conf="sim"]');
  await page.waitForFunction(() => !document.querySelector('#conf-ov') && !document.querySelector('[data-np="F026-P0114"]'), null, { timeout: 10000 });
  chk(true, 'descartar P0114 pela janela');
  // juntar P0237: tenta outro fundo (recusa) e depois a sugestão
  await page.click('[data-np-juntar="F026-P0237"]');
  await page.waitForSelector('#conf-campo');
  chk(await page.inputValue('#conf-campo') === 'F026-P0002', 'juntar vem preenchido com a sugestão');
  await page.fill('#conf-campo', 'F023-P0011');
  chk(await page.isDisabled('#conf-ov [data-conf="sim"]') && /Fundos não se misturam/.test(await page.textContent('#conf-err')), 'outro fundo: botão desligado e explicação');
  await page.fill('#conf-campo', 'F026-P0002');
  await page.click('#conf-ov [data-conf="sim"]');
  await page.waitForFunction(() => !document.querySelector('#conf-ov') && !document.querySelector('[data-np="F026-P0237"]'), null, { timeout: 10000 });
  await page.waitForFunction(() => document.getElementById('proj-nome-pasta').hidden, null, { timeout: 10000 });
  chk(true, 'juntar P0237 em P0002; o aviso some');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(800);
  const lista = await page.$$eval('#projetos-body tr[data-nav]', trs => trs.map(t => t.textContent));
  chk(!lista.some(t => /P0114|P0237/.test(t)), 'os dois somem da lista de Projetos');
  // operador não vê
  const op = await sessao('operador@camp.arq.br', 'senha-operador-123');
  await op.goto(BASE + '/#projetos'); await op.waitForSelector('#projetos-body tr', { timeout: 15000 }); await op.waitForTimeout(800);
  chk(await op.$eval('#proj-nome-pasta', e => e.hidden), 'operador não vê o aviso');
  chk(erros.length === 0, 'sem erro no console' + (erros.length ? ': ' + erros.join(' | ') : ''));
  console.log(linhas.join('\n')); console.log(prob.length ? `${prob.length} FALHA(S)` : 'TUDO OK');
  await b.close(); process.exit(prob.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1) });
