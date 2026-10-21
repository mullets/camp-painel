// CAMP-136 (21/10, Rafa: "preciso mudar o tipo de material, tem coisa como planta e é fotografia"), no navegador de verdade:
//  - "Mais ⋯" do projeto tem "Mudar o tipo de material": marca as folhas, escolhe a série (Fotografias vem escolhida), confirma;
//    as folhas ganham o código da série nova (mesmo D) e a página mostra o resultado;
//  - na revisão da folha, "Mudar o tipo de material…" abre o mesmo formulário com a folha já marcada;
//  - folha publicada no site aparece desabilitada, com o motivo; nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx):
//   CAMP_DB_PATH=/tmp/se.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/se.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8962)
//   CAMP_DB_PATH=/tmp/se.db CAMP_BASE=http://127.0.0.1:8962 node tests/navegador_serie.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8962', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0095', D = (s, n) => `${P}-1990-${s}-D0000${n}`;
py(`
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026',95)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F026',95,'Casa com fotos',1990,'São Paulo')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
for s in range(1,5):
    st, tid = ('no_ar', 4444) if s == 4 else ('nao_publicado', None)
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,origem,status_site,tainacan_item_id,titulo,tipo_documento,revisao) VALUES (?,?,?,?,?,?,?,?,?,?)",
      ("${P}-1990-S01-D%05d" % s,'${P}',"S01",s,'campvision',st,tid,"Foto %d" % s,'Planta','conferida'))
`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await new Promise(r => setTimeout(r, 150)); } return false; };
const um = q => py(`print((con.execute("""${q}""").fetchone() or [''])[0])`);
let PG = null;
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const pg = await br.newPage({ viewport: { width: 1400, height: 900 } }); PG = pg;
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#projeto/' + P); await pg.reload(); await pg.waitForSelector(`[data-pj-mais="${P}"]`, { timeout: 15000, state: "attached" }); await pg.waitForTimeout(1000);

  // 1) pelo "Mais ⋯" do projeto
  await pg.evaluate(p => document.querySelector(`[data-pj-mais="${p}"]`).click(), P);
  await pg.waitForSelector('#d-body [data-mais="serie"]', { timeout: 5000 });
  await pg.click('#d-body [data-mais="serie"]');
  await pg.waitForSelector('#d-body #mx-serie', { timeout: 5000 });
  chk(await pg.$eval('#mx-serie', s => s.value) === 'S03' && /Fotografias/.test(await pg.textContent('#mx-serie')), '"Mudar o tipo de material" abre com Fotografias já escolhida');
  chk(await pg.$eval(`#d-body .mx-it[value="${D('S01', 4)}"]`, x => x.disabled) && /despublique/.test(await pg.textContent('#d-body .mx-folhas')), 'a folha publicada no site aparece desabilitada, com o motivo');
  await pg.check(`#d-body .mx-it[value="${D('S01', 1)}"]`); await pg.check(`#d-body .mx-it[value="${D('S01', 2)}"]`);
  await pg.fill('#mx-tipo', 'Fotografia'); await pg.check('#mx-ok'); await pg.click('#mx-go');
  chk(await espera(() => um(`SELECT COUNT(*) FROM item WHERE projeto_codigo='${P}' AND serie_codigo='S03'`) === '2'), 'as 2 folhas marcadas viram S03 Fotografias');
  chk(um(`SELECT tipo_documento FROM item WHERE codigo='${D('S03', 1)}'`) === 'Fotografia' && um(`SELECT codigo_anterior FROM item WHERE codigo='${D('S03', 1)}'`) === D('S01', 1), 'mesmo D, o código antigo fica guardado e o tipo da folha muda');
  await pg.waitForTimeout(1500);
  chk(/S03/.test(await pg.textContent('#pd')) || (await pg.$$(`[data-rev-abrir="${D('S03', 1)}"]`)).length > 0, 'a página do projeto já mostra a folha com o código novo', '');

  // 2) pela revisão da folha
  await pg.evaluate(c => abrirRevisaoItem(c), D('S01', 3)); await pg.waitForSelector('[data-serie-abrir]', { timeout: 8000 }).catch(() => {});
  const at = await pg.$(`[data-serie-abrir="${D('S01', 3)}"]`);
  chk(!!at, 'a revisão da folha tem "Mudar o tipo de material…"');
  if (at) {
    await at.click(); await pg.waitForSelector('#d-body #mx-serie', { timeout: 5000 });
    chk(await pg.$eval(`#d-body .mx-it[value="${D('S01', 3)}"]`, x => x.checked), 'abre o formulário com a folha já marcada');
    await pg.selectOption('#mx-serie', 'S05'); await pg.check('#mx-ok'); await pg.click('#mx-go');
    chk(await espera(() => um(`SELECT serie_codigo FROM item WHERE codigo='${D('S05', 3)}'`) === 'S05'), 'e muda a série escolhida (S05 Slides)');
  }
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(async e => { console.log(linhas.join('\n')); console.error('ERRO', e.message.split('\n')[0]); process.exit(1); });
