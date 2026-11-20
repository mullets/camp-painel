// CAMP-EMAIL 20/11/2026 · e-mails num lugar só (Rafael: "Todos os e-mails num lugar só, não achei nem esse onde estão"): um item "E-mails"
// sempre à vista em Administração (tecla E), uma tela com três abas — Enviados (#emails), Modelos do Sender (#emails/modelos) e Quem aceita
// e-mails (#emails/aceite) —, abas pelo teclado (← → Home End), endereços antigos #emkt e #emailsite levam à aba certa, a tecla Y ficou livre,
// operador não vê nada (403 nas rotas).  Uso: CHROME=/opt/pw-browsers/chromium bash tests/rodar_um.sh tests/navegador_emails_abas.js
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
const login = (pg, email, senha) => pg.evaluate(([e, s]) => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: e, senha: s }) }).then(r => r.status), [email, senha]);
const lado = pg => pg.evaluate(() => { const m = document.querySelector('.main'); return Math.max(m.scrollWidth - m.clientWidth, document.scrollingElement.scrollWidth - innerWidth) });
// a aba aberta: [hash, aba selecionada, painel visível, quantos painéis visíveis]
const estado = pg => pg.evaluate(() => {
  const sel = [...document.querySelectorAll('#em-abas-tela [role="tab"]')].filter(b => b.getAttribute('aria-selected') === 'true').map(b => b.dataset.emTela);
  const vis = ['em-p-enviados', 'em-p-modelos', 'em-p-aceite'].filter(id => { const p = document.getElementById(id); return p && !p.hidden });
  return { hash: location.hash, sel: sel.join(','), vis: vis.join(','), on: !!document.querySelector('#v-emails.on') } });
const espera = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const br = await chromium.launch({ executablePath: process.env.CHROME || undefined }); const erros = [];
  const pg = await (await br.newContext({ viewport: { width: 1366, height: 900 }, colorScheme: 'light' })).newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/'); await login(pg, 'rafael@camp.arq.br', 'senha-bem-longa-123');
  await pg.goto(BASE + '/#painel'); await pg.reload(); await pg.waitForTimeout(1200);
  // 1) menu: um item só, "E-mails", à vista (fora do "Mais"), em Administração, tecla E; sem o item próprio de Quem aceita
  const menu = await pg.evaluate(() => {
    const b = document.querySelector('#nav button[data-v="emails"]'); if (!b) return null;
    let g = b.previousElementSibling; while (g && !g.classList.contains('grp')) g = g.previousElementSibling;
    return { nome: [...b.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim(), sec: b.classList.contains('nav-sec'), visivel: !!b.offsetParent,
      grupo: g && g.textContent.trim(), kbd: (b.querySelector('kbd') || {}).textContent, emkt: !!document.querySelector('#nav [data-v="emkt"],#nav [data-v="emailsite"]'),
      outros: [...document.querySelectorAll('#nav button')].filter(x => /e-mail/i.test(x.textContent)).length } });
  chk(menu && menu.nome === 'E-mails' && !menu.sec && menu.visivel, 'menu: item "E-mails" à vista, fora do "Mais"', JSON.stringify(menu));
  chk(menu && menu.grupo === 'Administração' && menu.kbd === 'E', 'menu: em Administração, tecla E', JSON.stringify(menu));
  chk(menu && !menu.emkt && menu.outros === 1, 'menu: um item de e-mail só (sem "Quem aceita e-mails da CAMP")', JSON.stringify(menu));
  // 2) tecla E abre E-mails na aba Enviados; Y não faz nada
  await pg.evaluate(() => document.activeElement && document.activeElement.blur()); await pg.keyboard.press('e'); await pg.waitForTimeout(900);
  let s = await estado(pg);
  chk(s.on && s.hash === '#emails' && s.sel === 'enviados' && s.vis === 'em-p-enviados', 'tecla E: E-mails, aba Enviados', JSON.stringify(s));
  chk(await pg.$eval('#v-emails h1', e => e.childNodes[0].textContent.trim()) === 'E-mails', 'título da tela: E-mails');
  const nomes = await pg.$$eval('#em-abas-tela [role="tab"]', bs => bs.map(b => b.textContent.trim()));
  chk(JSON.stringify(nomes) === JSON.stringify(['Enviados', 'Modelos do Sender', 'Quem aceita e-mails']), 'três abas: Enviados, Modelos do Sender, Quem aceita e-mails', JSON.stringify(nomes));
  chk(await pg.$eval('#em-abas-tela', t => t.getAttribute('role') === 'tablist' && [...t.querySelectorAll('[role="tab"]')].every(b => document.getElementById(b.getAttribute('aria-controls'))?.getAttribute('role') === 'tabpanel')).catch(() => false), 'abas acessíveis: tablist, tab → tabpanel');
  await pg.waitForSelector('#em-lista [data-em-abrir], #em-lista .empty', { timeout: 8000 }).catch(() => {});
  chk(await pg.$$eval('#em-lista [data-em-abrir]', l => l.length) > 0, 'aba Enviados carrega a lista');
  await pg.goto(BASE + '/#painel'); await pg.waitForTimeout(500); await pg.evaluate(() => document.activeElement && document.activeElement.blur());
  await pg.keyboard.press('y'); await pg.waitForTimeout(700);
  chk((await pg.evaluate(() => location.hash)) === '#painel', 'tecla Y ficou livre (não abre nada)', await pg.evaluate(() => location.hash));
  // 3) clique na aba
  await pg.goto(BASE + '/#emails'); await pg.waitForTimeout(800);
  await pg.click('#em-tab-modelos', { timeout: 2000 }).catch(() => {}); await pg.waitForTimeout(900);
  s = await estado(pg);
  chk(s.hash === '#emails/modelos' && s.sel === 'modelos' && s.vis === 'em-p-modelos', 'clique em Modelos do Sender: #emails/modelos', JSON.stringify(s));
  await pg.waitForSelector('#es-lista tr td', { timeout: 8000 }).catch(() => {});
  chk(!/^\s*Carregando…\s*$/.test(await pg.$eval('#es-lista', t => t.textContent).catch(() => 'Carregando…')), 'aba Modelos do Sender carrega (ou explica o que falta)');
  // 4) teclado: → ← Home End, o foco acompanha
  await pg.focus('#em-tab-modelos').catch(() => {}); await pg.keyboard.press('ArrowRight'); await pg.waitForTimeout(900);
  s = await estado(pg);
  chk(s.hash === '#emails/aceite' && s.sel === 'aceite' && s.vis === 'em-p-aceite' && await pg.evaluate(() => document.activeElement.id) === 'em-tab-aceite', '→: Quem aceita e-mails, com o foco na aba', JSON.stringify(s));
  await pg.waitForSelector('#ek-lista tr td', { timeout: 8000 }).catch(() => {});
  chk(!/^\s*Carregando…\s*$/.test(await pg.$eval('#ek-lista', t => t.textContent).catch(() => 'Carregando…')), 'aba Quem aceita e-mails carrega');
  await pg.keyboard.press('ArrowRight'); await pg.waitForTimeout(900); s = await estado(pg);
  chk(s.hash === '#emails' && s.sel === 'enviados' && await pg.evaluate(() => document.activeElement.id) === 'em-tab-enviados', '→ na última volta para Enviados', JSON.stringify(s));
  await pg.keyboard.press('ArrowLeft'); await pg.waitForTimeout(900); s = await estado(pg);
  chk(s.hash === '#emails/aceite' && s.sel === 'aceite', '← na primeira vai para a última', JSON.stringify(s));
  await pg.keyboard.press('Home'); await pg.waitForTimeout(900); s = await estado(pg);
  chk(s.sel === 'enviados', 'Home: primeira aba', JSON.stringify(s));
  await pg.keyboard.press('End'); await pg.waitForTimeout(900); s = await estado(pg);
  chk(s.sel === 'aceite', 'End: última aba', JSON.stringify(s));
  chk(await pg.$$eval('#em-abas-tela [role="tab"]', bs => bs.map(b => b.tabIndex).join(',')).catch(() => '') === '-1,-1,0', 'só a aba aberta entra no Tab (tabindex 0)');
  // 5) Voltar do navegador volta para a aba anterior
  await pg.goBack(); await pg.waitForTimeout(900); s = await estado(pg);
  chk(s.sel === 'enviados' && s.hash === '#emails', 'Voltar do navegador volta para a aba anterior', JSON.stringify(s));
  // 6) endereço direto e endereços antigos
  for (const [url, hash, aba] of [['/#emails/aceite', '#emails/aceite', 'aceite'], ['/#emails/modelos', '#emails/modelos', 'modelos'], ['/#emkt', '#emails/aceite', 'aceite'], ['/#emailsite', '#emails/modelos', 'modelos'], ['/#emails/xyz', '#emails/xyz', 'enviados']]) {
    await pg.goto(BASE + '/#painel'); await pg.goto(BASE + url); await pg.reload(); await pg.waitForTimeout(1300); s = await estado(pg);
    chk(s.on && s.hash === hash && s.sel === aba && s.vis === 'em-p-' + aba, `endereço ${url} abre a aba ${aba}${url !== hash ? ' (' + hash + ')' : ''}`, JSON.stringify(s));
  }
  await pg.goto(BASE + '/#painel'); await pg.waitForTimeout(400); await pg.evaluate(() => { location.hash = '#emkt' }); await pg.waitForTimeout(900); s = await estado(pg);
  chk(s.hash === '#emails/aceite' && s.sel === 'aceite', 'link antigo #emkt dentro do painel leva à aba Quem aceita e-mails', JSON.stringify(s));
  chk(/Administração/.test(await pg.$eval('#gcrumb', e => e.textContent).catch(() => '')) && /E-mails/.test(await pg.$eval('#gcrumb', e => e.textContent).catch(() => '')), 'trilha: Administração › E-mails');
  // 7) F foca o filtro da aba aberta
  await pg.evaluate(() => document.activeElement && document.activeElement.blur()); await pg.keyboard.press('f'); await pg.waitForTimeout(200);
  chk(await pg.evaluate(() => document.activeElement.id) === 'ek-q', 'F foca o filtro da aba aberta', await pg.evaluate(() => document.activeElement.id));
  // 8) celular
  const cel = await (await br.newContext({ viewport: { width: 390, height: 800 } })).newPage();
  cel.on('pageerror', e => erros.push('pageerror (390): ' + e.message));
  await cel.goto(BASE + '/'); await login(cel, 'rafael@camp.arq.br', 'senha-bem-longa-123'); await cel.goto(BASE + '/#emails/aceite'); await cel.reload(); await cel.waitForTimeout(1500);
  chk(await lado(cel) <= 0, '390 px: a tela não rola de lado', String(await lado(cel)));
  // 9) operador: não vê o item e nada abre; 403 nas três rotas
  const op = await (await br.newContext({ viewport: { width: 1366, height: 900 } })).newPage();
  await op.goto(BASE + '/'); await login(op, 'operador@camp.arq.br', 'senha-operador-123'); await op.reload(); await op.waitForTimeout(1200);
  chk(!(await op.$eval('#nav button[data-v="emails"]', b => !!b.offsetParent && !b.hidden).catch(() => false)), 'operador: sem o item E-mails no menu');
  const st = await op.evaluate(() => Promise.all(['/api/emails', '/api/emails-site', '/api/contatos-email'].map(u => fetch(u).then(r => r.status))));
  chk(st.every(x => x === 403), 'operador: 403 em /api/emails, /api/emails-site e /api/contatos-email', JSON.stringify(st));
  for (const u of ['/#emails', '/#emails/modelos', '/#emails/aceite', '/#emkt', '/#emailsite']) {
    await op.goto(BASE + u); await op.waitForTimeout(700);
    chk(!(await op.$eval('#v-emails', e => e.classList.contains('on'))), `operador: ${u} não abre a tela`);
  }
  chk(!erros.length, 'sem erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
