// CAMP-FIN (24/11/2026). Rafael, no print do Financeiro: "arruma o alinhamento aí de botões, e o sincronizar seria quando clicar aparecendo
// sincronizando e um loading nele". O botão "Sincronizar com o Mercado Pago" do topo não tinha ação nenhuma; os botões de "De onde vêm as
// saídas" (pequenos) e os das faixas (grandes) ficavam com larguras e bordas direitas diferentes.
// Prova: clicar → o botão fica desabilitado, com o giro (.busy) e o texto "Sincronizando…", com a mesma largura; termina quando
// /api/financeiro/mp/estado diz que acabou, o texto volta e aparece o aviso. As rotas de sincronizar/estado são interceptadas (nada vai ao
// Mercado Pago). Na aba Despesas, os botões das saídas têm a mesma largura e a mesma borda direita (±1 px).
// Uso (servidor PRÓPRIO, portas 9110–9119, banco com tests/semear_banco_teste.py + tests/semente_financeiro.py):
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9114 node tests/navegador_financeiro_sincronizar.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9114';
const problemas = [];
const chk = (ok, msg) => { console.log((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
(async () => {
  const br = await chromium.launch();
  const pg = await br.newPage({ viewport: { width: 1440, height: 900 } });
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  let posts = 0, estados = 0;
  await pg.route('**/api/financeiro/mp/sincronizar', r => { posts++; r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, iniciado: true }) }); });
  await pg.route('**/api/financeiro/mp/estado', r => { estados++; r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ em_andamento: estados < 3, ultimo_erro: '' }) }); });
  await pg.goto(BASE + '/');
  pg.on('dialog', d => d.dismiss().catch(() => {}));
  await pg.fill('#lg-email', 'rafael@camp.arq.br'); await pg.fill('#lg-senha', 'senha-bem-longa-123'); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  const pronto = () => pg.waitForFunction(() => document.getElementById('v-financeiro')?.classList.contains('on') && FIN.d && FIN.desp && !FIN.carregando, null, { timeout: 20000 });
  await pg.goto(BASE + '/#financeiro/geral'); await pronto();
  await pg.waitForTimeout(500);
  const b = pg.locator('#fin-sinc');
  const w0 = (await b.boundingBox()).width;
  await b.click();
  await pg.waitForTimeout(250);
  const durante = await b.evaluate(x => ({ dis: x.disabled, busy: x.classList.contains('busy'), aria: x.getAttribute('aria-busy'), txt: x.textContent.trim(), w: x.getBoundingClientRect().width, giro: getComputedStyle(x, '::before').animationName }));
  chk(posts === 1, `clicar chama POST /api/financeiro/mp/sincronizar uma vez (${posts})`);
  chk(durante.dis && durante.busy && durante.aria === 'true', 'durante: botão desabilitado, com .busy e aria-busy');
  chk(durante.txt === 'Sincronizando…', `durante: texto "Sincronizando…" (${durante.txt})`);
  chk(durante.giro && durante.giro !== 'none', `durante: o giro aparece (${durante.giro})`);
  chk(Math.abs(durante.w - w0) <= 1, `durante: mesma largura (${w0} → ${durante.w})`);
  await pg.screenshot({ path: (process.env.PRINTS || '/dev/shm') + '/fin-sinc-durante.png', clip: { x: 980, y: 290, width: 300, height: 80 } });
  await b.click({ force: true }).catch(() => {});
  chk(posts === 1, 'clicar de novo durante a sincronização não pede outra');
  await pg.waitForFunction(() => { const x = document.getElementById('fin-sinc'); return x && !x.disabled && x.textContent.trim() === 'Sincronizar com o Mercado Pago'; }, null, { timeout: 15000 }).then(() => chk(true, 'ao terminar: o botão volta ao normal'), () => chk(false, 'ao terminar: o botão volta ao normal'));
  chk(estados >= 3, `acompanhou /mp/estado até acabar (${estados} leituras)`);
  const toast = await pg.locator('#toast, .toast').allTextContents().catch(() => []);
  chk(toast.join(' ').includes('Sincronizado com o Mercado Pago'), `aviso "Sincronizado com o Mercado Pago." (${toast.join(' | ').slice(0, 120)})`);
  // alinhamento na aba Despesas
  await pg.goto(BASE + '/#financeiro/despesas'); await pronto();
  await pg.waitForTimeout(800);
  const bt = await pg.evaluate(() => [...document.querySelectorAll('#fin-p-despesas .fin-fontes li>.btn, #fin-p-despesas .fin-faixa .btn')].filter(x => x.offsetParent).map(x => { const r = x.getBoundingClientRect(); return { t: x.textContent.trim(), w: Math.round(r.width), d: Math.round(r.right) }; }));
  console.log('      botões:', JSON.stringify(bt));
  if (bt.length >= 2) {
    const ws = bt.map(x => x.w), ds = bt.map(x => x.d);
    chk(Math.max(...ws) - Math.min(...ws) <= 1, `botões das saídas com a mesma largura (${ws.join(', ')})`);
    chk(Math.max(...ds) - Math.min(...ds) <= 1, `botões das saídas com a mesma borda direita (${ds.join(', ')})`);
  } else chk(false, `botões das saídas na tela (${bt.length})`);
  await pg.screenshot({ path: (process.env.PRINTS || '/dev/shm') + '/fin-despesas-botoes.png', fullPage: false });
  chk(erros.length === 0, 'nenhum erro de JS ' + erros.join(' | ').slice(0, 200));
  await br.close();
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
