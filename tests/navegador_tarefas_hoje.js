// Dashboard "Tarefas de hoje" no navegador de verdade (Playwright + Chromium): fila com "Melhorar a base", "Agora não",
// qualidade da base (painel inicial e página do fundo), melhorias por pessoa, ficha do arquiteto pela rota, celular, e NENHUM erro no console.
// Uso: suba a API com o banco de tests/semear_banco_teste.py e rode
//   CAMP_BASE=http://127.0.0.1:8880 CHROMIUM=/opt/pw-browsers/chromium-1194/chrome-linux/chrome NODE_PATH=$(npm root -g) node tests/navegador_tarefas_hoje.js
const {chromium} = require('playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8880';
const problemas = [], oks = [];
const ok = (cond, msg) => (cond ? oks : problemas).push(msg);

(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM || undefined});
  const ctx = await browser.newContext({viewport: {width: 1366, height: 900}});
  const page = await ctx.newPage();
  const erros = [];
  // conhecidos e fora deste cartão: o 401 de /api/auth/eu ANTES do login (é assim que a tela descobre que precisa entrar) e o /favicon.ico que o painel não tem
  const ESPERADO = m => /\[\/api\/auth\/eu\]$|\[\/favicon\.ico\]$/.test(m);
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO('[' + ((m.location() || {}).url || '').replace(BASE, '') + ']')) erros.push('console.error: ' + m.text() + ' [' + ((m.location() || {}).url || '').replace(BASE, '') + ']'); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  const falhas = []; page.on('response', r => { if (r.status() >= 400) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  const api = async (url, opt = {}) => page.evaluate(async ([u, o]) => { const r = await fetch(u, {credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, ...o}); return {status: r.status, json: await r.json().catch(() => null)}; }, [url, opt]);

  await page.goto(BASE + '/');
  await page.fill('#lg-email', 'rafael@camp.arq.br');
  await page.fill('#lg-senha', 'senha-bem-longa-123');
  await page.press('#lg-senha', 'Enter');
  await page.waitForSelector('#ini-qualidade .qb-geral', {timeout: 15000});

  // ---- fila única: grupo "Melhorar a base" com "Agora não" ----
  const grupo = page.locator('[data-ini-grupo="base"]');
  ok(await grupo.count() === 1, 'painel inicial: grupo "Melhorar a base" em "O que fazer agora"');
  ok(/fundos sem sigla|arquitetos sem fonte/.test(await grupo.locator('.ini-tipos').innerText()), 'o grupo diz quanto falta de cada tipo');
  const adiar = grupo.locator('[data-ini-adiar]').first();
  const id = await adiar.getAttribute('data-ini-adiar');
  ok(!!id, 'cada tarefa da base tem o botão "Agora não" (' + id + ')');
  await adiar.click();
  await page.waitForFunction(() => /Escondida por 7 dias/.test(document.getElementById('toast').textContent), null, {timeout: 8000});
  await page.waitForFunction(i => !document.querySelector(`[data-ini-adiar="${i}"]`) && document.querySelector('#ini-qualidade .qb-geral'), id, {timeout: 8000});
  ok(true, '"Agora não": aviso de 7 dias e a tarefa some da tela');
  const hj = await api('/api/hoje');
  ok(!hj.json.acoes.some(a => a.id === id), 'e some também da fila do servidor (/api/hoje) para esta pessoa');

  // ---- qualidade da base (visão geral) ----
  const qb = await page.locator('#ini-qualidade').innerText();
  ok(/\d+(,\d)?%/.test(qb) && /Com imagem/.test(qb) && /Com código completo/.test(qb) && /Com título/.test(qb) && /Com direitos definidos/.test(qb), 'visão geral: índice e as 4 medidas em %');
  ok(await page.locator('#ini-qualidade progress').count() === 4, 'as 4 medidas em barras (sem estilo inline)');
  ok(await page.locator('#ini-qualidade .qb-fundos [data-ini-rota^="fundo/"]').count() > 0, 'lista dos fundos que mais precisam de cuidado, cada um leva à página do fundo');

  // ---- corrigir uma tarefa: some da fila e conta como melhoria de hoje ----
  const sig = hj.json.acoes.find(a => a.id && a.id.startsWith('q_sigla_') && a.id !== id);
  if (sig) {
    const cod = sig.id.replace('q_sigla_', '');
    const antes = ((await api('/api/melhorias')).json.pessoas.find(x => x.nome === 'Rafael') || {hoje: 0}).hoje;
    const r = await api('/api/fundos/' + cod, {method: 'PATCH', body: JSON.stringify({sigla: 'Q' + String.fromCharCode(65 + Math.floor(Math.random() * 26), 65 + Math.floor(Math.random() * 26))})});
    ok(r.status === 200, 'dar a sigla ao fundo ' + cod + ' (HTTP ' + r.status + ')');
    await page.evaluate(() => carregarPainel());
    await page.waitForFunction(i => !document.querySelector(`[data-ini-adiar="${i}"]`) && /Rafael/.test(document.getElementById('ini-melhorias').textContent), sig.id, {timeout: 8000}).catch(() => {});
    ok(!(await page.locator(`[data-ini-adiar="${sig.id}"]`).count()), 'corrigida, a tarefa "fundo sem sigla" sai da fila');
    const mh = await page.locator('#ini-melhorias').innerText();
    ok(new RegExp('Rafael\\s*' + (antes + 1) + '\\s*hoje').test(mh), `Melhorias de hoje: Rafael aparece com ${antes + 1} correção(ões) hoje (era ${antes})`);
  } else problemas.push('o banco de teste não tem fundo sem sigla para corrigir');

  // ---- a tarefa leva à tela onde se corrige ----
  const bt = page.locator('[data-ini-grupo="base"] .ini-task:has([data-ini-adiar^="q_sigla_"]) [data-ini-acao], [data-ini-grupo="base"] .ini-task:has([data-ini-adiar^="q_proj_"]) [data-ini-acao]').first();
  const rotulo = await bt.innerText();
  await bt.click();
  await page.waitForFunction(() => !location.hash.startsWith('#painel') && location.hash.length > 1, null, {timeout: 8000});
  ok(true, `"${rotulo}" leva à tela de correção (${await page.evaluate(() => location.hash)})`);

  // ---- página do fundo ----
  await page.evaluate(() => nav('fundo/F026'));
  await page.waitForFunction(() => { const c = document.querySelector('#fd .dethdr .code'), q = document.getElementById('fd-qualidade'); return c && c.textContent === 'F026' && q && !/Carregando/.test(q.textContent); }, null, {timeout: 10000});
  const fd = await page.locator('#fd-qualidade').innerText();
  ok(/Qualidade das folhas/.test(fd) && /%/.test(fd) && /Com título/.test(fd), 'página do fundo: índice de qualidade com as 4 medidas');

  // ---- ficha do arquiteto pela rota da tarefa ----
  const ag = (await api('/api/hoje')).json.acoes.find(a => a.id.startsWith('q_agente_'));
  if (ag) {
    await page.evaluate(r => nav(r), ag.rota);
    await page.waitForFunction(() => document.querySelector('main') && document.getElementById('ea-fonte'), null, {timeout: 8000});
    ok(true, 'a tarefa "arquiteto sem fonte" abre a ficha dele, no campo da fonte');
    await page.evaluate(() => closeDrawer(true));
  }

  // ---- celular: sem rolagem lateral ----
  await page.setViewportSize({width: 390, height: 800});
  await page.evaluate(() => nav('painel'));
  await page.waitForSelector('#ini-melhorias', {timeout: 10000});
  const larg = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  ok(larg[0] <= larg[1] + 1, `celular (390 px): sem rolagem lateral (${larg[0]} ≤ ${larg[1]})`);

  const tela = await page.locator('#v-painel').innerText();
  for (const ruim of ['undefined', 'NaN', '[object Object]', 'null%']) ok(!tela.includes(ruim), `painel sem "${ruim}" na tela`);
  console.log('  (respostas 4xx: ' + (falhas.join(', ') || 'nenhuma') + ')');
  ok(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.join(' | ') : ''));
  await browser.close();
  oks.forEach(m => console.log('  ok    ' + m));
  problemas.forEach(m => console.log('  FALHA ' + m));
  console.log(problemas.length ? `${problemas.length} FALHA(S)` : 'TUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
