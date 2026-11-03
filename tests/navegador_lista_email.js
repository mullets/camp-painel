// 03/11 (Rafael: "mostrar no painel quem aceitou receber e-mails da CAMP, para exportar a lista para o Sender.net"): Downloads mostra
// quantas pessoas aceitaram, o botão do CSV para o Sender.net, a lista e "tirar da lista".  Uso: bash tests/rodar_um.sh tests/navegador_lista_email.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765', DB = process.env.CAMP_DB_PATH;
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
execFileSync('python3', ['-c', `
import sqlite3,sys,json
con=sqlite3.connect(sys.argv[1])
con.execute("INSERT INTO inscricao (site_id,tipo,curso_id,curso,nome,email,emkt) VALUES (9701,'inscricao','res','Residência','Lia Teste','lia@exemplo.org',1)")
con.execute("INSERT INTO uso_download (form_id,origem_id,recebida_em,nome,email,resposta_json) VALUES (4,9702,'2026-11-03 10:00:00','Rui Teste','rui@exemplo.org',?)",(json.dumps({"consentimento_base":"on"}),))
con.commit()`, DB]);
(async () => {
  const br = await chromium.launch(); const erros = [];
  const pg = await (await br.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#uso'); await pg.reload();
  await pg.waitForSelector('#us-emkt a[href="/api/contatos-email.csv"]', { timeout: 10000 }).catch(() => {});
  const t = (await pg.textContent('#us-emkt').catch(() => '')) || '';
  chk(/2 pessoas aceitaram receber e-mails da CAMP/.test(t), 'Downloads mostra quantas pessoas aceitaram', t.slice(0, 160));
  chk(!!(await pg.$('#us-emkt a[href="/api/contatos-email.csv"]')), 'botão "Baixar a lista para o Sender.net (CSV)"');
  const csv = await (await pg.request.get(BASE + '/api/contatos-email.csv')).text();
  chk(csv.includes('email,firstname,lastname') && csv.includes('lia@exemplo.org') && csv.includes('rui@exemplo.org'), 'o CSV traz as duas pessoas');
  await pg.click('#us-emkt details summary');
  await pg.click('[data-emkt-tirar="rui@exemplo.org"]');
  const bt = await pg.waitForSelector('#conf-ov button:has-text("Tirar da lista")', { timeout: 5000 }).catch(() => null);
  if (bt) await bt.click();
  await pg.waitForTimeout(1500);
  const t2 = (await pg.textContent('#us-emkt').catch(() => '')) || '';
  chk(/1 pessoa aceitou/.test(t2) && /Saíram da lista \(1\)/.test(t2), 'tirar da lista atualiza a contagem e mostra em "Saíram da lista"', t2.slice(0, 200));
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})();
