// CAMP-PROB-REAL (22/11/2026): a lista de Problemas com o FORMATO dos dados reais, no navegador de verdade (Playwright + Chromium).
// Rafael, com o print da produção: "tá bem ruim de UI e UX, nem consigo alterar as coisas" — no banco real os grupos só tinham "Ver uma a uma",
// as linhas só "Analisar" e toda miniatura era "sem imagem". Prova: grupo com "Todas são deste projeto"; linha solta com os botões; miniaturas
// <img> pela rota de prévia; "É deste projeto" resolve a linha; linha sem decisão diz por quê; o topo cabe (1ª linha visível em 1366×768);
// abas sem "(N)" em monoespaçada; nenhum filtro rápido com 0.
// Uso (servidor PRÓPRIO, porta 9020–9029; o banco semeado com tests/semear_banco_teste.py + tests/semear_problemas_real.py):
//   CAMP_DB_PATH=/dev/shm/x/pr.db python3 tests/semear_banco_teste.py      (na pasta backend)
//   CAMP_DB_PATH=/dev/shm/x/pr.db PYTHONPATH=backend python3 tests/semear_problemas_real.py /dev/shm/x/prontos
//   (cd backend && CAMP_DB_PATH=/dev/shm/x/pr.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 9022)
//   CAMP_DB_PATH=/dev/shm/x/pr.db CAMP_BASE=http://127.0.0.1:9022 [PRINTS=/pasta] node tests/navegador_problemas_real.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9022', DB = process.env.CAMP_DB_PATH, PRINTS = process.env.PRINTS || '';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
if (py(`print(con.execute("SELECT COUNT(*) FROM erro WHERE codigo LIKE 'F001-%'").fetchone()[0])`) === '0') { console.error('rode antes tests/semear_problemas_real.py'); process.exit(2); }
// um problema em "Aguardando revisão": sem decisão rápida, a linha tem de dizer por quê (idempotente)
py(`
if not con.execute("SELECT 1 FROM erro WHERE descricao='[real] escala errada'").fetchone():
    con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,situacao,fase) VALUES ('corrigir','metadado','operador','F001-P0003-1970-S01-D00003','[real] escala errada','em_correcao','aguardando_revisao')")`);
const F21 = 'F001-P0021-1970-S01-D00001';
const id21 = +py(`print(con.execute("SELECT id FROM erro WHERE codigo='${F21}' AND chave LIKE 'campvision:erros:%'").fetchone()[0])`);
const idRev = +py(`print(con.execute("SELECT id FROM erro WHERE descricao='[real] escala errada'").fetchone()[0])`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } }); const page = await ctx.newPage();
    page.on('pageerror', e => erros.push(e.message)); page.on('dialog', d => d.dismiss().catch(() => {}));
    await page.goto(BASE + '/'); await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await page.waitForTimeout(500);
    const espera = async () => { await page.waitForFunction(() => { const b = document.getElementById('err-body'); return b && b.getAttribute('aria-busy') === 'false' && b.querySelector('[data-err-linha],[data-cp-grupo]'); }, null, { timeout: 15000 }); await page.waitForTimeout(700); };
    // como o print do Rafael: Críticos, agrupado (padrão com Críticos); a caixa de ajuda fechada
    await page.goto(BASE + '/#erros/~chip=critico'); await page.waitForTimeout(1500);
    await page.evaluate(() => { const b = [...document.querySelectorAll('[data-ajuda-fechar]')].find(x => x.offsetParent); if (b) b.click(); });
    await page.reload(); await espera();
    if (PRINTS) await page.screenshot({ path: PRINTS + '/depois-criticos-1366x768.png' });
    // topo
    const topo = await page.evaluate(() => { const l = document.querySelector('#err-body [data-err-linha],#err-body [data-cp-grupo]'); const r = l.getBoundingClientRect();
      return { top: r.top, bottom: r.bottom, h: innerHeight }; });
    chk(topo.bottom <= topo.h, `o topo cabe: a 1ª linha inteira (com os botões) aparece em 1366×768 sem rolar (vai até ${Math.round(topo.bottom)} px de ${topo.h}, mesmo com o aviso do QNAP)`);
    const abas = await page.$$eval('#err-abas .cp-aba', bs => bs.map(b => { const n = b.querySelector('b'); return { t: b.textContent, f: n ? getComputedStyle(n).fontFamily : '' }; }));
    chk(abas.length === 4 && abas.every(a => !/[()]/.test(a.t) && !/mono/i.test(a.f)), `abas com selo de contagem, sem "(N)" e sem monoespaçada (${JSON.stringify(abas).slice(0, 160)})`);
    const ctl = await page.evaluate(() => { const els = ['[data-cp-seq]', '#cp-agrupar', '#cp-ordem'].map(s => document.querySelector(s)); const box = els[0].closest('.cp-ctl');
      return { mesmo: !!box && els.every(e => box.contains(e)), nowrap: box ? getComputedStyle(box).flexWrap : '', y: els.map(e => Math.round(e.getBoundingClientRect().top + e.getBoundingClientRect().height / 2)) }; });
    chk(ctl.mesmo && ctl.nowrap === 'nowrap' && Math.max(...ctl.y) - Math.min(...ctl.y) <= 6, `"Resolver em sequência", "Agrupar" e "Ordenar por" num só grupo que não quebra: sempre na mesma linha (${JSON.stringify(ctl)})`);
    const chips = await page.$$eval('#cp-chips .cp-chip', bs => bs.map(b => ({ t: b.textContent.trim(), n: b.querySelector('b') ? +b.querySelector('b').textContent.replace(/\D/g, '') : null, on: b.getAttribute('aria-pressed') === 'true' })));
    chk(chips.length > 0 && chips.every(c => c.on || c.n !== 0), `nenhum filtro rápido com 0 (o ativo fica): ${chips.map(c => c.t).join(' | ')}`);
    const faixa = await page.$eval('#err-filtro-ativo', el => ({ bg: getComputedStyle(el).backgroundColor, h: el.getBoundingClientRect().height }));
    chk(/rgba\(0, 0, 0, 0\)|transparent/.test(faixa.bg) && faixa.h <= 36, `a faixa dos filtros ativos é uma linha fina, sem a barra bege (${JSON.stringify(faixa)})`);
    // grupo real
    const g = '#err-body [data-cp-grupo^="F001-P0001|"]';
    chk(!!(await page.$(`${g} [data-cp-g="deste_projeto"]`)), 'grupo "Residência Teresa Martino · 12 folhas": tem "Todas são deste projeto" (antes só "Ver uma a uma")');
    chk(!!(await page.$(`${g} [data-cp-g="fica_fora"]`)) && /não dá para mover/i.test(await page.$eval(g, el => el.textContent)), 'grupo: "Todas são de outro projeto (ficam fora)" e o porquê de não ter "Mover todas"');
    await page.waitForTimeout(800);
    const th = await page.$$eval(`${g} > .cp-corpo .cp-g-thumbs > *`, els => els.map(e => ({ tag: e.tagName, src: e.getAttribute('src') || '', ok: e.tagName === 'IMG' && e.complete && e.naturalWidth > 0, txt: e.textContent })));
    const imgs = th.filter(x => x.tag === 'IMG');
    chk(imgs.length >= 7 && imgs.every(x => /^\/api\/itens\/F001-P0001-1970-S01-D\d+\/previa\?t=240&q=1$/.test(x.src)) && imgs.filter(x => x.ok).length >= 7,
      `miniaturas do grupo: <img> pela rota de prévia, carregadas (${imgs.filter(x => x.ok).length} de ${th.length}; ${th.map(x => x.tag === 'IMG' ? 'img' : x.txt).join(',')})`);
    chk(th.filter(x => /sem imagem/.test(x.txt)).length <= 1, `"sem imagem" só onde a rota não tem imagem (no máximo a folha sem prévia): ${th.filter(x => /sem imagem/.test(x.txt)).length}`);
    // linha solta real
    const l21 = `#err-body [data-err-linha="${id21}"]`;
    chk(!!(await page.$(`${l21} [data-cp-r="deste_projeto"]`)) && !!(await page.$(`${l21} [data-cp-r="fica_fora"]`)), 'linha F001·P0021·D00001: botões "É deste projeto" e "É de outro projeto (fica fora)" na linha (antes só "Analisar" e ⋯)');
    chk(await page.$eval(l21, el => /fora do painel/.test(el.textContent) && !/não existe mais/.test(el.textContent) && /RESIDÊNCIA RAMALHO ALVES/.test(el.textContent)), 'linha: o carimbo, "(fora do painel)" e nunca "(não existe mais)"');
    chk(await page.$eval(`${l21} .cp-rap img`, el => /\/api\/itens\/F001-P0021-1970-S01-D00001\/previa/.test(el.getAttribute('src')) && el.naturalWidth > 0).catch(() => false), 'linha: a miniatura é <img> pela rota de prévia e carrega');
    // É deste projeto na linha
    const n0 = +(await page.$eval('#err-cnt', el => el.textContent.replace(/\D/g, '') || 0));
    await page.click(`${l21} [data-cp-r="deste_projeto"]`, { timeout: 4000 }).catch(() => {});
    await page.waitForFunction(s => !document.querySelector(s), l21, { timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(900);
    const sit = py(`print(con.execute("SELECT situacao||'|'||fase FROM erro WHERE id=${id21}").fetchone()[0])`);
    const ret = py(`print(con.execute("SELECT situacao FROM erro WHERE chave='campvision:retirado:${F21}'").fetchone()[0])`);
    const n1 = +(await page.$eval('#err-cnt', el => el.textContent.replace(/\D/g, '') || 0));
    chk(!(await page.$(l21)) && sit === 'corrigido|resolvido' && ret !== 'aberto' && n1 === n0 - 1, `"É deste projeto" na linha: a linha sai, Resolvido no banco, a retirada da mesma folha fecha junto (${sit}, retirada ${ret}, ${n0}→${n1})`);
    chk(await page.$eval('#toast', el => /Resolvido/.test(el.textContent) && /Desfazer/.test(el.textContent)), 'aviso "Resolvido. Desfazer"');
    // sem decisão rápida: o porquê
    await page.goto(BASE + '/#erros/~aba=todos&agrupar=0&por=100'); await espera();
    chk(await page.$eval(`#err-body [data-err-linha="${idRev}"] .cp-rap-motivo`, el => /Por que não tem decisão rápida/.test(el.textContent) && /Aguardando revisão/.test(el.textContent)).catch(() => false),
      'linha sem decisão rápida diz por quê ("Aguardando revisão": continue pelo painel)');
    const caladas = await page.$$eval('#err-body > [data-err-linha]', ls => ls.filter(l => !l.querySelector('.cp-rap [data-cp-r], .cp-rap-motivo')).map(l => l.dataset.errLinha));
    chk(caladas.length === 0, `toda linha aberta tem botão ou o porquê (${caladas.join(',')})`);
    if (PRINTS) { await page.goto(BASE + '/#erros/~chip=critico'); await espera(); await page.setViewportSize({ width: 1366, height: 2000 }); await page.waitForTimeout(1200); await page.screenshot({ path: PRINTS + '/depois-criticos-pagina.png' }); }
    chk(!erros.length, 'sem erro de JavaScript na página' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  } catch (e) { chk(false, 'o teste quebrou: ' + (e && e.message || e).slice(0, 300)); }
  finally { await browser.close(); }
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
