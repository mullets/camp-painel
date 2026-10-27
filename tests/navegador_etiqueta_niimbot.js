// UX-42 · NIIMBOT imprime pela janela de impressão, como as outras impressoras (pedido de 27/10: "vai enviar pro servidor de etiquetas
// da rede como todas outras… e aí ele escolhe a impressora"). Para os formatos NIIMBOT (40 × 12, 30 × 12, 50 × 15):
//  - Imprimir chama window.print() (stub) e NÃO fala com o niimblue-node (nenhum pedido para localhost:5000);
//  - o CSS de impressão tem @page do tamanho do formato (ex. 40mm 12mm, margem 0) e cada etiqueta vira uma página
//    (prova pelo PDF do Chromium: N páginas de 40 × 12 mm para N etiquetas);
//  - a etiqueta continua o desenho da NIIMBOT (canvas com QR, preto e branco puro), no tamanho físico certo e sem suavização;
//  - a tela não tem mais o fluxo do niimblue-node (procurar impressora, conexão, densidade, "NIIMBOT não encontrada");
//  - a impressão fica registrada em Impressas, como nas outras.
// Uso (servidor PRÓPRIO, banco próprio):
//   CAMP_DB_PATH=/tmp/ag_n/n.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ag_n/n.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8998)
//   CAMP_DB_PATH=/tmp/ag_n/n.db CAMP_BASE=http://127.0.0.1:8998 node tests/navegador_etiqueta_niimbot.js
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const { execFileSync } = require('child_process');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8998';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const DB = process.env.CAMP_DB_PATH;
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
const FOLHA = 'F023-P0011-1959-S01-D00019';
if (DB) execFileSync('python3', ['-c', `import sqlite3; c = sqlite3.connect(${JSON.stringify(DB)}); c.execute("DELETE FROM etiqueta_impressao"); c.execute("DELETE FROM usuario_preferencia WHERE chave LIKE 'etiqueta.%'"); c.commit()`]);
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const ctx = await br.newContext({ viewport: { width: 1400, height: 900 } });
  const niimPedidos = [];
  await ctx.route(/localhost:5000|127\.0\.0\.1:5000/, route => { niimPedidos.push(route.request().url()); route.fulfill({ status: 200, contentType: 'application/json', body: '{"connected":true}' }); });
  const pg = await ctx.newPage(); const erros = []; pg.on('pageerror', e => erros.push(e.message));
  await pg.addInitScript(() => { window.__impressoes = 0; window.print = () => { window.__impressoes++; }; });
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#etiquetas/folha/' + FOLHA); await pg.reload(); await pg.waitForSelector('.lab-preview .label', { timeout: 15000 });
  await pg.waitForFunction(() => document.getElementById('l-proj').value === 'F023-P0011', null, { timeout: 10000 }).catch(() => {});
  const antes = await pg.evaluate(() => fetch('/api/etiquetas/impressas').then(r => r.json())).catch(() => []);
  for (const [f, w, h, n] of [['40x12', 40, 12, 3], ['50x15', 50, 15, 1]]) {
    await pg.selectOption('#l-fmt', f); if (await pg.isVisible('#l-papel')) await pg.selectOption('#l-papel', 'rolo');
    await pg.fill('#l-qty', String(n)); await pg.dispatchEvent('#l-qty', 'input'); await pg.dispatchEvent('#l-qty', 'change'); await pg.waitForTimeout(400);
    const tela = await pg.evaluate(() => ({ bt: document.getElementById('lab-imprimir').textContent, aviso: document.getElementById('lab-aviso').textContent,
      corpo: document.getElementById('v-etiquetas').innerText, cv: !!document.querySelector('.lab-preview canvas[data-niim]') }));
    chk(tela.cv, `${f}: a prévia continua o desenho da NIIMBOT (canvas)`);
    chk(!/na NIIMBOT/.test(tela.bt) && /^Imprimir/.test(tela.bt), `${f}: o botão é o Imprimir de sempre`, tela.bt);
    chk(!/niimblue|niim\.blue|localhost|niimbot_mac|Bluetooth|USB/i.test(tela.aviso + tela.corpo), `${f}: a tela não fala mais de niimblue-node, cabo ou Bluetooth`, tela.aviso);
    chk(/janela de impressão/.test(tela.aviso) && tela.aviso.includes(`${w} × ${h} mm`), `${f}: o aviso manda escolher a NIIMBOT na janela de impressão, papel ${w} × ${h} mm`, tela.aviso);
    const p0 = await pg.evaluate(() => window.__impressoes);
    await pg.click('#lab-imprimir'); await pg.waitForTimeout(1200);
    chk(await pg.evaluate(() => window.__impressoes) === p0 + 1, `${f}: Imprimir chama window.print()`);
    const css = await pg.evaluate(() => (document.getElementById('lab-page') || {}).textContent || '');
    chk(css.includes(`@page{size:${w}mm ${h}mm;margin:0}`), `${f}: @page do tamanho do formato (${w}mm ${h}mm, margem 0)`, css.slice(0, 200));
    // impresso: tamanho físico de cada etiqueta e do desenho; preto e branco puro; sem suavização
    await pg.emulateMedia({ media: 'print' });
    const m = await pg.evaluate(() => { const px = 96 / 25.4, ls = [...document.querySelectorAll('.printgrid .label')];
      return ls.map(l => { const r = l.getBoundingClientRect(), cv = l.querySelector('canvas'), rc = cv && cv.getBoundingClientRect(), cs = cv && getComputedStyle(cv);
        let pb = true; if (cv) { const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data; let pretos = 0; for (let i = 0; i < d.length; i += 4) { if (!((d[i] === 0 || d[i] === 255) && d[i] === d[i + 1] && d[i] === d[i + 2])) { pb = false; break; } if (!d[i]) pretos++; } if (pretos < 200) pb = false; }
        return { w: +(r.width / px).toFixed(2), h: +(r.height / px).toFixed(2), cw: rc && +(rc.width / px).toFixed(2), ch: rc && +(rc.height / px).toFixed(2), pts: cv && cv.width + 'x' + cv.height, pb, ir: cs && cs.imageRendering, quebra: getComputedStyle(l).breakAfter }; }); });
    await pg.emulateMedia({ media: null });   // (com 'screen' o pdf() usaria o CSS de tela)
    chk(m.length === n, `${f}: ${n} etiqueta(s) na área de impressão (uma por cópia)`, String(m.length));
    chk(m.length && m.every(x => Math.abs(x.w - w) < 0.3 && Math.abs(x.h - h) < 0.3), `${f}: cada etiqueta impressa tem ${w} × ${h} mm`, JSON.stringify(m[0]));
    chk(m.length && m.every(x => Math.abs(x.cw - w) < 0.3 && Math.abs(x.ch - 12) < 0.3 && x.pts === `${w * 8}x96`), `${f}: o desenho sai com ${w} × 12 mm a 8 pontos/mm (${w * 8} × 96 pontos)`, JSON.stringify(m[0]));
    chk(m.length && m.every(x => x.pb && x.ir === 'pixelated'), `${f}: preto e branco puro, sem suavização (image-rendering: pixelated)`, JSON.stringify(m[0]));
    chk(m.length && m.slice(0, -1).every(x => x.quebra === 'page'), `${f}: quebra de página depois de cada etiqueta`, JSON.stringify(m.map(x => x.quebra)));
    // PDF do Chromium com o tamanho de página do CSS: uma página por etiqueta, do tamanho do formato
    const pdfB = await pg.pdf({ preferCSSPageSize: true, printBackground: true }); if (process.env.PDF_DIR) require('fs').writeFileSync(`${process.env.PDF_DIR}/${f}.pdf`, pdfB); const pdf = pdfB.toString('latin1');
    const pags = (pdf.match(/\/Type\s*\/Page[^s]/g) || []).length, mb = (pdf.match(/\/MediaBox\s*\[\s*0 0 ([\d.]+) ([\d.]+)\s*\]/) || []).slice(1).map(x => +(x * 25.4 / 72).toFixed(1));
    chk(pags === n, `${f}: o PDF da impressão tem ${n} página(s), uma por etiqueta`, String(pags));
    chk(mb.length === 2 && Math.abs(mb[0] - w) < 0.6 && Math.abs(mb[1] - h) < 0.6, `${f}: cada página tem ${w} × ${h} mm`, JSON.stringify(mb));
  }
  chk(niimPedidos.length === 0, 'nenhum pedido ao niimblue-node (localhost:5000)', niimPedidos.join(' '));
  const sobra = await pg.evaluate(() => ['niimReq', 'imprimirNiimbot', 'niimEscolherImpressora', 'niimAjuda', 'niimConexao', 'niimServidor'].filter(f => typeof window[f] === 'function'));
  chk(sobra.length === 0, 'o fluxo do niimblue-node (procurar impressora, conexão, densidade) saiu do painel', sobra.join(', '));
  const html = await pg.evaluate(() => document.documentElement.innerHTML);
  chk(!/NIIMBOT não encontrad|camp\.niim\.(servidor|conexao|densidade)/.test(html), 'sem "NIIMBOT não encontrada" nem camp.niim.servidor/conexao/densidade');
  // registro em Impressas, como as outras
  const imp = await pg.evaluate(() => fetch('/api/etiquetas/impressas').then(r => r.json()));
  const novas = imp.slice(0, imp.length - antes.length);
  const r40 = novas.find(x => x.formato_mm === '40x12'), r50 = novas.find(x => x.formato_mm === '50x15');
  chk(novas.length === 2 && r40 && r40.quantidade === 3 && r40.tipo === 'documento' && r40.papel === 'niimbot' && r50 && r50.quantidade === 1, 'cada Imprimir fica registrado em Impressas (formato, quantidade, NIIMBOT)', JSON.stringify(novas).slice(0, 400));
  await pg.click('#lab-tabs [data-t="impressas"]');
  await pg.waitForSelector('#lab-impressas-body [data-lab-reimp]', { timeout: 10000 }).catch(() => {});
  const linha = await pg.evaluate(() => (document.querySelector('#lab-impressas-body tr') || {}).textContent || '');
  chk(/50 × 15 mm · NIIMBOT/.test(linha), 'a aba Impressas mostra a etiqueta da NIIMBOT', linha);
  chk(erros.length === 0, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
