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
  const pt = await pg.evaluate(() => fetch('/api/projetos/F023-P0011', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ identificacao_original: 'Tubos 118 (RESIDÊNCIA SR. LUIZ MARCELO SALES). Pesquisa (Patricia de Souza Gonçalves, Belas Artes): EO-REF-007.' }) }).then(r => r.status));
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
  // 150 × 100 deitada (rolo 100 × 150): a mesma faixa D, corpo largo; na impressão a página é o rolo e o desenho sai girado
  const faixaTela = () => pg.evaluate(() => { const px = 96 / 25.4, l = document.querySelector('.lab-preview .lab-d'), f = l.querySelector('[data-lombada]'), R = e => e.getBoundingClientRect(), z = R(l).width / (parseFloat(l.style.width) * px);
    const mm = v => +(v / px / z).toFixed(2); return { l: [mm(R(l).width), mm(R(l).height)], maisDir: Math.max(...[...f.querySelectorAll('*')].filter(e => R(e).width > 0).map(e => mm(R(e).right - R(l).left))),
      maisBaixo: Math.max(...[...f.querySelectorAll('*')].filter(e => R(e).height > 0).map(e => mm(R(e).bottom - R(l).top))), txt: f.textContent }; });
  let ft = await faixaTela();
  chk(/Oswaldo Corrêa Gonçalves/.test(ft.txt) && /1959/.test(ft.txt), 'a faixa traz o arquiteto e o ano (100 × 50)', ft.txt);
  chk(ft.maisBaixo <= 50.05, 'nada da faixa passa da borda de baixo (100 × 50)', String(ft.maisBaixo));
  await pg.selectOption('#l-fmt', '150x100'); await pg.waitForTimeout(500);
  chk(await pg.$('.lab-preview .lab-d.larga [data-lombada]') !== null, '150 × 100 deitada: layout D com a faixa e o corpo largo');
  await pg.locator('.lab-preview .label').first().screenshot({ path: (process.env.OUT || '/tmp') + '/etiqueta_150x100.png' }).catch(() => {});
  ft = await faixaTela();
  chk(ft.l[0] === 150 && ft.l[1] === 100 && ft.maisDir <= 17.05 && ft.maisBaixo <= 100.05 && /Oswaldo Corrêa Gonçalves/.test(ft.txt) && /1959/.test(ft.txt), '150 × 100: 150 × 100 mm, faixa até 17 mm com nome, arquiteto e ano, nada fora', JSON.stringify(ft));
  const corpo = await pg.evaluate(() => { const l = document.querySelector('.lab-preview .lab-d'), kv = [...l.querySelectorAll('.ld-kv b')].map(b => b.textContent), lb = l.getBoundingClientRect().bottom;
    return { kv, fora: [...l.querySelectorAll('.ld-corpo *')].filter(e => e.getBoundingClientRect().bottom > lb + 1).length }; });
  chk(['Material', 'Fundo', 'Cidade · ano', 'Volume', 'Local', 'Conteúdo'].every(x => corpo.kv.includes(x)) && !corpo.kv.includes('Documentos no volume'), '150 × 100: o corpo traz mais campos; vazio ou 0 não ocupa lugar', corpo.kv.join(', '));
  chk(corpo.fora === 0, '150 × 100: nada do corpo passa da borda de baixo', String(corpo.fora));
  const tubo = await pg.evaluate(() => { const s = [...document.querySelectorAll('.lab-preview .ld-kv span')].find(x => /Tubo original/.test(x.textContent)); return s ? s.textContent : ''; });
  chk(pt === 200 && /Tubos 118$/.test(tubo) && !/Pesquisa/.test(tubo), '"Tubo original" mostra só o tubo ("Tubos 118"), não o texto inteiro da identificação', pt + ' ' + tubo);
  await pg.fill('#l-qty', '2'); await pg.waitForTimeout(300);
  await pg.emulateMedia({ media: null });
  const pdf = await pg.pdf({ preferCSSPageSize: true, printBackground: true }), ps = pdf.toString('latin1');
  const caixas = [...ps.matchAll(/\/MediaBox\s*\[\s*0 0 ([\d.]+) ([\d.]+)\s*\]/g)].map(m => [+(m[1] / 72 * 25.4).toFixed(0), +(m[2] / 72 * 25.4).toFixed(0)]);
  chk(caixas.length === 2 && caixas.every(([a, b]) => a === 100 && b === 150), 'impressão deitada: uma página 100 × 150 (o rolo) por etiqueta, sem página a mais', JSON.stringify(caixas));
  const giro = await pg.evaluate(() => { const st = document.getElementById('lab-page').textContent; return /giro-pag/.test(st) && /rotate\(90deg\)/.test(st) && document.querySelectorAll('#printgrid .giro-pag > .label').length; });
  chk(giro === 2, 'na impressão cada etiqueta vai numa página do rolo, girada 90°', String(giro));
  await pg.selectOption('#l-fmt', '100x50'); await pg.waitForTimeout(300);
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
  // dados reais longos (print do Rafa, F009-P0092): nada se sobrepõe, observação na faixa, faixa com 20 mm
  await pg.evaluate(() => fetch('/api/projetos/F023-P0011', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ titulo: 'Residência Sr. Luiz Marcelo Sales', cidade: 'ALTO DE PINHEIROS', cliente: 'Luiz Marcelo Sales', endereco_obra: 'RUA DR. ALBERTO FARIA' }) }));
  await pg.reload(); await pg.waitForSelector('.lab-preview .label', { timeout: 15000 }); await pg.fill('#l-obs', 'Croquis');
  for (const f of ['100x50', '150x100']) {
    await pg.selectOption('#l-fmt', f); await pg.waitForTimeout(600);
    await pg.locator('.lab-preview .label').first().screenshot({ path: (process.env.OUT || '/tmp') + `/real_${f}.png` }).catch(() => {});
    const r = await pg.evaluate(() => { const l = document.querySelector('.lab-preview .lab-d'), R = e => e.getBoundingClientRect(), px = R(l).width / parseFloat(l.style.width);
      const sobre = c => { const k = [...c.children].filter(e => R(e).height > 0); const ruins = []; for (let i = 1; i < k.length; i++) if (R(k[i]).top < R(k[i - 1]).bottom - .3 * px) ruins.push(k[i - 1].className + '/' + k[i].className); return ruins; };
      const f = l.querySelector('[data-lombada]'), dentro = [...l.querySelectorAll('*')].filter(e => R(e).height > 0 && R(e).bottom > R(l).bottom + .3 * px).map(e => e.className);
      return { faixa_mm: +(R(f).width / px).toFixed(2), obs: /Croquis/.test(f.textContent), sobrepostos: [...sobre(f), ...sobre(l.querySelector('.ld-corpo'))], fora: dentro }; });
    chk(r.faixa_mm === 20 && r.obs && !r.sobrepostos.length && !r.fora.length, `${f} com dados longos: faixa de 20 mm, observação na faixa, nada sobreposto nem fora da etiqueta`, JSON.stringify(r));
  }
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.log(linhas.join('\n')); console.error('ERRO', e.message); process.exit(1); });
