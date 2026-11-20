// 18/11 CAMP-SENDER (Rafael: "quem aceitou receber e-mails da CAMP… seria bom saber e conseguir filtrar"): tela "Quem aceita e-mails
// da CAMP" (só admin) com situação no Sender, filtros, seleção e CSV; coluna "Aceita e-mails" nos Amigos.
// Uso: bash tests/rodar_um.sh tests/navegador_emkt_sender.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765', DB = process.env.CAMP_DB_PATH;
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
execFileSync('python3', ['-c', `
import sqlite3,sys
con=sqlite3.connect(sys.argv[1])
for sid,em,nome,org,on,q,sit,err in (("post-1","ana@exemplo.org","Ana Teste","agendamento","Visita ou biblioteca","2026-11-10 10:00:00","inscrito",""),
    ("post-2","bia@exemplo.org","Bia Teste","contato","Contato","2026-11-11 10:00:00","pendente","grupo não configurado"),
    ("ff-3","caio@exemplo.org","Caio Teste","download","Cadastro de download","2026-11-12 10:00:00","erro","HTTP 422"),
    ("post-4","dora@exemplo.org","Dora Teste","apoio","Amigos e adoções","2026-11-13 10:00:00","cancelou","no Sender: unsubscribed")):
    con.execute("INSERT INTO emkt_site (site_id,email,nome,origem,origem_nome,aceite_em,versao,situacao,erro) VALUES (?,?,?,?,?,?,'2026-11-02',?,?)",(sid,em,nome,org,on,q,sit,err))
con.execute("INSERT INTO amigo (tipo,nome,email,emkt,situacao) VALUES ('amigo','Ana Teste','ana@exemplo.org',1,'pago')")
con.execute("INSERT INTO amigo (tipo,nome,email,emkt,situacao) VALUES ('amigo','Eli Teste','eli@exemplo.org',0,'pago')")
con.commit()`, DB]);
(async () => {
  const br = await chromium.launch(); const erros = [];
  const pg = await (await br.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#emails/aceite'); await pg.reload();   // CAMP-EMAIL 20/11: agora é a aba Quem aceita e-mails da tela E-mails
  await pg.waitForSelector('#ek-lista .ek-ck', { timeout: 10000 }).catch(() => {});
  const n = async () => (await pg.$$('#ek-lista .ek-ck')).length;
  chk(!(await pg.$('nav button[data-v="emkt"]')) && !!(await pg.$('nav button[data-v="emails"]')), 'sem item próprio no menu: fica em E-mails');
  const h1 = (await pg.textContent('#v-emails h1').catch(() => '')) || '';
  chk(h1.trim() === 'E-mails' && await pg.$eval('#em-tab-aceite', b => b.getAttribute('aria-selected')) === 'true' && await pg.$eval('#em-p-aceite', p => !p.hidden), 'tela E-mails, aba Quem aceita e-mails aberta', h1);
  const k = (await pg.textContent('#ek-kpis').catch(() => '')) || '';
  chk(/4\s*aceitam e-mails/.test(k) && /1\s*no Sender/.test(k) && /2\s*ainda não entraram/.test(k) && /1\s*cancelaram/.test(k), 'números do topo por situação', k.slice(0, 200));
  chk(await n() === 4, '4 pessoas na lista');
  const tl = (await pg.textContent('#ek-lista').catch(() => '')) || '';
  chk(/No Sender/.test(tl) && /Pendente/.test(tl) && /grupo não configurado/.test(tl) && /Cancelou/.test(tl), 'situação no Sender com o motivo', tl.slice(0, 300));
  await pg.click('[data-ek-sit="pendente"]'); await pg.waitForTimeout(800);
  chk(await n() === 1 && /bia@exemplo.org/.test(await pg.textContent('#ek-lista')), 'filtro por situação');
  chk(/situacao=pendente/.test(await pg.getAttribute('#ek-csv', 'href')), 'Exportar CSV leva o filtro');
  await pg.click('[data-ek-sit="todas"]'); await pg.waitForTimeout(800);
  await pg.selectOption('#ek-origem', 'download'); await pg.waitForTimeout(800);
  chk(await n() === 1 && /caio@exemplo.org/.test(await pg.textContent('#ek-lista')), 'filtro por origem');
  await pg.selectOption('#ek-origem', 'todas'); await pg.waitForTimeout(800);
  await pg.fill('#ek-de', '2026-11-12'); await pg.dispatchEvent('#ek-de', 'change'); await pg.waitForTimeout(800);
  await pg.fill('#ek-ate', '2026-11-13'); await pg.dispatchEvent('#ek-ate', 'change'); await pg.waitForTimeout(800);
  chk(await n() === 2, 'filtro por período (aceitou de … até)', await pg.textContent('#ek-lista'));
  await pg.fill('#ek-de', ''); await pg.dispatchEvent('#ek-de', 'change'); await pg.waitForTimeout(500);
  await pg.fill('#ek-ate', ''); await pg.dispatchEvent('#ek-ate', 'change'); await pg.waitForTimeout(800);
  await pg.check('#ek-todos'); await pg.waitForTimeout(200);
  chk(!(await pg.$eval('#ek-selbar', e => e.hidden)) && /4 selecionados/.test(await pg.textContent('#ek-seln')), 'selecionar todos mostra a barra');
  const csv = await pg.evaluate(async () => (await fetch('/api/contatos-email.csv', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ emails: ['ana@exemplo.org', 'bia@exemplo.org'] }) })).text());
  chk(csv.includes('situacao_sender') && csv.includes('ana@exemplo.org') && csv.includes('bia@exemplo.org') && !csv.includes('caio@exemplo.org'), 'CSV dos selecionados');
  await pg.goto(BASE + '/#amigos'); await pg.waitForSelector('#am-lista tr[data-am-abrir]', { timeout: 10000 }).catch(() => {});
  const am = (await pg.textContent('#am-lista').catch(() => '')) || '', hd = (await pg.textContent('#am-head').catch(() => '')) || '';
  chk(/Aceita e-mails/.test(hd) && /aceita/.test(am), 'Amigos: coluna "Aceita e-mails"', hd + ' | ' + am.slice(0, 200));
  await pg.selectOption('#am-emkt', 'sim'); await pg.waitForTimeout(800);
  const am2 = (await pg.textContent('#am-lista').catch(() => '')) || '';
  chk(/ana@exemplo.org/.test(am2) && !/eli@exemplo.org/.test(am2), 'Amigos: filtro "Aceita e-mails"', am2.slice(0, 200));
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})();
