// 15/11/2026 (Rafael, F002-P0147): despublicar projeto grande mostrava "Não foi possível alterar a publicação / A operação demorou demais".
// No navegador de verdade, com o WordPress FALSO lento: Despublicar vira tarefa (o chip do topo diz "Despublicando F096-P0001 · N de 8 folhas"),
// o 2º clique só acompanha a mesma tarefa, nenhuma gaveta "Não foi possível", no fim as folhas que falharam ficam listadas com
// "Tentar de novo só estas 2" (que repete SÓ elas) e, se o painel parar de esperar (60 s), a frase diz que a ação pode continuar.
// Uso (servidor PRÓPRIO com o WordPress FALSO numa porta 89xx, nunca a 8765 compartilhada nem o site de verdade):
//   CAMP_DB_PATH=/tmp/desp.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/desp.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 WP_FALSO_ESPERA_S=0.4 WP_FALSO_FALHA_1X=960003,960006 python3 ../tests/servidor_wp_falso.py 8990)
//   CAMP_DB_PATH=/tmp/desp.db CAMP_BASE=http://127.0.0.1:8990 node tests/navegador_despublicar_tarefa.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8990', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...args) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...args], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F096-P0001';
py(`
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F096','Fundo Grande','FGR',1)")
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES ('F096',1)")
con.execute("INSERT OR IGNORE INTO wp_item (id,colecao_id,status,titulo) VALUES (960000,8007,'publish','d')")
con.execute("INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,status_site,tainacan_item_id) VALUES ('${P}','F096',1,'Residência Grande',1975,'São Paulo','no_ar',960000)")
con.execute("DELETE FROM tarefa_publicacao WHERE projeto_codigo='${P}'")
for k in range(1, 9):
    con.execute("INSERT OR IGNORE INTO wp_item (id,colecao_id,status,titulo) VALUES (?,8013,'publish','f')", (960000 + k,))
    con.execute("INSERT OR IGNORE INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,origem,revisao,status_site,tainacan_item_id,pendencias) VALUES (?,?,'S01',?,?,'importado','conferida','no_ar',?,'{}')",
                ('${P}-1975-S01-D%05d' % k, '${P}', k, 'Planta %d' % k, 960000 + k))
`);
const contar = q => +py(`print(con.execute(${JSON.stringify(q)}).fetchone()[0])`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|site-falso\.invalid|\/previa\?|\/api\/teste-lento/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  const so = t => String(t || '').replace(/\s+/g, ' ').trim();
  const corpos = []; page.on('request', r => { if (r.method() === 'POST' && /\/api\/projetos\/F096-P0001\/(publicar|despublicar)/.test(r.url())) corpos.push(r.url().replace(BASE, '') + ' ' + (r.postData() || '')); });
  const confirmarSim = async () => { await page.waitForSelector('#conf-ov [data-conf="sim"]', { timeout: 8000 }); await page.click('#conf-ov [data-conf="sim"]'); };
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(p => nav('projeto/' + p), P);
    await page.waitForSelector('#pd', { timeout: 20000 }); await page.waitForTimeout(500);

    // ---- Despublicar (o mesmo botão "Despublicar…" do quadro de publicação) ----
    const t0 = Date.now();
    await page.evaluate(p => { publicarProjeto(p, 'tirar_do_ar'); }, P); await confirmarSim();
    await page.waitForFunction(() => /Despublicando F096-P0001 · \d+ de 8 folhas/.test((document.getElementById('tarefas-chip') || {}).textContent || ''), null, { timeout: 10000 });
    chk(true, 'o chip do topo mostra o andamento: "' + so(await page.textContent('#tarefas-chip')) + '"');
    chk(Date.now() - t0 < 8000, 'a tarefa aparece logo (sem esperar o site terminar as 9 chamadas lentas)');
    // 2º clique enquanto roda: acompanha a mesma tarefa, não despublica de novo
    await page.evaluate(p => { publicarProjeto(p, 'tirar_do_ar'); }, P); await confirmarSim();
    await page.waitForFunction(() => /Já está rodando/.test(document.getElementById('toast').textContent), null, { timeout: 8000 }).then(() => chk(true, '2º clique com a tarefa rodando: "Já está rodando: o andamento fica no topo da página."'), () => chk(false, '2º clique: não avisou que já está rodando'));
    chk(contar(`SELECT COUNT(*) FROM tarefa_publicacao WHERE projeto_codigo='${P}'`) === 1, 'e não criou outra tarefa (uma só no banco)');
    // fim: gaveta com as 2 que falharam, nunca "Não foi possível"
    await page.waitForFunction(() => /A publicação não foi concluída/.test((document.getElementById('d-title') || document.body).textContent || '') && document.querySelector('[data-pub-repetir]'), null, { timeout: 30000 });
    const gav = so(await page.textContent('#d-body'));
    chk(/F096-P0001-1975-S01-D00003/.test(gav) && /F096-P0001-1975-S01-D00006/.test(gav) && /504/.test(gav), 'no fim, a gaveta lista as 2 folhas que o site recusou e o motivo');
    chk(/Tentar de novo só estas 2/.test(gav), 'com o botão "Tentar de novo só estas 2"');
    const corpo = so(await page.innerText("body")), mm = corpo.match(/.{0,80}(Não foi possível (alterar|publicar)|demorou demais).{0,60}/i);   // (outras telas escondidas têm "Não foi possível carregar…": não é deste fluxo)
    chk(!mm, 'em nenhum momento aparece "Não foi possível alterar a publicação" nem "demorou demais"' + (mm ? ': …' + mm[0] : ''));
    chk(contar(`SELECT COUNT(*) FROM item WHERE projeto_codigo='${P}' AND status_site='fora_do_ar'`) === 6 && py(`print(con.execute("SELECT status_site FROM projeto WHERE codigo='${P}'").fetchone()[0])`) === 'fora_do_ar', 'estado: 6 folhas despublicadas, 2 ainda publicadas');
    // repetir só as que falharam
    corpos.length = 0;
    await page.click('[data-pub-repetir]');
    await page.waitForFunction(() => /2 registros? despublicad/.test(document.getElementById('toast').textContent + ' ' + ((document.getElementById('tarefas-chip') || {}).textContent || '')), null, { timeout: 20000 }).catch(() => {});
    await page.waitForTimeout(800);
    chk(corpos.length === 1 && /"somente":\["F096-P0001-1975-S01-D00003","F096-P0001-1975-S01-D00006"\]/.test(corpos[0]), 'o botão repete SÓ as que falharam (' + corpos.join(' | ') + ')');
    chk(contar(`SELECT COUNT(*) FROM item WHERE projeto_codigo='${P}' AND status_site<>'fora_do_ar'`) === 0, 'e agora todas as folhas estão despublicadas');
    chk(contar(`SELECT total FROM tarefa_publicacao WHERE projeto_codigo='${P}' ORDER BY id DESC LIMIT 1`) === 2, 'a 2ª tarefa só tinha as 2 folhas');

    // ---- se o painel parar de esperar (60 s) uma escrita: a frase diz que pode continuar, nunca "tente novamente" ----
    await page.route('**/api/teste-lento', () => {});   // nunca responde
    const r = await page.evaluate(async () => { const st = window.setTimeout; window.setTimeout = (f, ms, ...a) => st(f, ms >= 60000 ? 50 : ms, ...a);
      try { await API('/api/teste-lento', { method: 'POST' }); return { ok: true }; } catch (e) { return { st: e.status, msg: e.message }; } finally { window.setTimeout = st; } });
    chk(r.st === 408 && /pode continuar no servidor/.test(r.msg) && !/Tente novamente/.test(r.msg), 'escrita sem resposta em 60 s: "' + r.msg + '"');
    await page.evaluate(([p, m]) => erroPublicacao(p, 'tirar_do_ar', Object.assign(new Error(m), { status: 408 })), [P, r.msg]);
    const g2 = so(await page.textContent('#d-title')) + ' ' + so(await page.textContent('#d-body'));
    chk(/O painel parou de esperar a resposta/.test(g2) && !/Não foi possível/.test(g2) && /Ver a situação do projeto/.test(g2), 'e a gaveta não diz "Não foi possível": "' + g2.slice(0, 160) + '"');
  } catch (e) { chk(false, 'o teste quebrou: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma chamada da API falhou' + (falhas.length ? ': ' + falhas.slice(0, 4).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
