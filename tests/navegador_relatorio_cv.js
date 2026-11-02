// 02/11 (Rafael: "esses relatórios do campvision, consigo acessar no meu painel? / tudo que ele fez resumidamente e o valor gasto / no
// painel de um fundo, o quanto já gastamos com ele"): Qualidade do CAMP Vision mostra o que ele fez (hoje, 7, 30 dias, dia a dia com os
// projetos) e o gasto por fundo; a página do fundo mostra o gasto com o CAMP Vision (admin).  Uso: bash tests/rodar_um.sh tests/navegador_relatorio_cv.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765', DB = process.env.CAMP_DB_PATH;
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
execFileSync('python3', ['-c', `
import sqlite3,sys,datetime
con=sqlite3.connect(sys.argv[1]); h=datetime.date.today().isoformat()
con.execute("INSERT INTO cv_evento (quando,dia,projeto,fundo,pasta,pranchas,com_carimbo,erros,custo_usd,duracao_s) VALUES (?,?,?,?,?,?,?,?,?,?)",(h+'T10:00:00',h,'F026-P9001 - Casa Teste','F026','/a',12,9,0,0.53,300))
con.execute("UPDATE configuracao SET valor='5' WHERE chave='custos.cotacao_dolar'")
con.commit()`, DB]);
(async () => {
  const br = await chromium.launch(); const erros = [];
  const pg = await (await br.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#qualidade'); await pg.reload();
  await pg.waitForSelector('#qc-fez', { timeout: 10000 }).catch(() => {});
  const t = (await pg.textContent('#qc-relatorio').catch(() => '')) || '';
  chk(/O que o CAMP Vision fez/.test(t) && /US\$ 0,53/.test(t) && /12 pranchas/.test(t), 'Qualidade mostra o que o CAMP Vision fez hoje e o gasto', t.slice(0, 200));
  chk(/R\$ 2,65/.test(t), 'mostra também em reais pela cotação de Configurações');
  await pg.click('#qc-fez details summary'); await pg.waitForTimeout(300);
  chk((await pg.textContent('#qc-fez details')).includes('F026-P9001 - Casa Teste'), 'o dia abre a lista dos projetos');
  chk(/Gasto por fundo/.test(t) && t.includes('F026'), 'tabela de gasto por fundo');
  await pg.goto(BASE + '/#fundo/F026'); await pg.reload();
  await pg.waitForSelector('#fd-gasto .qb-geral', { timeout: 10000 }).catch(() => {});
  const f = (await pg.textContent('#fd-gasto').catch(() => '')) || '';
  chk(/Gasto com o CAMP Vision/.test(f) && /US\$ 0,53/.test(f) && /12 pranchas lidas/.test(f), 'a página do fundo mostra quanto já gastamos com ele', f.slice(0, 200));
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})();
