// CAMP-EMAIL 18/11/2026 · E-mails enviados (Rafael: "temos um painel no admin de e-mails enviados? com log e tudo?"): números do topo,
// lista de todos os canais com o motivo das falhas, filtros, busca, detalhe com as variáveis enviadas e "ver no Sender", CSV, só admin/master,
// sem rolar de lado.  Uso: CHROME=/opt/pw-browsers/chromium bash tests/rodar_um.sh tests/navegador_emails_enviados.js
// (CAMP_PRINT=<arquivo.png> guarda o print da lista em 1366 px, tema claro)
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
const login = (pg, email, senha) => pg.evaluate(([e, s]) => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: e, senha: s }) }).then(r => r.status), [email, senha]);
const lado = pg => pg.evaluate(() => { const m = document.querySelector('.main'); return Math.max(m.scrollWidth - m.clientWidth, document.scrollingElement.scrollWidth - innerWidth) });
(async () => {
  const br = await chromium.launch({ executablePath: process.env.CHROME || undefined }); const erros = [];
  const ctx = await br.newContext({ viewport: { width: 1366, height: 900 }, colorScheme: 'light' });
  const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/'); await login(pg, 'rafael@camp.arq.br', 'senha-bem-longa-123');
  await pg.goto(BASE + '/#emails'); await pg.reload();
  await pg.waitForSelector('[data-em-abrir]', { timeout: 10000 }).catch(() => {});
  await pg.waitForTimeout(500);
  chk(await pg.$eval('#v-emails h1', e => e.childNodes[0].textContent.trim()) === 'E-mails' && await pg.$eval('#em-tab-enviados', b => b.getAttribute('aria-selected')) === 'true', 'tela E-mails (CAMP-EMAIL 20/11), aba Enviados aberta');
  chk(await pg.$eval('#nav button[data-v="emails"]', b => !b.hidden && !b.classList.contains('nav-sec')), 'item "E-mails" no menu para o master (Administração, fora do "Mais")');
  const kpis = await pg.$$eval('#em-kpis .hoje-kpi .l', ls => ls.map(l => l.textContent));
  chk(JSON.stringify(kpis) === JSON.stringify(['enviados hoje', 'enviados em 7 dias', 'falhas em 7 dias', 'não saíram pelo Sender']), 'números do topo: hoje, 7 dias, falhas, não saíram pelo Sender', JSON.stringify(kpis));
  const vals = await pg.$$eval('#em-kpis .hoje-kpi .v', vs => vs.map(v => v.textContent));
  chk(vals[3] === '1' && +vals[2] >= 2, '1 não saiu pelo Sender e as falhas contadas (inscrição e alerta)', JSON.stringify(vals));
  const txt = await pg.$eval('#em-lista', t => t.textContent);
  chk(/Lia Teste Prado/.test(txt) && /Pedido recebidoTR04/.test(txt) && /Recibo do Amigos da CAMP/.test(txt) && /o QNAP não responde/.test(txt), 'lista junta site (TR04), Amigos (recibo) e alerta interno', txt.slice(0, 300));
  chk(/Não saiu pelo Sender/.test(txt) && /o Sender recusou: HTTP 401/.test(txt), 'mostra "Não saiu pelo Sender" com o motivo');
  chk(/Falhou/.test(txt) && /SMTP não configurado/.test(txt), 'falha com o motivo (alerta sem SMTP)');
  chk(await lado(pg) <= 0, '1366 px: a tela não rola de lado', String(await lado(pg)));
  if (process.env.CAMP_PRINT) await pg.screenshot({ path: process.env.CAMP_PRINT, fullPage: false });
  // filtro por situação
  await pg.click('#em-abas [data-em-sit="nao_sender"]'); await pg.waitForTimeout(500);
  const ns = await pg.$$eval('#em-lista [data-em-abrir]', rs => rs.map(r => r.textContent));
  chk(ns.length === 1 && /Rui Teste Gomes/.test(ns[0]), 'aba "Não saiu pelo Sender": só a visita do Rui', JSON.stringify(ns));
  await pg.click('#em-abas [data-em-sit=""]'); await pg.waitForTimeout(400);
  // filtro por canal
  await pg.selectOption('#em-canal', 'smtp'); await pg.waitForTimeout(500);
  const sm = await pg.$$eval('#em-lista [data-em-abrir]', rs => rs.map(r => r.dataset.emAbrir));
  chk(sm.length >= 1 && sm.every(i => /^(alerta|resumo|uso):/.test(i)), 'canal SMTP do painel: só alertas/resumo/Downloads', JSON.stringify(sm));
  chk(/canal=smtp/.test(await pg.$eval('#em-csv', a => a.href)), 'Exportar CSV segue os filtros');
  await pg.selectOption('#em-canal', ''); await pg.waitForTimeout(400);
  // busca por protocolo
  await pg.fill('#em-q', 'CAMP-2026-008103'); await pg.waitForTimeout(900);
  const bq = await pg.$$eval('#em-lista [data-em-abrir]', rs => rs.map(r => r.textContent));
  chk(bq.length === 1 && /Ivo Teste Luz/.test(bq[0]), 'busca pelo protocolo acha a inscrição do Ivo', JSON.stringify(bq));
  await pg.fill('#em-q', ''); await pg.waitForTimeout(900);
  // detalhe: Amigo com as variáveis enviadas
  await pg.click('#em-lista [data-em-abrir^="amigo:"] td:nth-child(3)'); await pg.waitForTimeout(500);
  const det = await pg.$eval('#d-body', e => e.textContent);
  chk(/Variáveis enviadas/.test(det) && /valor_pago/.test(det) && /R\$ 450,00/.test(det) && /ver no Sender/.test(det) && /em-7001/.test(det) && /TR20/.test(det), 'detalhe: TR20, variáveis enviadas, id no Sender e "ver no Sender"', det.slice(0, 300));
  await pg.evaluate(() => closeDrawer(true)); await pg.waitForTimeout(300);
  // CSV
  const csv = await pg.evaluate(() => fetch('/api/emails/exportar.csv?periodo=todos').then(r => r.text()));
  chk(/^﻿?data_utc;destinatario;/.test(csv) && /lia@exemplo.com/.test(csv), 'CSV com cabeçalho e os e-mails');
  // celular
  const cel = await (await br.newContext({ viewport: { width: 390, height: 800 } })).newPage();
  cel.on('pageerror', e => erros.push('pageerror (390): ' + e.message));
  await cel.goto(BASE + '/'); await login(cel, 'rafael@camp.arq.br', 'senha-bem-longa-123'); await cel.goto(BASE + '/#emails'); await cel.reload();
  await cel.waitForSelector('[data-em-abrir]', { timeout: 10000 }).catch(() => {}); await cel.waitForTimeout(500);
  chk(await lado(cel) <= 0, '390 px: a tela não rola de lado', String(await lado(cel)));
  // operador não vê
  const op = await (await br.newContext({ viewport: { width: 1366, height: 900 } })).newPage();
  await op.goto(BASE + '/'); await login(op, 'operador@camp.arq.br', 'senha-operador-123'); await op.reload(); await op.waitForTimeout(1200);
  const vis = await op.$eval('#nav button[data-v="emails"]', b => !b.hidden && getComputedStyle(b).display !== 'none').catch(() => false);
  const st = await op.evaluate(() => fetch('/api/emails').then(r => r.status));
  chk(!vis && st === 403, 'operador: sem o item no menu e 403 na API (dados pessoais)', JSON.stringify({ vis, st }));
  await op.goto(BASE + '/#emails'); await op.waitForTimeout(800);
  chk(!(await op.$eval('#v-emails', e => e.classList.contains('on'))), 'operador: o endereço #emails não abre a tela');
  chk(!erros.length, 'sem erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
