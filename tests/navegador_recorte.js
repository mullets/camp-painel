// Revisão da folha: "Recortar e alinhar" no navegador de verdade (Playwright + Chromium). Pedido de 19/10.
// Prova: K abre a tela de recortar; arrastar os cantos (mouse e toque) muda a caixa; ±0,5°, o deslizador e o campo mudam o ângulo e a imagem
// gira ao vivo (CSS) com a grade por cima; Esc cancela sem fechar a gaveta; "Aplicar" grava e a prévia da revisão passa a ser o JPG corrigido
// (200x100, reto); "Desfazer recorte/alinhamento" volta à imagem do CAMP Vision (400x300); nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/rec.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/rec.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8931)
//   CAMP_DB_PATH=/tmp/rec.db CAMP_BASE=http://127.0.0.1:8931 [CAMP_SHOTS=/pasta] node tests/navegador_recorte.js
const { execFileSync } = require('child_process');
const os = require('os'), path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8931', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const SHOTS = process.env.CAMP_SHOTS || os.tmpdir();
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const PRONTOS = path.join(path.dirname(DB), 'prontos_recorte_ui'); fs.mkdirSync(PRONTOS, { recursive: true });
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PRONTOS], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0095', D1 = P + '-1975-S01-D00001';

// Uma folha "torta" (retângulo preto 200x100 numa folha 400x300, girada 5° anti-horário) num lote em revisão.
py(`
from pathlib import Path
from PIL import Image, ImageDraw
raiz = Path(sys.argv[2]); rel = "_campvision/preview/${P}/${D1}.jpg"; (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
im = Image.new("RGB", (400, 300), "white"); ImageDraw.Draw(im).rectangle((100, 100, 299, 199), fill="black")
im.rotate(5, resample=Image.Resampling.BICUBIC, fillcolor="white").save(raiz / rel, "JPEG", quality=95)
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 95)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F026',95,'Casa Torta',1975,'São Paulo')")
con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote torto','${P}','/x/torto','revisao')")
lid = con.execute("SELECT MAX(id) FROM lista_processamento").fetchone()[0]
con.execute("DELETE FROM item WHERE codigo='${D1}'")
con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,folha,ano_folha,origem,lote_id,revisao,pendencias) VALUES ('${D1}','${P}','S01',1,'Planta torta','1',1975,'campvision',?,'pendente',?)", (lid, json.dumps({"previa": rel})))
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test/.test(u);
  async function entrar(email, senha, ctxOpt) {
    const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 }, ...(ctxOpt || {}) });
    const page = await ctx.newPage();
    page.on('console', m => { const u = ((m.location() || {}).url || ''); if (m.type() === 'error' && !ESPERADO(u) && !/ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|exemplo\.test/.test(m.text())) erros.push(email + ' console.error: ' + m.text() + ' [' + u.replace(BASE, '') + ']'); });
    page.on('pageerror', e => erros.push(email + ' pageerror: ' + e.message));
    page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(email + ' ' + r.status() + ' ' + r.url().replace(BASE, '')); });
    await page.goto(BASE + '/');
    await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== "undefined" && EU && document.getElementById('login') && !document.getElementById('login').classList.contains('on'), null, { timeout: 15000 });
    return page;
  }
  const tamanhoRv = (page, w, h) => page.waitForFunction(([w, h]) => { const i = document.getElementById('rv-img'); return i && i.complete && Math.abs(i.naturalWidth - w) <= 3 && Math.abs(i.naturalHeight - h) <= 3 }, [w, h], { timeout: 10000 }).then(() => true, () => false);
  const caixa = page => page.evaluate(() => AJ && { ...AJ.box, ang: AJ.ang });
  async function arrastar(page, sel, fx, fy) {       // arrasta o puxador `sel` até o canto/borda da caixa ficar na fração (fx, fy) do palco
    const p = await page.$eval('#aj-palco', e => { const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height } });
    const h = await page.$eval(sel, e => { const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 } });
    const bx = await caixa(page), m = sel.slice(4), cx = m.includes('w') ? bx.x : m.includes('e') ? bx.x + bx.w : null, cy = m.includes('n') ? bx.y : m.includes('s') ? bx.y + bx.h : null;
    const dx = cx === null ? 0 : (fx - cx) * p.w, dy = cy === null ? 0 : (fy - cy) * p.h;
    await page.mouse.move(h.x, h.y); await page.mouse.down();
    await page.mouse.move(h.x + dx / 2, h.y + dy / 2, { steps: 4 });
    await page.mouse.move(h.x + dx, h.y + dy, { steps: 4 }); await page.mouse.up();
  }
  try {
    const page = await entrar('rafael@camp.arq.br', 'senha-bem-longa-123');
    await page.evaluate(p => { nav('projeto/' + p) }, P);
    await page.waitForSelector(`.thumb[data-rev-abrir="${D1}"]`, { timeout: 15000 });
    await page.click(`.thumb[data-rev-abrir="${D1}"]`);
    await page.waitForSelector('#d-body [data-rev-ajustar]', { timeout: 10000 });
    chk(await tamanhoRv(page, 400, 300), 'revisão: a prévia começa como veio do CAMP Vision (400x300)');
    chk(await page.$eval('[data-rev-ajuste-desfazer]', b => b.hidden), 'sem ajuste, "Desfazer recorte/alinhamento" fica escondido');
    // ---------- abrir com K ----------
    await page.keyboard.press('k');
    await page.waitForSelector('#aj-ed #aj-palco img', { timeout: 5000 });
    await page.waitForFunction(() => { const i = document.getElementById('aj-img'); return i && i.complete && i.naturalWidth === 400 }, null, { timeout: 8000 }); await page.waitForTimeout(400);   // a gaveta termina de assentar antes de arrastar
    chk(!!(await page.$('#aj-ed .aj-grade')) && (await page.$$('#aj-ed .aj-al')).length === 8, 'K abre "Recortar e alinhar": imagem inteira, grade e 8 puxadores');
    chk(JSON.stringify(await caixa(page)) === JSON.stringify({ x: 0, y: 0, w: 1, h: 1, ang: 0 }), 'a caixa começa na imagem inteira e o ângulo em 0');
    // ---------- Esc cancela sem fechar a gaveta ----------
    await arrastar(page, '.aj-nw', 0.3, 0.3); await page.keyboard.press('Escape');
    chk(!(await page.$('#aj-ed')) && (await page.textContent('#d-title')) === 'Revisar folha' && !!(await page.$('#rv-img')), 'Esc cancela: a tela de recortar fecha, a gaveta "Revisar folha" continua e nada foi gravado');
    // ---------- recortar (mouse) ----------
    await page.click('#d-body [data-rev-ajustar]'); await page.waitForSelector('#aj-ed #aj-caixa');
    await page.waitForFunction(() => { const i = document.getElementById('aj-img'); return i && i.complete && i.naturalWidth === 400 }, null, { timeout: 8000 }); await page.waitForTimeout(400);   // a gaveta termina de assentar antes de arrastar
    await arrastar(page, '.aj-nw', 0.25, 1 / 3);
    await arrastar(page, '.aj-se', 0.75, 2 / 3);
    let b = await caixa(page);
    chk(Math.abs(b.x - 0.25) < 0.02 && Math.abs(b.y - 1 / 3) < 0.02 && Math.abs(b.x + b.w - 0.75) < 0.02 && Math.abs(b.y + b.h - 2 / 3) < 0.02, 'arrastar os cantos com o mouse leva a caixa até o retângulo: ' + JSON.stringify(b));
    const est = await page.$eval('#aj-caixa', e => e.style.left + ' ' + e.style.width);
    chk(/%/.test(est), 'a caixa é desenhada em % do palco (' + est + ')');
    // ---------- toque: arrastar a borda direita com pointerType touch e voltar ----------
    const antes = (await caixa(page)).w;
    await page.evaluate(() => {
      const h = document.querySelector('.aj-e'), r = h.getBoundingClientRect(), p = document.getElementById('aj-palco').getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
      const ev = (t, cx) => new PointerEvent(t, { bubbles: true, cancelable: true, pointerId: 7, pointerType: 'touch', isPrimary: true, clientX: cx, clientY: y });
      h.dispatchEvent(ev('pointerdown', x)); h.dispatchEvent(ev('pointermove', x - p.width * 0.1)); h.dispatchEvent(ev('pointerup', x - p.width * 0.1));
    });
    const tocou = (await caixa(page)).w;
    chk(Math.abs(antes - tocou - 0.1) < 0.02, `toque: arrastar a borda direita 10% para dentro estreita a caixa (${antes.toFixed(3)} → ${tocou.toFixed(3)})`);
    await arrastar(page, '.aj-e', 0.75, 0.5);
    // ---------- ângulo: botões, deslizador e campo ----------
    for (let i = 0; i < 4; i++) await page.click('[data-aj-passo="0.5"]');
    chk((await caixa(page)).ang === 2 && (await page.inputValue('#aj-ang-n')) === '2', '+0,5° quatro vezes dá 2° (campo numérico acompanha)');
    await page.fill('#aj-ang-n', '4.5');
    chk((await caixa(page)).ang === 4.5 && (await page.inputValue('#aj-ang')) === '4.5', 'digitar 4,5 no campo move o deslizador');
    await page.keyboard.press('Escape').catch(() => {}); // Esc no campo: cancela também (testado acima); reabre para seguir
    await page.click('#d-body [data-rev-ajustar]'); await page.waitForSelector('#aj-ed #aj-caixa');
    await page.waitForFunction(() => { const i = document.getElementById('aj-img'); return i && i.complete && i.naturalWidth === 400 }, null, { timeout: 8000 }); await page.waitForTimeout(400);   // a gaveta termina de assentar antes de arrastar
    await arrastar(page, '.aj-nw', 0.25, 1 / 3); await arrastar(page, '.aj-se', 0.75, 2 / 3);
    await page.$eval('#aj-ang', e => { e.value = '4.5'; e.dispatchEvent(new Event('input', { bubbles: true })) });
    await page.locator('#aj-palco').click({ position: { x: 5, y: 5 }, force: true }).catch(() => {});   // tira o foco do campo para as teclas
    await page.keyboard.press(']');
    b = await caixa(page);
    chk(b.ang === 5, 'deslizador em 4,5 e a tecla ] (+0,5°) dão 5°: ' + b.ang);
    const tr = await page.$eval('#aj-img', e => e.style.transform);
    chk(tr === 'rotate(5deg)', 'prévia ao vivo: a imagem gira por CSS (' + tr + ')');
    await page.screenshot({ path: path.join(SHOTS, 'recorte_editor.png') });
    await page.locator('#d-body .rev-col-img').screenshot({ path: path.join(SHOTS, 'recorte_editor_detalhe.png') });
    // ---------- aplicar ----------
    await page.click('[data-aj-aplicar]');
    await page.waitForSelector('#rv-img', { timeout: 8000 });
    chk(!(await page.$('#aj-ed')), 'Aplicar fecha a tela de recortar');
    chk(await tamanhoRv(page, 200, 100), 'depois de aplicar, a prévia da revisão é o JPG corrigido (200x100, ±3 px do arrasto)');
    const src = await page.$eval('#rv-img', e => e.getAttribute('src'));
    chk(/&a=5_0\.2[45]\d*_/.test(src), 'a URL da prévia leva a marca do ajuste (evita imagem velha guardada): ' + src);
    const escuro = await page.evaluate(() => { const i = document.getElementById('rv-img'), c = document.createElement('canvas'); c.width = i.naturalWidth; c.height = i.naturalHeight; const g = c.getContext('2d'); g.drawImage(i, 0, 0); return [[4, 4], [195, 4], [4, 95], [195, 95], [100, 50]].map(([x, y]) => g.getImageData(x, y, 1, 1).data[0]) });
    chk(escuro.every(v => v < 110), 'a folha ficou reta e recortada: cantos e centro do JPG corrigido são do retângulo preto (' + escuro + ')');
    const det = await page.evaluate(async p => (await API('/api/projetos/' + p + '/detalhe')).itens.find(i => i.codigo.endsWith('D00001')), P);
    chk(det && det.alinhamento === 5 && det.recorte && Math.abs(det.recorte.w - 0.5) < 0.03, 'gravado na folha: 5° e a caixa (' + JSON.stringify(det && det.recorte) + ')');
    chk(!(await page.$eval('[data-rev-ajuste-desfazer]', b => b.hidden)), 'com ajuste, "Desfazer recorte/alinhamento" aparece');
    const mini = await page.$eval(`.thumb[data-rev-abrir="${D1}"] img.img-prev`, e => e.getAttribute('src'));
    chk(/&a=5_/.test(mini), 'a miniatura do cartão também troca para a corrigida: ' + mini);
    await page.locator('#d-body .rev-col-img').screenshot({ path: path.join(SHOTS, 'recorte_aplicado.png') });
    // ---------- desfazer ----------
    await page.click('[data-rev-ajuste-desfazer]');
    await page.waitForSelector('#conf-ov [data-conf="sim"]'); await page.click('#conf-ov [data-conf="sim"]');
    chk(await tamanhoRv(page, 400, 300), '"Desfazer recorte/alinhamento" volta à imagem do CAMP Vision (400x300)');
    chk(await page.$eval('[data-rev-ajuste-desfazer]', b => b.hidden), 'depois de desfazer, o botão some de novo');
    // ---------- celular: tela de recortar cabe sem rolagem lateral ----------
    const cel = await entrar('rafael@camp.arq.br', 'senha-bem-longa-123', { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    await cel.evaluate(p => { nav('projeto/' + p) }, P);
    await cel.waitForSelector(`.thumb[data-rev-abrir="${D1}"]`, { timeout: 15000 });
    await cel.evaluate(c => abrirRevisaoItem(c), D1);
    await cel.waitForSelector('#d-body [data-rev-ajustar]'); await cel.click('#d-body [data-rev-ajustar]'); await cel.waitForSelector('#aj-ed #aj-caixa');
    await cel.waitForFunction(() => { const i = document.getElementById('aj-img'); return i && i.complete && i.naturalWidth === 400 }, null, { timeout: 8000 }); await cel.waitForTimeout(400);
    const larg = await cel.evaluate(() => { const e = document.getElementById('aj-ed').getBoundingClientRect(); return { dir: e.right, vw: window.innerWidth } });
    chk(larg.dir <= larg.vw + 1, 'celular (390 px): a tela de recortar cabe na largura (' + JSON.stringify(larg) + ')');
    await cel.locator('#aj-ed').screenshot({ path: path.join(SHOTS, 'recorte_celular.png') });
    await cel.context().close();
  } catch (e) { chk(false, 'exceção: ' + e.message.split('\n')[0]); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 5).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma resposta de erro do painel' + (falhas.length ? ': ' + falhas.slice(0, 5).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
