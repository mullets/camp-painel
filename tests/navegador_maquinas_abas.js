// UX-24 no navegador de verdade (Playwright + Chromium): Máquinas em abas "Agora" | "Alertas" | "Logs".
// Prova: o operador abre Máquinas e vê SÓ "Agora" (Preservação e "Como está agora"; sem abas, sem alertas, sem logs, sem painéis técnicos);
// o admin vê as 3 abas; o interruptor "Resumo do dia" grava alertas.resumo_diario no banco (sem a tela pedir para editar chave);
// fora do horário de trabalho as estações desligadas ficam recolhidas em "N desligadas (normal)". Nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux24.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux24.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8952)
//   CAMP_DB_PATH=/tmp/ux24.db CAMP_BASE=http://127.0.0.1:8952 node tests/navegador_maquinas_abas.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8952', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || undefined;
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const cfg = k => py(`r=con.execute("SELECT valor FROM configuracao WHERE chave=?",("${k}",)).fetchone();print(r[0] if r else '')`);
py(`con.execute("UPDATE configuracao SET valor='0' WHERE chave='alertas.resumo_diario'")
con.execute("UPDATE configuracao SET valor='' WHERE chave='alertas.resumo_email'")
con.execute("UPDATE configuracao SET valor='rafael@camp.arq.br' WHERE chave='avisos.email'")`);   // estado inicial: pode rodar de novo no mesmo banco
const DOMINGO_NOITE = new Date('2026-10-25T22:00:00');   // fora do horário de trabalho (seg. a sex., 8h às 19h)

(async () => {
  const browser = await chromium.launch(CHROME ? { executablePath: CHROME } : {});
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=|\/api\/analytics/.test(u);
  async function entrar(email, senha) {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    await ctx.route('**/*', rt => rt.request().url().startsWith(BASE) ? rt.continue() : rt.fulfill({ status: 200, contentType: 'text/css', body: '' }));
    const page = await ctx.newPage();
    await page.clock.setFixedTime(DOMINGO_NOITE);
    page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(email + ': ' + m.text()); });
    page.on('pageerror', e => erros.push(email + ' pageerror: ' + e.message));
    page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(email + ' ' + r.status() + ' ' + r.url().replace(BASE, '')); });
    await page.goto(BASE + '/');
    await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    return { ctx, page };
  }
  const vis = (page, sel) => page.evaluate(s => { const e = document.querySelector(s); return !!e && !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length); }, sel);
  try {
    // ---- operador: só "Agora" ----
    const op = await entrar('operador@camp.arq.br', 'senha-operador-123');
    await op.page.evaluate(() => go('estacoes'));
    await op.page.waitForSelector('#est-hoje', { timeout: 30000 }); await op.page.waitForTimeout(2500);
    chk(await op.page.evaluate(() => rotaAtual().split('/')[0] === 'estacoes') && await vis(op.page, '#v-estacoes'), 'operador abre Máquinas (antes: "Sem acesso")');
    chk(await vis(op.page, '#est-hoje') && await vis(op.page, '#preservacao'), 'operador vê "Como está agora" e a Preservação (aba Agora)');
    chk(!(await vis(op.page, '#est-abas')) && !(await vis(op.page, '#logs-panel')) && await op.page.$('#al-painel') === null && await op.page.$('#avpref-painel') === null, 'operador não vê as abas, os alertas nem os logs');
    chk(await op.page.$('#qnap-card') === null && await op.page.$('.est-tecnico') === null && await op.page.$('#bk-painel') === null, 'operador não vê os painéis técnicos (QNAP detalhado, backup, detalhes técnicos)');
    await op.page.evaluate(() => go('estacoes/logs')); await op.page.waitForTimeout(1200);
    chk(await vis(op.page, '#est-hoje') && !(await vis(op.page, '#logs-panel')), 'operador em #estacoes/logs continua só na aba Agora');
    chk(!(await vis(op.page, '#nav button[data-v="estacoes"]')), 'o menu do operador continua sem Máquinas (CAMP-154)');
    const g = await op.ctx.request.get(BASE + '/api/logs'), a = await op.ctx.request.get(BASE + '/api/alertas'), w = await op.ctx.request.put(BASE + '/api/alertas/preferencias', { data: { resumo: { ligado: true } } });
    chk(g.status() === 403 && a.status() === 403 && w.status() === 403 && cfg('alertas.resumo_diario') === '0', 'operador: /api/logs, /api/alertas e gravar o resumo dão 403 (nada gravado)');
    const txtOp = await op.page.evaluate(() => document.getElementById('v-estacoes').innerText);
    chk(!/alertas\.resumo|resumo_diario|mude "/.test(txtOp), 'a tela do operador não pede para editar chave');
    await op.ctx.close();

    // ---- admin: 3 abas ----
    const ad = await entrar('rafael@camp.arq.br', 'senha-bem-longa-123');
    await ad.page.evaluate(() => nav('estacoes'));
    await ad.page.waitForSelector('#est-hoje', { timeout: 30000 });
    const abas = await ad.page.$$eval('#est-abas [data-est-aba]', l => l.filter(b => b.offsetWidth).map(b => b.textContent.trim()));
    chk(abas.join('|') === 'Agora|Alertas|Logs', 'admin vê as 3 abas: ' + abas.join('|'));
    chk(await vis(ad.page, '#est-hoje') && !(await vis(ad.page, '#est-alertas')) && !(await vis(ad.page, '#logs-panel')), 'abre na aba Agora');
    const desl = await ad.page.evaluate(() => { const d = document.getElementById('est-desligadas'); return d ? { s: d.querySelector('summary').textContent.trim(), aberto: d.open, n: d.querySelectorAll('.est-lista>li').length, foraNaLista: [...document.querySelectorAll('#est-hoje > .est-lista>li')].some(li => /normal fora do horário/.test(li.textContent)) } : null; });
    chk(desl && /^\d+ desligadas? \(normal\)$/.test(desl.s) && !desl.aberto && desl.n === +desl.s.split(' ')[0] && !desl.foraNaLista, 'fora do horário: desligadas recolhidas em "N desligadas (normal)", fechado: ' + JSON.stringify(desl));
    await ad.page.click('#est-abas [data-est-aba="alertas"]');
    await ad.page.waitForSelector('#al-painel #al-resumo-liga', { timeout: 30000 });
    chk(await vis(ad.page, '#al-painel') && !(await vis(ad.page, '#est-hoje')), 'aba Alertas: mostra os alertas e esconde o Agora');
    const tAl = await ad.page.evaluate(() => document.getElementById('est-alertas').innerText);
    chk(!/alertas\.resumo|resumo_diario|resumo_email/.test(tAl) && /Mandar todo dia às 18h um e-mail com o resumo do dia/.test(tAl), 'o resumo do dia é um interruptor com rótulo, sem chave crua');
    chk(await ad.page.$eval('#al-resumo-liga', c => !c.checked && c.getAttribute('role') === 'switch'), 'o interruptor começa desligado (como no banco)');
    await ad.page.click('#al-resumo-liga');
    await ad.page.waitForFunction(() => /Resumo do dia ligado/.test(document.body.innerText), null, { timeout: 10000 });
    await ad.page.waitForTimeout(800);
    chk(cfg('alertas.resumo_diario') === '1', 'ligar o interruptor grava alertas.resumo_diario=1 no banco');
    chk(await ad.page.$eval('#al-resumo-liga', c => c.checked) && /ligado/.test(await ad.page.textContent('#al-resumo-estado')), 'depois de gravar a tela mostra "ligado"');
    await ad.page.fill('#al-resumo-email', 'equipe@camp.arq.br'); await ad.page.click('#al-resumo-salvar');
    await ad.page.waitForFunction(() => /E-mail do resumo salvo/.test(document.body.innerText), null, { timeout: 10000 }); await ad.page.waitForTimeout(800);
    chk(cfg('alertas.resumo_email') === 'equipe@camp.arq.br' && /equipe@camp\.arq\.br/.test(await ad.page.textContent('#al-resumo-estado')), 'o e-mail do resumo é gravado e aparece na frase');
    await ad.page.click('#al-resumo-liga');
    await ad.page.waitForFunction(() => /Resumo do dia desligado/.test(document.body.innerText), null, { timeout: 10000 }); await ad.page.waitForTimeout(600);
    chk(cfg('alertas.resumo_diario') === '0', 'desligar grava 0');
    await ad.page.click('#est-abas [data-est-aba="logs"]');
    await ad.page.waitForFunction(() => { const c = document.getElementById('log-cnt'); return c && /registros/.test(c.textContent); }, null, { timeout: 15000 });
    chk(await vis(ad.page, '#logs-panel') && !(await vis(ad.page, '#al-painel')) && !(await vis(ad.page, '#est-hoje')), 'aba Logs: mostra os logs técnicos e esconde o resto');
    await ad.page.click('#est-abas [data-est-aba="agora"]');
    chk(await vis(ad.page, '#est-hoje') && !(await vis(ad.page, '#logs-panel')), 'voltar para Agora');
    await ad.page.setViewportSize({ width: 390, height: 844 }); await ad.page.waitForTimeout(300);
    chk(await ad.page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'no celular (390 px) a tela não rola para o lado');
    await ad.ctx.close();
  } catch (e) { chk(false, 'o teste quebrou: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma resposta de erro do servidor' + (falhas.length ? ': ' + falhas.slice(0, 5).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
