// 23/10 (print de "Problemas por tipo": "já conferi e fica lá"): conferir não tira "outro projeto?" nem "folha de outro projeto" (CAMP-068).
// Agora o cartão desses avisos tem "São deste projeto (N)": um clique confirma "É deste projeto" em todas as folhas do cartão.
// Prova, num projeto com 4 folhas conferidas (D2 e D4 com "projeto divergente" + o problema "folha de outro projeto" do CAMP Vision):
//  - os dois cartões mostram o botão "São deste projeto (2)";
//  - confirmar tira o aviso das duas folhas e fecha os problemas (API), e os cartões somem;
//  - D1 e D3 não mudam; fica no histórico de cada folha; nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/dl.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/dl.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8994)
//   CAMP_DB_PATH=/tmp/dl.db CAMP_BASE=http://127.0.0.1:8994 node tests/navegador_deste_lote.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8994', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0097', D = n => `${P}-1976-S01-D0000${n}`;
py(`
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 97)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade) VALUES ('${P}','F026',97,'Residência Deste Lote',1976,'São Paulo')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote deste','${P}','/x/deste','revisao')").lastrowid
for s in range(1, 5):
    cod = "${P}-1976-S01-D%05d" % s
    div = s in (2, 4)
    pend = {"bloqueios": [], "sinais": ["projeto divergente"] if div else [], "ressalvas": []}
    con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, origem, lote_id, revisao, status_site, titulo, tipo_documento, pendencias) VALUES (?,?,'S01',?,'campvision',?,'conferida','nao_publicado',?,'Planta',?)",
                (cod, "${P}", s, lid, "Planta %d" % s, json.dumps(pend)))
    if div:
        con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,relatado_por) VALUES ('aviso','projeto_errado','campvision',?,'folha de outro projeto','CAMP Vision')", (cod,))
`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await new Promise(r => setTimeout(r, 150)); } return false; };

(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push(`pageerror: ${e.message}`));
  pg.on('console', m => { if (m.type() === 'error' && !/401|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|Failed to load resource/.test(m.text())) erros.push(`console.error: ${m.text()}`); });
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#projeto/' + P); await pg.reload();
  await pg.waitForFunction(() => typeof showProjeto === 'function' && typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  await pg.evaluate(c => showProjeto(c, 'erros'), P);          // "Problemas por tipo" fica na aba Problemas do projeto
  await pg.waitForSelector('#pj-prob-tipos', { timeout: 15000 });
  const bt = sel => pg.$(`#pj-prob-tipos [data-pt-tipo="${sel}"] [data-deste-lote]`);
  const b1 = await bt('outro_projeto'), b2 = await bt('erro-projeto_errado');
  chk(!!b1 && /São deste projeto \(2\)/.test(await b1.textContent()), 'cartão "outro projeto?": botão "São deste projeto (2)"', b1 ? await b1.textContent() : 'sem botão');
  chk(!!b2, 'cartão "folha de outro projeto": também tem o botão');
  if (b1) {
    await b1.click(); await pg.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 5000 });
    chk(/D00002, D00004/.test(await pg.$eval('#conf-ov', o => o.textContent)), 'a confirmação diz quais folhas (D00002, D00004)');
    await pg.click('#conf-ov [data-conf="sim"]');
    await espera(async () => !(await pg.$('#pj-prob-tipos [data-pt-tipo="outro_projeto"]')), 10000);
  }
  const est = JSON.parse(py(`print(json.dumps({
  "sinais": {c: json.loads(p or '{}').get('sinais') for c, p in con.execute("SELECT codigo, pendencias FROM item WHERE projeto_codigo='${P}' ORDER BY codigo")},
  "abertos": con.execute("SELECT COUNT(*) FROM erro WHERE codigo LIKE '${P}%' AND situacao IN ('aberto','em_correcao')").fetchone()[0],
  "hist": con.execute("SELECT COUNT(*) FROM evento WHERE tipo='projeto_confirmado' AND codigo LIKE '${P}%'").fetchone()[0]}))`));
  chk(est.sinais[D(2)].length === 0 && est.sinais[D(4)].length === 0, 'D00002 e D00004 sem o aviso "projeto divergente" (API)', JSON.stringify(est.sinais));
  chk(est.abertos === 0, 'os 2 problemas "folha de outro projeto" fecharam', String(est.abertos));
  chk(est.hist === 2, 'fica no histórico de cada folha (2 registros)', String(est.hist));
  chk(!(await pg.$('#pj-prob-tipos [data-pt-tipo="outro_projeto"]')) && !(await pg.$('#pj-prob-tipos [data-pt-tipo="erro-projeto_errado"]')), 'os dois cartões somem da página');
  chk(erros.length === 0, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
