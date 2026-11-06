// Arrastar as folhas para mudar a ordem na página do projeto (06/11/2026: "queria poder organizar as fotos arrastando pra nova ordem"),
// no navegador de verdade (Playwright + Chromium), com o banco real do servidor de teste:
//  1) Ordem "definida à mão" no select; só com ela (e sem filtro) a grade fica ordenável, com a alça ⠿ e o cursor de agarrar;
//  2) arrastar com o mouse: o cartão some do lugar, o fantasma segue o ponteiro, a linha azul diz onde cai; soltar grava sozinho
//     ("Ordem salva") e NÃO abre a revisão; o banco guarda a posição (o código D não muda);
//  3) recarregar a página: a ordem continua, e o projeto abre na "definida à mão" sem a pessoa escolher;
//  4) Desfazer volta à ordem de antes (banco e tela);
//  5) teclado: setas na alça movem a folha (o foco fica nela); ⋯ "Mover para depois" também;
//  6) "Revisar folha": ‹ Anterior · N de M · Próxima › seguem a ordem nova;
//  7) com filtro: não arrasta e aparece a dica "mostre Todas";
//  8) erro do servidor: as folhas voltam para onde estavam e o motivo aparece;
//  9) "Voltar à ordem do código" pergunta, limpa no banco e a grade volta ao código;
// 10) permissões: leitura não vê alça nem "Mover para…"; operador vê; 390 px escuro com toque (pointerType touch) na alça; sem erro de JS.
// Uso (servidor PRÓPRIO):
//   CAMP_DB_PATH=/tmp/x/t.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x/t.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8987)
//   CAMP_DB_PATH=/tmp/x/t.db CAMP_BASE=http://127.0.0.1:8987 CHROME=/opt/pw-browsers/chromium [PRINTS=/pasta] node tests/navegador_ordem_folhas.js
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8987', DB = process.env.CAMP_DB_PATH, PRINTS = process.env.PRINTS || '';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
if (PRINTS) fs.mkdirSync(PRINTS, { recursive: true });
const PRONTOS = path.join(path.dirname(DB), 'prontos_ordem'); fs.mkdirSync(PRONTOS, { recursive: true });
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PRONTOS], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0172', D = n => `${P}-1975-S03-D${String(n).padStart(5, '0')}`, N = 6;
function semear() {
  py(`
from pathlib import Path
from PIL import Image, ImageDraw
raiz = Path(sys.argv[2])
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 172)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,uf) VALUES ('${P}','F026',172,'Casa das Fotos em Ordem',1975,'Santos','SP')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
con.execute("DELETE FROM lista_processamento WHERE projeto_codigo='${P}'")
con.execute("DELETE FROM evento WHERE codigo='${P}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote fotos','${P}','/x/ordem','revisao')").lastrowid
CORES = [(200,80,60),(60,140,90),(60,90,170),(190,160,40),(130,70,150),(60,150,160)]
for s in range(1, ${N} + 1):
    cod = "${P}-1975-S03-D%05d" % s
    rel = "_campvision/preview/${P}/%s.jpg" % cod
    (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (1200, 900), CORES[s-1]); dr = ImageDraw.Draw(im); dr.rectangle((40, 40, 1160, 860), outline="white", width=10); dr.text((560, 430), "FOTO %d" % s, fill="white")
    im.save(raiz / rel, "JPEG", quality=70)
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,origem,lote_id,status_site,pendencias,revisao) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P}', 'S03', s, "Foto %d" % s, 'Fotografia', 'campvision', lid, 'nao_publicado', json.dumps({"previa": rel}), 'pendente'))
`);
}
const um = (sql, ...a) => py(`r=con.execute(${JSON.stringify(sql)}, ${JSON.stringify(a)}).fetchone()\nprint('' if r is None else (r[0] if r[0] is not None else ''))`);
const ordemBanco = () => py(`print(','.join(r[0][-2:] for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo='${P}' ORDER BY (ordem_manual IS NULL), ordem_manual, sequencial")))`);
const nComOrdem = () => +um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND ordem_manual IS NOT NULL", P);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await f()) return true; } catch (_) {} await new Promise(r => setTimeout(r, 150)); } return false; };
const ordemTela = pg => pg.evaluate(() => [...document.querySelectorAll('#pd .pj-folhas .thumb[data-rev-abrir]')].map(t => t.dataset.revAbrir.slice(-2)).join(','));
const toastTxt = pg => pg.evaluate(() => (document.getElementById('toast') || {}).textContent || '');
const foto = async (pg, nome) => { if (PRINTS) await pg.screenshot({ path: path.join(PRINTS, nome) }); };

async function entrar(br, email, senha, o = {}, erros) {
  const ctx = await br.newContext({ viewport: o.vp || { width: 1366, height: 768 }, deviceScaleFactor: 1, colorScheme: o.escuro ? 'dark' : 'light', hasTouch: !!o.toque });
  const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push(`${email}: pageerror: ${e.message}`));
  pg.on('console', m => { if (m.type() === 'error' && !/400|401|403|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ERR_FAILED|Failed to load resource|Failed to fetch/.test(m.text())) erros.push(`${email}: console.error: ${m.text()}`); });
  await pg.addInitScript(() => { try { localStorage.setItem('camp.dicaRev', '9'); localStorage.setItem('camp.revCheia', '0'); localStorage.setItem('camp.folhasVista', 'grade') } catch (_) {} });
  await pg.goto(BASE + '/');
  await pg.fill('#lg-email', email); await pg.fill('#lg-senha', senha); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, pg };
}
async function abrirProjeto(pg) {
  await pg.evaluate(c => { closeDrawer(true); nav('projeto/' + c); showProjeto(c, 'folhas'); }, P);
  await pg.waitForSelector('#pd .pj-folhas .thumb', { timeout: 15000, state: 'attached' });
  await pg.waitForTimeout(900);
  for (const a of await pg.$$('[data-ajuda-fechar]')) { try { if (await a.isVisible()) await a.click(); } catch (_) {} }
}
const centro = async (pg, sel) => { const b = await (await pg.$(sel)).boundingBox(); return { x: b.x + b.width / 2, y: b.y + b.height / 2, b }; };
// arrasta com o mouse o cartão `de` para antes (lado esquerdo) do cartão `para`; `meio` roda com o botão ainda apertado
async function arrastar(pg, de, para, meio) {
  await pg.evaluate(c => document.querySelector(`#pd .thumb[data-rev-abrir="${c}"]`).scrollIntoView({ block: 'center' }), de); await pg.waitForTimeout(150);
  const a = await centro(pg, `#pd .thumb[data-rev-abrir="${de}"] .img-real`);
  await pg.mouse.move(a.x, a.y); await pg.mouse.down();
  const b = await centro(pg, `#pd .thumb[data-rev-abrir="${para}"] .img-real`), bx = b.b.x + b.b.width * 0.2;
  for (let k = 1; k <= 12; k++) await pg.mouse.move(a.x + (bx - a.x) * k / 12, a.y + (b.y - a.y) * k / 12);
  if (meio) await meio();
  await pg.mouse.up();
}

(async () => {
  semear();
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const { ctx, pg } = await entrar(br, 'rafael@camp.arq.br', 'senha-bem-longa-123', {}, erros);
    await pg.evaluate(() => { try { Object.keys(localStorage).filter(k => k.startsWith('camp.ordem_folhas')).forEach(k => localStorage.removeItem(k)) } catch (_) {} });
    await abrirProjeto(pg);

    // ---------- 1) o select e quando a grade é ordenável ----------
    const s0 = await pg.evaluate(() => { const s = document.querySelector('#pd .folhas-bar [data-fl-ordem]'); return { v: s.value, ops: [...s.options].map(o => o.value + ':' + o.textContent),
      ordenavel: document.querySelector('#pd .pj-folhas').classList.contains('ordenavel'), alcaVis: [...document.querySelectorAll('#pd .cap-alca')].some(x => x.offsetParent) }; });
    chk(s0.v === 'codigo' && s0.ops.includes('manual:definida à mão'), 'Ordem tem "definida à mão"; sem ordem gravada o projeto abre na do código', JSON.stringify(s0));
    chk(!s0.ordenavel && !s0.alcaVis, 'na ordem do código a grade não arrasta (sem alça à vista)', JSON.stringify(s0));
    chk(await ordemTela(pg) === '01,02,03,04,05,06', 'grade começa na ordem do código', await ordemTela(pg));
    await pg.selectOption('#pd .folhas-bar [data-fl-ordem]', 'manual'); await pg.waitForTimeout(300);
    const s1 = await pg.evaluate(() => { const al = document.querySelector('#pd .thumb .cap-alca'); return { ordenavel: document.querySelector('#pd .pj-folhas').classList.contains('ordenavel'),
      alca: !!(al && al.offsetParent), cursor: al ? getComputedStyle(al).cursor : '', dica: (document.querySelector('#pd .fb-ordem-dica') || {}).offsetParent ? document.querySelector('#pd .fb-ordem-dica').textContent : '',
      limpar: !!document.querySelector('#pd [data-ordem-limpar]'), aria: al ? al.getAttribute('aria-label') : '' }; });
    chk(s1.ordenavel && s1.alca && s1.cursor === 'grab', '"definida à mão": alça ⠿ à vista com cursor de agarrar', JSON.stringify(s1));
    chk(/Arraste as folhas/.test(s1.dica) && !s1.limpar, 'dica "Arraste as folhas…"; sem ordem gravada ainda não há "Voltar à ordem do código"', JSON.stringify(s1));
    chk(/Mudar a ordem: .*Setas/.test(s1.aria), 'a alça diz ao leitor de tela o que fazer (setas ou arrastar)', s1.aria);
    chk(nComOrdem() === 0, 'só escolher "definida à mão" não grava nada no banco');

    // ---------- 2) arrastar com o mouse ----------
    let durante = null;
    await arrastar(pg, D(5), D(2), async () => {
      durante = await pg.evaluate(c => ({ fant: !!document.querySelector('#pd .thumb-fantasma'), apagado: document.querySelector(`#pd .thumb[data-rev-abrir="${c}"]`).classList.contains('arrastando'),
        alvo: (document.querySelector('#pd .thumb.solta-antes') || {}).dataset?.revAbrir || '', cursor: getComputedStyle(document.body).cursor }), D(5));
      await foto(pg, 'ordem-1366-claro-arrastando.png');
    });
    chk(durante && durante.fant && durante.apagado && durante.alvo === D(2) && durante.cursor === 'grabbing', 'durante o arraste: fantasma segue o ponteiro, cartão apagado, linha azul antes da D02', JSON.stringify(durante));
    chk(await espera(() => ordemBanco() === '01,05,02,03,04,06'), 'soltar grava sozinho: banco na ordem nova (D05 antes da D02)', ordemBanco());
    chk(await espera(async () => /Ordem salva/.test(await toastTxt(pg))) && !!(await pg.$('#toast .toast-acao')), '"Ordem salva" com Desfazer', await toastTxt(pg));
    chk(await ordemTela(pg) === '01,05,02,03,04,06', 'a grade mostra a ordem nova', await ordemTela(pg));
    chk(!(await pg.evaluate(() => mainEl.classList.contains('with-drawer'))), 'soltar o cartão NÃO abre a revisão');
    chk(+um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND codigo LIKE ?", P, `${P}-1975-S03-D0000%`) === N && um("SELECT sequencial FROM item WHERE codigo=?", D(5)) === '5', 'nenhum código mudou (só a posição)');
    chk(!!(await pg.$('#pd [data-ordem-limpar]')), 'com ordem gravada aparece "Voltar à ordem do código"');
    await foto(pg, 'ordem-1366-claro-salva.png');

    // ---------- 3) recarregar: a ordem fica e o projeto abre nela ----------
    await pg.evaluate(c => { try { localStorage.removeItem('camp.ordem_folhas.' + c); localStorage.setItem('camp.ordem_folhas', 'codigo') } catch (_) {} }, P);
    await pg.reload(); await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await abrirProjeto(pg);
    chk(await ordemTela(pg) === '01,05,02,03,04,06', 'depois de recarregar, a grade continua na ordem nova', await ordemTela(pg));
    chk(await pg.evaluate(() => document.querySelector('#pd .folhas-bar [data-fl-ordem]').value) === 'manual', 'projeto com ordem gravada abre em "definida à mão" (mesmo com o navegador lembrando "código")');

    // ---------- 4) Desfazer ----------
    await arrastar(pg, D(6), D(1));
    chk(await espera(() => ordemBanco() === '06,01,05,02,03,04'), 'segundo arraste grava (D06 primeiro)', ordemBanco());
    await pg.waitForSelector('#toast .toast-acao'); await pg.click('#toast .toast-acao');
    chk(await espera(() => ordemBanco() === '01,05,02,03,04,06'), 'Desfazer volta o banco à ordem de antes', ordemBanco());
    chk(await espera(async () => await ordemTela(pg) === '01,05,02,03,04,06'), 'Desfazer volta a grade', await ordemTela(pg));

    // ---------- 5) teclado e menu ⋯ ----------
    await pg.focus(`#pd .thumb[data-rev-abrir="${D(3)}"] [data-ordem-alca]`); await pg.keyboard.press('ArrowLeft');
    chk(await espera(() => ordemBanco() === '01,05,03,02,04,06'), 'seta ← na alça: a D03 vai para antes da D02 (gravado)', ordemBanco());
    chk(await pg.evaluate(c => (document.activeElement || {}).dataset?.ordemAlca === c, D(3)), 'o foco continua na alça da folha movida');
    await pg.keyboard.press('ArrowLeft'); await pg.waitForTimeout(80); await pg.keyboard.press('ArrowLeft');
    chk(await espera(() => ordemBanco() === '03,01,05,02,04,06'), 'duas setas seguidas (a 2ª durante a gravação da 1ª) chegam as duas ao banco', ordemBanco());
    await pg.keyboard.press('ArrowLeft');
    chk(await espera(async () => /primeira folha da série/.test(await toastTxt(pg))) && ordemBanco() === '03,01,05,02,04,06', 'na primeira posição, avisa e não muda nada', await toastTxt(pg));
    await pg.click(`#pd .thumb[data-rev-abrir="${D(3)}"] .lista-mais summary`);
    await pg.click(`#pd .thumb[data-rev-abrir="${D(3)}"] [data-ordem-mover="1"]`);
    chk(await espera(() => ordemBanco() === '01,03,05,02,04,06'), '⋯ "Mover para depois" troca com a vizinha (gravado)', ordemBanco());
    chk(!(await pg.evaluate(() => mainEl.classList.contains('with-drawer'))), 'o menu não abre a revisão');

    // ---------- 6) Revisar folha segue a ordem nova ----------
    await pg.click(`#pd .thumb[data-rev-abrir="${D(1)}"] .img-real`);
    chk(await espera(() => pg.evaluate(c => (document.getElementById('d-sub') || {}).textContent === c && !!document.querySelector('#d-body .rv-rodape'), D(1))), 'clicar abre a revisão da D01');
    const nav1 = await pg.evaluate(() => ({ pos: (document.querySelector('#d-body .rv-nav .rev-prog b') || {}).textContent || '', prox: [...document.querySelectorAll('#d-body .rv-nav [data-rev-ir]')].map(b => b.dataset.revIr.slice(-2)) }));
    chk(nav1.pos === '1 de 6' && nav1.prox[1] === '03', 'Revisar folha: "1 de 6" e Próxima › = D03 (a ordem nova, não a do código)', JSON.stringify(nav1));
    await pg.click('#d-body .rv-nav [data-rev-ir]:not([disabled]) >> text=Próxima');
    chk(await espera(() => pg.evaluate(c => (document.getElementById('d-sub') || {}).textContent === c, D(3))), '"Próxima ›" abre a D03');
    const nav2 = await pg.evaluate(() => ({ pos: (document.querySelector('#d-body .rv-nav .rev-prog b') || {}).textContent || '', ir: [...document.querySelectorAll('#d-body .rv-nav [data-rev-ir]')].map(b => b.dataset.revIr.slice(-2)) }));
    chk(nav2.pos === '2 de 6' && nav2.ir[0] === '01' && nav2.ir[1] === '05', 'na D03: "2 de 6", ‹ Anterior = D01, Próxima › = D05', JSON.stringify(nav2));
    await pg.click('#d-body [data-rev-fechar]'); await pg.waitForTimeout(300);

    // ---------- 7) filtro: não arrasta, dica ----------
    await pg.click('#pd .folhas-bar [data-fl-f="conferir"]'); await pg.waitForTimeout(200);
    const f1 = await pg.evaluate(() => ({ ordenavel: document.querySelector('#pd .pj-folhas').classList.contains('ordenavel'), dica: (document.querySelector('#pd .fb-ordem-filtro') || {}).offsetParent ? document.querySelector('#pd .fb-ordem-filtro').textContent : '' }));
    chk(!f1.ordenavel && /mostre Todas/.test(f1.dica), 'com filtro a grade não arrasta e a dica pede "Todas"', JSON.stringify(f1));
    await pg.click('#pd .folhas-bar [data-fl-f=""]'); await pg.waitForTimeout(200);
    chk(await pg.evaluate(() => document.querySelector('#pd .pj-folhas').classList.contains('ordenavel')), 'em "Todas" volta a arrastar');

    // ---------- 8) erro do servidor ----------
    await pg.route('**/ordem-folhas', r => r.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ erro: 'Esta folha não é deste projeto: teste' }) }));
    await pg.focus(`#pd .thumb[data-rev-abrir="${D(5)}"] [data-ordem-alca]`); await pg.keyboard.press('ArrowRight');
    chk(await espera(async () => /A ordem não foi salva: .*não é deste projeto.*voltaram/.test(await toastTxt(pg))), 'erro do servidor: o motivo aparece', await toastTxt(pg));
    chk(await espera(async () => await ordemTela(pg) === '01,03,05,02,04,06') && ordemBanco() === '01,03,05,02,04,06', 'erro do servidor: a grade volta para onde estava (igual ao banco)', await ordemTela(pg));
    await pg.unroute('**/ordem-folhas');

    // ---------- 9) Voltar à ordem do código ----------
    await pg.click('#pd [data-ordem-limpar]');
    chk(await espera(() => pg.evaluate(() => /Voltar à ordem do código\?/.test((document.getElementById('conf-ov') || {}).innerText || ''))), '"Voltar à ordem do código" pergunta antes');
    await pg.click('#conf-ov [data-conf="sim"]');
    chk(await espera(() => nComOrdem() === 0), 'confirmar limpa a ordem no banco (todas sem posição)');
    chk(await espera(async () => await ordemTela(pg) === '01,02,03,04,05,06') && await pg.evaluate(() => document.querySelector('#pd .folhas-bar [data-fl-ordem]').value) === 'codigo', 'a grade volta à ordem do código e o select também', await ordemTela(pg));
    chk(+um("SELECT COUNT(*) FROM evento WHERE codigo=? AND tipo='ordem_folhas_limpa'", P) === 1 && +um("SELECT COUNT(*) FROM evento WHERE codigo=? AND tipo='ordem_folhas'", P) >= 3, 'Histórico do projeto: as mudanças de ordem e a volta ao código ficam registradas');
    await ctx.close();

    // ---------- 10) permissões ----------
    const L = await entrar(br, 'leitor@camp.arq.br', 'senha-leitor-1234', {}, erros);
    await abrirProjeto(L.pg); await L.pg.selectOption('#pd .folhas-bar [data-fl-ordem]', 'manual'); await L.pg.waitForTimeout(300);
    const le = await L.pg.evaluate(() => ({ alca: document.querySelectorAll('#pd .cap-alca').length, mover: document.querySelectorAll('#pd [data-ordem-mover]').length, ordenavel: document.querySelector('#pd .pj-folhas').classList.contains('ordenavel'), limpar: !!document.querySelector('#pd [data-ordem-limpar]') }));
    chk(!le.alca && !le.mover && !le.ordenavel && !le.limpar, 'leitura: sem alça, sem "Mover para…", sem "Voltar à ordem do código"', JSON.stringify(le));
    await L.ctx.close();

    const O = await entrar(br, 'operador@camp.arq.br', 'senha-operador-123', { vp: { width: 390, height: 844 }, escuro: true, toque: true }, erros);
    await abrirProjeto(O.pg); await O.pg.selectOption('#pd .folhas-bar [data-fl-ordem]', 'manual'); await O.pg.waitForTimeout(300);
    const lat = await O.pg.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
    chk(lat, '390 px: sem rolagem lateral');
    chk(await O.pg.evaluate(() => [...document.querySelectorAll('#pd .cap-alca')].filter(x => x.offsetParent).length) === N, 'operador (390 px): alça em todas as folhas');
    // toque: pointerType "touch" na alça (o resto do cartão rola a página)
    await O.pg.evaluate(c => document.querySelector(`#pd .thumb[data-rev-abrir="${c}"]`).scrollIntoView({ block: 'center' }), D(4)); await O.pg.waitForTimeout(150);
    const t0 = await O.pg.evaluate(([de, para]) => { const a = document.querySelector(`#pd .thumb[data-rev-abrir="${de}"] .cap-alca`).getBoundingClientRect(), b = document.querySelector(`#pd .thumb[data-rev-abrir="${para}"] .img-real`).getBoundingClientRect();
      return { ax: a.left + a.width / 2, ay: a.top + a.height / 2, bx: b.left + b.width * 0.5, by: b.top + b.height * 0.2 }; }, [D(4), D(3)]);
    const toque = (tipo, x, y) => O.pg.evaluate(([tipo, x, y, c]) => { const alvo = tipo === 'pointerdown' ? document.querySelector(`#pd .thumb[data-rev-abrir="${c}"] .cap-alca`) : document.elementFromPoint(x, y) || document.body;
      alvo.dispatchEvent(new PointerEvent(tipo, { bubbles: true, cancelable: true, pointerId: 7, pointerType: 'touch', isPrimary: true, clientX: x, clientY: y })); }, [tipo, x, y, D(4)]);
    await toque('pointerdown', t0.ax, t0.ay);
    for (let k = 1; k <= 10; k++) await toque('pointermove', t0.ax + (t0.bx - t0.ax) * k / 10, t0.ay + (t0.by - t0.ay) * k / 10);
    const dt = await O.pg.evaluate(() => ({ fant: !!document.querySelector('#pd .thumb-fantasma'), alvo: (document.querySelector('#pd .thumb.solta-antes,#pd .thumb.solta-depois') || {}).dataset?.revAbrir || '' }));
    chk(dt.fant && dt.alvo === D(3), 'toque na alça (390 px, escuro): o fantasma segue o dedo e a linha marca a D03', JSON.stringify(dt));
    await foto(O.pg, 'ordem-390-escuro-arrastando.png');
    await toque('pointerup', t0.bx, t0.by);
    chk(await espera(() => ordemBanco() === '01,02,04,03,05,06'), 'toque: soltar grava (D04 antes da D03)', ordemBanco());
    chk(await espera(async () => /Ordem salva/.test(await O.pg.evaluate(() => (document.getElementById('toast') || {}).textContent || ''))), 'toque: "Ordem salva"');
    await foto(O.pg, 'ordem-390-escuro-salva.png');
    await O.ctx.close();
    chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  } catch (e) {
    chk(false, 'o teste rodou até o fim', e.stack || String(e));
  } finally {
    await br.close();
    console.log(linhas.join('\n'));
    console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
    process.exit(problemas.length ? 1 : 0);
  }
})();
