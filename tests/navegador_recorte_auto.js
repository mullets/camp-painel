// UX-44 · Recorte automático na conferência (Playwright + Chromium). Prova: a revisão mostra o retângulo proposto (tracejado) sobre a prévia,
// no lugar certo, e o selo "recorte automático"; "Usar recorte inteiro (sem recorte)" grava a escolha e o selo muda; "Usar recorte automático"
// volta; K abre "Recortar e alinhar" já com a caixa na proposta; papel vegetal mostra "recorte automático incerto" e nenhum retângulo; na tela
// cheia o tracejado acompanha a imagem; "Ver como vai ao site" devolve a imagem recortada; nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx): R=<repo> nav.sh 8987 tests/navegador_recorte_auto.js  (ou como em tests/navegador_recorte.js)
const { execFileSync } = require('child_process');
const os = require('os'), path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8987', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const SHOTS = process.env.CAMP_SHOTS || os.tmpdir();
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const PRONTOS = path.join(path.dirname(DB), 'prontos_recorte_auto_ui'); fs.mkdirSync(PRONTOS, { recursive: true });
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\nsys.path.insert(0,sys.argv[3])\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PRONTOS, __dirname], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F009-P0016', D1 = P + '-1960-S01-D00001', D2 = P + '-1960-S01-D00002';

// Duas folhas sintéticas (tests/fixtures_recorte.py): planta clara no fundo lilás com listras (1500x1000) e papel vegetal.
py(`
from pathlib import Path
import fixtures_recorte as fx
raiz = Path(sys.argv[2])
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F009','Euclides Oliveira','EOL',1)")
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F009', 16)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F009',16,'SESI Ribeirão Preto',1960,'Ribeirão Preto')")
con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote plantas','${P}','/x/plantas','revisao')")
lid = con.execute("SELECT MAX(id) FROM lista_processamento").fetchone()[0]
for n, im in ((1, fx.planta(1500, 1000, caixa=(300, 325, 1200, 650))), (2, fx.vegetal(1500, 1000))):
    cod = "${P}-1960-S01-D%05d" % n; rel = f"_campvision/preview/${P}/{cod}.jpg"; (raiz / rel).parent.mkdir(parents=True, exist_ok=True); im.save(raiz / rel, "JPEG", quality=92)
    con.execute("DELETE FROM item WHERE codigo=?", (cod,))
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,folha,ano_folha,origem,lote_id,revisao,pendencias) VALUES (?,'${P}','S01',?,'Corte',?,1960,'campvision',?,'pendente',?)", (cod, n, str(n), lid, json.dumps({"previa": rel})))
`);
const sql = q => py(`print(con.execute(${JSON.stringify(q)}).fetchone()[0])`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 } });
  const page = await ctx.newPage();
  page.on('console', m => { const u = ((m.location() || {}).url || ''); if (m.type() === 'error' && !ESPERADO(u) && !/ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|exemplo\.test/.test(m.text())) erros.push('console.error: ' + m.text() + ' [' + u.replace(BASE, '') + ']'); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  // posição do tracejado em frações da imagem MOSTRADA (object-fit: contain)
  const fracoes = () => page.evaluate(() => {
    const im = document.getElementById('rv-img'), cx = document.getElementById('ra-caixa'); if (!im || !cx || cx.hidden) return null;
    const ri = im.getBoundingClientRect(), rc = cx.getBoundingClientRect(), k = Math.min(ri.width / im.naturalWidth, ri.height / im.naturalHeight), dw = im.naturalWidth * k, dh = im.naturalHeight * k;
    const x0 = ri.left + (ri.width - dw) / 2, y0 = ri.top + (ri.height - dh) / 2;
    return { x: (rc.left - x0) / dw, y: (rc.top - y0) / dh, w: rc.width / dw, h: rc.height / dh, borda: getComputedStyle(cx).borderStyle };
  });
  const perto = (a, b) => a && ['x', 'y', 'w', 'h'].every(k => Math.abs(a[k] - b[k]) < 0.02);
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== "undefined" && EU && !document.getElementById('login').classList.contains('on'), null, { timeout: 15000 });
    await page.evaluate(p => { nav('projeto/' + p) }, P);
    await page.waitForSelector(`.thumb[data-rev-abrir="${D1}"]`, { timeout: 15000 });
    await page.click(`.thumb[data-rev-abrir="${D1}"]`);
    await page.waitForSelector('#d-body [data-ra-selo="ok"]', { timeout: 15000 });
    await page.waitForFunction(() => { const i = document.getElementById('rv-img'); return i && i.complete && i.naturalWidth === 1500 }, null, { timeout: 10000 });
    await page.waitForTimeout(400);
    const prop = await page.evaluate(c => RA_PROP[c].recorte, D1);
    chk(prop && Math.abs(prop.x - 0.19) < 0.02 && Math.abs(prop.w - 0.62) < 0.03, 'a proposta acerta a borda do papel (x≈0,19, w≈0,62): ' + JSON.stringify(prop));
    const f1 = await fracoes();
    chk(perto(f1, prop) && f1.borda === 'dashed', 'o retângulo tracejado aparece sobre a prévia, no lugar da proposta: ' + JSON.stringify(f1));
    chk((await page.textContent('#ra-info')).includes('recorte automático') && !!(await page.$('#ra-info [data-ra-inteira]')), 'selo "recorte automático" e o botão "Usar recorte inteiro (sem recorte)"');
    await page.locator('#d-body .rev-col-img').screenshot({ path: path.join(SHOTS, 'recorte_auto_conferencia.png') });
    // ---------- "Ver como vai ao site" ----------
    const href = await page.$eval('#ra-info [data-ra-publica]', a => a.getAttribute('href'));
    const tam = await page.evaluate(async h => { const b = await (await fetch(h)).blob(); const bm = await createImageBitmap(b); return [bm.width, bm.height] }, href);
    chk(Math.abs(tam[0] - Math.round(prop.w * 1500)) <= 3 && Math.abs(tam[1] - Math.round(prop.h * 1000)) <= 3, '"Ver como vai ao site" devolve a imagem recortada (' + tam + ')');
    // ---------- usar recorte inteiro / voltar ----------
    await page.click('#ra-info [data-ra-inteira]');
    await page.waitForSelector('#d-body [data-ra-selo="recusado"]', { timeout: 8000 });
    chk(sql(`SELECT sem_recorte_auto FROM item WHERE codigo='${D1}'`) === '1', '"Usar recorte inteiro (sem recorte)" grava a escolha na folha');
    chk(await page.$eval('#ra-caixa', e => e.classList.contains('recusado')), 'o tracejado fica apagado (só referência) e o selo diz "sem recorte (escolhido na conferência)"');
    await page.click('#ra-info [data-ra-usar]');
    await page.waitForSelector('#d-body [data-ra-selo="ok"]', { timeout: 8000 });
    chk(sql(`SELECT sem_recorte_auto FROM item WHERE codigo='${D1}'`) === '0', '"Usar recorte automático" volta ao recorte proposto');
    // ---------- K: o recorte manual parte da proposta ----------
    await page.keyboard.press('k');
    await page.waitForSelector('#aj-ed #aj-caixa', { timeout: 5000 });
    const bx = await page.evaluate(() => AJ && AJ.box);
    chk(perto(bx, prop), 'K abre "Recortar e alinhar" com a caixa já na proposta: ' + JSON.stringify(bx));
    await page.keyboard.press('Escape');
    await page.waitForSelector('#rv-img', { timeout: 5000 });
    // ---------- tela cheia ----------
    await page.keyboard.press('f');
    await page.waitForFunction(() => document.querySelector('.main').classList.contains('rev-cheia'), null, { timeout: 5000 });
    await page.waitForTimeout(600);
    const f2 = await fracoes();
    chk(perto(f2, prop), 'tela cheia: o tracejado acompanha a imagem: ' + JSON.stringify(f2));
    await page.keyboard.press('f'); await page.waitForTimeout(300);
    // ---------- vegetal ----------
    await page.evaluate(c => abrirRevisaoItem(c), D2);
    await page.waitForSelector('#d-body [data-ra-selo="incerto"]', { timeout: 15000 });
    chk(!(await page.$('#ra-caixa')) && /incerto/.test(await page.textContent('#ra-info')), 'papel vegetal: selo "recorte automático incerto", com o motivo, e nenhum retângulo');
    await page.locator('#d-body .rev-col-img').screenshot({ path: path.join(SHOTS, 'recorte_auto_incerto.png') });
  } catch (e) { chk(false, 'exceção: ' + e.message.split('\n')[0]); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 5).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma resposta de erro do painel' + (falhas.length ? ': ' + falhas.slice(0, 5).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
