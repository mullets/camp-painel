// UX-15 · título que é nome de pasta ou código (Playwright, Chromium de verdade). Servidor PRÓPRIO, nunca a 8765:
//   CAMP_DB_PATH=/tmp/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8946)
//   CAMP_DB_PATH=/tmp/x.db CAMP_BASE=http://127.0.0.1:8946 node tests/navegador_ux15_titulo.js
// O aviso da tela Projetos conta TODOS os títulos técnicos; o título sugerido só muda com o clique (um por vez); editar para T###_ é recusado;
// a cidade digitada noutra forma ("SAO PAULO") mostra a forma do acervo ("São Paulo") com o botão Usar.
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8946', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (code) => execFileSync('python3', ['-c', code, DB]).toString().trim();
py(`import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
for n,t in ((235,'T099_Casa_Azul'),(236,'Projeto Não Identificado 2')):
    c.execute('INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES (?,?)',('F026',n))
    c.execute('INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,cidade) VALUES (?,?,?,?,?)',(f'F026-P{n:04d}','F026',n,t,'SAO PAULO'))
c.commit()`);
const linhas = [], prob = [], erros = [];
const chk = (ok, m) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + m); if (!ok) prob.push(m) };
(async () => {
  const b = await chromium.launch({ executablePath: CHROME });
  const ctx = await b.newContext({ viewport: { width: 1280, height: 900 } });
  await ctx.route('**/*', rt => rt.request().url().startsWith(BASE) ? rt.continue() : rt.abort());
  const r = await ctx.request.post(BASE + '/api/auth/login', { data: { email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' } });
  chk(r.ok(), 'login');
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !/net::ERR_FAILED|Failed to load resource/.test(m.text())) erros.push(m.text()) });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await page.goto(BASE + '/#projetos');
  await page.waitForSelector('#proj-nome-pasta .aviso-pasta', { timeout: 15000 });
  const txt = await page.textContent('#proj-nome-pasta');
  chk(/2 projetos com nome de pasta do sistema/.test(txt), 'o aviso conta os 2 títulos técnicos (T###_ e Projeto Não Identificado): ' + txt.trim().slice(0, 80));
  await page.click('[data-np-abrir]');
  await page.waitForSelector('#d-body .np-card');
  const c235 = await page.textContent('#d-body [data-np="F026-P0235"]').catch(() => '');
  const c236 = await page.textContent('#d-body [data-np="F026-P0236"]').catch(() => '');
  chk(/Título sugerido: Casa Azul/.test(c235) && !!(await page.$('[data-np-titulo="F026-P0235"]')), 'T099_Casa_Azul: sugestão "Casa Azul" com o botão Usar o título sugerido');
  chk(/Sem sugestão/.test(c236) && !(await page.$('[data-np-titulo="F026-P0236"]')) && !!(await page.$('[data-np-editar="F026-P0236"]')), 'Projeto Não Identificado: sem sugestão, só Corrigir o título');
  chk(py(`import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute("SELECT titulo FROM projeto WHERE codigo='F026-P0235'").fetchone()[0])`) === 'T099_Casa_Azul', 'abrir a janela não renomeia nada');
  await page.click('[data-np-titulo="F026-P0235"]');
  await page.waitForSelector('#conf-ov');
  await page.click('#conf-ov [data-conf="sim"]');
  await page.waitForFunction(() => !document.querySelector('#conf-ov') && !document.querySelector('[data-np="F026-P0235"]'), null, { timeout: 10000 });
  chk(py(`import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute("SELECT titulo FROM projeto WHERE codigo='F026-P0235'").fetchone()[0])`) === 'Casa Azul', 'aceitar a sugestão grava "Casa Azul"');
  await page.waitForFunction(() => /1 projeto com nome de pasta do sistema/.test(document.getElementById('proj-nome-pasta').textContent), null, { timeout: 10000 }).then(() => chk(true, 'o aviso passa a contar 1'), () => chk(false, 'o aviso passa a contar 1'));
  // Corrigir o título: abre a edição; T###_ é recusado com a explicação
  await page.click('[data-np-editar="F026-P0236"]');
  await page.waitForSelector('#ep-titulo');
  await page.fill('#ep-titulo', 'T100_Casa Verde');
  await page.click('#drawer .act .btn.pri');
  await page.waitForFunction(() => /não serve como nome do projeto/.test(document.getElementById('drawer').textContent + (document.getElementById('toast') || {}).textContent), null, { timeout: 8000 })
    .then(() => chk(true, 'salvar T100_… mostra a recusa com a sugestão'), () => chk(false, 'salvar T100_… mostra a recusa com a sugestão'));
  chk(py(`import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute("SELECT titulo FROM projeto WHERE codigo='F026-P0236'").fetchone()[0])`) === 'Projeto Não Identificado 2', 'o título técnico não foi gravado');
  // cidade: SAO PAULO → a forma do acervo "São Paulo" com o botão Usar
  await page.fill('#ep-cidade', ''); await page.type('#ep-cidade', 'SAO PAULO');
  await page.waitForSelector('#drawer .cid-sug:not([hidden])', { timeout: 8000 }).catch(() => {});
  const sug = await page.textContent('#drawer .cid-sug').catch(() => '');
  chk(/São Paulo/.test(sug) && /Usar/.test(sug), 'cidade "SAO PAULO": sugere "São Paulo" (forma do acervo): ' + (sug || '').trim().slice(0, 80));
  await page.click('#drawer [data-cid-usar]').catch(() => {});
  chk(await page.inputValue('#ep-cidade') === 'São Paulo', 'Usar troca a cidade no campo (só no campo; grava ao salvar)');
  chk(await page.$eval('#ep-cidade', e => e.getAttribute('list') === 'dl-cidades' && document.querySelectorAll('#dl-cidades option').length > 0), 'autocomplete com as cidades do acervo');
  chk(erros.length === 0, 'sem erro no console' + (erros.length ? ': ' + erros.join(' | ') : ''));
  console.log(linhas.join('\n')); console.log(prob.length ? `${prob.length} FALHA(S)` : 'TUDO OK');
  await b.close(); process.exit(prob.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1) });
