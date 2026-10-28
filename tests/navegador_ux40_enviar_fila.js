// UX-40 no navegador de verdade: em Máquinas → "Catálogo local × site", ao lado de "N escritas pendentes", o admin vê
// "Enviar as N agora" (o operador não vê); a confirmação diz "Uma rodada só; o reenvio automático continua desligado";
// o clique vira UMA tarefa com o resultado (enviadas · falharam · ainda na fila) e a lista do que falhou, com o motivo;
// "Sincronizar agora" explica que só lê o site; site.reenvio_persistente continua 0; nenhum erro no console.
// O site aqui NÃO existe (WP_BASE_URL=http://127.0.0.1:9): todo envio falha e as folhas ficam na fila com o motivo.
// O caminho de sucesso (as folhas saem da fila) está no modo ux40_enviar_fila de tests/teste_backend.py, com o WordPress falso.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada nem o site de verdade):
//   CAMP_DB_PATH=/tmp/ux40/n.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux40/n.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8997)
//   CAMP_DB_PATH=/tmp/ux40/n.db CAMP_BASE=http://127.0.0.1:8997 node tests/navegador_ux40_enviar_fila.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8997', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...args) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...args], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const cfg = k => py(`r=con.execute("SELECT valor FROM configuracao WHERE chave=?", (sys.argv[2],)).fetchone()\nprint(r[0] if r else '')`, k);

// F075-P0001 publicado, 2 folhas no site corrigidas no painel (estão na fila) e uma escrita pendente antiga
py(`
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F075','Fundo Fila','FFL',1)")
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES ('F075',1)")
con.execute("INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,status_site,tainacan_item_id) VALUES ('F075-P0001','F075',1,'Casa da Fila',1960,'no_ar',750)")
con.execute("DELETE FROM fila_correcao_site")
con.execute("DELETE FROM evento WHERE codigo LIKE 'F075-%' OR tipo='site_correcoes_enviadas'")
con.execute("DELETE FROM item WHERE projeto_codigo='F075-P0001'")
con.execute("DELETE FROM divergencia_site WHERE codigo LIKE 'F075-%'")
for k in (1, 2):
    cod = 'F075-P0001-1960-S01-D%05d' % k
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,escala,origem,revisao,status_site,tainacan_item_id) VALUES (?,?,'S01',?,?,'1:50','campvision','conferida','no_ar',?)", (cod, 'F075-P0001', k, 'Planta %d' % k, 750 + k))
    con.execute("INSERT INTO evento (entidade,codigo,tipo,ator,detalhe) VALUES ('item',?,'site_item_criado','x','{}')", (cod,))
    con.execute("UPDATE item SET escala='1:100' WHERE codigo=?", (cod,))
    con.execute("INSERT INTO evento (entidade,codigo,tipo,ator,detalhe) VALUES ('item',?,'editado','x',?)", (cod, json.dumps({'antes': {'escala': '1:50'}})))
con.execute("INSERT INTO divergencia_site (entidade,codigo,campo,valor_painel) VALUES ('item','F075-P0001-1960-S01-D00001','pendente_Escala_no_site','o site respondeu 502')")
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=|\/api\/analytics/.test(u);
  async function entrar(email, senha) {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    await ctx.route('**/*', rt => rt.request().url().startsWith(BASE) ? rt.continue() : rt.fulfill({ status: 200, contentType: 'text/css', body: '' }));
    const page = await ctx.newPage();
    page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(email + ': ' + m.text()); });
    page.on('pageerror', e => erros.push(email + ' pageerror: ' + e.message));
    page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(email + ' ' + r.status() + ' ' + r.url().replace(BASE, '')); });
    await page.goto(BASE + '/');
    await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    return { ctx, page };
  }
  const so = t => String(t || '').replace(/\s+/g, ' ').trim();
  try {
    // ---- operador: Máquinas sem o botão; a rota recusa ----
    const op = await entrar('operador@camp.arq.br', 'senha-operador-123');
    await op.page.evaluate(() => go('estacoes'));
    await op.page.waitForSelector('#est-hoje', { timeout: 30000 }); await op.page.waitForTimeout(1500);
    chk(await op.page.$('#fila-site-enviar') === null, 'operador não vê "Enviar as N agora"');
    const r403 = await op.ctx.request.post(BASE + '/api/site/correcoes-pendentes/enviar?tarefa=1');
    chk(r403.status() === 403, `operador: a rota responde 403 (veio ${r403.status()})`);
    await op.ctx.close();

    // ---- admin ----
    const ad = await entrar('rafael@camp.arq.br', 'senha-bem-longa-123');
    let posts = 0;
    ad.page.on('request', r => { if (r.method() === 'POST' && /\/api\/site\/correcoes-pendentes\/enviar/.test(r.url())) posts++; });
    await ad.page.evaluate(() => go('estacoes'));
    await ad.page.waitForSelector('#fila-site-enviar', { timeout: 30000 });
    const dd = so(await ad.page.evaluate(() => document.getElementById('fila-site').closest('dd').innerText));
    chk(/1 escritas? pendentes?/.test(dd) && /2 correções de folhas esperando o site/.test(dd), `ao lado de "escritas pendentes": "2 correções de folhas esperando o site" (${dd})`);
    chk(so(await ad.page.textContent('#fila-site-enviar')) === 'Enviar as 2 agora', 'o botão diz "Enviar as 2 agora"');
    const sync = so(await ad.page.evaluate(() => { const b = [...document.querySelectorAll('button')].find(x => x.textContent.trim() === 'Sincronizar agora'); return b ? b.parentElement.innerText : ''; }));
    chk(/Só lê o site e atualiza as diferenças: não envia nada/.test(sync), `ao lado de "Sincronizar agora": só lê o site (${sync})`);

    await ad.page.click('#fila-site-enviar');
    await ad.page.waitForSelector('#conf-ov', { timeout: 5000 });
    const conf = so(await ad.page.textContent('#conf-ov'));
    chk(/Manda agora ao site as 2 correções que estão esperando\. Uma rodada só; o reenvio automático continua desligado\./.test(conf), `confirmação curta (${conf})`);
    await ad.page.click('#conf-ov [data-conf="sim"]');
    await ad.page.waitForFunction(() => { const a = document.querySelector('.aviso-local[data-aviso="enviar-fila-site"]'); return a && /Enviadas:/.test(a.innerText); }, null, { timeout: 60000 });
    const fim = so(await ad.page.evaluate(() => document.querySelector('.aviso-local[data-aviso="enviar-fila-site"]').innerText));
    chk(/0 enviadas, 2 falharam, 2 ainda na fila/.test(fim) && /Enviadas: 0 · falharam: 2 · ainda na fila: 2/.test(fim), `resultado com a contagem (${fim})`);
    chk(/F075-P0001-1960-S01-D00001/.test(fim) && /F075-P0001-1960-S01-D00002/.test(fim) && /Escala:/.test(fim), 'a lista mostra cada folha que falhou, com o motivo');
    chk(posts === 1, `um clique = UMA chamada (${posts})`);
    await ad.page.waitForFunction(() => !document.getElementById('fila-site-enviar') && /esperam a próxima tentativa/.test((document.getElementById('fila-site') || {}).innerText || ''), null, { timeout: 15000 }).catch(() => {});
    const depois = so(await ad.page.evaluate(() => (document.getElementById('fila-site') || {}).innerText || ''));
    chk(await ad.page.$('#fila-site-enviar') === null && /2 correções de folhas esperando o site \(2 esperam a próxima tentativa/.test(depois), `depois: as que falharam esperam a próxima tentativa, sem botão (${depois})`);
    chk(py(`print(con.execute("SELECT COUNT(*) FROM fila_correcao_site WHERE ultimo_erro IS NOT NULL AND tentativas=1").fetchone()[0])`) === '2', 'no banco: as 2 continuam na fila com o motivo');
    chk(cfg('site.reenvio_persistente') === '0', 'site.reenvio_persistente continua 0');
    chk(py(`print(con.execute("SELECT COUNT(*) FROM evento WHERE tipo='site_correcoes_enviadas' AND ator='rafael@camp.arq.br'").fetchone()[0])`) === '1', 'Histórico de ações: um registro de quem mandou');
    await ad.page.evaluate(() => go('auditoria'));
    await ad.page.waitForFunction(() => /mandou ao site as correções e escritas que estavam esperando/.test(document.getElementById('v-auditoria').innerText), null, { timeout: 15000 }).catch(() => {});
    const au = so(await ad.page.evaluate(() => document.getElementById('v-auditoria').innerText));
    chk(/mandou ao site as correções e escritas que estavam esperando/.test(au) && /0 enviadas, 2 falharam, 2 ainda na fila/.test(au), 'o Histórico de ações mostra a frase e a contagem');
    await ad.ctx.close();
  } catch (e) { chk(false, 'exceção: ' + e.message); }
  chk(!erros.length, 'sem erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  chk(!falhas.filter(f => !/correcoes-pendentes\/enviar/.test(f)).length, 'sem resposta de erro inesperada' + (falhas.length ? ': ' + falhas.slice(0, 3).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
