// CAMP-FIX 15/11/2026 (Rafael, Máquinas): "Ver as 48 que falharam" e "6 desligadas (normal)" abriam listas com bolinhas VAZIAS.
// Navegador de verdade (Playwright + Chromium). Prova: ao abrir cada lista recolhida, cada item mostra o seu texto (código + motivo;
// nome da máquina + frase), visível na tela (não só no DOM).
// Uso (servidor PRÓPRIO numa porta 89xx, site inexistente para as correções falharem):
//   CAMP_DB_PATH=/tmp/lr.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/lr.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8994)
//   CAMP_DB_PATH=/tmp/lr.db CAMP_BASE=http://127.0.0.1:8994 node tests/navegador_listas_recolhidas.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8994', DB = process.env.CAMP_DB_PATH;
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\ncon.row_factory=sqlite3.Row\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
// 12 folhas no site com uma correção de verdade (escala) esperando: o site não responde, as 12 falham (mais de 10: a lista vem recolhida)
py(`base=dict(con.execute("SELECT * FROM item WHERE tainacan_item_id IS NOT NULL AND status_site IN ('no_ar','rascunho') LIMIT 1").fetchone())
con.execute("UPDATE configuracao SET valor='1' WHERE chave='site.enviar_correcoes_sozinho'")
for k in range(12):
    cod=base['codigo'][:-5]+'%05d'%(90000+k)
    if con.execute("SELECT 1 FROM item WHERE codigo=?",(cod,)).fetchone(): continue
    d=dict(base); d['codigo']=cod; d['sequencial']=90000+k; d['tainacan_item_id']=880000+k; d['escala']='1:50'
    cols=[c for c in d if c not in ('id',)]
    con.execute(f"INSERT INTO item ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",[d[c] for c in cols])
    con.execute("INSERT INTO evento (entidade,codigo,tipo,ator,detalhe) VALUES ('item',?,'site_item_criado','x','{}')",(cod,))
    con.execute("UPDATE item SET escala='1:100' WHERE codigo=?",(cod,))
    con.execute("INSERT INTO evento (entidade,codigo,tipo,ator,detalhe) VALUES ('item',?,'editado','x',?)",(cod,json.dumps({"antes":{"escala":"1:50"}})))`);
const DOMINGO_NOITE = new Date('2026-10-25T22:00:00');   // fora do horário de trabalho: as máquinas desligadas ficam recolhidas

(async () => {
  const browser = await chromium.launch();
  const erros = [];
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  await ctx.route('**/*', rt => rt.request().url().startsWith(BASE) ? rt.continue() : rt.fulfill({ status: 200, contentType: 'text/css', body: '' }));
  const page = await ctx.newPage();
  await page.clock.setFixedTime(DOMINGO_NOITE);
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  // o texto de cada item da lista, como aparece na tela (innerText vazio = bolinha vazia)
  const itens = sel => page.evaluate(s => { const d = document.querySelector(s); if (!d) return null; d.open = true;
    return [...d.querySelectorAll('li')].map(li => ({ t: li.innerText.trim(), h: li.getBoundingClientRect().height })); }, sel);
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => go('estacoes'));
    await page.waitForSelector('#est-hoje', { timeout: 30000 }); await page.waitForTimeout(2500);
    const desl = await itens('#est-desligadas');
    chk(desl && desl.length > 0 && desl.every(x => x.t.length > 3 && x.h > 4), '"N desligadas (normal)": cada máquina aparece com o nome e a frase: ' + JSON.stringify(desl));
    await page.waitForSelector('#fila-site-enviar', { timeout: 20000 });
    await page.click('#fila-site-enviar');
    await page.click('.modal button.pri, .modal .btn.pri', { timeout: 5000 }).catch(async () => { await page.getByRole('button', { name: 'Enviar agora' }).click(); });
    await page.waitForFunction(() => { const a = document.querySelector('.aviso-local[data-aviso="enviar-fila-site"]'); return a && !a.classList.contains('rodando'); }, null, { timeout: 60000 });
    const fal = await itens('.aviso-local[data-aviso="enviar-fila-site"] details');
    chk(fal && fal.length >= 11 && fal.every(x => x.t.length > 10 && x.h > 4), '"Ver as N que falharam": cada item tem o código e o motivo: ' + JSON.stringify((fal || []).slice(0, 3)));
    // o mesmo resultado no cartão da tarefa (Tarefas e avisos recentes)
    await page.evaluate(() => abrirTarefas()); await page.waitForTimeout(1500);
    const card = await page.evaluate(() => [...document.querySelectorAll('#d-body .tarefa-card .dec-motivos li')].map(li => li.innerText.trim()));
    chk(card.length > 0 && card.every(t => t.length > 3), 'cartão da tarefa: as falhas aparecem com texto: ' + JSON.stringify(card.slice(0, 3)));
    chk(!erros.length, 'nenhum erro de página: ' + erros.join(' | '));
  } catch (e) { chk(false, 'exceção: ' + e.message); }
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
