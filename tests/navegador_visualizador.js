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
//  - Duplicatas (lado a lado, 22/11): cada lado com a mesma barra (‹ Anterior · grupo N de M · Próxima › andam entre os grupos); girar
//    chama a mesma rota; R L C + − 0 valem para o lado sob o mouse (ou com o foco) e não vão ao menu nem confirmam; fora das folhas,
//    C continua confirmando o grupo; ← → e "‹ Anterior" mudam de grupo;
//  - o leitor (papel leitura) vê a barra sem girar nem recortar (também em Duplicatas);  nenhum erro de JavaScript.
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
const P2 = 'F026-P0168', E = n => `${P2}-1976-S01-D0000${n}`;   // Duplicatas: 2 grupos (D1 ← cópia D2; D3 ← cópia D4), todas com prévia
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
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 168)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,uf) VALUES ('${P2}','F026',168,'Casa Duplicatas',1976,'Santos','SP')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P2}'")
lid2 = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote duplicatas','${P2}','/x/dup','revisao')").lastrowid
for s in range(1, 5):
    cod = "${P2}-1976-S01-D%05d" % s
    rel = "_campvision/preview/${P2}/%s.jpg" % cod
    (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (1400, 2000), "white"); dr = ImageDraw.Draw(im); dr.rectangle((60, 60, 1340, 1940), outline="black", width=12); dr.text((680, 300), "DUP D%d" % s, fill="black")
    im.save(raiz / rel, "JPEG", quality=80)
    pend = {"bloqueios": [], "sinais": [], "ressalvas": [], "previa": rel}
    orig = None if s % 2 else "${P2}-1976-S01-D%05d" % (s - 1)
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,folha,origem,lote_id,status_site,pendencias,revisao,duplicata_de,tipo_duplicata) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P2}', 'S01', s, "Corte %d" % s, 'Corte', "%02d" % s, 'campvision', lid2, 'nao_publicado', json.dumps(pend, ensure_ascii=False), 'pendente', orig, 'exata' if orig else None))
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

    // ---------- 7. Duplicatas (lado a lado): a mesma barra em cada lado; as teclas valem para o lado com o foco ou sob o mouse ----------
    await ir('duplicatas/' + P2);
    await espera(async () => (await pg.$$('#dupv-grupos figure.dupv-folha')).length === 4);
    const lado = c => `#dupv figure[data-dupv-folha="${c}"]`;
    const NAV_DUP = ['‹ Anterior', 'Próxima ›', '↺ Girar à esquerda', '↻ Girar 90°', '✂ Recortar e alinhar', '−', '+', 'Ajustar', 'Abrir a imagem numa aba nova ↗'];
    const bs = await Promise.all([1, 2, 3, 4].map(n => barra(pg, lado(E(n)))));
    chk(bs.every(x => igual(x, CONTROLES, NAV_DUP)), 'Duplicatas: cada lado da comparação (a que vai ao site e a cópia) tem a mesma barra, na mesma ordem', JSON.stringify(bs.map(x => x && x.acoes)));
    chk(/grupo 1 de 2/.test(await pg.textContent(lado(E(1)) + ' .visor-pos')) && await pg.$eval(lado(E(2)) + ' [data-visor-acao="anterior"]', x => x.disabled) && !(await pg.$eval(lado(E(2)) + ' [data-visor-acao="proxima"]', x => x.disabled)),
      'Duplicatas: ‹ Anterior · "grupo 1 de 2" · Próxima › (no 1º grupo, Anterior desligado)');
    chk(/\/api\/itens\/.+\/previa/.test(await pg.getAttribute(lado(E(2)) + ' [data-visor-acao="abrir"]', 'href')), 'Duplicatas: "Abrir a imagem numa aba nova" abre a imagem grande daquele lado');
    // a ação da tela continua: "Confirmar" (simulado: o banco não muda) e a imagem ainda abre em outra aba
    const decis = []; await pg.route('**/duplicatas/decisoes', async r => { decis.push(JSON.parse(r.request().postData() || '{}')); await r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ feitas: 1, falhas: 0, resultados: [{ ok: true }] }) }); });
    const gir = []; await pg.route('**/api/itens/*/girar', async r => { const req = r.request(); gir.push({ url: new URL(req.url()).pathname, corpo: JSON.parse(req.postData() || '{}') }); await r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ giro_manual: 90, no_site: false }) }); });
    await pg.click(lado(E(2)) + ' [data-visor-acao="girar-dir"]').catch(() => {}); await espera(async () => gir.length >= 1, 4000);
    chk(gir[0] && gir[0].url === `/api/itens/${E(2)}/girar` && gir[0].corpo.graus === 90, 'Duplicatas: "↻ Girar 90°" da cópia chama POST /api/itens/{cópia}/girar com 90 (a mesma rota)', JSON.stringify(gir));
    await pg.waitForTimeout(1500);
    await pg.hover(lado(E(1)) + ' .dupv-img'); await pg.keyboard.press('r'); await espera(async () => gir.length >= 2, 4000);
    chk(gir[1] && gir[1].url === `/api/itens/${E(1)}/girar` && gir[1].corpo.graus === 90 && (await rota()) === '#duplicatas/' + P2, 'Duplicatas: a tecla R gira o lado sob o mouse (a que vai ao site) e NÃO vai para Cobranças', JSON.stringify({ gir, rota: await rota() }));
    await pg.waitForTimeout(1500);
    await pg.hover(lado(E(2)) + ' .dupv-img'); await pg.keyboard.press('l'); await espera(async () => gir.length >= 3, 4000);
    chk(gir[2] && gir[2].url === `/api/itens/${E(2)}/girar` && gir[2].corpo.graus === -90 && (await rota()) === '#duplicatas/' + P2, 'Duplicatas: com o mouse na cópia, a tecla L gira a cópia para a esquerda (e NÃO vai para Relatórios)', JSON.stringify({ gir, rota: await rota() }));
    await pg.unroute('**/api/itens/*/girar'); await pg.waitForTimeout(1500);
    await pg.hover(lado(E(2)) + ' .dupv-img'); await pg.keyboard.press('c');
    chk(await espera(async () => !!(await pg.$(lado(E(2)) + ' #aj-ed')), 4000) && !decis.length, 'Duplicatas: com o mouse na cópia, a tecla C abre o recorte DELA (e não confirma o grupo)', JSON.stringify({ decis }));
    await pg.click('#aj-ed [data-aj-cancelar]').catch(() => {}); await pg.waitForTimeout(300);
    chk(!(await pg.$('#aj-ed')) && !!(await pg.$(lado(E(2)) + ' a.dupv-img img')), 'Duplicatas: Cancelar fecha o recorte e a imagem da cópia volta');
    await pg.hover(lado(E(2)) + ' .dupv-img'); await pg.keyboard.press('+'); await pg.waitForTimeout(250);
    const zc = (await barra(pg, lado(E(2)))).pct, zo = (await barra(pg, lado(E(1)))).pct;
    chk(zc === '150%' && zo === '100%', 'Duplicatas: + amplia só o lado sob o mouse (cópia 150%, a outra 100%)', zc + ' / ' + zo);
    await pg.focus(lado(E(1)) + ' [data-visor-acao="zoom-ajustar"]'); await pg.mouse.move(5, 5); await pg.keyboard.press('+'); await pg.waitForTimeout(250);
    chk((await barra(pg, lado(E(1)))).pct === '150%' && (await barra(pg, lado(E(2)))).pct === '150%', 'Duplicatas: sem o mouse em cima, a tecla vale para o lado com o foco', (await barra(pg, lado(E(1)))).pct);
    await pg.keyboard.press('0'); await pg.waitForTimeout(200);
    chk((await barra(pg, lado(E(1)))).pct === '100%', 'Duplicatas: 0 volta o lado com o foco à imagem inteira');
    await pg.evaluate(() => document.activeElement && document.activeElement.blur()); await pg.mouse.move(5, 5);
    await pg.keyboard.press('ArrowRight'); await pg.waitForTimeout(400);
    chk(await pg.evaluate(() => [...document.querySelectorAll('#dupv-grupos .dupv-grupo')].findIndex(g => g.classList.contains('foco'))) === 1, 'Duplicatas: → vai para o próximo grupo (como "Próxima ›" da barra)');
    await pg.click(lado(E(3)) + ' [data-visor-acao="anterior"]').catch(() => {}); await pg.waitForTimeout(400);
    chk(await pg.evaluate(() => [...document.querySelectorAll('#dupv-grupos .dupv-grupo')].findIndex(g => g.classList.contains('foco'))) === 0, 'Duplicatas: "‹ Anterior" da barra volta ao grupo anterior');
    await pg.evaluate(() => document.activeElement && document.activeElement.blur()); await pg.mouse.move(5, 5);   // o clique deixou o foco no botão da barra (que é de um lado)
    await pg.keyboard.press('c'); await espera(async () => decis.length >= 1, 4000);
    chk(decis[0] && decis[0].decisoes && decis[0].decisoes[0].acao === 'confirmar' && decis[0].decisoes[0].original === E(1), 'Duplicatas: fora das folhas, a tecla C continua confirmando o grupo (ação da tela mantida)', JSON.stringify(decis));
    await pg.unroute('**/duplicatas/decisoes');

    // ---------- 6. só leitura: a barra sem girar nem recortar ----------
    const ctxL = await br.newContext({ viewport: { width: 1366, height: 768 } }); const pl = await ctxL.newPage();
    pl.on('pageerror', e => erros.push(`pageerror (leitura): ${e.message}`));
    await pl.goto(BASE + '/');
    const ok = await pl.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'leitor@camp.arq.br', senha: 'senha-leitor-1234' }) }).then(r => r.ok));
    if (ok) {
      await pl.reload(); await pl.waitForTimeout(1000); await pl.evaluate(x => { location.hash = x; }, 'item/' + D(1)); await pl.waitForTimeout(1800);
      const bl = await barra(pl, '#idet');
      chk(igual(bl, ['anterior', 'proxima', 'zoom-menos', 'zoom-mais', 'zoom-ajustar', 'abrir'], ['‹ Anterior', 'Próxima ›', '−', '+', 'Ajustar', 'Abrir a imagem numa aba nova ↗']), 'só leitura: a mesma barra sem girar nem recortar', JSON.stringify(bl));
      await pl.evaluate(x => { location.hash = x; }, 'duplicatas/' + P2); await pl.waitForTimeout(1800);
      const bd = await barra(pl, `#dupv figure[data-dupv-folha="${E(2)}"]`);
      chk(igual(bd, ['anterior', 'proxima', 'zoom-menos', 'zoom-mais', 'zoom-ajustar', 'abrir'], ['‹ Anterior', 'Próxima ›', '−', '+', 'Ajustar', 'Abrir a imagem numa aba nova ↗']), 'só leitura: em Duplicatas, a mesma barra sem girar nem recortar', JSON.stringify(bd));
    } else linhas.push('(sem conta de leitura na semente: parte do papel leitura não rodou)');
    await ctxL.close();
  } catch (e) { chk(false, 'o teste rodou até o fim', e.stack || e.message); }
  chk(!erros.length, 'nenhum erro de JavaScript', erros.slice(0, 3).join(' | '));
  await br.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
