// CAMP-PROB-RAPIDO (22/11/2026): decisões rápidas na lista de Problemas, no navegador de verdade (Playwright + Chromium).
// Rafael: "Decisões simples e rápidas podem ser clicks aí mesmo para resolver, não?" Prova: os botões da linha resolvem e o número cai sem
// recarregar a lista; o Desfazer do aviso funciona; a linha do grupo com "Todas são deste projeto"; "Resolver em sequência" com as teclas 1/J/K/Esc
// e o avanço sozinho; a "Atividade recente" sem código interno; a linha não fica toda pintada; o topo não muda; nada passa de 390 px.
// Uso (servidor PRÓPRIO numa porta 89xx):
//   CAMP_DB_PATH=/tmp/x/pr.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x/pr.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8984)
//   CAMP_DB_PATH=/tmp/x/pr.db CAMP_BASE=http://127.0.0.1:8984 node tests/navegador_problemas_rapido.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8984', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// parecido com o print do Rafael: várias "folha pode ser de outro projeto" do MESMO projeto (idempotente)
py(`
if not con.execute("SELECT 1 FROM fundo WHERE codigo='F061'").fetchone():
    con.execute("INSERT INTO fundo (codigo,titulo) VALUES ('F061','Escritório Teste')")
P=[("F061-P0081",81,"Residência Teresa Martino",9),("F061-P0815",815,"Estação de Rádio",6),("F061-P0900",900,"Sierna 3 Bairro do Limão",1),("F061-P0901",901,"Edifício Piratininga",4)]
f=lambda c,n: "%s-1970-S01-D%05d"%(c,n)
for c,n,t,k in P:
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES ('F061',?)",(n,))
    con.execute("INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,ano) VALUES (?,?,?,?,1970)",(c,"F061",n,t))
    for i in range(1,k+1):
        con.execute("INSERT OR IGNORE INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,origem,revisao) VALUES (?,?,?,?,?,'importado','conferida')",(f(c,i),c,"S01",i,"Planta %d"%i))
if not con.execute("SELECT 1 FROM erro WHERE descricao LIKE '[rapido]%' LIMIT 1").fetchone():
    ins=lambda g,cat,cod,d,ori="campvision": con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,criado_em) VALUES (?,?,?,?,?,datetime('now','-24 days'))",(g,cat,ori,cod,'[rapido] '+d))
    for i in range(1,9): ins("bloqueia","projeto_errado",f("F061-P0081",i),"projeto divergente: o carimbo diz 'SIERNA 3 · BAIRRO DO LIMÃO' — fora da publicação até decisão")
    for i in range(1,6): ins("bloqueia","projeto_errado",f("F061-P0815",i),"sem identificação: pasta com várias obras e a folha não diz de qual é")
    ins("bloqueia","projeto_errado",f("F061-P0901",1),"projeto divergente: o carimbo diz 'ESTAÇÃO DE RÁDIO' — fora da publicação até decisão")
    ins("bloqueia","autoria_divergente",f("F061-P0901",2),"Carimbo de outro escritório")
    ins("corrigir","metadado",f("F061-P0901",3),"Documento sem data identificada","operador")
    con.execute("INSERT INTO evento (entidade,codigo,tipo,ator) SELECT 'erro',CAST(MAX(id) AS TEXT),'fechado_na_conferencia','painel (automático)' FROM erro")
`);
const P0081 = (n) => `F061-P0081-1970-S01-D${String(n).padStart(5, '0')}`;
const idDe = (cod) => +py(`print(con.execute("SELECT id FROM erro WHERE codigo=? AND descricao LIKE '[rapido]%'", ("${cod}",)).fetchone()[0])`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const nova = async (w, h) => { const ctx = await browser.newContext({ viewport: { width: w, height: h } }); const page = await ctx.newPage();
    page.on('pageerror', e => erros.push(e.message)); page.on('dialog', d => d.dismiss().catch(() => {}));
    await page.goto(BASE + '/'); await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await page.waitForTimeout(600); return { ctx, page }; };
  const RN = new WeakMap();
  const espera = async (page) => { const n0 = RN.get(page) || 0; await page.waitForFunction(n => +(document.getElementById('err-body').dataset.render || 0) > n && document.getElementById('err-body').getAttribute('aria-busy') === 'false', n0, { timeout: 15000 });
    RN.set(page, await page.$eval('#err-body', el => +el.dataset.render)); };
  const cnt = (page) => page.$eval('#err-cnt', el => +el.textContent.replace(/\D/g, '') || 0);
  const crit = (page) => page.$eval('[data-cp-cartao="criticos"] .cp-c-n', el => +el.textContent.replace(/\D/g, ''));
  try {
    const { ctx, page } = await nova(1366, 900);
    await page.goto(BASE + '/#projetos'); await page.waitForTimeout(1200);
    const topo = () => page.evaluate(() => { const t = document.querySelector('.top'); const f = el => el.tagName + '#' + (el.id || '') + '.' + [...el.classList].sort().join('.') + '[' + [...el.children].map(f).join(',') + ']'; return t ? f(t) : null; });
    const topoAntes = await topo();
    // linhas soltas (sem agrupar), só críticos
    await page.goto(BASE + '/#erros/~aba=todos&chip=critico&agrupar=0'); await espera(page);
    chk(topoAntes && topoAntes === await topo(), 'o topo (usuário, situação, temperatura) é o mesmo em Projetos e em Problemas');
    await page.waitForSelector('#cp-lateral .cp-ativ'); await page.waitForTimeout(400);
    const at0 = await page.$eval('#cp-lateral', el => [...el.querySelectorAll('.cp-ativ li')].map(l => l.textContent).join(' | '));
    chk(/Resolvido na conferência/.test(at0) && !/Fechado_na_conferencia|fechado_na_conferencia/i.test(at0), `Atividade recente: "Resolvido na conferência", nunca "Fechado_na_conferencia" (${at0.slice(0, 120)})`);
    const cor = await page.evaluate(() => { const l = document.querySelector('#err-body .cp-linha.sev-critico'); const t = document.createElement('div'); t.style.background = 'var(--surface)'; document.body.appendChild(t);
      const s = getComputedStyle(t).backgroundColor; t.remove(); return l ? { bg: getComputedStyle(l).backgroundColor, s, borda: getComputedStyle(l).borderLeftColor, outra: getComputedStyle(l).borderTopColor } : null; });
    chk(cor && cor.bg === cor.s && cor.borda !== cor.outra, `linha crítica branca; só a borda esquerda (e a pílula) com a cor (${JSON.stringify(cor)})`);
    chk(!(await page.$('#err-body .cp-razao')) && await page.$eval('#err-body .cp-linha.sev-critico .cp-sev-tag', el => /Prioridade/.test(el.title || '')), 'a frase da prioridade saiu da linha e foi para a dica da pílula');
    const id1 = idDe(P0081(1));
    const n0 = await cnt(page), c0 = await crit(page);
    const linha1 = `#err-body [data-err-linha="${id1}"]`;
    chk(await page.$eval(`${linha1} .cp-rap`, el => /SIERNA 3/.test(el.textContent) && /Residência Teresa Martino/.test(el.textContent)), 'a linha mostra o que o carimbo diz ao lado do projeto atual');
    chk(!!(await page.$(`${linha1} [data-cp-r="mover"][data-cp-destino="F061-P0900"]`)), 'admin vê "Mover para" o projeto que combina com o carimbo');
    const r0 = await page.$eval('#err-body', el => +el.dataset.render);
    await page.click(`${linha1} [data-cp-r="deste_projeto"]`);
    await page.waitForFunction(s => !document.querySelector(s), linha1, { timeout: 10000 });
    await page.waitForTimeout(900);
    chk(await cnt(page) === n0 - 1 && await crit(page) === c0 - 1, `"É deste projeto" na linha: a linha sai, a lista e o cartão Críticos caem 1 (${n0}→${await cnt(page)}, ${c0}→${await crit(page)})`);
    chk(await page.$eval('#err-body', el => +el.dataset.render) === r0, 'sem recarregar a lista (a lista não foi desenhada de novo)');
    chk(py(`print(con.execute("SELECT situacao||'|'||fase FROM erro WHERE id=${id1}").fetchone()[0])`) === 'corrigido|resolvido', 'no banco: Resolvido');
    chk(await page.$eval('#toast', el => el.classList.contains('on') && /^Resolvido\.\s*Desfazer$/.test(el.textContent.trim())), `aviso curto e neutro: "Resolvido. Desfazer" (${await page.$eval('#toast', el => el.textContent)})`);
    await page.click('#toast .toast-acao'); await espera(page); await page.waitForTimeout(500);
    chk(!!(await page.$(linha1)) && await cnt(page) === n0 && py(`print(con.execute("SELECT situacao FROM erro WHERE id=${id1}").fetchone()[0])`) === 'aberto', 'Desfazer: o problema volta para a lista e o número volta');
    // "Não é problema…" do ⋯ não aparece em tipo sensível
    const idAut = idDe('F061-P0901-1970-S01-D00002');
    chk(!(await page.$(`#err-body [data-err-linha="${idAut}"] .cp-rap`)) && !(await page.$(`#err-body [data-err-linha="${idAut}"] [data-cp-r="nao"]`)), 'autoria (sensível): nenhuma decisão rápida na linha');
    // grupo
    await page.goto(BASE + '/#erros/~aba=todos&chip=critico'); await espera(page);
    const g = '#err-body [data-cp-grupo^="F061-P0081|projeto_errado"]';
    chk(await page.$eval(g, el => /Residência Teresa Martino · 8 folhas podem ser de outro projeto/.test(el.textContent)), 'grupo: "Residência Teresa Martino · 8 folhas podem ser de outro projeto"');
    const n1 = await cnt(page);
    chk(n1 === n0, `agrupado, o total continua contando problemas (${n1} = ${n0})`);
    await page.click(`${g} [data-cp-g="deste_projeto"]`);
    await page.click(`${g} [data-cp-deste-ok]`);
    await page.waitForFunction(s => !document.querySelector(s), g, { timeout: 10000 }); await page.waitForTimeout(900);
    chk(await cnt(page) === n1 - 8, `"Todas são deste projeto": a linha do grupo sai e o número cai 8 (${n1}→${await cnt(page)})`);
    chk(+py(`print(con.execute("SELECT COUNT(*) FROM erro WHERE codigo LIKE 'F061-P0081-%' AND descricao LIKE '[rapido]%' AND situacao='corrigido' AND fase='resolvido'").fetchone()[0])`) === 8, 'no banco: as 8 resolvidas');
    // Resolver em sequência
    await page.goto(BASE + '/#erros/~aba=todos&chip=critico&agrupar=0'); await espera(page);
    await page.click('[data-cp-seq]'); await page.waitForSelector('#cp-tri [data-cp-tri-id]');
    const prog = () => page.$eval('#cp-tri-prog', el => el.textContent);
    chk(/^1 de \d+/.test(await prog()), `progresso "1 de N" (${await prog()})`);
    let tent = 0;
    while (!(await page.$('#cp-tri [data-cp-tri-op="1"]')) && tent++ < 10) { await page.keyboard.press('j'); await page.waitForTimeout(200); }
    const antes = await page.$eval('#cp-tri [data-cp-tri-id]', el => +el.dataset.cpTriId);
    const hashAntes = await page.evaluate(() => location.hash);
    await page.keyboard.press('1');
    await page.waitForFunction(a => { const el = document.querySelector('#cp-tri [data-cp-tri-id]'); return !el || +el.dataset.cpTriId !== a; }, antes, { timeout: 10000 });
    chk(py(`print(con.execute("SELECT situacao FROM erro WHERE id=${antes}").fetchone()[0])`) === 'corrigido' && /^\d+ de \d+$/.test((await prog()).trim()), `tecla 1 resolve e avança sozinho; o progresso é só "N de M" (${await prog()})`);
    chk(await page.evaluate(() => location.hash) === hashAntes, 'a tecla 1 não foi para "Precisa de você" (as teclas do menu não valem na sequência)');
    const atual = await page.$eval('#cp-tri [data-cp-tri-id]', el => +el.dataset.cpTriId);
    await page.keyboard.press('j'); await page.waitForTimeout(250);
    const prox = await page.$eval('#cp-tri [data-cp-tri-id]', el => +el.dataset.cpTriId);
    await page.keyboard.press('k'); await page.waitForTimeout(250);
    chk(prox !== atual && await page.$eval('#cp-tri [data-cp-tri-id]', el => +el.dataset.cpTriId) === atual, 'J pula para a próxima e K volta');
    await page.keyboard.press('Escape'); await page.waitForTimeout(400);
    chk(!(await page.$('#cp-tri')), 'Esc sai da sequência');
    await espera(page).catch(() => {});
    // Atividade recente sem código interno
    await page.waitForSelector('#cp-lateral .cp-ativ'); await page.waitForTimeout(400);
    const at = await page.$eval('#cp-lateral', el => [...el.querySelectorAll('.cp-ativ li')].map(l => l.textContent).join(' | '));
    chk(at && !/[a-z]+_[a-z]+/i.test(at), `Atividade recente sem código de evento depois das ações rápidas (${at.slice(0, 160)})`);
    // celular
    const m = await nova(390, 844);
    await m.page.goto(BASE + '/#erros/~aba=todos&chip=critico'); await espera(m.page); await m.page.waitForTimeout(600);
    const larg = await m.page.evaluate(() => document.documentElement.scrollWidth);
    chk(larg <= 390, `390 px: nada passa da largura (${larg})`);
    await m.ctx.close(); await ctx.close();
  } catch (e) { chk(false, 'exceção: ' + (e && e.stack || e)); }
  chk(!erros.length, 'nenhum erro de JavaScript' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
