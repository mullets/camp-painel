// CAMP-FIN-CONSERTOS (24/11/2026). Rafael: "fui clicar em um item aqui do financeiro e simplesmente sumiu tudo" e "em qualquer aba, se eu
// clico num item pra ter infos dele, simplesmente fica tudo branco"; "depois só recarregando, e volta para a Visão geral".
// Causa: o painel lateral da RECEITA tinha um <div class="fin-fila"> esquecido; ".fin-fila" era a camada fixa de tela inteira da fila
// "Precisa justificar" (cor do fundo, z-index acima do painel lateral) e cobria a tela toda, sem erro no console.
// Este teste clica em TODOS os itens de cada aba (linhas, linhas da DRE, destaques, legenda do gráfico, barras, conferência, grade das
// contas fixas, orçamento do projeto, "Preparar nota do mês"), a 1440×900 e a 2000×1100 (a tela do Rafael), e depois de cada clique confere:
// nenhum erro de JS; #v-financeiro visível e com conteúdo; nada de camada de tela inteira por cima (elementFromPoint em vários pontos cai no
// conteúdo, no painel lateral aberto ou no fundo escuro dele); o painel lateral, se abriu, tem conteúdo e está na frente; a rota continua no
// Financeiro. Também: a fila "Precisa justificar" abre e fecha sem deixar a tela coberta (inclusive saindo e voltando pelo endereço), período
// ‹ ›, seletor de conta, busca natural, contas desativadas e o site sem o Mercado Pago (WP_BASE_URL morto).
// E o endereço guarda o estado: #financeiro/<aba>[/<detalhe>]?p=<período>&conta=<id>; recarregar volta à mesma aba, período e detalhe; o
// Voltar do navegador volta à aba anterior.
// Uso (servidor PRÓPRIO, portas 9110–9119, banco com tests/semear_banco_teste.py + tests/semente_financeiro.py + tests/semente_rouanet.py):
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9112 node tests/navegador_financeiro_cliques.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9112';
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const MAX_POR_ABA = +(process.env.FIN_MAX || 40);
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
const ABAS = ['geral', 'receitas', 'despesas', 'fixas', 'dre', 'conferencia', 'projeto'];
// o que não se clica às cegas: apaga, baixa arquivo, abre a impressão, sai da tela ou manda algo para fora
const PULAR = '[data-fin-acao="apagar-desp"],[data-fin-acao="cf-apagar"],[data-fin-acao="imprimir"],[data-fin-acao="sinc"],[data-fin-conta-ativa],[data-fin-regra-off],a[download],a[href*="exportar"],a[href*=".zip"],a[href^="http"],input[type=file],[data-fin-ir],[data-fin-pj="apagar"],[data-fin-pj="importar-aplicar"],[data-fin-nf]';
const ITENS = 'tr, li, button, a, summary, [role=button], [tabindex="0"], [data-fin-dre], [data-fin-rec], [data-fin-desp], [data-fin-cf], [data-fin-dica], rect, path[data-fin-dica], circle[data-fin-dica]';

async function entrar(browser, w, h, erros) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('console', m => { const url = ((m.location() || {}).url || ''); if (m.type() === 'error' && !/\/api\/auth\/eu$|\/favicon\.ico$|\/previa\?/.test(url) && !/status of (40[0-9]|50[0-9])|ERR_INSUFFICIENT_RESOURCES|Failed to load resource/.test(m.text())) erros.push(w + ': ' + m.text().slice(0, 200)); });
  page.on('pageerror', e => erros.push(w + ': pageerror: ' + e.message));
  page.on('dialog', d => d.dismiss().catch(() => {}));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, page };
}
const pronto = P => P.waitForFunction(() => document.getElementById('v-financeiro')?.classList.contains('on') && FIN.d && FIN.desp && !FIN.carregando, null, { timeout: 20000 });

// o estado da tela depois de um clique: o que está por cima em vários pontos, painel lateral, rota
async function estado(P) {
  return P.evaluate(() => {
    const v = document.getElementById('v-financeiro'), l = document.getElementById('fin-lado'), fila = document.getElementById('fin-fila'), fundo = document.getElementById('fin-fundo');
    const vis = e => !!e && !e.hidden && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().width > 0;
    const ladoAberto = vis(l), filaAberta = vis(fila);
    const pts = [[0.5, 0.5], [0.3, 0.45], [0.25, 0.75], [0.7, 0.3], [0.85, 0.6]].map(([x, y]) => {
      const e = document.elementFromPoint(innerWidth * x, innerHeight * y); if (!e) return 'nada';
      // uma camada fixa de tela inteira que não é a fila nem o fundo do painel lateral = tela coberta (vem antes: a camada esquecida estava DENTRO do painel lateral)
      for (let a = e; a && a !== document.body; a = a.parentElement) {
        const cs = getComputedStyle(a), r = a.getBoundingClientRect();
        if (cs.position === 'fixed' && r.width >= innerWidth * 0.9 && r.height >= innerHeight * 0.9 && a !== fila && a !== fundo) return 'COBERTA:' + (a.id || String(a.className) || a.tagName);
      }
      if (ladoAberto && l.contains(e)) return 'lado'; if (ladoAberto && e === fundo) return 'fundo';
      if (filaAberta && fila.contains(e)) return 'fila';
      return v.contains(e) ? 'conteudo' : (document.querySelector('.main')?.contains(e) || document.querySelector('.side, nav')?.contains(e) ? 'app' : 'FORA:' + (e.id || e.tagName));
    });
    let ladoFrente = true;
    if (ladoAberto) { const r = l.getBoundingClientRect(); const e = document.elementFromPoint(r.left + r.width / 2, r.top + Math.min(r.height / 2, 200)); ladoFrente = !!e && l.contains(e); }
    return { on: v.classList.contains('on') && !v.hidden, txt: v.innerText.length, hash: location.hash, ladoAberto, filaAberta, ladoTxt: ladoAberto ? l.innerText.trim().length : 0, ladoFrente, pts,
      erroAba: [...document.querySelectorAll('[data-fin-erro-aba]')].map(x => x.dataset.finErroAba).join(','), mainW: document.querySelector('.main').getBoundingClientRect().width };
  });
}
function ruim(r) {
  const p = [];
  if (!r.on) p.push('#v-financeiro escondido'); if (r.txt < 200) p.push('#v-financeiro quase vazio (' + r.txt + ')');
  if (!/^#financeiro(\/|\?|$)/.test(r.hash)) p.push('rota saiu do Financeiro: ' + r.hash);
  const cob = r.pts.filter(x => /^(COBERTA|FORA|nada)/.test(x)); if (cob.length) p.push('tela coberta/branca: ' + cob.join(' '));
  if (r.ladoAberto && (r.ladoTxt < 20 || !r.ladoFrente)) p.push('painel lateral aberto mas vazio ou atrás de outra camada');
  if (!r.ladoAberto && !r.filaAberta && r.pts.some(x => x === 'fundo' || x === 'lado')) p.push('fundo do painel lateral ficou');
  if (r.mainW < 300) p.push('.main encolheu para ' + r.mainW);
  if (r.erroAba) p.push('aba com erro de desenho: ' + r.erroAba);
  return p;
}
async function fechar(P) {
  for (let k = 0; k < 3; k++) {
    const st = await P.evaluate(() => ({ l: !document.getElementById('fin-lado').hidden, f: !document.getElementById('fin-fila').hidden, d: document.querySelector('.main').classList.contains('with-drawer') }));
    if (!st.l && !st.f && !st.d) return;
    if (st.l) await P.click('#fin-lado [data-fin-acao="fechar"]', { timeout: 2000 }).catch(() => P.keyboard.press('Escape'));
    else if (st.f) await P.click('#fin-fila [data-fin-acao="fila-fechar"]', { timeout: 2000 }).catch(() => P.keyboard.press('Escape'));
    else await P.evaluate(() => closeDrawer(true));
    await P.waitForTimeout(200);
  }
}
async function irAba(P, aba) {
  if (!/^#financeiro/.test(await P.evaluate(() => location.hash))) { await P.evaluate(() => nav('financeiro')); await pronto(P); }
  await fechar(P);
  const b = P.locator(`[data-fin-aba="${aba}"]`);
  if (!(await b.isVisible())) return false;
  await b.click(); await P.waitForTimeout(aba === 'projeto' ? 1200 : 300);
  return true;
}

async function varrer(P, w, rotulo, erros) {
  let total = 0, falhas = 0, linhasAbertas = 0;
  for (const aba of ABAS) {
    if (!(await irAba(P, aba))) { chk(aba === 'projeto', `[${rotulo}] aba ${aba} aparece`); continue; }
    const n = await P.evaluate(([aba, sel, pular, max]) => {
      document.querySelectorAll('[data-fcl]').forEach(e => e.removeAttribute('data-fcl'));
      const p = document.getElementById('fin-p-' + aba);
      const els = [...p.querySelectorAll(sel)].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !e.closest(pular) && !e.matches(pular) && !e.disabled; });
      // um por "tipo": linhas e itens primeiro (são o que o Rafael clica), depois o resto
      const peso = e => e.matches('[data-fin-rec],[data-fin-desp],[data-fin-dre],[data-fin-cf],tr') ? 0 : 1;
      els.sort((a, b) => peso(a) - peso(b));
      els.slice(0, max).forEach((e, i) => e.setAttribute('data-fcl', String(i)));
      return Math.min(els.length, max);
    }, [aba, ITENS, PULAR, MAX_POR_ABA]);
    chk(n > 0, `[${rotulo}] aba ${aba}: ${n} itens para clicar`);
    for (let i = 0; i < n; i++) {
      const el = P.locator(`[data-fcl="${i}"]`).first();
      if (!(await el.count()) || !(await el.isVisible().catch(() => false))) continue;
      const txt = ((await el.textContent().catch(() => '')) || '').trim().replace(/\s+/g, ' ').slice(0, 50);
      const antes = erros.length;
      await el.click({ timeout: 2500 }).catch(() => {});
      await P.waitForTimeout(350);
      const r = await estado(P);
      if (r.ladoAberto) linhasAbertas++;
      const pb = ruim(r).concat(erros.slice(antes));
      total++;
      if (pb.length) { falhas++; chk(false, `[${rotulo}] ${aba} · clique ${i} "${txt}": ${pb.join('; ')}`); await P.screenshot({ path: `/dev/shm/fcl-${w}-${aba}-${i}.png` }).catch(() => {}); }
      await fechar(P);
      const r2 = await estado(P);
      const pb2 = ruim(r2);
      if (pb2.length) { falhas++; chk(false, `[${rotulo}] ${aba} · depois de fechar o clique ${i} "${txt}": ${pb2.join('; ')}`); }
      // um clique pode ter trocado a aba, a lista (filtro) ou saído da tela: volta ao lugar e remarca os itens
      const ok = await P.evaluate(([aba]) => /^#financeiro/.test(location.hash) && FIN.aba === aba, [aba]);
      if (!ok) { await irAba(P, aba); }
      await P.evaluate(([aba, sel, pular, max]) => {
        if (document.querySelector('[data-fcl]')) return;
        const p = document.getElementById('fin-p-' + aba);
        const els = [...p.querySelectorAll(sel)].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !e.closest(pular) && !e.matches(pular) && !e.disabled; });
        const peso = e => e.matches('[data-fin-rec],[data-fin-desp],[data-fin-dre],[data-fin-cf],tr') ? 0 : 1;
        els.sort((a, b) => peso(a) - peso(b)); els.slice(0, max).forEach((e, k) => e.setAttribute('data-fcl', String(k)));
      }, [aba, ITENS, PULAR, MAX_POR_ABA]);
    }
  }
  chk(falhas === 0, `[${rotulo}] ${total} cliques em todas as abas, ${linhasAbertas} abriram o painel lateral: nenhum deixou a tela branca, coberta ou com erro (${falhas} problemas)`);
  chk(linhasAbertas >= 5, `[${rotulo}] o painel lateral abriu em vários itens (${linhasAbertas})`);
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    for (const [w, h] of [[2000, 1100], [1440, 900]]) {
      const { ctx, page: P } = await entrar(browser, w, h, erros);
      await P.evaluate(() => nav('financeiro')); await pronto(P);
      // ---- [A] o caso exato do Rafael: Receitas → clicar numa linha de doador
      await irAba(P, 'receitas');
      await P.locator('#fin-p-receitas [data-fin-rec]').first().click();
      await P.waitForSelector('#fin-lado:not([hidden])');
      let r = await estado(P);
      chk(ruim(r).length === 0 && r.ladoTxt > 50, `[A ${w}] Receitas → linha do doador: o painel lateral abre por cima da lista, sem cobrir a tela (${ruim(r).join('; ') || 'ok'})`);
      chk(r.pts.includes('fundo') && r.pts.includes('lado'), `[A ${w}] dá para ver o painel lateral e o fundo escurecido da lista (${r.pts.join(' ')})`);
      await fechar(P);
      // ---- [B] todos os itens de todas as abas
      await varrer(P, w, 'B ' + w, erros);
      // ---- [C] fila "Precisa justificar": abre, fecha, sai e volta pelo endereço
      await irAba(P, 'despesas');
      await P.click('#fin-kpis [data-fin-acao="fila"]');
      await P.waitForSelector('#fin-fila:not([hidden]) #fin-f-just');
      r = await estado(P);
      chk(r.filaAberta && r.pts.every(x => x === 'fila'), `[C ${w}] a fila abre de tela inteira, com conteúdo (${r.pts.join(' ')})`);
      await P.click('#fin-fila [data-fin-acao="fila-fechar"]'); await P.waitForTimeout(300);
      r = await estado(P);
      chk(!r.filaAberta && ruim(r).length === 0, `[C ${w}] fechar a fila devolve a tela (${ruim(r).join('; ') || 'ok'})`);
      await P.click('#fin-kpis [data-fin-acao="fila"]'); await P.waitForSelector('#fin-fila:not([hidden]) #fin-f-just');
      await P.evaluate(() => nav('painel')); await P.waitForTimeout(600);
      await P.evaluate(() => nav('financeiro')); await pronto(P); await P.waitForTimeout(300);
      r = await estado(P);
      chk(!r.filaAberta && ruim(r).length === 0, `[C ${w}] sair com a fila aberta e voltar ao Financeiro não deixa a tela coberta (${ruim(r).join('; ') || 'ok'})`);
      // ---- [D] período, conta, busca natural
      const p0 = await P.locator('#fin-per-txt').textContent();
      await P.click('[data-fin-passo="-1"]'); await pronto(P); await P.waitForTimeout(200);
      r = await estado(P); chk(ruim(r).length === 0 && (await P.locator('#fin-per-txt').textContent()) !== p0, `[D ${w}] seta ‹ troca o período sem quebrar a tela`);
      await P.click('[data-fin-passo="1"]'); await pronto(P);
      const opc = await P.$$eval('#fin-conta option', os => os.map(o => o.value).filter(Boolean));
      if (opc.length) { await P.selectOption('#fin-conta', opc[0]); await pronto(P); await P.waitForTimeout(200); r = await estado(P); chk(ruim(r).length === 0, `[D ${w}] escolher uma conta não quebra a tela`); await P.selectOption('#fin-conta', ''); await pronto(P); }
      await irAba(P, 'receitas');
      await P.fill('#fin-q', 'doações acima de 200'); await P.waitForTimeout(1200);
      r = await estado(P); chk(ruim(r).length === 0, `[D ${w}] busca natural não quebra a tela`);
      await P.locator('#fin-p-receitas [data-fin-rec]').first().click().catch(() => {}); await P.waitForTimeout(300);
      r = await estado(P); chk(ruim(r).length === 0 && r.ladoAberto, `[D ${w}] linha da busca abre o painel lateral`);
      await fechar(P);
      await P.evaluate(() => { FIN.q = ''; FIN.busca = null; finReceitas(); });
      if (await irAba(P, 'projeto')) {
        const bp = P.locator('#fin-p-projeto [data-fin-pj="preparar"]').first();
        chk(await bp.count() > 0, `[D ${w}] "Preparar nota do mês" aparece no projeto incentivado`);
        if (await bp.count()) { await bp.click(); await P.waitForTimeout(900); r = await estado(P); chk(ruim(r).length === 0, `[D ${w}] "Preparar nota do mês" não quebra a tela (${ruim(r).join('; ') || 'ok'})`); await fechar(P); }
      }
      await ctx.close();
    }

    // ---- [E] o endereço guarda o estado (2000 px)
    {
      const { ctx, page: P } = await entrar(browser, 2000, 1100, erros);
      await P.evaluate(() => nav('financeiro')); await pronto(P);
      await P.click('[data-fin-aba="geral"]');
      await P.click('[data-fin-aba="receitas"]'); await P.waitForTimeout(200);
      let h = await P.evaluate(() => location.hash);
      chk(/^#financeiro\/receitas\?p=2026-11$/.test(h), '[E] aba Receitas no endereço com o período: ' + h);
      const tit = await P.locator('#fin-p-receitas [data-fin-rec]').nth(2).locator('xpath=.').evaluate(e => e.textContent.replace(/\s+/g, ' ').trim());
      await P.locator('#fin-p-receitas [data-fin-rec]').nth(2).click(); await P.waitForSelector('#fin-lado:not([hidden])');
      const t1 = await P.locator('#fin-lado-tit').textContent();
      h = await P.evaluate(() => location.hash);
      chk(/^#financeiro\/receitas\/[^?]+\?p=2026-11$/.test(h), '[E] o detalhe aberto fica no endereço: ' + h);
      await P.reload(); await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await pronto(P);
      await P.waitForSelector('#fin-lado:not([hidden])', { timeout: 8000 }).catch(() => {});
      const t2 = await P.locator('#fin-lado-tit').textContent().catch(() => '');
      chk(await P.evaluate(() => FIN.aba) === 'receitas' && !(await P.locator('#fin-lado').isHidden()) && t2 === t1, `[E] recarregar volta a Receitas com o mesmo detalhe aberto ("${t1}" → "${t2}"; linha "${tit.slice(0, 40)}")`);
      await fechar(P);
      h = await P.evaluate(() => location.hash);
      chk(h === '#financeiro/receitas?p=2026-11', '[E] fechar o detalhe tira ele do endereço: ' + h);
      await P.click('[data-fin-aba="dre"]'); await P.waitForTimeout(200);
      await P.goBack(); await P.waitForTimeout(600);
      chk(await P.evaluate(() => FIN.aba) === 'receitas' && !(await P.locator('#fin-p-receitas').isHidden()), '[E] Voltar do navegador volta da DRE para Receitas: ' + await P.evaluate(() => location.hash));
      await P.goForward(); await P.waitForTimeout(600);
      chk(await P.evaluate(() => FIN.aba) === 'dre', '[E] Avançar vai de novo para a DRE');
      await P.click('[data-fin-passo="-1"]'); await pronto(P);
      const opc = await P.$$eval('#fin-conta option', os => os.map(o => o.value).filter(Boolean));
      await P.selectOption('#fin-conta', opc[0]); await pronto(P);
      h = await P.evaluate(() => location.hash);
      chk(h === `#financeiro/dre?p=2026-10&conta=${opc[0]}`, '[E] período e conta no endereço: ' + h);
      await P.reload(); await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await pronto(P);
      chk((await P.locator('#fin-per-txt').textContent()) === 'outubro de 2026' && await P.evaluate(() => FIN.aba) === 'dre' && (await P.inputValue('#fin-conta')) === opc[0], '[E] recarregar mantém aba, período e conta');
      await P.goto(BASE + '/#financeiro/despesas?p=2026-T4'); await P.reload(); await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await pronto(P);
      chk((await P.locator('#fin-per-txt').textContent()) === '4º trimestre de 2026' && await P.evaluate(() => FIN.aba) === 'despesas' && (await P.inputValue('#fin-conta')) === '', '[E] endereço com trimestre abre o trimestre, sem filtro de conta');
      const did = await P.locator('#fin-p-despesas [data-fin-desp]').first().getAttribute('data-fin-desp');
      await P.goto(BASE + `/#financeiro/despesas/${did}?p=2026-11`); await P.reload(); await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await pronto(P);
      await P.waitForSelector('#fin-lado:not([hidden])', { timeout: 8000 }).catch(() => {});
      chk(!(await P.locator('#fin-lado').isHidden()) && await P.evaluate(() => FIN.dAtual && String(FIN.dAtual.id)) === did, '[E] endereço com a despesa abre o detalhe dela: ' + did + ' ' + await P.evaluate(() => location.hash + ' ' + JSON.stringify(FIN.det) + ' ' + (FIN.dAtual && FIN.dAtual.id)));
      await fechar(P);
      await ctx.close();
    }

    // ---- [F] condição de produção: contas desativadas (o site já está sem Mercado Pago: WP_BASE_URL morto)
    {
      const { ctx, page: P } = await entrar(browser, 2000, 1100, erros);
      const contas = await P.evaluate(async () => (await API('/api/financeiro?mes=2026-11')).contas);
      let desat = 0;
      for (const c of contas) desat += await P.evaluate(c => API(`/api/financeiro/contas/${c.id}`, { method: 'PUT', body: JSON.stringify({ nome: c.nome, banco: c.banco || '', tipo: c.tipo, restrito: !!c.restrito, ativa: false, projeto: c.projeto || '' }) }).then(() => 1, () => 0), c);   // a do Mercado Pago não se desativa
      chk(desat >= 1, `[F] ${desat} conta(s) desativada(s)`);
      await P.evaluate(() => nav('financeiro')); await pronto(P);
      await varrer(P, 2000, 'F contas desativadas', erros);
      for (const c of contas) await P.evaluate(c => API(`/api/financeiro/contas/${c.id}`, { method: 'PUT', body: JSON.stringify({ nome: c.nome, banco: c.banco || '', tipo: c.tipo, restrito: !!c.restrito, ativa: !!c.ativa, projeto: c.projeto || '' }) }).catch(() => {}), c);
      // ---- [G] uma aba que falha ao desenhar mostra o aviso só nela, com "Tentar de novo"; as outras continuam
      await P.evaluate(() => { window._finRecOrig = FIN.d.linhas; FIN.d.linhas = null; finReceitas(); });
      await P.click('[data-fin-aba="receitas"]');
      const av = await P.locator('#fin-p-receitas [data-fin-erro-aba="receitas"]').innerText().catch(() => '');
      chk(/Não foi possível mostrar/.test(av) && /Tentar de novo/.test(av), '[G] erro ao desenhar Receitas: aviso na aba, com "Tentar de novo"');
      await P.click('[data-fin-aba="dre"]');
      chk((await P.locator('#fin-p-dre').innerText()).length > 100, '[G] as outras abas continuam');
      await P.click('[data-fin-aba="receitas"]');
      await P.evaluate(() => { FIN.d.linhas = window._finRecOrig; });
      await P.click('#fin-p-receitas [data-fin-acao="tentar-aba"]');
      chk((await P.locator('#fin-p-receitas [data-fin-rec]').count()) > 0, '[G] "Tentar de novo" desenha a aba de novo');
      erros.splice(0, erros.length, ...erros.filter(e => !/linhas|null|undefined/.test(e)));   // o erro provocado em [G]
      await ctx.close();
    }
  } catch (e) {
    chk(false, 'o teste quebrou: ' + (e.stack || e.message).slice(0, 400));
  } finally {
    await browser.close();
  }
  chk(erros.length === 0, 'nenhum erro de JS: ' + erros.slice(0, 5).join(' | '));
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
