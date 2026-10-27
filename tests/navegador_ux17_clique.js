// UX-17 (P2) no navegador de verdade: clique duplo em Publicar/Importar não faz a ação 2×.
// Caso do card: "Rafael publicou F009-P0019" 2× às 16:16. Prova: o Próximo passo diz o que muda antes do clique ("ao publicar, 3 folhas
// ficam públicas na hora"); dois cliques seguidos em "Publicar 3 folhas" = UMA chamada; o botão apaga na hora e diz "Publicando…";
// o resultado é "Publicado ✓ · 3 folhas públicas" com "Desfazer"; o site falso recebe UMA publicação; na Home, dois cliques em "Importar"
// = UMA chamada, com o botão apagado dizendo "Importando…"; nenhum erro no console.
// Uso (servidor PRÓPRIO com o WordPress FALSO numa porta 89xx, nunca a 8765 compartilhada nem o site de verdade):
//   CAMP_DB_PATH=/tmp/ux17.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux17.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 ../tests/servidor_wp_falso.py 8950)
//   CAMP_DB_PATH=/tmp/ux17.db CAMP_BASE=http://127.0.0.1:8950 node tests/navegador_ux17_clique.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8950', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...args) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...args], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// F074-P0001: 3 folhas conferidas, lote aprovado, fundo com direitos autorizados (pronto para publicar).
// F074-P0002: lote que chegou e falta importar (a pasta não existe: a importação responde erro, o que importa aqui é quantas vezes é chamada).
py(`
con.execute("UPDATE lista_processamento SET descartado_em=datetime('now') WHERE projeto_codigo NOT LIKE 'F074-%' AND descartado_em IS NULL")
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F074','Fundo Clique','FCL',1)")
con.execute("INSERT OR IGNORE INTO direitos_fundo (fundo_codigo,situacao,titular,documento_autorizacao) VALUES ('F074','autorizado','Família','Termo')")
con.execute("INSERT OR REPLACE INTO configuracao (chave,valor,descricao,sensivel) VALUES ('site.publicar_arquiteto_junto','0','x',0)")
for n, t in ((1, 'Residência Clique'), (2, 'Casa Importar')):
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES ('F074',?)", (n,))
    con.execute("INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,autorizado_site) VALUES (?,'F074',?,?,1975,'São Paulo',1)", ('F074-P%04d' % n, n, t))
con.execute("DELETE FROM evento WHERE codigo LIKE 'F074-%'")
con.execute("DELETE FROM item WHERE projeto_codigo LIKE 'F074-%'")
con.execute("DELETE FROM lista_processamento WHERE projeto_codigo LIKE 'F074-%'")
con.execute("UPDATE projeto SET status_site='nao_publicado', tainacan_item_id=NULL WHERE codigo LIKE 'F074-%'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, aprovado_em, aprovado_por) VALUES ('Residência Clique','F074-P0001','/x/F074-P0001','revisao',datetime('now'),'rafael@camp.arq.br')").lastrowid
for k in (1, 2, 3):
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,origem,revisao,status_site,lote_id,tipo_documento) VALUES (?,?,'S01',?,?,'campvision','conferida','nao_publicado',?,'Planta')",
                ('F074-P0001-1975-S01-D%05d' % k, 'F074-P0001', k, 'Planta %d' % k, lid))
con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, resultado) VALUES ('Casa Importar','F074-P0002','/x/nao-existe/F074-P0002','revisao','{\\"origem\\": \\"campvision2\\"}')")
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|site-falso\.invalid|\/previa\?|\/importar$/.test(u);   // a importação de propósito sem pasta
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  const so = t => String(t || '').replace(/\s+/g, ' ').trim();
  const posts = { publicar: 0, importar: 0 };
  page.on('request', r => { if (r.method() !== 'POST') return; if (/\/api\/projetos\/F074-P0001\/publicar-tudo/.test(r.url())) posts.publicar++; if (/\/api\/lotes\/\d+\/importar$/.test(r.url())) posts.importar++; });
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });

    // ---- Publicar no projeto ----
    await page.evaluate(() => nav('projeto/F074-P0001'));
    await page.waitForSelector('#pj-status [data-pjs-publicar]:not([disabled])', { timeout: 20000 }); await page.waitForTimeout(300);
    const antes = so(await page.textContent('#pj-status'));
    chk(/Publicar 3 folhas/.test(antes) && /ao publicar, 3 folhas ficam públicas na hora/.test(antes), 'antes do clique, o Próximo passo diz o que muda ("ao publicar, 3 folhas ficam públicas na hora"): "' + antes.slice(0, 220) + '"');
    const estadoNoClique = await page.evaluate(() => { const b = document.querySelector('#pj-status [data-pjs-publicar]'); b.click(); b.click(); const x = document.querySelector('#pj-status .pjs-pub'); return { dis: !!(x && x.disabled), txt: x ? x.textContent : '' }; });
    chk(estadoNoClique.dis && /Publicando/.test(estadoNoClique.txt), 'o botão apaga na hora e diz "Publicando…" (' + JSON.stringify(estadoNoClique) + ')');
    await page.waitForFunction(() => /Publicado ✓|Não terminou/.test((document.querySelector('#pj-status') || {}).textContent || ''), null, { timeout: 30000 });
    const depois = so(await page.textContent('#pj-status'));
    chk(/Publicado ✓ · 3 folhas públicas/.test(depois), 'resultado com o resumo: "Publicado ✓ · 3 folhas públicas": "' + depois.slice(0, 220) + '"');
    chk((await page.locator('#pj-status [data-pjs-desfazer]').count()) === 1, 'logo depois de publicar, "Desfazer" (voltar para rascunho) em 1 clique');
    const nPub = +py(`print(con.execute("SELECT COUNT(*) FROM evento WHERE entidade='projeto' AND codigo='F074-P0001' AND tipo='site_publicar'").fetchone()[0])`);
    chk(posts.publicar === 1 && nPub === 1, `dois cliques seguidos em Publicar = UMA chamada e UMA publicação (chamadas ${posts.publicar}, publicações ${nPub})`);

    // ---- Importar na Home ----
    await page.route('**/api/lotes/*/importar', async r => { await new Promise(x => setTimeout(x, 1200)); await r.continue(); });
    await page.evaluate(() => nav('painel'));
    await page.waitForSelector('#ini-tarefas .ini-task', { timeout: 15000 }); await page.waitForTimeout(400);
    const linhaImp = page.locator('#ini-tarefas .ini-task').filter({ hasText: 'F074-P0002' });
    chk((await linhaImp.count()) === 1, 'Home: o lote para importar aparece');
    const bImp = linhaImp.first().locator('[data-ini-acao]');
    const noClique = await bImp.evaluate(b => { b.click(); b.click(); return { dis: b.disabled, txt: b.textContent }; });
    chk(noClique.dis && /Importando/.test(noClique.txt), 'Home: o botão Importar apaga na hora e diz "Importando…" (' + JSON.stringify(noClique) + ')');
    await page.waitForTimeout(2500);
    chk(posts.importar === 1, `Home: dois cliques seguidos em Importar = UMA chamada (${posts.importar})`);
  } catch (e) { chk(false, 'o teste quebrou: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma chamada da API falhou' + (falhas.length ? ': ' + falhas.slice(0, 4).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
