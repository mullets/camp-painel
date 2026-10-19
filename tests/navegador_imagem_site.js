// Folha já no site girada/espelhada no painel (19/10): aparece "A imagem no site ainda é a antiga" com o botão "Atualizar imagem no site",
// na página da folha e na revisão. O site do teste não existe (WP_BASE_URL=http://127.0.0.1:9): o clique tem de dar erro em português,
// manter a faixa e oferecer "Tentar de novo". Nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO, porta 8973):
//   CAMP_DB_PATH=/tmp/is.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/is.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8973)
//   CAMP_DB_PATH=/tmp/is.db CAMP_BASE=http://127.0.0.1:8973 node tests/navegador_imagem_site.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8973', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0193', C = `${P}-1975-S01-D00001`;
py(`
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026',193)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,status_site) VALUES ('${P}','F026',193,'Casa Publicada',1975,'São Paulo','no_ar')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
lote=con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, aprovado_em, aprovado_por) VALUES ('Lote pub','${P}','/nao/existe','publicado',datetime('now'),'adm')").lastrowid
con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,origem,lote_id,status_site,revisao,titulo,pendencias) VALUES (?,?,?,?,?,?,?,?,?,?)",('${C}','${P}','S01',1,'campvision',lote,'no_ar','conferida','Planta',json.dumps({"sinais":[]})))
con.execute("DELETE FROM divergencia_site WHERE codigo='${C}'")
con.execute("INSERT INTO divergencia_site (entidade, codigo, campo, valor_painel, valor_site) VALUES ('item','${C}','pendente_imagem_ajustada','A imagem no site ainda é a antiga',NULL)")
`);
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const pg = await br.newPage({ viewport: { width: 1400, height: 900 } });
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  // página da folha
  await pg.goto(BASE + '/#item/' + C); await pg.reload();
  const temFaixa = await pg.waitForSelector(`#idet [data-img-site-pend="${C}"] [data-img-site="${C}"]`, { timeout: 15000 }).then(() => true, () => false);
  chk(temFaixa, 'página da folha: faixa "A imagem no site ainda é a antiga" com o botão "Atualizar imagem no site"');
  await pg.click(`#idet [data-img-site="${C}"]`);
  const tentou = await pg.waitForFunction(c => { const b = document.querySelector(`#idet [data-img-site="${c}"]`); return b && b.textContent === 'Tentar de novo' && !b.disabled; }, C, { timeout: 15000 }).then(() => true, () => false);
  chk(tentou, 'site fora do ar: o botão volta como "Tentar de novo" e a faixa continua');
  const t = await pg.evaluate(() => [...document.querySelectorAll('.toast,#toast,[role="status"]')].map(x => x.textContent).join(' | '));
  chk(/continua a antiga|não aceitou/.test(t), 'o erro aparece em português dizendo que a imagem do site continua a antiga', t.slice(0, 200));
  // revisão (gaveta) a partir da página do projeto
  await pg.goto(BASE + '/#projeto/' + P); await pg.reload(); await pg.waitForSelector(`.thumb[data-rev-abrir="${C}"]`, { timeout: 15000 });
  await pg.click(`.thumb[data-rev-abrir="${C}"]`);
  const naRev = await pg.waitForSelector(`#d-body [data-img-site-pend="${C}"] [data-img-site="${C}"]`, { timeout: 10000 }).then(() => true, () => false);
  chk(naRev, 'revisão da folha: a mesma faixa com o botão aparece na gaveta');
  // sem pendência: nada aparece
  py(`con.execute("UPDATE divergencia_site SET resolvida=1 WHERE codigo='${C}'")`);
  await pg.goto(BASE + '/#item/' + C); await pg.reload(); await pg.waitForSelector('#idet .dethdr', { timeout: 15000 });
  chk(!(await pg.$(`[data-img-site-pend="${C}"]`)), 'sem pendência, a faixa não aparece');
  chk(!erros.length, 'nenhum erro de JavaScript na página', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
