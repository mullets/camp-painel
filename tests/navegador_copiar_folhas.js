// Copiar folhas para outro projeto, com o projeto novo criado na hora, e a seleção de folhas com miniaturas (15/11/2026, Rafael:
// "Preciso criar uma opção de copiar para outro lote, e ter a opção de criar esse lote, seja no mesmo arquiteto ou em outro. Seria bom ter a
// opção selecionar todos, e thumbs, isso vale para tudo lá"), no navegador de verdade (Playwright + Chromium), com o banco real do servidor:
//  1) Mais ações → "Copiar folhas para outro projeto": cada folha com miniatura (imagem carregada), código e título; "N de M folhas marcadas";
//  2) "Selecionar todos" / "Limpar" e Shift+clique (intervalo);
//  3) "Novo projeto…" em OUTRO fundo (lista de fundos): confirma, cria o projeto com o próximo P do fundo e copia; a mensagem diz onde;
//     o banco tem as cópias no projeto novo e a original intacta;
//  4) o mesmo componente em "Mover folhas" (miniaturas; "Novo projeto…" sem escolher fundo: mover é só no mesmo fundo);
//  5) print 1366 claro do seletor; nenhum erro de JavaScript.
// Uso: bash tests/rodar_um.sh tests/navegador_copiar_folhas.js   (ou com CAMP_DB_PATH/CAMP_BASE de um servidor próprio)
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765', DB = process.env.CAMP_DB_PATH, PRINTS = process.env.PRINTS || '';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
if (PRINTS) fs.mkdirSync(PRINTS, { recursive: true });
const PRONTOS = path.join(path.dirname(DB), 'prontos_copiar'); fs.mkdirSync(PRONTOS, { recursive: true });
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PRONTOS], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0173', D = n => `${P}-1976-S03-D${String(n).padStart(5, '0')}`, N = 5;
function semear() {
  py(`
from pathlib import Path
from PIL import Image
raiz = Path(sys.argv[2])
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 173)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,uf) VALUES ('${P}','F026',173,'Casa das Fotos a Copiar',1976,'Santos','SP')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}' OR projeto_codigo IN (SELECT codigo FROM projeto WHERE titulo='Casa Copiada no Outro Fundo')")
con.execute("DELETE FROM projeto WHERE titulo='Casa Copiada no Outro Fundo'")   # (rodar de novo: o número gasto continua em numero_p, nunca volta)
con.execute("DELETE FROM lista_processamento WHERE projeto_codigo='${P}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote fotos','${P}','/x/copiar','revisao')").lastrowid
CORES = [(200,80,60),(60,140,90),(60,90,170),(190,160,40),(130,70,150)]
for s in range(1, ${N} + 1):
    cod = "${P}-1976-S03-D%05d" % s
    rel = "_campvision/preview/${P}/%s.jpg" % cod
    (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (900, 600), CORES[s-1]).save(raiz / rel, "JPEG", quality=70)
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,origem,lote_id,status_site,pendencias,revisao) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P}', 'S03', s, "Foto %d" % s, 'Fotografia', 'campvision', lid, 'nao_publicado', json.dumps({"previa": rel}), 'pendente'))
`);
}
const um = (sql, ...a) => py(`r=con.execute(${JSON.stringify(sql)}, ${JSON.stringify(a)}).fetchone()\nprint('' if r is None else (r[0] if r[0] is not None else ''))`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await f()) return true; } catch (_) {} await new Promise(r => setTimeout(r, 150)); } return false; };
const contagem = pg => pg.evaluate(() => (document.querySelector('#d-body .sf-n') || {}).textContent || '');
const marcadas = pg => pg.$$eval('#d-body .sf-grade input:checked', x => x.length);

async function entrar(br, email, senha, erros) {
  const ctx = await br.newContext({ viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1, colorScheme: 'light' });
  const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push(`pageerror: ${e.message}`));
  pg.on('console', m => { if (m.type() === 'error' && !/400|401|403|404|409|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ERR_FAILED|Failed to load resource|Failed to fetch/.test(m.text())) erros.push(`console.error: ${m.text()}`); });
  await pg.addInitScript(() => { try { localStorage.setItem('camp.dicaRev', '9'); localStorage.setItem('camp.folhasVista', 'grade') } catch (_) {} });
  await pg.goto(BASE + '/');
  await pg.fill('#lg-email', email); await pg.fill('#lg-senha', senha); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, pg };
}
async function abrirAcao(pg, acao) {
  await pg.evaluate(c => { closeDrawer(true); nav('projeto/' + c); showProjeto(c, 'folhas'); }, P);
  await pg.waitForSelector('#pd .pj-folhas .thumb', { timeout: 15000, state: 'attached' });
  await pg.waitForTimeout(600);
  await pg.evaluate(() => document.querySelector('[data-pj-mais]').click());
  await pg.waitForSelector(`#d-body [data-mais="${acao}"]`, { timeout: 5000 });
  await pg.click(`#d-body [data-mais="${acao}"]`);
  await pg.waitForSelector('#d-body .sf-it', { timeout: 5000 });
}

(async () => {
  semear();
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const { pg } = await entrar(br, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    await abrirAcao(pg, 'copiar');
    // 1) miniaturas, código e título
    chk(await pg.$$eval('#d-body .sf-it', x => x.length) === N, `lista as ${N} folhas, cada uma num cartão`);
    chk(await espera(() => pg.$$eval('#d-body .sf-it .sf-mini img', x => x.length === 5 && x.every(i => i.complete && i.naturalWidth > 0))), 'cada folha mostra a miniatura (imagem carregada)');
    chk(/D00001/.test(await pg.textContent('#d-body .sf-it')) && /Foto 1/.test(await pg.textContent('#d-body .sf-it')), 'cartão com o código (D) e o título');
    chk(/^0 de 5 folhas marcadas$/.test(await contagem(pg)), 'contagem começa em "0 de 5 folhas marcadas"', await contagem(pg));
    // 2) Selecionar todos / Limpar / Shift
    await pg.click('#d-body [data-sf-todas]');
    chk(await marcadas(pg) === 5 && /^5 de 5/.test(await contagem(pg)), '"Selecionar todos" marca as 5 e a contagem acompanha', await contagem(pg));
    await pg.click('#d-body [data-sf-limpar]');
    chk(await marcadas(pg) === 0 && /^0 de 5/.test(await contagem(pg)), '"Limpar" desmarca todas');
    const cx = await pg.$$('#d-body .sf-grade input');
    await cx[0].click(); await cx[3].click({ modifiers: ['Shift'] });
    chk(await marcadas(pg) === 4 && /^4 de 5/.test(await contagem(pg)), 'Shift+clique marca o intervalo (1 a 4)', await contagem(pg));
    await pg.click('#d-body [data-sf-todas]');
    // 3) Novo projeto em outro fundo
    chk(!!(await pg.$('#d-body #dn-box')) && !!(await pg.$('#d-body #dn-fundo')), '"Novo projeto…" com a escolha do fundo (copiar pode ir a outro arquiteto)');
    await pg.click('#d-body #dn-box summary');
    chk(await espera(() => pg.$$eval('#dn-fundos option', o => o.some(x => x.value === 'F023'))), 'a lista de fundos tem os outros arquitetos');
    await pg.fill('#dn-fundo', 'F023'); await pg.fill('#dn-titulo', 'Casa Copiada no Outro Fundo'); await pg.fill('#dn-ano', '1976');
    if (PRINTS) { await pg.evaluate(() => document.querySelector('#d-body .mx-folhas').scrollIntoView({ block: 'start' })); await pg.screenshot({ path: path.join(PRINTS, 'copiar-1366.png') }); }
    const proxP = +um("SELECT COALESCE(MAX(numero),0)+1 FROM numero_p WHERE fundo_codigo='F023'");
    const esperado = 'F023-P' + String(proxP).padStart(4, '0');
    await pg.check('#mx-ok'); await pg.click('#mx-go');
    await pg.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 8000 });
    const txt = await pg.textContent('#conf-ov');
    chk(new RegExp(esperado).test(txt) && /5 folhas/.test(txt) && /não mudam/.test(txt), 'a confirmação diz o projeto novo (próximo P do fundo), quantas folhas e que as daqui não mudam', txt.slice(0, 300));
    await pg.click('#conf-ov [data-conf="sim"]');
    chk(await espera(async () => new RegExp(`5 folhas copiadas para ${esperado}`).test(await pg.evaluate(() => (document.getElementById('toast') || {}).textContent || ''))), `mensagem: "5 folhas copiadas para ${esperado} (projeto novo)"`,
      await pg.evaluate(() => (document.getElementById('toast') || {}).textContent || ''));
    chk(um("SELECT fundo_codigo FROM projeto WHERE codigo=?", esperado) === 'F023' && +um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND copiada_de LIKE ?", esperado, P + '-%') === 5,
      'o banco tem o projeto novo no outro fundo com as 5 cópias');
    chk(+um("SELECT COUNT(*) FROM item WHERE projeto_codigo=?", P) === 5 && +um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND revisao='pendente' AND status_site='nao_publicado'", P) === 5,
      'as 5 originais continuam no projeto, como estavam');
    chk(+um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND codigo LIKE ?", esperado, esperado + '-1976-S03-D9%') === 5, 'as cópias têm o código do destino (faixa do painel, D90001+)');
    // 4) o mesmo componente no Mover
    await abrirAcao(pg, 'mover');
    chk(await pg.$$eval('#d-body .sf-it .sf-mini img', x => x.length) === 5 && !!(await pg.$('#d-body [data-sf-todas]')), 'Mover folhas: as mesmas miniaturas e "Selecionar todos"');
    chk(!!(await pg.$('#d-body #dn-box')) && !(await pg.$('#d-body #dn-fundo')), 'Mover folhas: "Novo projeto…" sem escolher fundo (só no mesmo fundo)');
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
