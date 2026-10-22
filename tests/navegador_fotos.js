// 21/10 (Rafa: "fotos precisa por ano da foto, estagio, fotografo"), no navegador de verdade:
//  - em Fotografias, "Ano, estágio e fotógrafo…" marca as fotos e preenche os três de uma vez;
//  - a página do projeto mostra as fotos em blocos (ano · estágio · fotógrafo), do ano mais antigo ao mais novo; as sem dados no fim;
//  - na revisão de uma foto, os três campos aparecem e salvam; folha de desenho não tem esses campos; nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx):
//   CAMP_DB_PATH=/tmp/fo.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/fo.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8963)
//   CAMP_DB_PATH=/tmp/fo.db CAMP_BASE=http://127.0.0.1:8963 node tests/navegador_fotos.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8963', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0096', D = (s, n) => `${P}-1990-${s}-D0000${n}`;
py(`
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026',96)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F026',96,'Casa das fotos',1990,'São Paulo')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
for s in range(1,6):
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,origem,status_site,titulo,tipo_documento,revisao) VALUES (?,?,?,?,?,?,?,?,?)",
      ("${P}-1990-S03-D%05d" % s,'${P}',"S03",s,'campvision','nao_publicado',"Foto %d" % s,'Fotografia','conferida'))
con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,origem,status_site,titulo,tipo_documento,revisao) VALUES (?,?,?,?,?,?,?,?,?)",
  ("${P}-1990-S01-D00006",'${P}',"S01",6,'campvision','nao_publicado',"Planta",'Planta','conferida'))
con.execute("UPDATE item SET foto_ano='2010', foto_estagio='Em uso', foto_fotografo='Bia' WHERE codigo='${P}-1990-S03-D00005'")
`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await new Promise(r => setTimeout(r, 150)); } return false; };
const um = q => py(`print((con.execute("""${q}""").fetchone() or [''])[0])`);
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const pg = await br.newPage({ viewport: { width: 1400, height: 900 } });
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#projeto/' + P); await pg.reload(); await pg.waitForSelector(`[data-fotos-abrir]`, { timeout: 15000, state: 'attached' }); await pg.waitForTimeout(800);
  chk(!(await pg.$('[data-fotos-serie="S01"]')), 'Desenhos não têm o botão (só Fotografias, Negativos e Slides)');
  chk(await pg.$$eval('[data-fotos-serie="S03"] .foto-bloco', b => b.length) === 2, 'já com uma foto preenchida: 2 blocos (2010 e as sem dados)');

  // 1) em lote
  await pg.click('[data-fotos-serie="S03"] [data-fotos-abrir]'); await pg.waitForSelector('#d-body #fd-ano', { timeout: 5000 });
  chk(await pg.$$eval('#d-body .fd-it:checked', x => x.length) === 4, 'abre com as fotos SEM dados já marcadas (4 de 5)');
  chk(await pg.$$eval('#d-body .fd-it', x => x.length) === 5, 'lista só as fotos (a planta fica de fora)');
  await pg.click('[data-fd-marcar="nenhuma"]'); await pg.check(`#d-body .fd-it[value="${D('S03', 1)}"]`); await pg.check(`#d-body .fd-it[value="${D('S03', 2)}"]`);
  await pg.fill('#fd-ano', 'noventa'); await pg.click('#fd-go');
  chk(/4 dígitos/.test(await pg.textContent('#fd-res')), 'ano sem 4 dígitos: avisa na hora e não envia');
  await pg.fill('#fd-ano', 'c. 1992'); await pg.fill('#fd-estagio', 'Em construção'); await pg.fill('#fd-fotografo', 'Ana Lima'); await pg.click('#fd-go');
  chk(await espera(() => um(`SELECT COUNT(*) FROM item WHERE projeto_codigo='${P}' AND foto_ano='c. 1992' AND foto_estagio='Em construção' AND foto_fotografo='Ana Lima'`) === '2'), 'as 2 marcadas ganham ano, estágio e fotógrafo');
  await pg.waitForFunction(() => document.querySelectorAll('[data-fotos-serie="S03"] .foto-bloco').length === 3, null, { timeout: 8000 }).catch(() => {});
  const blocos = await pg.$$eval('[data-fotos-serie="S03"] .foto-bloco-head', h => h.map(x => x.textContent.trim()));
  chk(blocos.length === 3 && /c\. 1992 · Em construção · Ana Lima\s*· 2 fotos/.test(blocos[0]) && /2010/.test(blocos[1]) && /Sem ano, estágio e fotógrafo/.test(blocos[2]),
      'blocos na ordem: 1992 (2 fotos), 2010, e as sem dados no fim', JSON.stringify(blocos));

  // 2) na revisão da foto
  await pg.evaluate(c => abrirRevisaoItem(c), D('S03', 3)); await pg.waitForSelector('#rv-foto-ano', { timeout: 8000 }).catch(() => {});
  chk(!!(await pg.$('#rv-foto-ano')) && !!(await pg.$('#rv-foto-estagio')) && !!(await pg.$('#rv-foto-fotografo')), 'a revisão da foto tem Ano da foto, Estágio e Fotógrafo');
  if (await pg.$('#rv-foto-ano')) {
    await pg.fill('#rv-foto-ano', '2001'); await pg.fill('#rv-foto-fotografo', 'Caio');
    await pg.click('[data-rev-item="corrigida"]');
    chk(await espera(() => um(`SELECT foto_ano||'|'||foto_fotografo FROM item WHERE codigo='${D('S03', 3)}'`) === '2001|Caio'), '"Salvar correção" grava os dados da foto');
  }
  await pg.evaluate(() => closeDrawer(true)); await pg.waitForTimeout(300);
  await pg.evaluate(c => abrirRevisaoItem(c), D('S01', 6)); await pg.waitForSelector('#rv-titulo', { timeout: 8000 }).catch(() => {});
  chk(!(await pg.$('#rv-foto-ano')), 'folha de desenho não tem os campos da foto');
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(async e => { console.log(linhas.join('\n')); console.error('ERRO', e.message.split('\n')[0]); process.exit(1); });
