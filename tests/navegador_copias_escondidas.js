// Página do projeto mostra só a folha que fica; as cópias ficam recolhidas (10/11/2026, Rafael: "no acervo do Arnaldo tem fotos repetidas
// 2–3 vezes: JPG, DNG e TIF. Deixe só uma."). No navegador de verdade (Playwright + Chromium), com o banco do servidor de teste:
//  1) projeto com a D01 (TIFF, a que fica), a D02 (DNG) e a D03 (JPG) marcadas como cópias da D01, e a D04 sozinha: a grade mostra 2 cartões;
//  2) o cartão da D01 diz "+2 cópias (DNG, JPG)" e abre as duplicatas lado a lado;
//  3) cabeçalho "2 folhas", aba "Folhas (2)", "Conferidas 0 de 2", barra da conferência "0 de 2": as cópias não contam;
//  4) filtro "Cópias (2)": só a D02 e a D03, cada uma com "cópia de D00001"; na lista, o mesmo;
//  5) "Revisar folha": "1 de 2" e Próxima › pula as cópias (D01 → D04);
//  6) ordem definida à mão: a cópia não tem alça; arrastar a D04 para antes da D01 grava D04, D01 (as cópias depois);
//  7) nada muda no banco além da ordem (duplicata_de igual); sem erro de JavaScript.
// Uso (servidor PRÓPRIO):
//   CAMP_DB_PATH=/tmp/x/t.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x/t.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8989)
//   CAMP_DB_PATH=/tmp/x/t.db CAMP_BASE=http://127.0.0.1:8989 CHROME=/opt/pw-browsers/chromium [PRINTS=/pasta] node tests/navegador_copias_escondidas.js
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8989', DB = process.env.CAMP_DB_PATH, PRINTS = process.env.PRINTS || '';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
if (PRINTS) fs.mkdirSync(PRINTS, { recursive: true });
const PRONTOS = path.join(path.dirname(DB), 'prontos_copias'); fs.mkdirSync(PRONTOS, { recursive: true });
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PRONTOS], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0173', D = n => `${P}-1975-S01-D${String(n).padStart(5, '0')}`;
function semear() {
  py(`
from pathlib import Path
from PIL import Image, ImageDraw
raiz = Path(sys.argv[2])
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 173)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,uf) VALUES ('${P}','F026',173,'Casa das Cópias',1975,'Santos','SP')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
con.execute("DELETE FROM lista_processamento WHERE projeto_codigo='${P}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote copias','${P}','/x/copias','revisao')").lastrowid
# (sequencial, folha, arquivo de origem, cópia de)
F = [(1, '1', 'P0173/TIFF/planta 1.tif', None), (2, '1', 'P0173/DNG/planta 1.dng', 1), (3, '1', 'P0173/JPG/planta 1.jpg', 1), (4, '2', 'P0173/TIFF/corte.tif', None)]
CORES = {1: (60, 90, 170), 2: (60, 90, 170), 3: (60, 90, 170), 4: (200, 80, 60)}
for s, folha, orig, dup in F:
    cod = "${P}-1975-S01-D%05d" % s
    rel = "_campvision/preview/${P}/%s.jpg" % cod
    (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (1200, 900), CORES[s]); dr = ImageDraw.Draw(im); dr.rectangle((40, 40, 1160, 860), outline="white", width=10); dr.text((540, 430), "PRANCHA %s" % folha, fill="white")
    im.save(raiz / rel, "JPEG", quality=70)
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,folha,origem,lote_id,status_site,pendencias,revisao,arquivo_origem,duplicata_de,tipo_duplicata) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P}', 'S01', s, "Planta %s" % folha, 'Planta', folha, 'campvision', lid, 'nao_publicado', json.dumps({"previa": rel}), 'pendente', orig,
       ("${P}-1975-S01-D%05d" % dup) if dup else None, 'mesma_folha' if dup else None))
`);
}
const ordemBanco = () => py(`print(','.join(r[0][-2:] for r in con.execute("SELECT codigo FROM item WHERE projeto_codigo='${P}' ORDER BY (ordem_manual IS NULL), ordem_manual, sequencial")))`);
const dups = () => py(`print(','.join((r[0] or '-')[-2:] for r in con.execute("SELECT duplicata_de FROM item WHERE projeto_codigo='${P}' ORDER BY sequencial")))`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await f()) return true; } catch (_) {} await new Promise(r => setTimeout(r, 150)); } return false; };
const visiveis = pg => pg.evaluate(() => [...document.querySelectorAll('#pd .pj-folhas .thumb')].filter(t => t.offsetParent).map(t => (t.dataset.revAbrir || '').slice(-2)).join(','));
const foto = async (pg, nome) => { if (PRINTS) await pg.screenshot({ path: path.join(PRINTS, nome) }); };

async function entrar(br, erros, vista) {
  const ctx = await br.newContext({ viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1, colorScheme: 'light' });
  const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push(`pageerror: ${e.message}`));
  pg.on('console', m => { if (m.type() === 'error' && !/400|401|403|404|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ERR_FAILED|Failed to load resource|Failed to fetch/.test(m.text())) erros.push(`console.error: ${m.text()}`); });
  await pg.addInitScript(v => { try { localStorage.setItem('camp.dicaRev', '9'); localStorage.setItem('camp.revCheia', '0'); localStorage.setItem('camp.folhasVista', v);
    Object.keys(localStorage).filter(k => k.startsWith('camp.ordem_folhas')).forEach(k => localStorage.removeItem(k)) } catch (_) {} }, vista || 'grade');
  await pg.goto(BASE + '/');
  await pg.fill('#lg-email', 'rafael@camp.arq.br'); await pg.fill('#lg-senha', 'senha-bem-longa-123'); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, pg };
}
async function abrirProjeto(pg, aba) {
  await pg.evaluate(([c, a]) => { closeDrawer(true); nav('projeto/' + c); showProjeto(c, a); }, [P, aba || 'folhas']);
  await pg.waitForSelector('#pd .pj-folhas .thumb', { timeout: 15000, state: 'attached' });
  await pg.waitForTimeout(900);
  for (const a of await pg.$$('[data-ajuda-fechar]')) { try { if (await a.isVisible()) await a.click(); } catch (_) {} }
}

(async () => {
  semear();
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const { ctx, pg } = await entrar(br, erros);
    await abrirProjeto(pg);

    // ---------- 1) a grade mostra só a folha que fica ----------
    chk(await visiveis(pg) === '01,04', 'a grade mostra 2 cartões: a D01 (TIFF) e a D04; as cópias D02/D03 ficam recolhidas', await visiveis(pg));
    chk(await pg.evaluate(() => document.querySelectorAll('#pd .pj-folhas .thumb[data-copia-de]').length) === 2, 'as cópias continuam na página (escondidas), prontas para o filtro');

    // ---------- 2) "+2 cópias (DNG, JPG)" ----------
    const tag = await pg.evaluate(c => { const b = document.querySelector(`#pd .thumb[data-rev-abrir="${c}"] .pj-copias`); return b ? { t: b.textContent.trim(), abre: b.dataset.dupvAbrir, title: b.title, ambar: b.classList.contains('a') } : null; }, D(1));
    chk(tag && tag.t === '+2 cópias (DNG, JPG)', 'o cartão da D01 diz "+2 cópias (DNG, JPG)"', JSON.stringify(tag));
    chk(tag && tag.abre === P && /duplicatas lado a lado/.test(tag.title) && tag.ambar, 'a marca abre as duplicatas lado a lado e fica âmbar (cópias ainda a conferir)', JSON.stringify(tag));
    chk(!(await pg.$(`#pd .thumb[data-rev-abrir="${D(4)}"] .pj-copias`)), 'a D04 (sem cópias) não tem a marca');

    // ---------- 3) as contas não contam as cópias ----------
    const ct = await pg.evaluate(() => ({ cab: (document.querySelector('#pd .dethdr .meta, #pd .dethdr') || {}).textContent || '', aba: [...document.querySelectorAll('#pd [role="tab"], #pd .pj-tabs button, #pd [data-pj-tab]')].map(b => b.textContent.trim()).find(t => /^Folhas/.test(t)) || '',
      cont: (document.querySelector('#pd .folhas-bar .fb-cont') || {}).textContent || '', todas: (document.querySelector('#pd .folhas-bar [data-fl-f=""]') || {}).textContent || '',
      conf: (document.querySelector('#pd .folhas-bar [data-fl-f="conferir"]') || {}).textContent || '', copias: (document.querySelector('#pd .folhas-bar [data-fl-f="copias"]') || {}).textContent || '',
      serie: (document.querySelector('#pd .project-series .project-series-head span') || {}).textContent || '' }));
    chk(/\b2 folhas\b/.test(ct.cab) && !/\b4 folhas\b/.test(ct.cab), 'cabeçalho: "2 folhas" (as cópias não contam)', ct.cab.slice(0, 300));
    chk(ct.aba === 'Folhas (2)', 'aba "Folhas (2)"', ct.aba);
    chk(/Conferidas 0 de 2/.test(ct.cont) && ct.todas === 'Todas (2)' && ct.conf === 'A conferir (2)' && ct.serie === '2', '"Conferidas 0 de 2", "Todas (2)", "A conferir (2)" e a série com 2', JSON.stringify(ct));
    chk(ct.copias === 'Cópias (2)', 'há o filtro "Cópias (2)"', ct.copias);
    await abrirProjeto(pg, 'itens'); await pg.waitForTimeout(600);
    const prog = await pg.evaluate(() => (document.querySelector('#pd .pj-conf-prog') || {}).textContent || '');
    chk(/0 de 2 folhas conferidas/.test(prog), 'barra da conferência (Visão geral): "0 de 2 folhas conferidas"', prog);
    await abrirProjeto(pg);

    // ---------- 4) filtro "Cópias" ----------
    await pg.click('#pd .folhas-bar [data-fl-f="copias"]'); await pg.waitForTimeout(200);
    chk(await visiveis(pg) === '02,03', '"Cópias": só a D02 e a D03', await visiveis(pg));
    const de = await pg.evaluate(() => [...document.querySelectorAll('#pd .pj-folhas .thumb')].filter(t => t.offsetParent).map(t => (t.querySelector('.pj-copia-de') || {}).textContent || ''));
    chk(de.length === 2 && de.every(t => t === 'cópia de D00001'), 'cada cópia diz "cópia de D00001"', JSON.stringify(de));
    await foto(pg, 'copias-1366-filtro.png');
    await pg.click('#pd .folhas-bar [data-fl-f=""]'); await pg.waitForTimeout(200);
    chk(await visiveis(pg) === '01,04', 'de volta a "Todas": as cópias somem de novo', await visiveis(pg));

    // ---------- 5) Revisar folha pula as cópias ----------
    await pg.click(`#pd .thumb[data-rev-abrir="${D(1)}"] .img-real`);
    chk(await espera(() => pg.evaluate(c => (document.getElementById('d-sub') || {}).textContent === c && !!document.querySelector('#d-body .rv-rodape'), D(1))), 'clicar abre a revisão da D01');
    const n1 = await pg.evaluate(() => ({ pos: (document.querySelector('#d-body .rv-nav .rev-prog b') || {}).textContent || '', ir: [...document.querySelectorAll('#d-body .rv-nav [data-rev-ir]')].map(b => (b.dataset.revIr || '').slice(-2)) }));
    chk(n1.pos === '1 de 2' && n1.ir.includes('04') && !n1.ir.includes('02'), 'Revisar folha: "1 de 2" e Próxima › = D04 (pula as cópias)', JSON.stringify(n1));
    await pg.click('#d-body .rv-nav [data-rev-ir]:not([disabled]) >> text=Próxima');
    chk(await espera(() => pg.evaluate(c => (document.getElementById('d-sub') || {}).textContent === c, D(4))), '"Próxima ›" abre a D04');
    await pg.click('#d-body [data-rev-fechar]'); await pg.waitForTimeout(300);

    // ---------- 6) ordem definida à mão ----------
    await pg.selectOption('#pd .folhas-bar [data-fl-ordem]', 'manual'); await pg.waitForTimeout(300);
    const al = await pg.evaluate(() => ({ copiaOrdem: document.querySelectorAll('#pd .thumb[data-copia-de][data-ordem]').length, alcas: [...document.querySelectorAll('#pd .cap-alca')].filter(x => x.offsetParent).length, ordenavel: document.querySelector('#pd .pj-folhas').classList.contains('ordenavel') }));
    chk(al.copiaOrdem === 0 && al.alcas === 2 && al.ordenavel, 'ordem à mão: as cópias não têm posição; 2 alças à vista', JSON.stringify(al));
    await pg.focus(`#pd .thumb[data-rev-abrir="${D(4)}"] [data-ordem-alca]`); await pg.keyboard.press('ArrowLeft');
    chk(await espera(() => ordemBanco() === '04,01,02,03'), 'mover a D04 para antes da D01 grava D04, D01 (as cópias depois)', ordemBanco());
    chk(await espera(async () => await visiveis(pg) === '04,01'), 'a grade mostra D04, D01 (cópias continuam escondidas)', await visiveis(pg));

    // ---------- lista ----------
    await pg.click('#pd .fb-vista [data-fl-vista="lista"]'); await pg.waitForTimeout(200);
    chk(await visiveis(pg) === '04,01', 'na Lista, também só as 2 folhas que ficam', await visiveis(pg));
    await pg.click('#pd .fb-vista [data-fl-vista="grade"]'); await pg.waitForTimeout(200);
    await pg.evaluate(() => { const m = document.getElementById('main') || document.querySelector('main'); if (m) m.scrollTop = 0; window.scrollTo(0, 0); });
    await pg.evaluate(c => document.querySelector(`#pd .thumb[data-rev-abrir="${c}"]`).scrollIntoView({ block: 'center' }), D(1)); await pg.waitForTimeout(300);
    await foto(pg, 'copias-1366.png');

    // ---------- 2b) a marca abre as duplicatas ----------
    await pg.click(`#pd .thumb[data-rev-abrir="${D(1)}"] .pj-copias`);
    chk(await espera(() => pg.evaluate(() => location.hash.startsWith('#duplicatas/'))), '"+2 cópias" abre "Duplicatas" do projeto (e não a revisão)', await pg.evaluate(() => location.hash));
    chk(!(await pg.evaluate(() => mainEl.classList.contains('with-drawer'))), 'clicar na marca não abre a revisão por baixo');

    chk(dups() === '-,01,01,-', 'nada mudou nas marcas de cópia do banco', dups());
    await ctx.close();
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
