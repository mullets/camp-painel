// UX-23 · lista de Fundos com unidade explícita (Playwright, Chromium de verdade). Servidor PRÓPRIO, nunca a 8765:
//   CAMP_DB_PATH=/tmp/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8946)
//   CAMP_DB_PATH=/tmp/x.db CAMP_BASE=http://127.0.0.1:8946 node tests/navegador_ux23_fundos.js
// Colunas "Projetos", "Projetos no site", "Folhas no site", "Rascunhos no site" (com explicação); sem "+N rasc."; a aba "Com pendência"
// conta "direitos ainda não registrados"; o título da página é o nome do menu ("Fundos e arquitetos").
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8946', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
// F026: 2 páginas de projeto e 5 folhas publicadas, 1 + 3 em rascunho; direitos nunca registrados
execFileSync('python3', ['-c', `import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
c.execute("DELETE FROM direitos_fundo WHERE fundo_codigo='F026'")
i=990000
for col,st,k in ((8007,'publish',2),(8013,'publish',5),(8007,'draft',1),(8013,'draft',3)):
    for _ in range(k):
        i+=1; c.execute("INSERT OR REPLACE INTO wp_item (id,colecao_id,status,fundo_detectado) VALUES (?,?,?,'F026')",(i,col,st))
c.commit()`, DB]);
const linhas = [], prob = [], erros = [];
const chk = (ok, m) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + m); if (!ok) prob.push(m) };
(async () => {
  const b = await chromium.launch({ executablePath: CHROME });
  const ctx = await b.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.route('**/*', rt => rt.request().url().startsWith(BASE) ? rt.continue() : rt.abort());
  const r = await ctx.request.post(BASE + '/api/auth/login', { data: { email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' } });
  chk(r.ok(), 'login');
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !/net::ERR_FAILED|Failed to load resource/.test(m.text())) erros.push(m.text()) });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await page.goto(BASE + '/#fundos');
  await page.waitForSelector('#fundos-body tr[data-nav="fundo/F026"]', { timeout: 15000 });
  const ths = await page.$$eval('#v-fundos thead th', t => t.map(x => x.textContent.replace('ⓘ', '').trim()));
  chk(['Projetos', 'Projetos no site', 'Folhas no site', 'Rascunhos no site'].every(h => ths.includes(h)) && !ths.includes('Publicados'), 'cabeçalhos com unidade: ' + ths.join(' | '));
  chk(/só a equipe vê/.test(await page.$eval('#v-fundos thead th[title*="Rascunho"]', e => e.title).catch(() => '')), 'tooltip do "Rascunhos no site"');
  chk(/Rascunhos no site: já está no site, mas só a equipe vê/.test(await page.textContent('#fundos-legenda').catch(() => '')), 'legenda abaixo da tabela');
  const api = await (await ctx.request.get(BASE + '/api/fundos/resumo')).json(), a26 = api.find(f => f.codigo === 'F026') || {};
  const tds = await page.$$eval('#fundos-body tr[data-nav="fundo/F026"] td.num', t => t.map(x => x.textContent.trim()));
  const esp = [a26.projetos, a26.projetos_no_site, a26.folhas_no_site, a26.rascunhos_site].map(String);
  chk(tds.join(',') === esp.join(',') && a26.projetos_no_site >= 2 && a26.folhas_no_site >= 5 && a26.rascunhos_site === a26.rascunhos_projetos_site + a26.rascunhos_folhas_site,
      `F026: projetos, projetos no site, folhas no site e rascunhos em colunas separadas (${tds.join(',')} × ${esp.join(',')})`);
  chk(!/rasc\./.test(await page.textContent('#fundos-body')), 'não aparece mais "+N rasc."');
  const dicas = await page.$$eval('#fundos-body tr[data-nav="fundo/F026"] td[title]', t => t.map(x => x.title).join(' '));
  chk(new RegExp(`${a26.rascunhos_projetos_site} páginas? de projeto e ${a26.rascunhos_folhas_site} folhas? em rascunho`).test(dicas), 'o rascunho diz quantos são páginas de projeto e quantos são folhas: ' + dicas);
  // Com pendência: inclui os fundos com direitos ainda não registrados
  const esperado = api.filter(f => !f.so_no_site && (f.direitos !== 'autorizado' || !f.sigla || f.travado)).length;
  const nPend = +(await page.textContent('#ffc-pendencia')).replace(/\D/g, '');
  chk(nPend === esperado && nPend > 0, `aba Com pendência conta ${nPend} (esperado ${esperado}, com "direitos ainda não registrados")`);
  await page.click('[data-ff="pendencia"]'); await page.waitForTimeout(300);
  chk(!!(await page.$('#fundos-body tr[data-nav="fundo/F026"]')), 'F026 (direitos não registrados) aparece em Com pendência');
  await page.click('[data-ff="todos"]');
  // título = nome do menu
  const primeiro = sel => page.$eval(sel, e => [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim());
  const h1 = await primeiro('#v-fundos h1'), menu = await primeiro('.side [data-v="fundos"]');
  chk(h1 === menu && h1 === 'Fundos e arquitetos', `título da página = nome do menu ("${h1}" × "${menu}")`);
  await page.click('[data-fundos-arq]', { timeout: 3000 }).catch(() => {}); await page.waitForTimeout(500);
  chk(/#arquitetos$/.test(page.url()), '"Ver arquitetos" leva à lista de arquitetos');
  chk(erros.length === 0, 'sem erro no console' + (erros.length ? ': ' + erros.join(' | ') : ''));
  console.log(linhas.join('\n')); console.log(prob.length ? `${prob.length} FALHA(S)` : 'TUDO OK');
  await b.close(); process.exit(prob.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1) });
