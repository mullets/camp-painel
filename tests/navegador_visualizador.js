// CAMP-VIEW no navegador de verdade (Playwright + Chromium): o visualizador padrão da folha.
// Rafael, no print de #item/F002-P0002-1973-S04-D00032: "cadê a opção de girar? cortar e etc? … mantenha as views meio padronizadas".
// Antes: a página da folha só tinha "− 100% + Ajustar" (sem girar nem recortar) e anterior/próxima no cabeçalho; a gaveta "Revisar folha"
// tinha outra barra, com outra ordem; as teclas mudavam de tela para tela (C só recortava na tela cheia; + − 0 só ampliavam na tela cheia).
// Prova, a 1366×768, num lote de 3 folhas com prévia do CAMP Vision:
//  - a MESMA barra (.visor-barra, os mesmos controles na mesma ordem: ‹ Anterior · Próxima › · ↺ Girar à esquerda · ↻ Girar 90° ·
//    ✂ Recortar e alinhar · − · + · Ajustar · Abrir a imagem numa aba nova ↗) em: #item, a gaveta "Revisar folha" aberta da grade do projeto,
//    a tela cheia, a tela de conferir (#conferir/…, aberta do Material novo) e a folha aberta de Problemas ("Abrir a folha para girar");
//  - em #item, "↻ Girar 90°", a tecla R e a tecla L chamam POST /api/itens/{c}/girar com 90 / 90 / −90 (rota simulada no navegador: o banco
//    não muda) e a tecla R NÃO vai para Cobranças; "✂ Recortar e alinhar" e a tecla C abrem o editor de recorte de sempre (Cancelar fecha);
//    + − 0 ampliam (150% / 100% / 100%); → e ← andam de folha;
//  - na gaveta, C abre o recorte (antes só na tela cheia) e + amplia (antes só na tela cheia);
//  - o leitor (papel leitura) vê a barra sem girar nem recortar;  nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx):
//   CAMP_DB_PATH=/tmp/vis/t.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/vis/t.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8900)
//   CAMP_DB_PATH=/tmp/vis/t.db CAMP_BASE=http://127.0.0.1:8900 node tests/navegador_visualizador.js
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8900', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const PRONTOS = path.join(path.dirname(DB), 'prontos_visor'); fs.mkdirSync(PRONTOS, { recursive: true });
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PRONTOS], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0167', D = n => `${P}-1976-S01-D0000${n}`;
py(`
from pathlib import Path
from PIL import Image, ImageDraw
raiz = Path(sys.argv[2])
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 167)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,uf,cliente) VALUES ('${P}','F026',167,'Casa Visor',1976,'Santos','SP','Cliente X')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
con.execute("DELETE FROM erro WHERE codigo LIKE '${P}%'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote visor','${P}','/x/visor','revisao')").lastrowid
for s in range(1, 4):
    cod = "${P}-1976-S01-D%05d" % s
    rel = "_campvision/preview/${P}/%s.jpg" % cod
    (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (1400, 2000), "white"); dr = ImageDraw.Draw(im); dr.rectangle((60, 60, 1340, 1940), outline="black", width=12); dr.text((680, 300), "TOPO D%d" % s, fill="black")
    im.save(raiz / rel, "JPEG", quality=80)
    pend = {"bloqueios": [], "sinais": [], "ressalvas": [], "previa": rel, "titulo_lido": "Planta %d" % s}
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,folha,origem,lote_id,status_site,pendencias,revisao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P}', 'S01', s, "Planta %d" % s, 'Planta', "%02d/03" % s, 'campvision', lid, 'nao_publicado', json.dumps(pend, ensure_ascii=False), 'pendente'))
`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await f()) return true; } catch (_) {} await new Promise(r => setTimeout(r, 150)); } return false; };
const CONTROLES = ['anterior', 'proxima', 'girar-esq', 'girar-dir', 'recortar', 'zoom-menos', 'zoom-mais', 'zoom-ajustar', 'abrir'];
const ROTULOS = ['‹ Anterior', 'Próxima ›', '↺ Girar à esquerda', '↻ Girar 90°', '✂ Recortar e alinhar', '−', '+', 'Ajustar', 'Abrir a imagem numa aba nova ↗'];
// a barra do visualizador dentro de `host`: os controles padrão, na ordem em que aparecem, com o texto de cada um
const barra = (pg, host) => pg.evaluate(host => {
  const b = document.querySelector(host + ' .visor-barra'); if (!b) return null;
  const xs = [...b.querySelectorAll('[data-visor-acao]')].filter(x => !x.hidden);
  return { acoes: xs.map(x => x.dataset.visorAcao), rotulos: xs.map(x => x.textContent.trim()), pct: (b.querySelector('.visor-pct') || {}).textContent || '', role: b.getAttribute('role') };
}, host);
const igual = (b, controles = CONTROLES, rotulos = ROTULOS) => !!b && JSON.stringify(b.acoes) === JSON.stringify(controles) && JSON.stringify(b.rotulos) === JSON.stringify(rotulos) && b.role === 'toolbar';

(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ctx = await br.newContext({ viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1 }); const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push(`pageerror: ${e.message}`));
  pg.on('console', m => { if (m.type() === 'error' && !/401|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ERR_FAILED|Failed to load resource|Failed to fetch/.test(m.text())) erros.push(`console.error: ${m.text()}`); });
  await pg.addInitScript(() => { try { localStorage.setItem('camp.dicaRev', '9'); localStorage.setItem('camp.revCheia', '0'); } catch (_) {} });
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.reload(); await pg.waitForTimeout(1200);
  const ir = async h => { await pg.evaluate(x => { location.hash = x; }, h); await pg.waitForTimeout(1500); };
  const rota = () => pg.evaluate(() => location.hash);
  try {
    // ---------- 1. #item ----------
    await ir('item/' + D(1));
    await espera(async () => !!(await barra(pg, '#idet')));
    let b = await barra(pg, '#idet');
    chk(igual(b), '#item: a barra padrão (anterior/próxima, girar, recortar, zoom, abrir) na ordem padrão', JSON.stringify(b));
    chk(!(await pg.$('#idet .dethdr .pager')), '#item: anterior/próxima saíram do cabeçalho (estão na barra do visualizador)');
    // girar: a rota de sempre (simulada aqui: o banco não muda)
    const pedidos = [];
    await pg.route('**/api/itens/*/girar', async r => { const req = r.request(); pedidos.push({ url: new URL(req.url()).pathname, corpo: JSON.parse(req.postData() || '{}') }); await r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ giro_manual: 90, no_site: false }) }); });
    await pg.click('#idet [data-visor-acao="girar-dir"]', { timeout: 3000 }).catch(() => {}); await espera(async () => pedidos.length >= 1, 4000);
    chk(pedidos[0] && pedidos[0].url === `/api/itens/${D(1)}/girar` && pedidos[0].corpo.graus === 90, '#item: "↻ Girar 90°" chama POST /api/itens/{c}/girar com 90', JSON.stringify(pedidos));
    await pg.waitForTimeout(900);
    await pg.keyboard.press('r'); await espera(async () => pedidos.length >= 2, 4000);
    chk(pedidos[1] && pedidos[1].corpo.graus === 90 && (await rota()) === '#item/' + D(1), '#item: a tecla R gira 90° (e NÃO vai para Cobranças)', JSON.stringify({ pedidos, rota: await rota() }));
    await pg.waitForTimeout(900);
    await pg.keyboard.press('l'); await espera(async () => pedidos.length >= 3, 4000);
    chk(pedidos[2] && pedidos[2].corpo.graus === -90 && (await rota()) === '#item/' + D(1), '#item: a tecla L gira 90° para a esquerda (e NÃO vai para Relatórios)', JSON.stringify({ pedidos, rota: await rota() }));
    await pg.unroute('**/api/itens/*/girar');
    await pg.waitForTimeout(900);
    // recortar: o editor de recorte de sempre, aqui mesmo
    await pg.click('#idet [data-visor-acao="recortar"]', { timeout: 3000 }).catch(() => {});
    chk(await espera(async () => !!(await pg.$('#idet #aj-ed'))), '#item: "✂ Recortar e alinhar" abre o editor de recorte na página da folha');
    await pg.click('#idet [data-aj-cancelar]').catch(() => {}); await pg.waitForTimeout(300);
    chk(!(await pg.$('#idet #aj-ed')) && !!(await pg.$('#idet [data-zoom] img')), '#item: Cancelar fecha o recorte e a imagem volta');
    await pg.mouse.click(5, 300).catch(() => {});
    await pg.keyboard.press('c');
    chk(await espera(async () => !!(await pg.$('#idet #aj-ed')), 3000) && (await rota()) === '#item/' + D(1), '#item: a tecla C abre o recorte (e NÃO vai para Configurações)', await rota());
    await pg.click('#idet [data-aj-cancelar]').catch(() => {}); await pg.waitForTimeout(300);
    // zoom
    await pg.keyboard.press('+'); await pg.waitForTimeout(250); const z1 = (await barra(pg, '#idet')).pct;
    await pg.keyboard.press('-'); await pg.waitForTimeout(250); const z2 = (await barra(pg, '#idet')).pct;
    await pg.keyboard.press('+'); await pg.keyboard.press('+'); await pg.keyboard.press('0'); await pg.waitForTimeout(250); const z3 = (await barra(pg, '#idet')).pct;
    chk(z1 === '150%' && z2 === '100%' && z3 === '100%', '#item: + − 0 ampliam, diminuem e voltam à imagem inteira (o % da barra acompanha)', [z1, z2, z3].join(' '));
    await pg.keyboard.press('ArrowRight'); const foi = await espera(async () => (await rota()) === '#item/' + D(2), 4000);
    await pg.waitForTimeout(800);
    await pg.keyboard.press('ArrowLeft'); const voltou = await espera(async () => (await rota()) === '#item/' + D(1), 4000);
    chk(foi && voltou, '#item: → e ← andam de folha', await rota());

    // ---------- 2. gaveta "Revisar folha" (grade do projeto) ----------
    await ir('projeto/' + P);
    await espera(async () => !!(await pg.$(`.thumb[data-rev-abrir="${D(1)}"]`)));
    await pg.click(`.thumb[data-rev-abrir="${D(1)}"]`).catch(() => {});
    await espera(async () => !!(await barra(pg, '#d-body')));
    b = await barra(pg, '#d-body');
    chk(igual(b), 'gaveta "Revisar folha" (grade do projeto): a mesma barra, na mesma ordem', JSON.stringify(b));
    await pg.locator('#d-body').focus().catch(() => {});
    await pg.keyboard.press('+'); await pg.waitForTimeout(250);
    chk((await barra(pg, '#d-body')).pct === '125%', 'gaveta: a tecla + amplia (antes só na tela cheia)', (await barra(pg, '#d-body')).pct);
    await pg.keyboard.press('0'); await pg.waitForTimeout(200);
    await pg.keyboard.press('c');
    chk(await espera(async () => !!(await pg.$('#d-body #aj-ed')), 3000), 'gaveta: a tecla C abre o recorte (antes só na tela cheia)');
    await pg.click('#d-body [data-aj-cancelar]').catch(() => {}); await pg.waitForTimeout(300);
    // ---------- 3. tela cheia ----------
    await pg.click('#d-body [data-rev-cheia]').catch(() => {}); await pg.waitForTimeout(600);
    b = await barra(pg, '#d-body');
    chk(await pg.evaluate(() => document.querySelector('.main').classList.contains('rev-cheia')) && igual(b), 'tela cheia: a mesma barra, na mesma ordem', JSON.stringify(b));
    await pg.click('#d-body [data-rev-cheia]').catch(() => {}); await pg.waitForTimeout(300);
    await pg.evaluate(() => closeDrawer(true)); await pg.waitForTimeout(300);

    // ---------- 4. Material novo → o lote → "Iniciar conferência"; e a tela de conferir ----------
    await ir('filas'); await pg.waitForTimeout(800);
    await pg.click(`#v-filas tr[data-nav="projeto/${P}"]`, { timeout: 4000 }).catch(() => {});
    const noProjeto = await espera(async () => (await rota()) === '#projeto/' + P && !!(await pg.$('#pj-proximo .btn.pri')), 6000);
    await pg.click('#pj-proximo .btn.pri', { timeout: 3000 }).catch(() => {});
    const abriuMN = await espera(async () => (await pg.evaluate(() => document.querySelector('.main').classList.contains('with-drawer') && (document.getElementById('d-sub') || {}).textContent || '')).startsWith(P) && !!(await barra(pg, '#d-body')), 6000);
    b = await barra(pg, '#d-body');
    chk(noProjeto && abriuMN && igual(b), 'Material novo → lote → "Iniciar conferência": a folha abre com a mesma barra', JSON.stringify({ noProjeto, abriuMN, b }));
    await pg.evaluate(() => { if (document.querySelector('.main.rev-cheia')) alternarRevCheia(); closeDrawer(true); }); await pg.waitForTimeout(300);
    await ir('conferir/' + P);
    await espera(async () => (await rota()).startsWith('#conferir/' + P) && !!(await barra(pg, '#cf-pane')));
    b = await barra(pg, '#cf-pane');
    chk(igual(b), 'tela de conferir (#conferir/…): a mesma barra, na mesma ordem', JSON.stringify(b));
    const atual0 = await pg.evaluate(() => CONF.atual);
    await pg.click('#cf-pane [data-visor-acao="proxima"]').catch(() => {});
    chk(await espera(async () => (await pg.evaluate(() => CONF.atual)) !== atual0, 3000), 'tela de conferir: "Próxima ›" da barra passa para a próxima folha da lista');

    // ---------- 5. Problemas: "Abrir a folha para girar" ----------
    const er = await pg.evaluate(c => fetch('/api/erros', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ codigo: c, gravidade: 'aviso', categoria: 'orientacao', descricao: 'Folha deitada (teste do visualizador)', origem: 'operador' }) }).then(r => r.json()), D(2));
    await ir('erros'); await pg.waitForTimeout(800);
    await pg.evaluate(id => { if (window.abrirErro) abrirErro(id); }, er.id); await pg.waitForTimeout(800);
    await pg.click('[data-err-acao="girar"]').catch(() => {});
    const abriu = await espera(async () => (await pg.evaluate(() => document.querySelector('.main').classList.contains('with-drawer') && (document.getElementById('d-sub') || {}).textContent)) === D(2) && !!(await barra(pg, '#d-body')), 9000);
    b = await barra(pg, '#d-body');
    chk(abriu && igual(b), 'Problemas → "Abrir a folha para girar": a folha abre com a mesma barra', JSON.stringify({ abriu, b, rota: await rota() }));
    await pg.evaluate(() => closeDrawer(true));

    // ---------- 6. só leitura: a barra sem girar nem recortar ----------
    const ctxL = await br.newContext({ viewport: { width: 1366, height: 768 } }); const pl = await ctxL.newPage();
    pl.on('pageerror', e => erros.push(`pageerror (leitura): ${e.message}`));
    await pl.goto(BASE + '/');
    const ok = await pl.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'leitor@camp.arq.br', senha: 'senha-leitor-1234' }) }).then(r => r.ok));
    if (ok) {
      await pl.reload(); await pl.waitForTimeout(1000); await pl.evaluate(x => { location.hash = x; }, 'item/' + D(1)); await pl.waitForTimeout(1800);
      const bl = await barra(pl, '#idet');
      chk(igual(bl, ['anterior', 'proxima', 'zoom-menos', 'zoom-mais', 'zoom-ajustar', 'abrir'], ['‹ Anterior', 'Próxima ›', '−', '+', 'Ajustar', 'Abrir a imagem numa aba nova ↗']), 'só leitura: a mesma barra sem girar nem recortar', JSON.stringify(bl));
    } else linhas.push('(sem conta de leitura na semente: parte do papel leitura não rodou)');
    await ctxL.close();
  } catch (e) { chk(false, 'o teste rodou até o fim', e.stack || e.message); }
  chk(!erros.length, 'nenhum erro de JavaScript', erros.slice(0, 3).join(' | '));
  await br.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
