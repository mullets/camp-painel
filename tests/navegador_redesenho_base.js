// Redesenho §3, §4, §18, §19 e §20 (plano do Rafael, 04/11/2026) no navegador de verdade (Playwright + Chromium):
//  - §3 menu: grupos Principal · Acervo · Público e processos · Administração; item ativo evidente (aria-current, fundo próprio, barra);
//    contador só em item que é demanda; setas ↑ ↓ andam pelo menu; o operador não vê item de admin.
//  - §19 moldura: no celular (390) o menu é uma gaveta aberta pelo ☰ do cabeçalho (Esc, fundo e item fecham; o foco volta ao ☰);
//    no tablet (1024) o menu começa recolhido; grade da Home com coluna secundária mais estreita no desktop e empilhada no tablet;
//    sem rolagem lateral em 390, 1024, 1366 e 1920.
//  - §4 topo: busca com "Buscar projeto, fundo, arquiteto ou código" e resultados com categoria; botão "Estado dos sistemas" que NÃO
//    fica verde com a falha REAL do banco de teste (o QNAP não está montado neste servidor) e diz a falha; painel com cada sistema e a
//    última verificação; "desatualizado" quando a verificação envelhece; alerta persistente (sem "Fechar por hoje") também na Home e
//    para o operador; nome + avatar num menu só.
//  - §18: contraste WCAG AA medido no navegador dos textos principais (claro e escuro) e foco visível pelo teclado.
//  - §20: estadoHTML (carregando, vazio, erro com serviço, sem permissão com quem autoriza, sucesso com o identificador real,
//    desatualizado com a última sincronização, Desfazer) e a página "Sem acesso" do operador.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/red_a.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/red_a.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8981)
//   CAMP_BASE=http://127.0.0.1:8981 node tests/navegador_redesenho_base.js        (CAMP_SHOTS=/pasta grava prints)
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8981';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const SHOTS = process.env.CAMP_SHOTS || '';
const linhas = [], prob = [], erros = [];
const chk = (ok, m) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + m); if (!ok) prob.push(m) };

async function entrar(b, email, senha, w, h, tema) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, colorScheme: tema || 'light' });
  await ctx.route('**/*', rt => rt.request().url().startsWith(BASE) ? rt.continue() : rt.abort());
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !/net::ERR_FAILED|Failed to load resource/.test(m.text())) erros.push(email + ': ' + m.text()) });
  page.on('pageerror', e => erros.push(email + ': pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.evaluate(() => { try { localStorage.clear() } catch (_) {} });
  await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  await page.waitForTimeout(1200);
  return { ctx, page };
}
const semRolagem = async (pg, nome) => { const r = await pg.evaluate(() => { const m = document.querySelector('.main'), W = innerWidth; return { doc: document.documentElement.scrollWidth, W, main: m.scrollWidth, mainC: m.clientWidth,
  largos: [...document.querySelectorAll('.main *')].filter(e => { if (!e.offsetParent || e.closest('.tw')) return false; const r = e.getBoundingClientRect(); return r.right > W + 1 }).slice(0, 4).map(e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + '.' + String(e.className).split(' ')[0] + ' ' + Math.round(e.getBoundingClientRect().right)) } });
  const ok = r.doc <= r.W + 1 && r.main <= r.mainC + 1; if (!ok) linhas.push('      ' + (nome || '') + ' ' + JSON.stringify(r)); return ok };

// contraste: cor do texto × fundo efetivo (sobe pelos pais até achar um fundo opaco)
const CONTRASTE = () => {
  const rgb = s => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 } };
  const lum = c => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4) }; return .2126 * f(c.r) + .7152 * f(c.g) + .0722 * f(c.b) };
  const mix = (top, bot) => ({ r: top.r * top.a + bot.r * (1 - top.a), g: top.g * top.a + bot.g * (1 - top.a), b: top.b * top.a + bot.b * (1 - top.a), a: 1 });
  const fundo = el => { const pilha = []; for (let e = el; e; e = e.parentElement) { const c = rgb(getComputedStyle(e).backgroundColor); if (c && c.a > 0) { pilha.push(c); if (c.a >= 1) break } }
    let f = { r: 255, g: 255, b: 255, a: 1 }; for (let i = pilha.length - 1; i >= 0; i--) f = mix(pilha[i], f); return f };
  const razao = el => { const cs = getComputedStyle(el), t = rgb(cs.color), f = fundo(el), tx = mix(t, f), a = lum(tx), b = lum(f); return (Math.max(a, b) + .05) / (Math.min(a, b) + .05) };
  const ALVOS = [['texto do corpo', '#v-painel .ini-task .t b'], ['título da página', '#v-painel h1'], ['título de seção', '#v-painel .panel .ph h2'],
    ['item do menu', '#nav button[data-v="projetos"]'], ['item ativo do menu', '#nav button.on'], ['grupo do menu', '#nav .grp'],
    ['contador do menu', '#nav button .n:not([hidden])'], ['subtítulo', '#v-painel .sub'], ['texto secundário', '#v-painel .ini-task small'],
    ['busca (texto)', '#q'], ['botão secundário', '#v-painel .btn:not(.pri)'], ['botão primário', '#v-painel .btn.pri'],
    ['botão Estado dos sistemas', '#machine-status .sis-txt b'], ['nome na conta', '.who .who-nome'], ['trilha', '#gcrumb b'],
    ['alerta do topo', '#system-banner b'], ['link', '#v-painel a[href], #v-painel .lnk']];
  return ALVOS.map(([nome, sel]) => { const el = [...document.querySelectorAll(sel)].find(e => e.offsetParent !== null || getComputedStyle(e).position === 'fixed');
    if (!el) return { nome, sel, r: null }; const cs = getComputedStyle(el), px = parseFloat(cs.fontSize), grande = px >= 24 || (px >= 18.66 && +cs.fontWeight >= 600);
    return { nome, sel, r: +razao(el).toFixed(2), min: grande ? 3 : 4.5, px } });
};

(async () => {
  const b = await chromium.launch({ executablePath: CHROME });
  try {
    // ================= admin, 1366 (desktop largo) =================
    let { ctx, page } = await entrar(b, 'rafael@camp.arq.br', 'senha-bem-longa-123', 1366, 900);
    await page.evaluate(() => nav('painel')); await page.waitForSelector('#v-painel .ini-grid', { timeout: 20000 });
    await page.waitForSelector('#machine-status .sis-btn', { timeout: 20000 }).catch(() => chk(false, '§4 o botão "Estado dos sistemas" (.sis-btn) não apareceu no topo')); await page.waitForTimeout(600);

    try {
    // §3 grupos e item ativo
    const grupos = await page.$$eval('#nav > .grp', es => es.filter(e => e.offsetParent).map(e => e.textContent.trim()));
    chk(grupos.join(' · ') === 'Principal · Acervo · Público e processos · Administração', '§3 grupos do menu: ' + grupos.join(' · '));
    const ativo = await page.evaluate(() => { const a = document.querySelector('#nav button.on'), o = document.querySelector('#nav button:not(.on)[data-v="projetos"]'), side = document.querySelector('.side');
      const cs = getComputedStyle(a), bar = getComputedStyle(a, '::before');
      return { v: a.dataset.v, cur: a.getAttribute('aria-current'), bg: cs.backgroundColor, bgSide: getComputedStyle(side).backgroundColor, bgOutro: getComputedStyle(o).backgroundColor, peso: +cs.fontWeight, pesoOutro: +getComputedStyle(o).fontWeight, bar: bar.width, barBg: bar.backgroundColor } });
    chk(ativo.v === 'painel' && ativo.cur === 'page', '§3 item ativo com aria-current="page": ' + ativo.v);
    chk(ativo.bg !== ativo.bgSide && ativo.bg !== ativo.bgOutro && ativo.peso > ativo.pesoOutro && parseFloat(ativo.bar) >= 3, `§3 item ativo evidente: fundo próprio (${ativo.bg} × menu ${ativo.bgSide}), texto mais forte (${ativo.peso} × ${ativo.pesoOutro}) e barra de ${ativo.bar}`);
    const comNumero = await page.$$eval('#nav button .n', ns => ns.map(n => n.closest('button').dataset.v));
    const DEMANDA = ['painel', 'filas', 'erros', 'decisoes', 'solicitacoes', 'inscricoes', 'emprestimos'];
    chk(comNumero.every(v => DEMANDA.includes(v)), '§3 contador só em item que é demanda: ' + comNumero.join(', '));
    const icones = await page.$$eval('#nav > button', bs => [...new Set(bs.filter(x => x.offsetParent).map(x => { const r = x.querySelector('svg').getBoundingClientRect(); return Math.round(r.width) + 'x' + Math.round(r.height) }))]);
    chk(icones.length === 1, '§3 ícones do menu de um tamanho só: ' + icones.join(', '));
    await page.focus('#nav button[data-v="painel"]'); await page.keyboard.press('ArrowDown');
    chk(await page.evaluate(() => document.activeElement.dataset.v) === 'filas', '§3 seta ↓ no menu vai para o próximo item (Material novo)');
    await page.keyboard.press('ArrowUp');
    chk(await page.evaluate(() => document.activeElement.dataset.v) === 'painel', '§3 seta ↑ volta');

    } catch (e) { chk(false, 'bloco "§3 grupos e item ativo" quebrou: ' + String(e && e.message || e).split('\n')[0]) }
    // §19 grade da Home no desktop largo
    const grade = await page.evaluate(() => [...document.querySelectorAll('#v-painel .ini-grid > .ini-col')].map(c => Math.round(c.getBoundingClientRect().width)));
    chk(grade.length === 2 && grade[0] > grade[1] * 1.6 && grade[1] >= 290, '§19 Home ≥1280: coluna principal larga + secundária estreita: ' + grade.join(' × '));

    // §4 busca
    chk(await page.getAttribute('#q', 'placeholder') === 'Buscar projeto, fundo, arquiteto ou código', '§4 busca com o texto do plano');
    const qr = await page.evaluate(() => { const s = document.querySelector('.top .search').getBoundingClientRect(), t = document.querySelector('.top').getBoundingClientRect(); return { w: s.width, centro: Math.abs((s.left + s.width / 2) - (t.left + t.width / 2)) } });
    chk(qr.w >= 380, `§4 busca em destaque (${Math.round(qr.w)} px de largura)`);
    await page.keyboard.press('Control+k'); await page.waitForTimeout(150);
    chk(await page.evaluate(() => document.activeElement.id) === 'q', '§4 ⌘/Ctrl+K continua focando a busca');
    await page.keyboard.type('tarum'); await page.waitForSelector('#qres.open [data-search-index]', { timeout: 8000 }).catch(() => {});
    const res = await page.$$eval('#qres [data-search-index]', ds => ds.map(d => [(d.querySelector('.recent-kind') || {}).textContent, (d.querySelector('.code') || {}).textContent]));
    chk(res.length > 0 && res.every(r => r[0] && r[1]), '§4 busca sem acento ("tarum") acha e mostra categoria + código: ' + JSON.stringify(res.slice(0, 3)));
    await page.keyboard.press('Escape'); await page.fill('#q', '');

    try {
    // §4 Estado dos sistemas com a falha REAL deste servidor (QNAP não montado)
    const est = await (await ctx.request.get(BASE + '/api/estacoes')).json();
    const crit = (est.estado_geral.partes || []).filter(p => p.nivel === 'critico').map(p => p.texto);
    chk(est.qnap && est.qnap.montado === false && crit.includes('QNAP desconectado'), 'precondição: neste servidor o QNAP está desconectado de verdade: ' + crit.join(', '));
    const botao = await page.evaluate(() => { const s = document.querySelector('#machine-status .sis-btn'); return { txt: s.textContent.replace(/\s+/g, ' '), cls: s.className, aria: s.getAttribute('aria-label'), ico: s.querySelector('.ms-ponto').textContent } });
    chk(!/Sistemas funcionando|operacionais/.test(botao.txt) && /crit/.test(botao.cls) && /QNAP desconectado/.test(botao.txt) && botao.ico === '✕', '§4 o botão não fica verde e diz a falha, com ícone além da cor: "' + botao.txt + '"');
    chk(/^Estado dos sistemas: /.test(botao.aria || ''), '§4 nome acessível "Estado dos sistemas: …": ' + botao.aria);
    await page.click('#machine-status .sis-btn'); await page.waitForTimeout(250);
    const painel = await page.evaluate(() => { const p = document.querySelector('#machine-status .sis-painel'); const r = p.getBoundingClientRect();
      return { vis: r.width > 0 && r.height > 0, itens: [...p.querySelectorAll('.sis-item')].map(i => [i.dataset.sis, (i.querySelector('.tag') || {}).textContent]), quando: p.querySelector('.sis-quando').textContent, maq: p.querySelectorAll('.ms-linha').length, dentro: r.right <= innerWidth + 1 } });
    chk(painel.vis && painel.dentro, '§4 o botão abre o painel "Estado dos sistemas" dentro da tela');
    chk(painel.itens[0] && painel.itens[0][1] === 'crítico' && painel.itens.some(i => i[0] === 'qnap' && i[1] === 'crítico'), '§4 falhas críticas primeiro, QNAP crítico: ' + JSON.stringify(painel.itens));
    chk(/Última verificação: às \d\d:\d\d/.test(painel.quando) && painel.maq >= 2, '§4 hora da última verificação e as máquinas no painel: "' + painel.quando + '"');
    if (SHOTS) await page.screenshot({ path: SHOTS + '/a-teste-estado-sistemas-1366.png' });
    await page.keyboard.press('Escape'); await page.waitForTimeout(150);
    chk(await page.evaluate(() => !document.querySelector('#machine-status details.sis').open && document.activeElement.classList.contains('sis-btn')), '§4 Esc fecha o painel e o foco volta ao botão');
    const velho = await page.evaluate(() => { SIS_ULTIMA_LOCAL = Date.now() - 10 * 60e3; sisQuando(); const s = document.querySelector('#machine-status .sis-btn'); return { cls: s.className, q: document.querySelector('#machine-status .sis-quando').textContent, vis: !s.querySelector('.sis-velho-txt').hidden } });
    chk(/sis-velho/.test(velho.cls) && velho.vis && /desatualizada/.test(velho.q), '§4 verificação velha (10 min sem resposta) = "desatualizado" no botão e no painel: "' + velho.q + '"');
    await page.evaluate(() => { SIS_ULTIMA_LOCAL = Date.now(); sisQuando() });
    const faixa = await page.evaluate(() => { const f = document.getElementById('system-banner'); return { on: f.classList.contains('on') && getComputedStyle(f).display !== 'none', impede: f.classList.contains('impede'), fechar: !!f.querySelector('[data-faixa-fechar]'), txt: f.textContent.replace(/\s+/g, ' '), role: f.getAttribute('role') } });
    chk(faixa.on && faixa.impede && !faixa.fechar && faixa.role === 'alert' && /QNAP não está conectado/.test(faixa.txt), '§4 alerta persistente na Home (sem "Fechar por hoje") porque o QNAP impede o trabalho: "' + faixa.txt.slice(0, 90) + '"');
    await page.click('.who'); await page.waitForTimeout(150);
    const conta = await page.evaluate(() => { const m = document.getElementById('who-menu'); return { vis: !m.hidden, cab: m.querySelector('.who-cab').textContent, itens: [...m.querySelectorAll('[data-who]')].map(x => x.dataset.who) } });
    chk(conta.vis && /Rafael/.test(conta.cab) && /admin master/.test(conta.cab) && ['perfil', 'sair'].every(x => conta.itens.includes(x)), '§4 nome, papel e opções da conta num menu só: ' + conta.cab);
    await page.keyboard.press('Escape');
    } catch (e) { chk(false, 'bloco "§4 Estado dos sistemas com a falha REAL " quebrou: ' + String(e && e.message || e).split('\n')[0]) }

    try {
    // §18 foco visível pelo teclado
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    const focos = [];
    for (const sel of ['#nav button[data-v="fundos"]', '#q', '#machine-status .sis-btn', '#v-painel .btn']) {
      await page.evaluate(s => { document.querySelector(s).focus() }, sel); await page.keyboard.press('Shift');
      const f = await page.evaluate(s => { const e = document.querySelector(s), cs = getComputedStyle(e); return { ow: parseFloat(cs.outlineWidth), os: cs.outlineStyle, sh: cs.boxShadow } }, sel);
      focos.push([sel, f]); }
    await page.keyboard.press('Tab');
    chk(focos.every(([, f]) => (f.os !== 'none' && f.ow >= 2) || /px/.test(f.sh)), '§18 foco visível (anel ≥ 2 px) em menu, busca, Estado dos sistemas e botões: ' + JSON.stringify(focos.map(([s, f]) => s.split(' ').pop() + ' ' + f.ow + 'px ' + f.os)));

    } catch (e) { chk(false, 'bloco "§18 foco visível pelo teclado" quebrou: ' + String(e && e.message || e).split('\n')[0]) }
    try {
    // §20 estados
    const st = await page.evaluate(() => {
      const el = document.createElement('div'); document.body.appendChild(el); const out = {};
      for (const [t, o] of [['carregando', {}], ['vazio', { titulo: 'Nenhuma visita nos últimos 7 dias.' }], ['erro', { servico: 'QNAP', ultima: new Date(Date.now() - 5 * 60e3).toISOString(), acoes: '<button class="btn sm">Ver diagnóstico</button>' }],
        ['sem-permissao', { titulo: 'Só um admin aprova.', quem: 'um administrador' }], ['sucesso', { titulo: 'Lote conferido', id: 'F003-P9001', desfazer: { attr: 'data-teste-desfazer="1"' } }], ['desatualizado', { ultima: new Date(Date.now() - 3 * 3600e3).toISOString() }]]) {
        el.innerHTML = estadoHTML(t, o); const e = el.firstElementChild; out[t] = { cls: e.className, role: e.getAttribute('role'), txt: e.textContent.replace(/\s+/g, ' ').trim(), esq: e.querySelectorAll('.esq').length, desf: !!e.querySelector('[data-teste-desfazer]') } }
      el.remove(); return out });
    chk(st.carregando.role === 'status' && st.carregando.esq >= 3, '§20 carregando: esqueleto (' + st.carregando.esq + ' linhas) com role=status');
    chk(/Nenhuma visita/.test(st.vazio.txt) && !/\b0\b/.test(st.vazio.txt), '§20 vazio explica sem número inventado: ' + st.vazio.txt);
    chk(st.erro.role === 'alert' && /Serviço afetado: QNAP/.test(st.erro.txt) && /Última informação conhecida: (às|em \d\d\/\d\d às) \d\d:\d\d \(há 5 min\)/.test(st.erro.txt) && /Ver diagnóstico/.test(st.erro.txt), '§20 erro com serviço, última informação e diagnóstico: ' + st.erro.txt);
    chk(/Quem pode autorizar: um administrador/.test(st['sem-permissao'].txt), '§20 sem permissão diz quem autoriza: ' + st['sem-permissao'].txt);
    chk(/Lote conferido: F003-P9001/.test(st.sucesso.txt) && st.sucesso.desf, '§20 sucesso com o identificador real e Desfazer: ' + st.sucesso.txt);
    chk(/Última sincronização: (às|em) /.test(st.desatualizado.txt), '§20 desatualizado com a última sincronização: ' + st.desatualizado.txt);

    } catch (e) { chk(false, 'bloco "§20 estados" quebrou: ' + String(e && e.message || e).split('\n')[0]) }
    // contraste (claro) + sem rolagem lateral em 1366
    const cClaro = await page.evaluate(CONTRASTE);
    const ruinsC = cClaro.filter(x => x.r !== null && x.r < x.min);
    chk(!ruinsC.length && cClaro.filter(x => x.r !== null).length >= 14, '§18 contraste AA no tema claro (' + cClaro.filter(x => x.r !== null).length + ' textos medidos): ' + (ruinsC.length ? JSON.stringify(ruinsC) : cClaro.map(x => x.nome + ' ' + x.r).join(' · ')));
    chk(await semRolagem(page), '§19 1366: sem rolagem lateral');
    await ctx.close();

    // ================= tema escuro, 1920 =================
    ({ ctx, page } = await entrar(b, 'rafael@camp.arq.br', 'senha-bem-longa-123', 1920, 1000, 'dark'));
    await page.evaluate(() => nav('painel')); await page.waitForSelector('#v-painel .ini-grid', { timeout: 20000 }); await page.waitForSelector('#machine-status .sis-btn', { timeout: 20000 }).catch(() => chk(false, '§4 o botão "Estado dos sistemas" (.sis-btn) não apareceu no topo')); await page.waitForTimeout(600);
    const cEsc = await page.evaluate(CONTRASTE), ruinsE = cEsc.filter(x => x.r !== null && x.r < x.min);
    chk(!ruinsE.length && cEsc.filter(x => x.r !== null).length >= 14, '§18 contraste AA no tema escuro (' + cEsc.filter(x => x.r !== null).length + ' textos medidos): ' + (ruinsE.length ? JSON.stringify(ruinsE) : cEsc.map(x => x.nome + ' ' + x.r).join(' · ')));
    const deg = await page.evaluate(() => { const v = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim(); return [v('--bg'), v('--surface'), v('--hover'), v('--sel')] });
    chk(new Set(deg).size === 4, '§18 tema escuro com degraus distintos de fundo, cartão, hover e selecionado: ' + deg.join(' · '));
    chk(await semRolagem(page), '§19 1920: sem rolagem lateral');
    if (SHOTS) await page.screenshot({ path: SHOTS + '/a-teste-1920-escuro.png' });
    await ctx.close();

    try {
    // ================= tablet 1024 =================
    ({ ctx, page } = await entrar(b, 'rafael@camp.arq.br', 'senha-bem-longa-123', 1024, 768));
    await page.evaluate(() => nav('painel')); await page.waitForSelector('#v-painel .ini-grid', { timeout: 20000 }); await page.waitForTimeout(500);
    const tab = await page.evaluate(() => ({ rec: document.querySelector('.app').classList.contains('collapsed'), side: Math.round(document.querySelector('.side').getBoundingClientRect().width), cols: getComputedStyle(document.querySelector('#v-painel .ini-grid')).gridTemplateColumns.split(' ').length }));
    chk(tab.rec && tab.side <= 72, `§19 tablet: o menu começa recolhido (${tab.side} px)`);
    chk(tab.cols === 1, '§19 tablet: a coluna da direita da Home desce para baixo da principal');
    chk(await semRolagem(page), '§19 1024: sem rolagem lateral');
    await page.click('#collapse'); await page.waitForTimeout(200); await page.reload(); await page.waitForTimeout(1500);
    chk(!(await page.evaluate(() => document.querySelector('.app').classList.contains('collapsed'))), '§19 tablet: quem expandiu o menu continua com ele expandido depois de recarregar');
    await ctx.close();
    } catch (e) { chk(false, 'bloco "tablet 1024" quebrou: ' + String(e && e.message || e).split('\n')[0]); await ctx.close().catch(() => {}) }

    try {
    // ================= celular 390: gaveta =================
    ({ ctx, page } = await entrar(b, 'rafael@camp.arq.br', 'senha-bem-longa-123', 390, 844));
    await page.evaluate(() => nav('painel')); await page.waitForSelector('#v-painel .ini-grid', { timeout: 20000 }); await page.waitForTimeout(500);
    const fechada = await page.evaluate(() => { const s = document.querySelector('.side'), r = s.getBoundingClientRect(), g = document.getElementById('nav-gaveta'); return { vis: getComputedStyle(s).visibility, dir: r.right, g: !!g && g.offsetParent !== null, ex: g.getAttribute('aria-expanded'), alt: Math.round(g.getBoundingClientRect().height) } });
    chk(fechada.vis === 'hidden' && fechada.dir <= 0 && fechada.g && fechada.ex === 'false' && fechada.alt >= 44, '§19 celular: menu fechado fora da tela e o ☰ (44 px) no cabeçalho: ' + JSON.stringify(fechada));
    chk(await semRolagem(page), '§19 390: sem rolagem lateral');
    if (SHOTS) await page.screenshot({ path: SHOTS + '/a-teste-390-home.png' });
    await page.click('#nav-gaveta'); await page.waitForTimeout(350);
    const aberta = await page.evaluate(() => { const s = document.querySelector('.side'), r = s.getBoundingClientRect(); return { vis: getComputedStyle(s).visibility, l: r.left, w: r.width, ex: document.getElementById('nav-gaveta').getAttribute('aria-expanded'), foco: !!document.activeElement.closest('#nav'), inerte: document.querySelector('.main').inert, todos: [...document.querySelectorAll('#nav > button[data-v]')].filter(x => x.offsetParent).length } });
    chk(aberta.vis === 'visible' && aberta.l >= 0 && aberta.w <= 390 && aberta.ex === 'true' && aberta.foco && aberta.inerte, '§19 o ☰ abre a gaveta, o foco entra nela e o resto da tela fica inerte: ' + JSON.stringify(aberta));
    chk(aberta.todos >= 15, `§19 a gaveta tem o menu inteiro (${aberta.todos} itens)`);
    if (SHOTS) await page.screenshot({ path: SHOTS + '/a-teste-390-gaveta.png' });
    await page.keyboard.press('Escape'); await page.waitForTimeout(300);
    chk(await page.evaluate(() => !document.body.classList.contains('nav-aberto') && document.activeElement.id === 'nav-gaveta' && !document.querySelector('.main').inert), '§19 Esc fecha a gaveta e o foco volta ao ☰');
    await page.click('#nav-gaveta'); await page.waitForTimeout(300); await page.mouse.click(370, 400); await page.waitForTimeout(300);
    chk(await page.evaluate(() => !document.body.classList.contains('nav-aberto')), '§19 tocar no fundo escurecido fecha a gaveta');
    await page.click('#nav-gaveta'); await page.waitForTimeout(300); await page.click('#nav button[data-v="fundos"]'); await page.waitForTimeout(600);
    chk(await page.evaluate(() => rotaAtual() === 'fundos' && !document.body.classList.contains('nav-aberto')), '§19 escolher um item na gaveta abre a tela e fecha a gaveta');
    chk(await semRolagem(page, 'fundos 390'), '§19 390 (Fundos): sem rolagem lateral');
    await page.click('#machine-status .sis-btn'); await page.waitForTimeout(250);
    const p390 = await page.evaluate(() => { const r = document.querySelector('#machine-status .sis-painel').getBoundingClientRect(); return { l: r.left, r: r.right } });
    chk(p390.l >= 0 && p390.r <= 390, '§4 celular: o painel "Estado dos sistemas" cabe na tela: ' + JSON.stringify(p390));
    await ctx.close();

    } catch (e) { chk(false, 'bloco "================= celular 390: gaveta ==" quebrou: ' + String(e && e.message || e).split('\n')[0]); await ctx.close().catch(() => {}) }
    try {
    // ================= operador: menu sem itens de admin, alerta persistente, "Sem acesso" =================
    ({ ctx, page } = await entrar(b, 'operador@camp.arq.br', 'senha-operador-123', 1366, 900));
    await page.evaluate(() => nav('painel')); await page.waitForTimeout(2500);
    const op = await page.evaluate(() => ({ adm: ['config', 'auditoria', 'qualidade', 'uso', 'inscricoes', 'estacoes'].filter(v => { const x = document.querySelector(`#nav button[data-v="${v}"]`); return x && x.offsetParent }), grpAdm: !!document.querySelector('#nav .grp[data-grp="admin"]').offsetParent, botao: !!document.querySelector('#machine-status .sis-btn') }));
    chk(!op.adm.length && !op.grpAdm, '§3 operador: itens e grupo de admin não aparecem: ' + op.adm.join(','));
    chk(!op.botao, '§4 operador: o botão das máquinas continua só de admin (docs/vocabulario.md "Quem vê o quê")');
    await page.waitForFunction(() => document.getElementById('system-banner').classList.contains('impede'), null, { timeout: 40000 }).catch(() => {});
    const fop = await page.evaluate(() => { const f = document.getElementById('system-banner'); return { on: f.classList.contains('on') && getComputedStyle(f).display !== 'none', impede: f.classList.contains('impede'), fechar: !!f.querySelector('[data-faixa-fechar]'), backup: /backup/.test(f.textContent) } });
    chk(fop.on && fop.impede && !fop.fechar && !fop.backup, '§4 operador também vê o alerta que impede o trabalho (QNAP), sem "Fechar por hoje" e sem os avisos de admin: ' + JSON.stringify(fop));
    await page.evaluate(() => { location.hash = '#config' }); await page.waitForTimeout(800);
    const sa = await page.evaluate(() => { const e = document.querySelector('#v-nao-encontrado .estado.sem-permissao'); return e ? e.textContent.replace(/\s+/g, ' ') : '' });
    chk(/Quem pode autorizar/.test(sa) && /Voltar/.test(sa), '§20 "Sem acesso" usa o estado sem permissão (porquê + quem autoriza): ' + sa);
    await ctx.close();
    } catch (e) { chk(false, 'bloco "================= operador: menu sem ite" quebrou: ' + String(e && e.message || e).split('\n')[0]); await ctx.close().catch(() => {}) }
  } catch (e) { chk(false, 'o teste quebrou: ' + (e && e.stack || e)) }
  chk(!erros.length, 'nenhum erro de JavaScript no console: ' + erros.slice(0, 3).join(' | '));
  await b.close();
  console.log(linhas.join('\n'));
  console.log(prob.length ? `\n${prob.length} PROBLEMA(S)` : '\nTUDO OK');
  process.exit(prob.length ? 1 : 0);
})();
