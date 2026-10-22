// CAMP-067 (20/10, operadora: "o botão para a etapa importar não funciona sempre"; "pra uns projetos rola e outros não").
// Prova no navegador: (1) projeto que JÁ tem folhas de um lote (a conferir) e recebeu um lote novo: o cartão Folhas mostra "Importar folhas"
// apontando para o lote NOVO (antes o botão sumia, trocado por "Conferir", ou ia no primeiro lote não aprovado); ao clicar, o botão desliga,
// aparece "Importando…" e as 3 folhas entram; (2) projeto cujo lote não dá para importar (pasta fora do QNAP): nada de botão que falha,
// o cartão e o próximo passo dizem por quê. Nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO, porta 89xx):
//   CAMP_DB_PATH=/tmp/imp.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/imp.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8912)
//   CAMP_DB_PATH=/tmp/imp.db CAMP_BASE=http://127.0.0.1:8912 node tests/navegador_importar.js
const { execFileSync } = require('child_process');
const fs = require('fs'), os = require('os'), path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8912', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0194', Q = 'F026-P0195';
const pasta = fs.mkdtempSync(path.join(os.tmpdir(), 'imp067_'));
fs.mkdirSync(path.join(pasta, 'catalogacao'));
const fix = fs.readFileSync(path.join(__dirname, 'fixtures/campvision/lote_normal/catalogacao/pacote_tainacan.json'), 'utf-8');
fs.writeFileSync(path.join(pasta, 'catalogacao/pacote_tainacan.json'), fix.split('F026-P0001').join(P));
const ids = JSON.parse(py(`
for c_,n in (('${P}',194),('${Q}',195)):
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026',?)",(n,))
    con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES (?, 'F026', ?, ?, 1972, 'São Paulo')",(c_,n,'Casa Importar '+str(n)))
A=con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote antigo','${P}','/nao/existe/a','revisao')").lastrowid
for n in (11,12):
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,origem,lote_id,status_site,pendencias,titulo,revisao) VALUES (?,?,?,?,?,?,?,?,?,?)",('${P}-1972-S01-D%05d'%n,'${P}','S01',n,'campvision',A,'nao_publicado','{}','Prancha %d'%n,'pendente'))
B=con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote novo','${P}',?,'revisao')",(${JSON.stringify(pasta)},)).lastrowid
C=con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote sem pasta','${Q}','/nao/existe/camp067','revisao')").lastrowid
print(json.dumps({'A':A,'B':B,'C':C}))
`));
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const pg = await br.newPage({ viewport: { width: 1400, height: 900 } });
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  const abrir = async c => { await pg.goto(BASE + '/#projeto/' + c); await pg.reload(); await pg.waitForSelector('#pj-cards .pjc[data-pjc="folhas"]', { timeout: 15000 });
    await pg.waitForFunction(() => window.SL && SL.revisao && !/…/.test(document.getElementById('pj-cards').textContent), null, { timeout: 15000 }); await pg.waitForTimeout(600) };
  const cartao = () => pg.$eval('#pj-cards .pjc[data-pjc="folhas"]', c => c.innerText.replace(/\s+/g, ' ').trim());
  // (1) projeto com folhas de um lote e um lote novo para importar
  await abrir(P);
  const bt = await pg.$(`#pj-cards .pjc[data-pjc="folhas"] [data-pp="importar"]`);
  chk(!!bt, 'projeto que já tem folhas a conferir + lote novo: o cartão Folhas mostra "Importar folhas"', await cartao());
  chk(bt && (await bt.getAttribute('data-lote')) === String(ids.B), 'o botão importa o lote NOVO (o que está sem folhas), não o antigo', bt ? await bt.getAttribute('data-lote') : '');
  chk(!!(await pg.$('#pj-cards .pjc[data-pjc="folhas"] [data-pjc-conferir]')), 'o "Conferir" do lote antigo continua ao lado');
  if (bt) {
    await pg.route('**/api/lotes/*/importar', async rt => { await new Promise(r => setTimeout(r, 700)); await rt.continue() });
    await bt.click();
    const viu = await pg.waitForFunction(() => /Importando/.test(document.body.innerText), null, { timeout: 3000 }).then(() => true, () => false);
    chk(viu, 'ao clicar aparece "Importando…" (antes nada mudava enquanto o QNAP respondia)');
    const entrou = await pg.waitForFunction(() => (window.ITENS_PJ || []).length >= 5, null, { timeout: 15000 }).then(() => true, () => false);
    chk(entrou, 'as 3 folhas do lote novo entram no projeto (5 no total)', await pg.evaluate(() => (window.ITENS_PJ || []).length));
    const n = py(`print(con.execute("SELECT COUNT(*) FROM item WHERE lote_id=${ids.B}").fetchone()[0])`);
    chk(n === '3', 'no banco, as folhas são do lote novo', n);
  }
  // (2) lote que não dá para importar: sem botão, com o motivo
  await abrir(Q);
  chk(!(await pg.$('#pj-cards [data-pp="importar"]')) && !(await pg.$('#pj-proximo [data-pp="importar"]')), 'pasta fora do QNAP: nenhum botão "Importar" que só falharia');
  chk(/Ainda não dá para importar/.test(await cartao()) && /não acha a pasta/.test(await cartao()), 'o cartão Folhas diz por quê (o painel não acha a pasta)', await cartao());
  const pp = await pg.evaluate(() => ((window.PP_ULT || {}).r || {}).lote || {});
  chk(/não acha a pasta/.test(pp.importar_motivo || ''), 'o próximo passo (fila e projeto) traz o mesmo motivo', JSON.stringify(pp).slice(0, 200));
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close(); fs.rmSync(pasta, { recursive: true, force: true });
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
