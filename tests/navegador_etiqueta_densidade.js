// UX-26 · Legibilidade do código de barras nos formatos pequenos. Code 39 é pouco denso: com o código de folha mais longo (26 caracteres,
// ex. F009-P0015-1973-S01-D00001) a barra estreita fica abaixo de ~0,19 mm em alguns formatos e o leitor não lê com segurança.
// Prova (Chromium, mídia de impressão, tamanho real):
//  - a tabela de comprimento das barras usada no cálculo (LAB_BARRA_MM) bate com o que sai impresso em cada formato e desenho;
//  - labDensidade(): 70 × 35 e 20 × 140 marcados "não cabe legível" (sai QR); 100 × 50, 150 × 100, capa e Brother (Code 128) cabem;
//  - a folha de 26 caracteres em 70 × 35 sai com QR + o código escrito, nada passa da borda; em 100 × 50 continua Code 39;
//    códigos curtos (tubo F023-P0011 em 20 × 140) continuam Code 39; o seletor e o aviso dizem que sai QR;
//  - o QR e o Code 39 impressos são lidos pelo MESMO leitor do "Ler etiqueta" (ZXing com CODE_39 + QR_CODE) e o texto lido abre a folha.
// A prova física (imprimir e ler com o leitor da CAMP e com o celular) continua com uma pessoa.
// Uso (servidor PRÓPRIO, banco próprio):
//   CAMP_DB_PATH=/tmp/ag_h/d.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ag_h/d.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8948)
//   ZXING_LOCAL=/caminho/@zxing/library@0.21.3/umd/index.min.js CAMP_BASE=http://127.0.0.1:8948 node tests/navegador_etiqueta_densidade.js
//   (ZXING_LOCAL: `npm pack @zxing/library@0.21.3`; sem ele, a leitura é PULADA e o teste diz isso)
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const fs = require('fs');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8948';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const ZX = process.env.ZXING_LOCAL && fs.existsSync(process.env.ZXING_LOCAL) ? process.env.ZXING_LOCAL : null;
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
const FOLHA = 'F023-P0011-1959-S01-D00019';   // 26 caracteres, como F009-P0015-1973-S01-D00001
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const ctx = await br.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.route(/unpkg\.com\/@zxing\/library@0\.21\.3\//, route => ZX ? route.fulfill({ status: 200, contentType: 'application/javascript', body: fs.readFileSync(ZX) }) : route.fulfill({ status: 404, body: '' }));
  const pg = await ctx.newPage(); const erros = []; pg.on('pageerror', e => erros.push(e.message));
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#etiquetas/folha/' + FOLHA); await pg.reload(); await pg.waitForSelector('.lab-preview .label', { timeout: 15000 });
  await pg.evaluate(() => { try { localStorage.clear(); } catch (_) {} });
  await pg.waitForFunction(c => document.getElementById('lab-origem').textContent.includes(c.slice(-10)) && document.getElementById('l-proj').value === 'F023-P0011', FOLHA, { timeout: 10000 }).catch(() => {});
  const aba = async t => { await pg.click(`#lab-tabs [data-t="${t}"]`); await pg.waitForTimeout(400); };
  const fmt = async f => { await pg.selectOption('#l-fmt', f); if (await pg.isVisible('#l-papel')) await pg.selectOption('#l-papel', 'rolo'); await pg.fill('#l-qty', '1'); await pg.waitForTimeout(300); };
  // medida impressa: comprimento das barras (mm) do 1º código (o maior lado, porque a 150 × 100 sai girada e o tubo em pé)
  const impresso = async () => { await pg.emulateMedia({ media: 'print' }); const m = await pg.evaluate(() => { const px = 96 / 25.4, l = document.querySelector('.printgrid .label'); if (!l) return null;
      const R = e => e.getBoundingClientRect(), s = l.querySelector('svg:not(.logo)'), rl = R(l), fora = [...l.querySelectorAll('*')].filter(e => { const r = R(e); return r.width > 0 && (r.right > rl.right + 1 || r.bottom > rl.bottom + 1 || r.left < rl.left - 1 || r.top < rl.top - 1); }).length;
      return s ? { len: +(Math.max(R(s).width, R(s).height) / px).toFixed(2), lado: +(Math.min(R(s).width, R(s).height) / px).toFixed(2), qr: s.classList.contains('qr'), vb: s.getAttribute('viewBox'), fora, txt: l.textContent } : null; });
    await pg.emulateMedia({ media: 'screen' }); return m; };
  const tabela = await pg.evaluate(() => LAB_BARRA_MM);
  // 1) a tabela bate com o impresso (códigos curtos e longos que continuam em Code 39)
  const casos = [['documento', 'std', '100x50'], ['documento', 'std', '150x100'], ['tubo', 'std', '70x35'], ['tubo', 'tubo', '20x140'], ['documento', 'capa', '200x287'], ['projeto', 'd', '100x50'], ['projeto', 'd', '150x100']];
  for (const [t, des, f] of casos) {
    await aba(t); await fmt(f); const m = await impresso();
    chk(m && !m.qr && Math.abs(m.len - tabela[des][f]) <= 0.8, `tabela de densidade bate com o impresso: ${des} ${f} (${tabela[des][f]} mm)`, JSON.stringify(m && { len: m.len, qr: m.qr }));
  }
  // 2) o cálculo por formato
  const dens = await pg.evaluate(() => labDensidade());
  const d = f => dens.find(x => x.formato === f) || {};
  chk(d('70x35').cabe === false && d('70x35').simbolo === 'qr' && d('70x35').modulo_mm < 0.19, '70 × 35: barra estreita < 0,19 mm com 26 caracteres → "não cabe legível", sai QR', JSON.stringify(d('70x35')));
  chk(d('20x140').cabe === false && d('20x140').simbolo === 'qr', '20 × 140 (lombada): folha de 26 caracteres não cabe legível → QR', JSON.stringify(d('20x140')));
  chk(['100x50', '150x100', '200x287'].every(f => d(f).cabe === true && d(f).simbolo === 'code39'), '100 × 50, 150 × 100 e capa: Code 39 cabe legível', JSON.stringify(dens.filter(x => ['100x50', '150x100', '200x287'].includes(x.formato))));
  chk(d('100x50').modulo_mm >= 0.21 && d('100x50').modulo_mm <= 0.22, '100 × 50: barra estreita de ~0,216 mm com 26 caracteres (no limite, mas acima)', String(d('100x50').modulo_mm));
  chk(d('90x29').simbolo === 'code128' && d('90x29').cabe === true && d('90x29').modulo_mm >= 0.25, '90 × 29 (Brother): Code 128 com módulo de 3 pontos (0,254 mm)', JSON.stringify(d('90x29')));
  chk(['50x15', '40x12', '30x12'].every(f => d(f).simbolo === 'qr'), 'NIIMBOT (50 × 15, 40 × 12, 30 × 12): QR, como já era', JSON.stringify(dens.filter(x => /x1[25]$/.test(x.formato))));
  const op = await pg.evaluate(() => [...document.querySelectorAll('#l-fmt option')].filter(o => /folha sai com QR/.test(o.textContent)).map(o => o.value));
  chk(JSON.stringify(op.sort()) === JSON.stringify(['20x140', '70x35']), 'o seletor de formato avisa onde a folha sai com QR (70 × 35 e 20 × 140)', JSON.stringify(op));
  // 3) a folha de 26 caracteres em 70 × 35: QR + código escrito, nada fora da etiqueta; o aviso explica
  await aba('documento'); await fmt('70x35');
  let m = await impresso();
  chk(m && m.qr && m.lado >= 10 && m.txt.includes(FOLHA), '70 × 35: a folha sai com QR (≥ 10 mm) e o código escrito', JSON.stringify(m && { qr: m.qr, lado: m.lado }));
  chk(m && m.fora === 0, '70 × 35 com QR: nada passa da borda da etiqueta', String(m && m.fora));
  const mod = m && m.vb ? m.lado / +m.vb.split(' ')[2] : 0;
  chk(mod >= 0.3, 'o módulo do QR impresso tem ≥ 0,3 mm', mod.toFixed(3));
  const aviso = await pg.textContent('#lab-aviso');
  chk(/sai um QR/.test(aviso) && /Leitor só de código de barras não lê QR/.test(aviso), 'o aviso da prévia diz que sai QR e que leitor só de código de barras não o lê', aviso);
  const svgQR = await pg.evaluate(() => document.querySelector('.printgrid .label svg.qr').outerHTML);
  await fmt('20x140'); m = await impresso();
  chk(m && m.qr && m.txt.includes(FOLHA) && m.fora === 0, '20 × 140 com a folha: QR, código escrito, nada fora', JSON.stringify(m && { qr: m.qr, fora: m.fora }));
  // 4) onde cabe, continua Code 39 (nada muda para quem já usa)
  await fmt('100x50'); m = await impresso();
  chk(m && !m.qr && m.vb === '0 0 414.4 20', '100 × 50 com a folha: continua Code 39', JSON.stringify(m && { qr: m.qr, vb: m.vb }));
  const svgC39 = await pg.evaluate(() => document.querySelector('.printgrid .label svg:not(.logo)').outerHTML);
  chk(!/folha sai com QR|sai um QR/.test(await pg.textContent('#lab-aviso')), '100 × 50: sem aviso de QR');
  await aba('tubo'); m = await impresso();
  chk(m && !m.qr, 'lombada 20 × 140 com o código do projeto (10 caracteres): continua Code 39', JSON.stringify(m && { qr: m.qr }));
  // 5) leitura com o mesmo leitor do "Ler etiqueta" (ZXing, formatos CODE_39 e QR_CODE)
  if (!ZX) linhas.push('PULADO leitura do QR e do Code 39 (defina ZXING_LOCAL com o index.min.js do @zxing/library 0.21.3)');
  else {
    const lido = await pg.evaluate(async ([qr, c39]) => {
      const ZXL = await estnCarregarZXing(), hints = new Map(); hints.set(ZXL.DecodeHintType.POSSIBLE_FORMATS, [ZXL.BarcodeFormat.CODE_39, ZXL.BarcodeFormat.QR_CODE]); hints.set(ZXL.DecodeHintType.TRY_HARDER, true);
      const ler = (svg, w, h) => new Promise(ok => { const img = new Image(); img.onload = () => { const cv = document.createElement('canvas'); cv.width = w + 80; cv.height = h + 80; const cx = cv.getContext('2d'); cx.fillStyle = '#fff'; cx.fillRect(0, 0, cv.width, cv.height); cx.drawImage(img, 40, 40, w, h);
        try { const r = new ZXL.MultiFormatReader(); r.setHints(hints); const bm = new ZXL.BinaryBitmap(new ZXL.HybridBinarizer(new ZXL.HTMLCanvasElementLuminanceSource(cv))); const x = r.decode(bm); ok({ texto: x.getText(), formato: ZXL.BarcodeFormat[x.getBarcodeFormat()] }); } catch (e) { ok({ erro: String(e && e.name || e) }); } };
        img.onerror = () => ok({ erro: 'svg' }); img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ')); });
      return [await ler(qr, 264, 264), await ler(c39.replace('preserveAspectRatio="none"', ''), 1243, 120)];
    }, [svgQR, svgC39]);
    chk(lido[0].texto === FOLHA && lido[0].formato === 'QR_CODE', 'o QR da etiqueta 70 × 35 é lido pelo leitor do "Ler etiqueta" (ZXing) e dá o código da folha', JSON.stringify(lido[0]));
    chk(lido[1].texto === FOLHA && lido[1].formato === 'CODE_39', 'controle: o Code 39 da 100 × 50 também é lido pelo mesmo leitor', JSON.stringify(lido[1]));
    const res = await pg.evaluate(c => fetch('/api/resolver-codigo?c=' + encodeURIComponent(c)).then(r => r.json()), lido[0].texto || '');
    chk(res.tipo === 'folha' && res.rota === 'item/' + FOLHA, 'o texto lido do QR abre a folha certa no "Ler etiqueta"', JSON.stringify(res).slice(0, 200));
    const formatosLeitor = await pg.evaluate(() => /BarcodeFormat\.CODE_39,\s*ZX\.BarcodeFormat\.QR_CODE/.test(document.documentElement.innerHTML) && /\['code_39','qr_code'\]/.test(document.documentElement.innerHTML));
    chk(formatosLeitor, 'o "Ler etiqueta" pede Code 39 e QR (BarcodeDetector e ZXing)');
  }
  chk(erros.length === 0, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
