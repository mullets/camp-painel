// Redesenho da Home, parte de cima (plano do Rafael de 03/11/2026, §5 a §9), no navegador de verdade (Playwright + Chromium):
//  §5 o subtítulo diz a contagem REAL da fila ("N coisas pedem sua atenção hoje" = fila.pedem_atencao do servidor = o que é da função da
//     pessoa, fora "Melhorar a base"); a data fica numa linha discreta;
//  §6 "Entenda esta página": inteira na 1ª vez, fechada (uma linha) depois do primeiro uso, e depois do "Entendi" não volta (nem no F5);
//     o "?" traz a explicação inteira; ajuda curta por seção ("Como a fila é ordenada?");
//  §7 indicadores com número grande, um só tipo de unidade cada, clicáveis levando à lista certa; "Sem dados" quando não há medida;
//  §8 filtros com os contadores do servidor; ordenação pelo servidor; linha com tipo, código, espera, "Urgente" + motivo e o botão;
//     "⋯" com "Agora não" (urgente pede motivo, que vai para o Histórico) e Desfazer; "Conferir" abre a 1ª folha pendente DO LOTE;
//     a lista não se mexe com o menu aberto ("Há novidades na lista"); quem só lê não tem botão nem "⋯";
//  §9 uma linha por sistema, o que falha primeiro, com texto (não só cor) e a hora da verificação; "Verificar agora";
//  1366×768: indicadores e a 1ª tarefa à vista sem rolar; 390 px: sem rolagem lateral.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada; o teste MUDA o banco: semeie de novo antes de repetir):
//   CAMP_DB_PATH=/tmp/rb/home.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/rb/home.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8982)
//   CAMP_DB_PATH=/tmp/rb/home.db CAMP_BASE=http://127.0.0.1:8982 node tests/navegador_redesenho_topo.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8982', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const problemas = [], linhas = [];
let ESPERA_500 = false;   // enquanto o teste simula a falha do ritmo, o 500 no console é esperado
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

async function entrar(browser, email, senha, erros, vp = { width: 1366, height: 768 }) {
  const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: 1 });
  const page = await ctx.newPage(); page.setDefaultTimeout(8000);
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?|\/api\/pedidos\/coleta$/.test(u);   // a semente não tem imagens; a coleta de pedidos é de operador (fora desta área)
  page.on('console', m => { if (m.type() === 'error' && !(ESPERA_500 && /status of 500/.test(m.text())) && !ESPERADO(((m.location() || {}).url || ''))) erros.push(email + ': ' + m.text()); });
  page.on('pageerror', e => erros.push(email + ': pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, page };
}
async function abrirHome(page) {
  await page.evaluate(() => { nav('painel'); carregarPainel() });
  await page.waitForSelector('#v-painel .ini-grid #ini-tarefas', { timeout: 15000 });
  await page.waitForFunction(() => !document.querySelector('#ini-saude .ini-hskel'), null, { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(500);
}
const api = (page, url, o) => page.evaluate(async ([u, o]) => { const r = await fetch(u, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...(o || {}) }); return { status: r.status, json: await r.json().catch(() => null) }; }, [url, o]);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    // começa do zero na ajuda da Home (como alguém que nunca abriu) e sem nada escondido
    py(`con.execute("DELETE FROM usuario_preferencia WHERE chave LIKE 'ajuda.%'")\ncon.execute("DELETE FROM tarefa_adiada")`);
    const adm = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    const P = adm.page;
    py(`con.execute("DELETE FROM usuario_preferencia WHERE chave LIKE 'ajuda.%'")`);   // o login já abriu a Home: zera de novo para a "1ª vez"
    await P.evaluate(() => { try { localStorage.clear() } catch (_) {} });
    await P.reload(); await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await abrirHome(P);

    // ---------- §6: 1ª vez inteira; depois fechada; "Entendi" não volta ----------
    const caixa = () => P.evaluate(() => { const b = document.querySelector('#v-painel > .ajuda-caixa'); if (!b) return null;
      return { recolhida: b.tagName === 'DETAILS', aberta: b.tagName !== 'DETAILS' || b.open, txt: b.textContent, alt: Math.round(b.getBoundingClientRect().height), assuntos: b.querySelectorAll('details.aj-assunto').length }; });
    let c = await caixa();
    chk(c && !c.recolhida && /Entenda esta página/.test(c.txt) && /Para que serve/.test(c.txt) && c.assuntos >= 3, `§6: na 1ª vez "Entenda esta página" vem inteira, com o conteúdo dividido por assunto (${c && c.assuntos} assuntos): ${JSON.stringify(c && { r: c.recolhida, t: c.txt.slice(0, 60) })}`);
    chk(c && /PARADO esperando/.test(c.txt) && /quase cheio/.test(c.txt) && /Diferenças com o site/.test(c.txt), '§6: o conteúdo de antes foi preservado (Decidir/PARADO, QNAP quase cheio, diferenças com o site)');
    await abrirHome(P);   // de novo na mesma visita: continua inteira
    c = await caixa();
    chk(c && !c.recolhida, '§6: na mesma visita (a Home redesenhada depois de uma ação), a caixa continua inteira');
    await P.reload(); await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await abrirHome(P);   // a próxima visita
    c = await caixa();
    chk(c && c.recolhida && !c.aberta && c.alt < 60, `§6: depois do primeiro uso, a caixa chega FECHADA, numa linha (${c && c.alt}px)`);
    await P.click('#v-painel > .ajuda-caixa > summary'); await P.click('#v-painel [data-ajuda-fechar="painel"]'); await P.waitForTimeout(800);
    await P.reload(); await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await abrirHome(P);
    chk(!(await caixa()), '§6: depois do "Entendi", a caixa não volta (nem depois do F5)');
    await P.click('#v-painel .ini-q'); await P.waitForTimeout(500);
    c = await caixa();
    chk(c && !c.recolhida && /Entenda esta página/.test(c.txt), '§6: o "?" do cabeçalho traz a explicação inteira');
    await P.click('#v-painel [data-ajuda-fechar="painel"]'); await P.waitForTimeout(500);
    await P.click('#v-painel [data-ini-ajuda="fila"] > summary');
    chk(/Mais urgente primeiro/.test(await P.innerText('#v-painel [data-ini-ajuda="fila"]')), '§6: ajuda curta da seção: "Como a fila é ordenada?" diz a regra');
    await P.keyboard.press('Escape');

    // ---------- §5: subtítulo = contagem real ----------
    const pa = (await api(P, '/api/painel')).json;
    const sub = await P.innerText('#ini-sub'), h1 = await P.innerText('#ini-saud'), data = await P.innerText('#v-painel .ini-data');
    const n = pa.fila.pedem_atencao;
    chk(/^(Bom dia|Boa tarde|Boa noite), Rafael\.$/.test(h1), `§5: título forte só com a saudação: "${h1}"`);
    chk(n > 0 && sub === `${n} ${n === 1 ? 'coisa pede' : 'coisas pedem'} sua atenção hoje`, `§5: subtítulo com a contagem real da fila (${n}): "${sub}"`);
    const todas = pa.fila.contagens.todas, base = pa.fila.contagens.base;
    chk(n === todas - base && n === pa.fila.itens.filter(i => i.meu && i.filtro !== 'base').length, `§5: a contagem é a fila sem "Melhorar a base" (${todas} − ${base} = ${n})`);
    chk(/\d{4} · \d{2}:\d{2}$/.test(data), `§5: dia e hora numa linha discreta: "${data}"`);
    const fs = await P.evaluate(() => ({ h1: parseFloat(getComputedStyle(document.getElementById('ini-saud')).fontSize), d: parseFloat(getComputedStyle(document.querySelector('.ini-data')).fontSize) }));
    chk(fs.h1 >= 26 && fs.h1 <= 32 && fs.d < fs.h1, `§5: título entre 26 e 32 px (${fs.h1}), data menor (${fs.d})`);

    // ---------- §7: indicadores ----------
    const pend = (await api(P, '/api/pendencias')).json;
    const ks = await P.evaluate(() => [...document.querySelectorAll('#v-painel .ini-kpi')].map(b => ({ rota: b.dataset.iniRota || null, v: b.querySelector('.v').textContent.trim(), l: b.querySelector('.l').textContent.trim(), alt: Math.round(b.getBoundingClientRect().height), fs: parseFloat(getComputedStyle(b.querySelector('.v')).fontSize), botao: b.tagName === 'BUTTON' })));
    chk(ks.length >= 3 && ks.length <= 4, `§7: ${ks.length} indicadores (3 ou 4)`);
    chk(new Set(ks.map(k => k.alt)).size === 1 && ks.every(k => k.fs >= 24), `§7: mesma altura e número grande (${ks.map(k => k.alt + 'px/' + k.fs).join(', ')})`);
    const kc = ks.find(k => k.rota === 'filas/conferir'), kd = ks.find(k => k.rota === 'decisoes'), kh = ks.find(k => /conferidas? hoje/.test(k.l));
    chk(kc && +kc.v === pend.lotes_conferir && /lotes? para conferir/.test(kc.l), `§7: "lotes para conferir" = ${pend.lotes_conferir} (fonte única)`);
    chk(kd && +kd.v === pend.decisoes, `§7: "decisões pendentes" = ${pend.decisoes}`);
    chk(kh && !kh.botao && (/^\d+$/.test(kh.v) || kh.v === 'Sem dados'), `§7: "folhas conferidas hoje" (não é lista: não é botão): "${kh && kh.v}"`);
    chk(ks.every(k => !/\b(lote|decis|folha)/.test(k.l) || [/lote/, /decis/, /folha/].filter(r => r.test(k.l)).length === 1), '§7: cada indicador conta um tipo só (lotes, decisões ou folhas)');
    await P.click('#v-painel .ini-kpi[data-ini-rota="filas/conferir"]'); await P.waitForTimeout(1500);
    chk(/^filas\/conferir/.test(await P.evaluate(() => rotaAtual())) && await P.locator('#filas-body tr[data-fase]').count() === pend.lotes_conferir, '§7: clicar em "lotes para conferir" abre Material novo filtrado com as mesmas linhas');
    await abrirHome(P);
    await P.click('#v-painel .ini-kpi[data-ini-rota="decisoes"]'); await P.waitForTimeout(1500);
    chk(/^decisoes/.test(await P.evaluate(() => rotaAtual())) && await P.locator('#dec-body tr[data-abrir]').count() === pend.decisoes, '§7: clicar em "decisões pendentes" abre Decisões com as mesmas linhas');
    // "Sem dados" ≠ 0: sem a medida do ritmo, o cartão não vira zero
    ESPERA_500 = true;
    await P.route('**/api/painel/ritmo**', r => r.fulfill({ status: 500, body: '{"detail":"falhou"}', contentType: 'application/json' }));
    await abrirHome(P);
    chk(/Sem dados/.test(await P.innerText('#ini-kpi-hoje')), '§7: sem a medida, "folhas conferidas hoje" diz "Sem dados" (não 0)');
    await P.unroute('**/api/painel/ritmo**'); ESPERA_500 = false;
    await abrirHome(P);

    // ---------- §8: filtros com os contadores do servidor ----------
    const fil = await P.evaluate(() => [...document.querySelectorAll('#ini-tarefas .ini-filtros [data-ini-filtro]')].map(b => [b.dataset.iniFiltro, +b.querySelector('b').textContent.replace(/\D/g, '')]));
    const esperado = Object.fromEntries(pa.fila.filtros.map(f => [f.id, f.n]));
    chk(['todas', 'conferir', 'publicar', 'responder', 'base'].every(id => fil.some(([f]) => f === id)) && fil.every(([f, v]) => esperado[f] === v), `§8: filtros Todas/Conferir/Publicar/Responder/Melhorar a base com os números do servidor: ${JSON.stringify(fil)}`);
    await P.click('#ini-tarefas [data-ini-filtro="conferir"]');
    const vis = await P.evaluate(() => [...document.querySelectorAll('#ini-lista .ini-task')].map(t => t.dataset.iniCat));
    chk(vis.length === Math.min(8, pa.fila.itens.filter(i => i.filtro === 'conferir').length) && vis.every(f => f === 'conferir'), `§8: o filtro "Conferir" mostra só as linhas de conferir (${vis.length})`);
    await P.click('#ini-tarefas [data-ini-filtro="todas"]');
    // a linha: tipo, código, espera, Urgente + motivo, botão principal
    const l0 = await P.evaluate(() => { const t = document.querySelector('#ini-lista .ini-task'); return { tipo: t.querySelector('.ini-tipo').textContent, urg: !!t.querySelector('.ini-urg'), motivo: (t.querySelector('.ini-motivo') || {}).textContent || '', cod: (t.querySelector('.code') || {}).textContent || '', esp: (t.querySelector('.ini-espera') || {}).textContent || '', pri: !!t.querySelector('button.pri[data-ini-acao]'), alt: Math.round(t.getBoundingClientRect().height) }; });
    chk(l0.urg && l0.motivo.length > 5 && /Decis/.test(l0.tipo) && /^F\d{3}/.test(l0.cod) && /há/.test(l0.esp) && l0.pri && l0.alt >= 52, `§8: a 1ª linha (mais urgente) tem tipo, "Urgente" + motivo, código, espera e o botão principal: ${JSON.stringify(l0)}`);
    const ordemApi = pa.fila.itens.map(i => i.titulo), ordemTela = await P.evaluate(() => [...document.querySelectorAll('#ini-lista .ini-task .t > b')].map(b => b.textContent));
    chk(JSON.stringify(ordemTela) === JSON.stringify(ordemApi.slice(0, ordemTela.length)), '§8: a tela segue a ordem do servidor ("mais urgente primeiro")');
    chk(await P.locator('#ini-tarefas .ini-task:not(.ini-base) .ini-ignorar > summary').first().innerText() === '⋯' && !/Ignorar/.test(await P.innerText('#ini-tarefas')), '§8: "Ignorar ▾" virou o menu discreto "⋯"');
    const nLinhas = pa.fila.itens.length;
    if (nLinhas > 8) { await P.click('#ini-tarefas [data-ini-vertodos]'); chk(await P.locator('#ini-lista .ini-task').count() === nLinhas, `§8: "Ver todos os itens da fila" mostra todas as ${nLinhas} linhas`); await P.click('#ini-tarefas [data-ini-vertodos]'); }
    // ordenação: a escolha vai ao servidor e fica lembrada
    const pedidos = []; P.on('request', r => { if (/\/api\/painel\?fila=/.test(r.url())) pedidos.push(r.url()); });
    await P.selectOption('#ini-ordem', 'antigo'); await P.waitForTimeout(1200);
    chk(pedidos.some(u => /fila=antigo/.test(u)) && await P.evaluate(() => localStorage.getItem('camp.ini.fila')) === 'antigo', '§8: "Mais antigo primeiro" pede a ordem ao servidor e fica lembrado');
    await P.selectOption('#ini-ordem', 'tipo'); await P.waitForTimeout(1200);
    chk(await P.locator('#ini-lista .ini-tgh').count() >= 2, '§8: "Por tipo" agrupa pela natureza do trabalho');
    await P.selectOption('#ini-ordem', 'urgente'); await P.waitForTimeout(1200);

    // a lista não se mexe com o menu "⋯" aberto
    await P.click('#ini-lista .ini-task:nth-child(2) .ini-ignorar > summary');
    const antes = await P.innerHTML('#ini-lista');
    await P.evaluate(() => carregarPainel()); await P.waitForTimeout(800);
    chk(await P.innerHTML('#ini-lista') === antes && /Há novidades na lista/.test(await P.innerText('#ini-fila-status')), '§8: com o menu aberto, a atualização espera ("Há novidades na lista")');
    await P.keyboard.press('Escape'); await P.click('#ini-fila-status [data-ini-aplicar]'); await P.waitForTimeout(1200);
    chk(!/Há novidades/.test(await P.innerText('#ini-tarefas')), '§8: "Atualizar a lista" aplica a atualização');

    // "Agora não" numa linha Urgente: pede o motivo, registra no Histórico e tem Desfazer
    const urg = pa.fila.itens.find(i => i.urgente && i.adiar);
    await P.click(`#ini-lista .ini-task[data-ini-urgente]:has([data-ini-adiar="${urg.adiar}"]) .ini-ignorar > summary`);
    await P.click(`[data-ini-adiar="${urg.adiar}"]`);
    await P.waitForSelector('#conf-ov', { timeout: 5000 });
    chk(/urgente/i.test(await P.innerText('#conf-ov')), '§8: esconder um item Urgente pede confirmação e o motivo');
    chk(await P.$eval('#conf-ov [data-conf="sim"]', b => b.disabled), '§8: sem motivo, o botão de esconder fica travado (motivo obrigatório)');
    await P.fill('#conf-ov textarea, #conf-ov input[type="text"]', 'vou decidir amanhã com a equipe');
    await P.click('#conf-ov [data-conf="sim"]');
    await P.waitForFunction(i => !document.querySelector(`#ini-lista [data-ini-adiar="${i}"]`), urg.adiar, { timeout: 8000 }).catch(() => {});
    chk(!(await P.$(`#ini-lista [data-ini-adiar="${urg.adiar}"]`)) && /Escondido por 7 dias/.test(await P.innerText('#ini-fila-status')), '§8: o item sai da lista e o resultado fica escrito na tela');
    const ev = py(`r=con.execute("SELECT detalhe FROM evento WHERE tipo='escondido_7_dias' ORDER BY id DESC LIMIT 1").fetchone()\nprint(r[0] if r else '')`);
    chk(/vou decidir amanhã/.test(ev), '§8: o motivo foi para o Histórico de ações: ' + ev.slice(0, 120));
    const sub2 = await P.innerText('#ini-sub');
    chk(sub2.startsWith(String(n - 1) + ' '), `§5: a contagem do subtítulo acompanha a fila (${n} → "${sub2}")`);
    await P.click('#toast button:has-text("Desfazer")').catch(() => {});
    await P.waitForFunction(i => !!document.querySelector(`#ini-lista [data-ini-adiar="${i}"]`), urg.adiar, { timeout: 8000 }).catch(() => {});
    chk(!!(await P.$(`#ini-lista [data-ini-adiar="${urg.adiar}"]`)), '§8: "Desfazer" traz o item de volta');
    // linha comum: sem pergunta, com Desfazer
    const comum = pa.fila.itens.find(i => !i.urgente && i.adiar && i.filtro !== 'base');
    if (comum) {
      await P.click(`#ini-lista .ini-task:has([data-ini-adiar="${comum.adiar}"]) .ini-ignorar > summary`); await P.click(`[data-ini-adiar="${comum.adiar}"]`); await P.waitForTimeout(1200);
      chk(!(await P.$('#conf-ov')) && !(await P.$(`#ini-lista [data-ini-adiar="${comum.adiar}"]`)), '§8: numa linha comum, "Agora não" é direto (com Desfazer)');
      await api(P, `/api/hoje/tarefas/${encodeURIComponent(comum.adiar)}/agora-nao`, { method: 'DELETE' }); await abrirHome(P);
    }

    // "Conferir" abre a 1ª folha pendente do LOTE certo
    const conf = pa.fila.itens.find(i => i.acao && i.acao.tipo === 'conferir');
    if (conf) {
      await P.evaluate(() => { window._ABRIU = null; const o = window.abrirRevisaoItem; window.abrirRevisaoItem = function (c, ...r) { window._ABRIU = c; return o.call(this, c, ...r) }; });
      await P.click(`#ini-lista .ini-task:has([data-ini-adiar="${conf.adiar}"]) [data-ini-acao]`);
      await P.waitForFunction(() => !!window._ABRIU, null, { timeout: 12000 }).catch(() => {});
      const abriu = await P.evaluate(() => window._ABRIU), det = (await api(P, `/api/projetos/${conf.codigo}/detalhe`)).json;
      const folha = ((det && det.itens) || []).find(x => x.codigo === abriu);
      chk(/^projeto\//.test(await P.evaluate(() => rotaAtual())) && folha && String(folha.lote_id) === String(conf.acao.lote) && folha.revisao === 'pendente', `§8: "Conferir" abriu a folha ${abriu} do lote ${conf.acao.lote} (não só a página do projeto)`);
      await P.evaluate(() => closeDrawer(true));
    } else chk(false, 'a semente deveria ter um lote para conferir');
    await abrirHome(P);

    // ---------- §9: saúde ----------
    const srv = await P.evaluate(() => [...document.querySelectorAll('#ini-saude .ini-srv')].map(x => ({ id: x.dataset.srv, n: x.dataset.nivel, tag: x.querySelector('.tag').textContent, ic: x.querySelector('.ini-srv-ic').textContent, t: x.innerText })));
    const ordem = { r: 0, a: 1, c: 2, g: 3 };
    chk(['qnap', 'campvision', 'site', 'estacoes', 'replica', 'backup'].every(id => srv.some(s => s.id === id)), `§9: uma linha por sistema: ${srv.map(s => s.id).join(', ')}`);
    chk(srv.every((s, i) => !i || ordem[srv[i - 1].n] <= ordem[s.n]) && srv[0].n === 'r', `§9: o que falha vem primeiro: ${srv.map(s => s.id + ':' + s.n).join(', ')}`);
    const q = srv.find(s => s.id === 'qnap');
    chk(q && q.n === 'r' && q.tag === 'crítico' && q.ic === '✕' && /desconectado/.test(q.t) && /importação/.test(q.t) && /copiadas/.test(q.t), '§9: QNAP desconectado: estado em texto ("crítico") e ícone, com o impacto na importação e nas cópias');
    chk(srv.every(s => ['crítico', 'atenção', 'não medido', 'normal', 'fora do expediente'].includes(s.tag)), '§9: todo estado tem rótulo em texto (não só cor)');
    chk(!srv.some(s => /em dia/i.test(s.t) && !/\d{2}:\d{2}/.test(s.t)), '§9: nada "em dia" sem a data da última cópia certa');
    chk(/Verificado às \d{2}:\d{2}/.test(await P.innerText('#ini-saude-quando')) && await P.locator('#ini-saude .ini-rodape[data-ini-rota="estacoes"]').count() === 1, '§9: hora da verificação e "Ver detalhes dos sistemas"');
    const fresco = []; P.on('request', r => { if (/\/api\/estacoes\?fresco=1/.test(r.url())) fresco.push(1); });
    await P.click('#ini-saude [data-ini-verificar]'); await P.waitForTimeout(2500);
    chk(fresco.length === 1 && /Verificado agora/.test(await P.innerText('#ini-saude-quando')), '§9: "Verificar agora" mede de novo e diz a hora');

    // ---------- 1366×768: indicadores e a 1ª tarefa sem rolar (uma visita nova, com a ajuda já usada) ----------
    await P.reload(); await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await abrirHome(P);
    const dobra = await P.evaluate(() => { const k = [...document.querySelectorAll('#v-painel .ini-kpi')].map(x => x.getBoundingClientRect().bottom), t = document.querySelector('#ini-lista .ini-task'), b = t.querySelector('[data-ini-acao]').getBoundingClientRect(); return { k: Math.max(...k), t: Math.round(t.getBoundingClientRect().bottom), b: Math.round(b.bottom), h: innerHeight, rola: document.querySelector('.main').scrollTop }; });
    chk(dobra.rola === 0 && dobra.k <= dobra.h && dobra.t <= dobra.h, `1366×768: indicadores e a 1ª tarefa (com o botão) à vista sem rolar: ${JSON.stringify(dobra)}`);
    await adm.ctx.close();

    // ---------- 390 px: sem rolagem lateral; botões com 44 px ----------
    const cel = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros, { width: 390, height: 844 });
    await abrirHome(cel.page);
    const lat = await cel.page.evaluate(() => { const m = document.querySelector('.main'); return { doc: document.documentElement.scrollWidth - innerWidth, main: m.scrollWidth - m.clientWidth, bt: Math.round(document.querySelector('#ini-lista [data-ini-acao]').getBoundingClientRect().height), larg: [...document.querySelectorAll('#v-painel .ini-task, #v-painel .ini-kpi, #v-painel .ini-srv')].filter(x => x.getBoundingClientRect().right > innerWidth + 1).length }; });
    chk(lat.doc <= 0 && lat.main <= 0 && lat.larg === 0, `390 px: sem rolagem lateral: ${JSON.stringify(lat)}`);
    chk(lat.bt >= 44, `390 px: botão da tarefa com alvo de toque de 44 px (${lat.bt})`);
    await cel.ctx.close();

    // ---------- quem só lê: nada de botão nem "⋯"; operador: a fila de admin esmaecida no fim ----------
    const le = await entrar(browser, 'leitor@camp.arq.br', 'senha-leitor-1234', erros);
    await abrirHome(le.page);
    chk(await le.page.locator('#ini-lista [data-ini-acao], #ini-lista .ini-ignorar').count() === 0 && await le.page.locator('#ini-lista .ini-task').count() > 0, 'quem só lê vê a fila, sem botão de ação e sem "⋯"');
    chk(/você pode ver tudo/.test(await le.page.innerText('#ini-sub')), 'quem só lê: o subtítulo diz que pode ver tudo, sem alterar');
    await le.ctx.close();
    const op = await entrar(browser, 'operador@camp.arq.br', 'senha-operador-123', erros);
    await abrirHome(op.page);
    const po = (await api(op.page, '/api/painel')).json, so = await op.page.innerText('#ini-sub');
    chk(so.startsWith(String(po.fila.pedem_atencao) + ' ') || (po.fila.pedem_atencao === 0 && /Nada pede/.test(so)), `operador: o subtítulo conta só a fila dele (${po.fila.pedem_atencao}): "${so}"`);
    const ult = await op.page.evaluate(() => { const t = [...document.querySelectorAll('#ini-lista .ini-task:not(.ini-base)')]; return t.map(x => x.classList.contains('ini-outro')); });
    chk(ult.length && ult.indexOf(true) === -1 || ult.slice(ult.indexOf(true)).every(Boolean), 'operador: o que é de admin vem esmaecido e no fim');
    await op.ctx.close();
  } catch (e) { problemas.push('exceção: ' + (e && e.stack || e)); }
  finally { await browser.close(); }
  for (const e of erros) problemas.push('console: ' + e);
  console.log(linhas.join('\n'));
  if (problemas.length) { console.log('\nPROBLEMAS (' + problemas.length + '):\n- ' + problemas.join('\n- ')); process.exit(1); }
  console.log('\nTUDO OK (' + linhas.length + ' verificações)');
})();
