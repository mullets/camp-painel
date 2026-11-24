// CAMP-PROJ (24/11/2026). Projetos da CAMP no navegador. Rafael: "vamos ter uma área de projetos no sistema, interligados aos outros módulos
// dele, que vai ter os objetivos e prazos, e precisa sempre me avisar tudo."
// Confere, a 1440×900 e a 390×844 (celular): menu "Projetos da CAMP" (tecla 7), lista com situação, próximo prazo, progresso e avisos; o
// projeto do PRONAC com cada aba (Visão geral, Cronograma, Orçamento do SALIC, Financeiro do projeto, Documentos, Histórico) e o endereço
// #projetos_camp/<id>/<aba> (recarregar volta à mesma aba; Voltar do navegador volta à aba anterior); criar uma tarefa e mudar a situação;
// o bloco "Projetos da CAMP" na Home (atrasados, 7 dias, mudanças); sem erro de JavaScript; sem rolagem lateral no celular. Prints em PRINTS.
// Uso (servidor PRÓPRIO, porta 9131, banco com tests/semear_banco_teste.py + tests/semente_projetos_camp.py):
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9131 PRINTS=/dev/shm/prints node tests/navegador_projetos_camp.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9131';
const PRINTS = process.env.PRINTS || '';
if (PRINTS) fs.mkdirSync(PRINTS, { recursive: true });
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
const ABAS = ['geral', 'cronograma', 'orcamento', 'financeiro', 'documentos', 'historico'];

async function entrar(browser, opts, erros) {
  const ctx = await browser.newContext(opts);
  const page = await ctx.newPage();
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/status of (40[0-9]|50[0-9])|Failed to load resource|ERR_/.test(m.text())) erros.push('console: ' + m.text()); });
  page.on('dialog', d => d.dismiss().catch(() => {}));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, page };
}
const foto = async (P, nome) => { if (PRINTS) await P.screenshot({ path: `${PRINTS}/${nome}.png`, fullPage: true }); };
const semRolagemLateral = P => P.evaluate(() => { const m = document.querySelector('.main') || document.documentElement; return document.documentElement.scrollWidth <= innerWidth + 1 && m.scrollWidth <= m.clientWidth + 1; });

(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  for (const [rot, opts] of [['1440', { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 }], ['390', { viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true }]]) {
    const erros = [];
    const { ctx, page: P } = await entrar(browser, opts, erros);
    // Home: bloco Projetos da CAMP
    await P.evaluate(() => nav('painel'));
    await P.waitForSelector('#ini-projetos-camp .pc-home', { timeout: 15000 });
    const home = await P.$eval('#ini-projetos-camp', e => e.innerText);
    chk(/Projetos da CAMP/.test(home) && /atrasad/.test(home) && /em 7 dias/.test(home), `${rot}: Home mostra o bloco Projetos da CAMP com atrasados e 7 dias`);
    chk(/Tratar as imagens do acervo Karazawa/.test(home), `${rot}: Home lista a tarefa atrasada`);
    // 1440 vem antes: conta a mudança de outra pessoa desde a última visita; depois de abrir o projeto (1440), o 390 já não conta nenhuma
    chk(rot === '1440' ? (/mudança/.test(home) && !/\b0 mudanças/.test(home)) : /\b0 mudanças/.test(home), `${rot}: Home conta as mudanças desde a última visita (e abrir o projeto zera)`);
    await P.$eval('#ini-projetos-camp', e => e.scrollIntoView({ block: 'center' })); await P.waitForTimeout(200);
    if (PRINTS) { const b = await (await P.$('#ini-projetos-camp')).boundingBox(); await P.screenshot({ path: `${PRINTS}/home-bloco-${rot}.png`, clip: { x: Math.max(0, b.x - 8), y: Math.max(0, b.y - 8), width: Math.min(b.width + 16, opts.viewport.width), height: Math.min(b.height + 16, opts.viewport.height) } }); await foto(P, `home-${rot}`); }
    // lista
    if (rot === '1440') { await P.keyboard.press('7'); } else { await P.evaluate(() => nav('projetos_camp')); }
    await P.waitForSelector('#v-projetos_camp.on .pc-lista tbody tr[data-pc-abrir]', { timeout: 15000 });
    chk(await P.evaluate(() => location.hash === '#projetos_camp'), `${rot}: ${rot === '1440' ? 'tecla 7 abre' : 'abre'} #projetos_camp`);
    const lista = await P.$eval('#pc-corpo', e => e.innerText);
    chk(/PRONAC 2613864/.test(lista) && /Captação/.test(lista) && /Mostra Arquitetura Paulista/.test(lista), `${rot}: lista com os dois projetos, código e situação`);
    chk(/atrasado/.test(lista) && /em 7 dias/.test(lista), `${rot}: lista mostra atrasos e prazos de 7 dias`);
    chk(await semRolagemLateral(P), `${rot}: lista sem rolagem lateral`);
    await foto(P, `lista-${rot}`);
    // projeto do PRONAC, cada aba
    await P.click('#pc-corpo tr[data-pc-abrir="1"] .pc-nome');
    await P.waitForFunction(() => location.hash === '#projetos_camp/1' && document.querySelector('#pc-aba .pc-card'), null, { timeout: 15000 });
    for (const aba of ABAS) {
      await P.click(`#pc-corpo [role=tab][data-pc-aba="${aba}"]`);
      await P.waitForFunction(a => location.hash === '#projetos_camp/1' + (a === 'geral' ? '' : '/' + a) && document.querySelector(`#pc-corpo [data-pc-aba="${a}"][aria-selected="true"]`), aba, { timeout: 10000 });
      const txt = await P.$eval('#pc-aba', e => e.innerText);
      const esperado = { geral: /A preencher|Objetivos e metas/, cronograma: /Produção do livro/, orcamento: /163\.475,31/, financeiro: /sem comprovante/, documentos: /Anexar/, historico: /Projeto criado a partir do Financeiro/ }[aba];
      chk(esperado.test(txt), `${rot}: aba ${aba} com conteúdo esperado`);
      chk(await semRolagemLateral(P), `${rot}: aba ${aba} sem rolagem lateral`);
      await foto(P, `projeto-${aba}-${rot}`);
    }
    if (rot === '1440') {
      // a barra da linha do tempo ganhou posição (sem estilo inline no HTML)
      await P.click('#pc-corpo [role=tab][data-pc-aba="cronograma"]');
      await P.waitForSelector('.pc-tl-trilho > i');
      chk(await P.$$eval('.pc-tl-trilho > i', is => is.every(i => i.style.left !== '')), '1440: linha do tempo posicionada');
      // recarregar mantém a aba; Voltar do navegador volta para a aba anterior
      await P.reload(); await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU && document.querySelector('#pc-corpo [data-pc-aba="cronograma"][aria-selected="true"]'), null, { timeout: 15000 });
      chk(true, '1440: recarregar volta ao mesmo projeto e aba');
      await P.click('#pc-corpo [role=tab][data-pc-aba="orcamento"]');
      await P.waitForFunction(() => location.hash === '#projetos_camp/1/orcamento');
      await P.goBack(); await P.waitForFunction(() => location.hash === '#projetos_camp/1/cronograma' && document.querySelector('#pc-corpo [data-pc-aba="cronograma"][aria-selected="true"]'), null, { timeout: 10000 });
      chk(true, '1440: Voltar do navegador volta à aba anterior');
      // nova tarefa e mudar situação
      await P.click('#pc-corpo [data-pc-tar-nova=""]');
      await P.waitForSelector('#d-body form[data-pc-form="tarefa"]');
      await P.fill('#d-body [name=o_que]', 'Pedir orçamento à gráfica');
      await P.fill('#d-body [name=prazo]', new Date(Date.now() + 2 * 864e5).toISOString().slice(0, 10));
      await P.click('#d-body button[type=submit]');
      await P.waitForFunction(() => /Pedir orçamento à gráfica/.test(document.getElementById('pc-aba').innerText), null, { timeout: 10000 });
      chk(true, '1440: tarefa nova aparece no cronograma');
      const sel = await P.evaluate(() => { const li = [...document.querySelectorAll('.pc-tar li')].find(l => /Pedir orçamento à gráfica/.test(l.innerText)); return li.querySelector('select').id; });
      await P.selectOption('#' + sel, 'feita');
      await P.waitForFunction(() => { const li = [...document.querySelectorAll('.pc-tar li')].find(l => /Pedir orçamento à gráfica/.test(l.innerText)); return li && li.dataset.s === 'feita'; }, null, { timeout: 10000 });
      chk(true, '1440: mudar a situação da tarefa para Feita');
      await P.click('#pc-corpo [role=tab][data-pc-aba="historico"]');
      await P.waitForFunction(() => /Tarefa alterada: Pedir orçamento à gráfica · Feita/.test(document.getElementById('pc-aba').innerText), null, { timeout: 10000 });
      chk(true, '1440: histórico registra a tarefa feita');
      // projeto interno: orçamento próprio com despesa ligada
      await P.evaluate(() => nav('projetos_camp/2/orcamento'));
      await P.waitForFunction(() => /Impressão das pranchas/.test((document.getElementById('pc-aba') || {}).innerText || ''), null, { timeout: 10000 });
      const orc = await P.$eval('#pc-aba', e => e.innerText);
      chk(/1\.290,00/.test(orc) && /Perto do limite|Acima/.test(await P.evaluate(() => JSON.stringify(PC.det.alertas))), '1440: orçamento próprio com o realizado da despesa ligada e aviso de limite');
      await foto(P, 'projeto-interno-orcamento-1440');
    }
    chk(!erros.length, `${rot}: sem erro de JavaScript (${erros.slice(0, 3).join(' | ')})`);
    await ctx.close();
  }
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.log(linhas.join('\n')); console.error('ERRO', e.message); process.exit(2); });
