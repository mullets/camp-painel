// 21/10 (Rafa: "muito confuso publicar um arquiteto, ou deixar um público"), no navegador de verdade, com o site FALSO:
//  - no fundo, o quadro "Página do arquiteto no site" diz em uma frase que a página não está pública e que, sem ela, NADA do fundo aparece;
//  - "Publicar a página do arquiteto" (um clique + confirmar) deixa a página publicada; o quadro muda na hora;
//  - no arquiteto, o mesmo quadro; o checklist não manda mais ao wp-admin; o "Situação no site" (que não fazia nada) saiu;
//  - o master tira a página do site com motivo; nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx, com o site falso):
//   CAMP_DB_PATH=/tmp/ar.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ar.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 ../tests/servidor_wp_falso.py 8966)
//   CAMP_DB_PATH=/tmp/ar.db CAMP_BASE=http://127.0.0.1:8966 node tests/navegador_arquiteto.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8966', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const AID = py(`
con.execute("INSERT OR REPLACE INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F084','Lina Teste','LNT',1)")
con.execute("INSERT OR REPLACE INTO direitos_fundo (fundo_codigo,situacao,titular,documento_autorizacao) VALUES ('F084','autorizado','Instituto','Termo 1')")
con.execute("INSERT INTO agente (forma_autorizada,tipo) VALUES ('Lina Teste','pessoa')")
aid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
con.execute("INSERT INTO fundo_agente (fundo_codigo,agente_id,papel) VALUES ('F084',?,'produtor')", (aid,))
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES ('F084',1)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,status_site) VALUES ('F084-P0001','F084',1,'Casa de vidro',1951,'no_ar')")
print(aid)
`);
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await f()) return true; await new Promise(r => setTimeout(r, 150)); } return false; };
const um = q => py(`print((con.execute("""${q}""").fetchone() or [''])[0])`);
(async () => {
  const br = await chromium.launch({ executablePath: CHROME }); const pg = await br.newPage({ viewport: { width: 1400, height: 900 } });
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  await pg.goto(BASE + '/'); await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#fundo/F084'); await pg.reload();
  await pg.waitForSelector('#fd-arq .arq-linha', { timeout: 15000 }).catch(() => {});
  const t0 = await pg.textContent('#fd-arq').catch(() => '');
  chk(/não publicada/.test(t0) && /nada do fundo F084 aparece no site/.test(t0), 'fundo: o quadro diz que a página não está pública e que, sem ela, nada do fundo aparece', t0.slice(0, 200));
  chk(!!(await pg.$('#fd-arq [data-arq-publicar="F084"]')), 'fundo: um botão "Publicar a página do arquiteto"');
  const ordem = await pg.evaluate(() => { const a = document.getElementById('fd-arq'), g = document.getElementById('fd-guia'); return !!(a && g && (a.compareDocumentPosition(g) & Node.DOCUMENT_POSITION_FOLLOWING)); });
  chk(ordem, 'o quadro do arquiteto vem antes do "Como publicar este fundo"');
  await pg.click('#fd-arq [data-arq-publicar]'); await pg.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 5000 });
  await pg.click('#conf-ov [data-conf="sim"]');
  chk(await espera(() => um("SELECT status FROM wp_pagina WHERE url LIKE '%/acervo/arquitetos/%' ORDER BY id DESC LIMIT 1") === 'publish'), 'publicar: a página do arquiteto fica publicada no site');
  chk(await espera(async () => /publicada/.test(await pg.textContent('#fd-arq')) && !/não publicada/.test(await pg.textContent('#fd-arq'))), 'o quadro do fundo muda na hora para "publicada", com o link');
  chk(um("SELECT COUNT(*) FROM evento WHERE entidade='fundo' AND codigo='F084' AND tipo='site_arquiteto_publicado'") === '1', 'fica no histórico do fundo');

  // no arquiteto
  await pg.evaluate(id => editarAgente(id), +AID); await pg.waitForSelector('#d-body .arq-site .arq-linha', { timeout: 8000 }).catch(() => {});
  const td = await pg.textContent('#d-body').catch(() => '');
  chk(/Página do arquiteto no site/.test(td) && /tag g">publicada/.test(await pg.innerHTML('#d-body .arq-site')), 'arquiteto: o mesmo quadro, já como publicada');
  chk(!/wp-admin/i.test(td), 'arquiteto: nada de "wp-admin" na tela', (td.match(/.{0,60}wp-admin.{0,60}/i) || [''])[0]);
  chk(!(await pg.$('#ea-status')), 'arquiteto: saiu o "Situação no site" que não publicava nada');
  // master tira do site
  const tirar = await pg.$('#d-body [data-arq-tirar="F084"]');
  chk(!!tirar, 'master vê "Tirar a página do arquiteto do site…"');
  if (tirar) {
    await tirar.click(); await pg.waitForSelector('#conf-motivo', { timeout: 5000 });
    chk(await pg.$eval('#conf-ov [data-conf="sim"]', b => b.disabled), 'sem motivo, não deixa confirmar');
    await pg.fill('#conf-motivo', 'pedido do instituto'); await pg.click('#conf-ov [data-conf="sim"]');
    chk(await espera(() => um("SELECT status FROM wp_pagina WHERE url LIKE '%/acervo/arquitetos/%' ORDER BY id DESC LIMIT 1") === 'draft'), 'tirar: a página volta a rascunho');
    chk(await espera(async () => /não publicada/.test(await pg.textContent('#d-body .arq-site'))), 'o quadro volta a "não publicada"');
  }
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})().catch(async e => { console.log(linhas.join('\n')); console.error('ERRO', e.message.split('\n')[0]); process.exit(1); });
