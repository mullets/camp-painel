// 01/11 (Rafael: "não recebi esses mails" — pedidos do site que não apareciam no painel): a tela Pedidos de alta resolução mostra
// quando o painel buscou pedidos no site pela última vez, se a busca falhou (com o motivo), o que ficou preso e, para admin,
// "Buscar agora". Uso: bash tests/rodar_um.sh tests/navegador_coleta_pedidos.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765', DB = process.env.CAMP_DB_PATH;
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
execFileSync('python3', ['-c', `
import sqlite3,sys
con=sqlite3.connect(sys.argv[1])
con.execute("INSERT INTO pedido_site_coleta (lidas,novas,importadas,erro) VALUES (0,0,0,'Site recusou as credenciais (401)')")
con.execute("INSERT INTO pedido_site (site_id,tipo,codigo,criado_no_site,payload,situacao,erro) VALUES (777,'alta-resolucao','F026-P0001',datetime('now'),'{}','falhou','ValueError: teste')")
con.commit()`, DB]);
(async () => {
  const br = await chromium.launch(); const erros = [];
  const pg = await (await br.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#solicitacoes'); await pg.reload();
  await pg.waitForSelector('#sol-coleta:not([hidden])', { timeout: 10000 }).catch(() => {});
  const t = (await pg.textContent('#sol-coleta').catch(() => '')) || '';
  chk(/última busca no site/.test(t), 'mostra a última busca de pedidos no site', t.slice(0, 200));
  chk(/a busca falhou/.test(t) && t.includes('401'), 'mostra que a busca falhou, com o motivo');
  chk(/não entrou/.test(t) && t.includes('#777'), 'mostra o pedido do site que ficou preso');
  chk(await pg.$('#sol-coletar') !== null, 'admin vê "Buscar agora"');
  await pg.click('#sol-coletar'); await pg.waitForTimeout(2500);
  const toast = (await pg.textContent('#toast').catch(() => '')) || '';
  chk(/Busca feita|A busca falhou|Application Password|credenciais/i.test(toast), '"Buscar agora" busca e avisa o resultado', toast);
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})();
