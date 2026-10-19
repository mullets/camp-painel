// Etiqueta da pasta 100 × 50 (layout D) com a faixa de 2 cm que dobra na lombada (19/10): "não consigo saber qual o projeto só de bater
// o olho na lombada", "a parte da lombada tá vazando depois da dobra de 2 cm" e "a escala não bate quando mando imprimir".
// Prova (Chromium, mídia de impressão): a faixa traz o NOME do projeto (em pé, como lombada de livro) e o código; nada da faixa passa de
// 17 mm (3 mm de folga antes da dobra); a etiqueta sai com 100 × 50 mm exatos; o "Ajuste desta impressora" (escala e mover) vale só na
// impressão, fica guardado neste computador e zera; a régua de teste sai no tamanho do formato com a marca da dobra; nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO, porta 8985):
//   CAMP_DB_PATH=/tmp/el.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/el.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8985)
//   CAMP_BASE=http://127.0.0.1:8985 node tests/navegador_etiqueta_lombada.js
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8985';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const pg = await br.newPage({ viewport: { width: 1400, height: 900 } });
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#etiquetas/projeto/F023-P0011'); await pg.reload(); await pg.waitForSelector('.lab-preview .label', { timeout: 15000 });
  await pg.evaluate(() => { try { localStorage.clear(); } catch (_) {} });
  await pg.selectOption('#l-fmt', '100x50'); await pg.selectOption('#l-papel', 'rolo'); await pg.waitForTimeout(500);
  const faixa = await pg.textContent('.lab-preview .lab-d [data-lombada]');
  chk(/Residência Riviera/.test(faixa) && /F023-P0011/.test(faixa), 'a faixa de 2 cm (layout D) mostra o NOME do projeto e o código', faixa);
  const medir = () => pg.evaluate(() => { const px = 96 / 25.4, l = document.querySelector('.printgrid .label'), f = l.querySelector('[data-lombada]'), R = e => e.getBoundingClientRect();
    const dentro = [...f.querySelectorAll('*')].filter(e => R(e).width > 0);
    return { l: [R(l).left / px, R(l).top / px, R(l).width / px, R(l).height / px].map(x => +x.toFixed(2)), faixaDir: +((R(f).right - R(l).left) / px).toFixed(2),
      maisDir: +Math.max(...dentro.map(e => (R(e).right - R(l).left) / px)).toFixed(2), nome: (() => { const n = f.querySelector('.ld-pnome'); return n ? [+(R(n).width / px).toFixed(1), +(R(n).height / px).toFixed(1), n.textContent] : null; })(), num: (() => { const n = f.querySelector('.ld-num'); return n ? +(n.scrollWidth / px).toFixed(1) : null; })() }; });
  await pg.emulateMedia({ media: 'print' });
  let m = await medir();
  chk(m.l[0] === 0 && m.l[1] === 0 && m.l[2] === 100 && m.l[3] === 50, 'impressão: a etiqueta tem exatamente 100 × 50 mm, no canto da página', JSON.stringify(m.l));
  chk(m.faixaDir === 20, 'a dobra (borda da faixa) fica a 20 mm', String(m.faixaDir));
  chk(m.maisDir <= 17.05, 'nada da faixa passa de 17 mm: 3 mm de folga antes da dobra (antes ia até 18,5 mm e vazava)', String(m.maisDir));
  chk(m.nome && m.nome[1] >= 2 && /Residência Riviera/.test(m.nome[2]), 'layout D mantido, agora com o nome do projeto na faixa (abaixo do código)', JSON.stringify(m.nome));
  chk(m.num && m.num <= 15.9, 'o número grande cabe na faixa sem cortar (antes passava de 2 cm)', String(m.num));
  await pg.emulateMedia({ media: 'screen' });
  // 100 × 150 (o rolo grande da CAMP): a mesma lombada de 2 cm, agora com 150 mm de altura
  await pg.selectOption('#l-fmt', '100x150'); await pg.waitForTimeout(500);
  chk(await pg.$('.lab-preview .lab-d.alta [data-lombada]') !== null && /Residência Riviera/.test(await pg.textContent('.lab-preview .lab-d [data-lombada]')), '100 × 150: layout com a lombada e o nome do projeto');
  await pg.locator('.lab-preview .label').first().screenshot({ path: (process.env.OUT || '/tmp') + '/etiqueta_100x150.png' }).catch(() => {});
  await pg.emulateMedia({ media: 'print' }); m = await medir(); await pg.emulateMedia({ media: 'screen' });
  chk(m.l[2] === 100 && m.l[3] === 150 && m.faixaDir === 20 && m.maisDir <= 17.05, '100 × 150: sai com 100 × 150 mm, dobra a 20 mm e nada da faixa passa de 17 mm', JSON.stringify(m));
  chk(m.nome && /Residência Riviera/.test(m.nome[2]) && m.num <= 15.9, '100 × 150: a mesma faixa D, com o nome do projeto e o número inteiro', JSON.stringify(m));
  await pg.selectOption('#l-fmt', '100x50'); await pg.waitForTimeout(300);
  // ajuste da impressora
  await pg.click('#lab-ajuste summary'); await pg.fill('#laj-escala', '98'); await pg.fill('#laj-x', '-1.5'); await pg.waitForTimeout(300);
  await pg.emulateMedia({ media: 'print' }); m = await medir(); await pg.emulateMedia({ media: 'screen' });
  chk(Math.abs(m.l[0] + 1.5) < 0.05 && Math.abs(m.l[2] - 98) < 0.05 && Math.abs(m.l[3] - 49) < 0.05, 'ajuste 98% e 1,5 mm para a esquerda: vale na impressão', JSON.stringify(m.l));
  const tela = await pg.evaluate(() => { const l = document.querySelector('.lab-preview .label'); return getComputedStyle(l).transform; });
  chk(tela === 'none', 'a prévia na tela não muda com o ajuste (só a impressão)', tela);
  await pg.reload(); await pg.waitForSelector('.lab-preview .label', { timeout: 15000 }); await pg.selectOption('#l-fmt', '100x50'); await pg.waitForTimeout(300);
  chk(await pg.inputValue('#laj-escala') === '98' && await pg.inputValue('#laj-x') === '-1.5' && /98%/.test(await pg.textContent('#laj-resumo')), 'o ajuste fica guardado neste computador para o formato (e aparece no resumo)');
  await pg.selectOption('#l-fmt', '70x35'); await pg.waitForTimeout(300);
  chk(await pg.inputValue('#laj-escala') === '100', 'outro formato tem o seu próprio ajuste (100%)');
  await pg.selectOption('#l-fmt', '100x50'); await pg.waitForTimeout(300);
  // régua de teste
  await pg.evaluate(() => { window.print = () => { window._imp = document.getElementById('printgrid').innerHTML; }; });
  await pg.click('#lab-ajuste summary').catch(() => {}); if (!(await pg.isVisible('#laj-regua'))) await pg.click('#lab-ajuste summary');
  await pg.click('#laj-regua'); const imp = await pg.evaluate(() => window._imp || '');
  chk(/Régua de teste 100 × 50 mm/.test(imp) && /dobra \(2 cm\)/.test(imp) && /width="100mm"/.test(imp), 'régua de teste: sai no tamanho do formato, com marcas e a dobra de 2 cm', imp.slice(0, 120));
  await pg.click('#laj-zerar'); await pg.waitForTimeout(200);
  chk(await pg.inputValue('#laj-escala') === '100' && await pg.inputValue('#laj-x') === '0', '"Zerar ajuste" volta a 100% sem deslocamento');
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.log(linhas.join('\n')); console.error('ERRO', e.message); process.exit(1); });
