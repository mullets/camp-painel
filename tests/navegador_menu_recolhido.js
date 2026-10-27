// UX-28 · menu RECOLHIDO (barra estreita só com ícones) e atalhos de teclado com o menu recolhido e expandido (Playwright, Chromium de verdade).
// Pedido do Rafael: "arrume os atalhos de teclado.. quando eu fecho o menu lateral fica todo quebrado".
// Servidor PRÓPRIO, nunca a 8765:
//   CAMP_DB_PATH=/tmp/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8992)
//   CAMP_BASE=http://127.0.0.1:8992 node tests/navegador_menu_recolhido.js
// Confere, em 1440×900 e 1280×800: largura da barra; nenhum texto do menu visível fora do ícone/dica (títulos de grupo viram linha fina,
// contador vira bolinha, tecla e rodapé de versão somem); sem rolagem horizontal; ícones centralizados; dica com nome + tecla no mouse e no
// foco; cada item leva à página certa; o estado fica lembrado; TODAS as teclas do menu, ⌘/Ctrl+K, [, ?, J/K das listas (UX-32) e o K da
// conferência (UX-44) funcionam recolhido e expandido.
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8992';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const SHOTS = process.env.CAMP_SHOTS || '';
const linhas = [], prob = [], erros = [];
const chk = (ok, m) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + m); if (!ok) prob.push(m) };
const rota = pg => pg.evaluate(() => rotaAtual().split('/')[0]);
const recolhido = pg => pg.evaluate(() => document.querySelector('.app').classList.contains('collapsed'));
const tecla = async (pg, k) => { await pg.evaluate(() => document.activeElement && document.activeElement.blur && document.activeElement.blur()); await pg.keyboard.press(k); await pg.waitForTimeout(300) };

// mede a barra recolhida: devolve a lista do que está errado (vazia = ok)
const medir = pg => pg.evaluate(() => {
  const ruim = [], side = document.querySelector('.side'), nav = document.getElementById('nav'), sr = side.getBoundingClientRect();
  if (sr.width > 72 || sr.width < 48) ruim.push('largura da barra ' + Math.round(sr.width) + 'px (esperado ~64)');
  if (getComputedStyle(side).overflowX !== 'visible' && side.scrollWidth > side.clientWidth + 1) ruim.push(`a barra rola na horizontal (${side.scrollWidth} > ${side.clientWidth})`);
  { const cb = document.getElementById('collapse'), r = cb.getBoundingClientRect(), e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); if (!e || !cb.contains(e)) ruim.push('o botão de expandir ficou escondido/cortado') }
  if (nav.scrollWidth > nav.clientWidth + 1) ruim.push(`o menu rola na horizontal (${nav.scrollWidth} > ${nav.clientWidth})`);
  if (document.documentElement.scrollWidth > innerWidth + 1) ruim.push('a página rola na horizontal');
  // texto visível dentro da barra (fora o selo "CAMP" do logotipo)
  const w = document.createTreeWalker(side, NodeFilter.SHOW_TEXT);
  for (let n; (n = w.nextNode());) {
    const t = n.textContent.trim(), el = n.parentElement; if (!t || el.closest('.brand .mark') || el.closest('[hidden]')) continue;
    const cs = getComputedStyle(el); if (parseFloat(cs.fontSize) < 1 || cs.visibility === 'hidden' || +cs.opacity === 0) continue;
    const rg = document.createRange(); rg.selectNodeContents(n); const r = rg.getBoundingClientRect();
    if (r.width >= 1 && r.height >= 1) ruim.push(`texto visível na barra: "${t.slice(0, 30)}" (${cs.fontSize}, ${el.tagName.toLowerCase()}${el.className ? '.' + el.className : ''})`);
  }
  for (const b of nav.querySelectorAll(':scope > button')) {
    if (!b.offsetParent) continue; const br = b.getBoundingClientRect(), sv = b.querySelector('svg'), s = sv && sv.getBoundingClientRect(), nome = b.dataset.v || b.id;
    if (!s || s.width < 10) { ruim.push(`"${nome}" sem ícone visível`); continue }
    if (Math.abs((s.left + s.width / 2) - (br.left + br.width / 2)) > 2) ruim.push(`ícone de "${nome}" fora do centro`);
    if (s.left < sr.left || s.right > sr.right) ruim.push(`ícone de "${nome}" fora da barra`);
    if (b.scrollWidth > b.clientWidth + 1) ruim.push(`"${nome}" vaza (${b.scrollWidth} > ${b.clientWidth})`);
    const n = b.querySelector('.n:not([hidden])');
    if (n) { const nr = n.getBoundingClientRect(); if (nr.width > 10 || nr.height > 10 || nr.width < 4) ruim.push(`contador de "${nome}" não é bolinha (${Math.round(nr.width)}×${Math.round(nr.height)})`);
      if (nr.right > br.right || nr.top < br.top - 1) ruim.push(`bolinha de "${nome}" fora do botão`) }
    if (br.height > 48) ruim.push(`"${nome}" alto demais (${Math.round(br.height)}px: o nome quebrou em linhas?)`);
  }
  for (const g of nav.querySelectorAll('.grp')) { if (!g.offsetParent) continue; const r = g.getBoundingClientRect(); if (r.height > 2) ruim.push(`título de grupo "${g.textContent.trim()}" não virou linha fina (${Math.round(r.height)}px)`) }
  { const mk = document.querySelector('.brand .mark'); if (mk && mk.scrollWidth > mk.clientWidth + 1) ruim.push('o selo CAMP vaza da caixa') }
  const ft = document.getElementById('foot'); if (ft && ft.offsetParent) ruim.push('rodapé de versão aparece');
  return ruim;
});
const dica = pg => pg.evaluate(() => { const d = document.getElementById('nav-dica'); if (!d || d.hidden) return null; const r = d.getBoundingClientRect(); if (r.width < 1 || getComputedStyle(d).display === 'none') return null; return { t: d.textContent.replace(/\s+/g, ' ').trim(), kbd: (d.querySelector('kbd') || {}).textContent || '', x: r.left, w: r.width } });

(async () => {
  const b = await chromium.launch({ executablePath: CHROME });
  for (const [W, H] of [[1440, 900], [1280, 800]]) {
    const tam = `${W}×${H}`;
    const ctx = await b.newContext({ viewport: { width: W, height: H } });
    await ctx.route('**/*', rt => rt.request().url().startsWith(BASE) ? rt.continue() : rt.abort());
    const r = await ctx.request.post(BASE + '/api/auth/login', { data: { email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' } });
    chk(r.ok(), `${tam} login admin`);
    const page = await ctx.newPage();
    page.on('console', m => { if (m.type() === 'error' && !/net::ERR_FAILED|Failed to load resource/.test(m.text())) erros.push(m.text()) });
    page.on('pageerror', e => erros.push('pageerror: ' + e.message));
    await page.goto(BASE + '/#painel');
    await page.evaluate(() => { try { localStorage.removeItem('camp.side'); localStorage.removeItem('camp.nav.mais') } catch (_) {} });
    await page.reload(); await page.waitForTimeout(1800);
    const NA = await page.evaluate(() => NAV_ATALHOS);

    // 1) expandido: como antes (largura cheia, nomes à vista, nenhuma dica flutuante)
    chk(!(await recolhido(page)), `${tam} começa expandido`);
    const larg0 = await page.$eval('.side', e => e.getBoundingClientRect().width);
    chk(larg0 > 200, `${tam} expandido: barra larga (${Math.round(larg0)}px)`);
    chk(await page.$eval('#nav button[data-v="solicitacoes"]', e => getComputedStyle(e).fontSize !== '0px' && e.getBoundingClientRect().width > 150), `${tam} expandido: nomes à vista`);
    await page.hover('#nav button[data-v="projetos"]'); await page.waitForTimeout(150);
    chk(!(await dica(page)), `${tam} expandido: sem dica flutuante (o nome já está à vista)`);

    // 2) recolher pelo botão "‹"
    await page.click('#collapse'); await page.waitForTimeout(300);
    chk(await recolhido(page), `${tam} o botão "‹" recolhe o menu`);
    chk(/Expandir menu/.test(await page.getAttribute('#collapse', 'aria-label') || ''), `${tam} recolhido: o botão diz "Expandir menu"`);
    let ruim = await medir(page);
    chk(!ruim.length, `${tam} recolhido ("Mais" fechado): só ícones, sem texto vazando, sem rolagem horizontal${ruim.length ? ': ' + ruim.join(' | ') : ''}`);
    await page.click('#nav-mais-pc'); await page.waitForTimeout(300);
    ruim = await medir(page);
    chk(!ruim.length, `${tam} recolhido ("Mais" aberto, todos os grupos): só ícones, títulos de grupo em linha fina${ruim.length ? ': ' + ruim.join(' | ') : ''}`);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/menu_recolhido_${W}.png` });

    // 3) dica: nome + tecla, no mouse e no foco pelo teclado; some ao sair
    const nomes = await page.$$eval('#nav > button', bs => bs.filter(b => b.offsetParent).map(b => [b.dataset.v || b.id, [...b.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim()]));
    let dicasOk = 0;
    for (const [v, nome] of nomes) {
      const sel = /^nav-/.test(v) ? '#' + v : `#nav button[data-v="${v}"]`;
      await page.hover(sel); await page.waitForTimeout(60);
      const d = await dica(page), k = NA[v] || (v === 'nav-busca' ? '⌘/Ctrl + K' : '');
      const ok = d && d.t.startsWith(nome) && d.kbd === k && d.x > 60;
      if (ok) dicasOk++; else chk(false, `${tam} dica de "${v}" no mouse: esperado "${nome}" + tecla "${k}", veio ${JSON.stringify(d)}`);
    }
    chk(dicasOk === nomes.length, `${tam} dica no mouse com nome + tecla em ${dicasOk}/${nomes.length} itens (ex.: "Pedidos de alta resolução 4", "Qualidade do CAMP Vision Q", "Busca ⌘/Ctrl + K")`);
    await page.mouse.move(W - 20, H - 20); await page.waitForTimeout(100);
    chk(!(await dica(page)), `${tam} a dica some quando o mouse sai do menu`);
    await page.focus('#nav button[data-v="estacoes"]'); await page.waitForTimeout(100);
    const df = await dica(page);
    chk(df && df.t.startsWith('Máquinas') && df.kbd === '5', `${tam} dica também no foco pelo teclado (Tab): ${JSON.stringify(df)}`);
    await page.evaluate(() => document.activeElement.blur()); await page.waitForTimeout(100);
    chk(!(await dica(page)), `${tam} a dica some quando o foco sai`);
    const cont = await page.$$eval('#nav button .n:not([hidden])', ns => ns.map(n => n.closest('button').dataset.v + '=' + n.textContent.trim()));
    if (cont.length) { const [v, n] = cont[0].split('='); await page.hover(`#nav button[data-v="${v}"]`); await page.waitForTimeout(60); const d = await dica(page);
      chk(d && d.t.includes('(' + n + ')'), `${tam} o número do contador (bolinha) aparece na dica de "${v}": ${d && d.t}`) }
    else chk(false, `${tam} o banco de teste deveria ter algum contador no menu`);

    // 4) cada item leva à página certa (clique no ícone)
    let cliques = 0; const errCl = [];
    for (const [v] of nomes) { if (/^nav-/.test(v)) continue; await page.click(`#nav button[data-v="${v}"]`); await page.waitForTimeout(250); if (await rota(page) === v) cliques++; else errCl.push(v + '→' + await rota(page)) }
    chk(!errCl.length, `${tam} recolhido: clicar no ícone abre a página do item (${cliques} itens)${errCl.length ? ': ' + errCl.join(', ') : ''}`);
    await page.click('#nav-busca'); await page.waitForTimeout(150);
    chk(await page.evaluate(() => document.activeElement && document.activeElement.id === 'q'), `${tam} recolhido: o ícone da Busca foca o campo de busca`);

    // 5) teclas do menu, recolhido e expandido
    for (const estado of ['recolhido', 'expandido']) {
      if (estado === 'expandido') { await tecla(page, '['); chk(!(await recolhido(page)), `${tam} [ expande o menu`) }
      const err = [];
      for (const [v, k] of Object.entries(NA)) { await page.evaluate(v => go(v === 'config' ? 'painel' : 'config'), v); await page.waitForTimeout(200); await tecla(page, k.toLowerCase()); if (await rota(page) !== v) err.push(`${k}→${await rota(page)} (esperado ${v})`) }
      chk(!err.length, `${tam} ${estado}: todas as ${Object.keys(NA).length} teclas do menu abrem a página certa${err.length ? ': ' + err.join(', ') : ''}`);
      await tecla(page, 'Control+k');
      chk(await page.evaluate(() => document.activeElement && document.activeElement.id === 'q'), `${tam} ${estado}: Ctrl+K foca a busca`);
      await tecla(page, 'Escape');
      await page.evaluate(() => go('painel')); await page.waitForTimeout(700);
      await tecla(page, 'j');
      chk(await page.evaluate(() => !!document.querySelector('#v-painel .ini-task.kb-atual')), `${tam} ${estado}: J escolhe o 1º item do Precisa de você (UX-32)`);
      await tecla(page, 'Escape'); await page.evaluate(() => { document.querySelectorAll('.kb-atual').forEach(x => x.classList.remove('kb-atual')); KB_ATUAL = null });
      await tecla(page, '?'); await page.waitForTimeout(300);
      chk(await page.evaluate(() => !!document.querySelector('section.content.on > .ajuda-caixa:not([hidden])') || /Atalhos|Passo a passo/.test((document.getElementById('d-title') || {}).textContent || '')), `${tam} ${estado}: ? abre a ajuda`);
      await tecla(page, 'Escape');
      if (estado === 'recolhido') { await tecla(page, 'Control+b'); chk(!(await recolhido(page)), `${tam} Ctrl+B expande`); await tecla(page, 'Control+b'); chk(await recolhido(page), `${tam} Ctrl+B recolhe de novo`) }
    }
    // 6) conferência (UX-10/UX-44): com o menu recolhido, K abre "Recortar e alinhar"; as letras do menu não valem conferindo
    await tecla(page, '['); chk(await recolhido(page), `${tam} [ recolhe o menu`);
    await page.evaluate(() => nav('conferir/F003-P9001'));
    const abriu = await page.waitForSelector('#cf-linhas .cf-linha', { timeout: 10000 }).then(() => true, () => false);
    chk(abriu, `${tam} a conferência abre com o menu recolhido`);
    if (abriu) { await page.waitForTimeout(800); await tecla(page, 'k');
      chk(await page.waitForSelector('#aj-ed', { timeout: 4000 }).then(() => true, () => false), `${tam} recolhido, conferindo: K abre "Recortar e alinhar" (UX-44)`);
      await tecla(page, 'Escape'); await page.waitForTimeout(200);
      await tecla(page, 'p'); chk(await rota(page) === 'conferir', `${tam} conferindo: a letra P do menu não sai da conferência (${await rota(page)})`);
      await tecla(page, 'Escape'); }
    // 7) estado lembrado
    await page.evaluate(() => go('painel')); await page.reload(); await page.waitForTimeout(1500);
    chk(await recolhido(page), `${tam} recolhido continua recolhido depois de recarregar`);
    ruim = await medir(page); chk(!ruim.length, `${tam} recolhido depois de recarregar: barra certa${ruim.length ? ': ' + ruim.join(' | ') : ''}`);
    await page.click('#collapse'); await page.waitForTimeout(200); await page.reload(); await page.waitForTimeout(1200);
    chk(!(await recolhido(page)), `${tam} expandido continua expandido depois de recarregar`);
    chk(Math.abs(await page.$eval('.side', e => e.getBoundingClientRect().width) - larg0) < 1, `${tam} expandido igual ao de antes`);
    await ctx.close();
  }
  // celular: o recolhido não vale (barra de baixo)
  { const ctx = await b.newContext({ viewport: { width: 390, height: 800 } });
    await ctx.request.post(BASE + '/api/auth/login', { data: { email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' } });
    const p = await ctx.newPage(); await p.goto(BASE + '/#painel'); await p.evaluate(() => { try { localStorage.setItem('camp.side', '1') } catch (_) {} }); await p.reload(); await p.waitForTimeout(1500);
    const fs = await p.$eval('#nav button[data-v="painel"]', e => getComputedStyle(e).fontSize);
    chk(fs !== '0px', `celular: com o recolhido lembrado do computador, a barra de baixo continua com os nomes (${fs})`);
    await ctx.close() }
  await b.close();
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  console.log(linhas.join('\n'));
  console.log(prob.length ? `\n${prob.length} FALHA(S)` : '\nTUDO OK');
  process.exit(prob.length ? 1 : 0);
})().catch(e => { console.log('Error', e); process.exit(2) });
