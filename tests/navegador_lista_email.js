// 03/11 (Rafael: "mostrar no painel quem aceitou receber e-mails da CAMP, para exportar a lista para o Sender.net"): quem aceitou fica
// em E-mails → Quem aceita e-mails (contagem, CSV para o Sender.net, "tirar da lista"); Downloads não mostra mais a lista.  Uso: bash tests/rodar_um.sh tests/navegador_lista_email.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765', DB = process.env.CAMP_DB_PATH;
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
execFileSync('python3', ['-c', `
import sqlite3,sys,json
con=sqlite3.connect(sys.argv[1])
con.execute("INSERT INTO inscricao (site_id,tipo,curso_id,curso,nome,email,emkt) VALUES (9701,'inscricao','res','Residência','Lia Teste','lia@exemplo.org',1)")
con.execute("INSERT INTO uso_download (form_id,origem_id,recebida_em,nome,email,resposta_json) VALUES (4,9702,'2026-11-03 10:00:00','Rui Teste','rui@exemplo.org',?)",(json.dumps({"consentimento_emkt":"on"}),))
con.commit()`, DB]);
(async () => {
  const br = await chromium.launch(); const erros = [];
  const pg = await (await br.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  // 21/11 (Rafael: "não acha meio estranho a lista de quem aceita e-mail estar na parte de downloads? não faz sentido"):
  // a lista saiu de Downloads; mora só em E-mails → Quem aceita e-mails (contar, CSV, tirar e devolver).
  await pg.goto(BASE + '/#uso'); await pg.reload();
  await pg.waitForTimeout(2500);
  const tu = (await pg.textContent('main').catch(() => '')) || '';
  chk(!(await pg.$('#us-emkt')) && !/Lista de e-mail da CAMP/.test(tu), 'Downloads não mostra mais a lista de e-mail');
  await pg.goto(BASE + '/#emails/aceite'); await pg.reload();
  await pg.waitForSelector('#ek-lista [data-emkt-tirar]', { timeout: 10000 }).catch(() => {});
  chk(/2 pessoas/.test((await pg.textContent('#ek-cnt').catch(() => '')) || ''), 'E-mails → Quem aceita e-mails mostra as 2 pessoas');
  chk(((await pg.getAttribute('#ek-csv', 'href').catch(() => '')) || '').startsWith('/api/contatos-email.csv'), 'botão do CSV para o Sender.net na aba');
  const csv = await (await pg.request.get(BASE + '/api/contatos-email.csv')).text();
  chk(csv.includes('email,firstname,lastname') && csv.includes('lia@exemplo.org') && csv.includes('rui@exemplo.org'), 'o CSV traz as duas pessoas');
  await pg.click('[data-emkt-tirar="rui@exemplo.org"]');
  const bt = await pg.waitForSelector('#conf-ov button:has-text("Tirar da lista")', { timeout: 5000 }).catch(() => null);
  if (bt) await bt.click();
  await pg.waitForTimeout(1500);
  chk(/1 pessoa/.test((await pg.textContent('#ek-cnt').catch(() => '')) || '') && /Saíram da lista \(1\)/.test((await pg.textContent('#ek-fora').catch(() => '')) || ''), 'tirar da lista atualiza a contagem e mostra em "Saíram da lista"');
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})();
