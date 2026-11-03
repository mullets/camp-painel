// UX-73 (Rafa: "Quero que possa publicar como está. Só precisa avisar que falta x ou h coisas serem feitas, como objetivos em uma gamificação";
// e "deixar bem claro como faz pro tipo, modalidade, nova obra e etc quando vai aprovar o lote"). Playwright + Chromium de verdade,
// servidor PRÓPRIO (porta 8974). Com publicacao.exige_conferencia = 0 (padrão):
//  A) projeto não publicado, lote com 6 folhas a conferir e sem tipo/natureza/modalidade: o cartão Site e o bloco "Próximo passo" têm
//     "Publicar como está" ATIVO; o quadro "Objetivos do projeto" tem a barra de progresso (N de M) igual ao servidor e
//     "Falta conferir 6 folhas"; o botão da meta "tipo da obra" abre a edição do projeto já no campo Programa / uso;
//     o botão da meta "conferir" abre a folha a conferir; a Revisão do lote mostra os dados que faltam; a lista de Projetos tem o selo
//     "objetivos N/M"; em 390 px não há rolagem lateral.
// Uso:
//   CAMP_DB_PATH=/tmp/ux73.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux73.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8974)
//   CAMP_DB_PATH=/tmp/ux73.db CAMP_BASE=http://127.0.0.1:8974 CHROME=/opt/pw-browsers/chromium node tests/navegador_ux73_metas.js
// Prints (opcional): PRINTS=/pasta → ux73_1366.png e ux73_390.png
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8974', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const PRINTS = process.env.PRINTS || '';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const A = 'F003-P9731';
py(`
con.execute("UPDATE configuracao SET valor='0' WHERE chave='publicacao.exige_direitos'")
con.execute("UPDATE configuracao SET valor='0' WHERE chave='publicacao.exige_conferencia'")
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F003', 9731)")
con.execute("INSERT OR IGNORE INTO projeto (codigo, fundo_codigo, numero, titulo, ano, cidade) VALUES ('${A}', 'F003', 9731, 'Teatro Municipal de Piracicaba', 1975, 'Piracicaba')")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('${A} - Teatro', '${A}', '/nao/existe/ux73', 'revisao')").lastrowid
for k in range(1, 7):
    con.execute("INSERT OR IGNORE INTO item (codigo, projeto_codigo, serie_codigo, sequencial, titulo, tipo_documento, origem, lote_id, revisao) VALUES (?,?,?,?,?,?,'campvision',?,'pendente')",
                ('${A}-1975-S01-D%05d' % k, '${A}', 'S01', k, 'Planta %d' % k, 'Planta', lid))
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|\/previa|\/miniatura|folhas-qnap\/arquivo|exemplo\.test|\/imagem/.test(u);
  const entrar = async (w, h) => {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const page = await ctx.newPage();
    page.on('console', m => { if (m.type() === 'error' && !ESPERADO((m.location() || {}).url || '')) erros.push(m.text() + ' @' + ((m.location() || {}).url || '')); });
    page.on('pageerror', e => erros.push('pageerror: ' + e.message));
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    for (const sel of ['.ajuda-caixa [data-ajuda-fechar]', '[data-faixa-fechar]']) { const b = await page.$(sel); if (b && await b.isVisible()) { await b.click(); await page.waitForTimeout(300) } }
    return { ctx, page };
  };
  const abrir = async (page, c) => { await page.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, c);
    await page.waitForFunction(c => window.PUB_G && PUB_G[c] && document.querySelector('#pj-cards .pjc[data-pjc="site"]') && !/…/.test(document.querySelector('#pj-cards .pjc[data-pjc="site"] .pjc-v').textContent)
, c, { timeout: 15000 });
    await page.waitForSelector('#pj-status .metas', { timeout: 5000 }).catch(() => {}); await page.waitForTimeout(1200) };
  try {
    const { ctx, page } = await entrar(1366, 900);
    await abrir(page, A);
    // 1) Publicar disponível com metas abertas
    const sa = await page.$eval('#pj-cards .pjc[data-pjc="site"]', c => c.innerText.replace(/\s+/g, ' ').trim());
    const pubCartao = await page.$('#pj-cards .pjc[data-pjc="site"] [data-pjc-publicar]:not([aria-disabled="true"])');
    chk(!!pubCartao && /Publicar como está/.test(await pubCartao.textContent()) && /publicar como está/.test(sa), '(A) cartão Site: "Publicar como está" ativo: "' + sa + '"');
    const pubBloco = await page.$('#pj-status [data-pjs-publicar]');
    chk(!!pubBloco && !(await pubBloco.isDisabled()) && /Publicar como está/.test(await pubBloco.textContent()), '(A) bloco Próximo passo: "Publicar como está" habilitado ("' + (pubBloco ? (await pubBloco.textContent()).trim() : '—') + '")');
    // 2) quadro de objetivos: barra de progresso igual ao servidor
    const srv = await page.evaluate(c => fetch('/api/projetos/' + c + '/publicacao').then(r => r.json()).then(j => j.metas), A);
    const q = await page.evaluate(() => { const s = document.querySelector('#pj-status .metas'); if (!s) return { cont: '(sem quadro de objetivos)', conferir: '' };
      return { v: +s.querySelector('progress.mt-barra').value, max: +s.querySelector('progress.mt-barra').max, cont: s.querySelector('.mt-cont').innerText.replace(/\s+/g, ' '),
        conferir: (s.querySelector('[data-meta="conferir"]') || {}).innerText || '', ok: s.querySelectorAll('.mt-item.feito').length, itens: s.querySelectorAll('.mt-item').length } });
    chk(srv && q.v === srv.feitas && q.max === srv.total && q.cont.includes(`${srv.feitas} de ${srv.total} objetivos`) && q.ok === srv.feitas && q.itens === srv.total,
      `(A) barra de progresso "${q.cont}" = servidor ${srv && srv.feitas}/${srv && srv.total} (${q.ok} com ✓)`);
    chk(/Falta conferir 6 folhas/.test(q.conferir) && /0 de 6/.test(q.conferir) && /Conferir as folhas/.test(q.conferir), '(A) meta "Falta conferir 6 folhas" (0 de 6) com botão: "' + q.conferir.replace(/\s+/g, ' ') + '"');
    const plano = await page.evaluate(c => fetch('/api/projetos/' + c + '/publicar/plano').then(r => r.json()), A);
    chk(plano.pode_executar === true && !(plano.bloqueios || []).length && plano.folhas_a_publicar === 6, '(A) o plano do Publicar não tem bloqueio e leva as 6 folhas não conferidas');
    if (PRINTS) await page.screenshot({ path: PRINTS + '/ux73_1366.png', fullPage: false });
    // 3) o botão da meta "tipo da obra" leva ao campo certo
    const b3 = await page.$('#pj-status .metas [data-meta="programa"] [data-pp-cond]'); if (b3) await b3.click();
    await page.waitForFunction(() => { const d = document.querySelector('#drawer details[data-tp-col="tipologia"]'); return d && d.open }, null, { timeout: 8000 }).catch(() => {});
    const campo = await page.evaluate(() => { const d = document.querySelector('#drawer details[data-tp-col="tipologia"]'); return { aberto: !!(d && d.open), realce: !!(d && d.classList.contains('realce')) } });
    chk(!!b3 && campo.aberto && campo.realce, '(A) "Escolher o tipo" abre a edição do projeto no campo Programa / uso (aberto e realçado)');
    await page.evaluate(() => closeDrawer(true)); await page.waitForTimeout(800);
    // 4) o botão da meta "conferir" abre a folha a conferir
    await page.waitForSelector('#pj-status .metas [data-meta="conferir"] [data-pp-cond]', { timeout: 8000 }).catch(() => {});
    const b4 = await page.$('#pj-status .metas [data-meta="conferir"] [data-pp-cond]'); if (b4) await b4.click();
    await page.waitForFunction(() => /D0000\d/.test((document.getElementById('drawer') || {}).innerText || '') || /conferir/.test(location.hash), null, { timeout: 8000 }).catch(() => {});
    const conf = await page.evaluate(() => ({ t: ((document.getElementById('drawer') || {}).innerText || '').slice(0, 200), h: location.hash }));
    chk(!!b4 && (/D0000\d/.test(conf.t) || /conferir/.test(conf.h)), '(A) "Conferir as folhas" abre a folha a conferir ("' + conf.t.replace(/\s+/g, ' ').slice(0, 70) + '")');
    await page.evaluate(() => closeDrawer(true)); await page.waitForTimeout(500);
    // 5) Revisão do lote: os dados do projeto que faltam, com botão
    await abrir(page, A);
    await page.evaluate(c => { const b = document.querySelector(`[data-pjc-gav="folhas"][data-codigo="${c}"]`) || document.querySelector('[data-pjc-gav="folhas"]'); if (b) b.click() }, A);
    await page.waitForFunction(() => { const r = document.querySelector('#pj-revisao [data-rev-dados]'); return r && /tipo da obra/.test(r.innerText) }, null, { timeout: 8000 }).catch(() => {});
    const rev = await page.evaluate(() => { const r = document.querySelector('#pj-revisao [data-rev-dados]'); return r ? { t: r.innerText, bt: !!r.querySelector('[data-pp-cond="editar_projeto"]') } : null });
    chk(!!rev && /Falta dizer o tipo da obra/.test(rev.t) && /natureza do trabalho/.test(rev.t) && /modalidade/.test(rev.t) && rev.bt, '(A) Revisão do lote: "Dados do projeto que faltam" com tipo, natureza e modalidade e o botão para preencher');
    // 6) lista de Projetos: selo "objetivos N/M"
    await page.evaluate(() => nav('projetos')); await page.waitForTimeout(400);
    await page.evaluate(c => carregarProjetosAPI({ q: c }), A);
    await page.waitForFunction(c => document.querySelector(`#projetos-body tr[data-nav="projeto/${c}"]`), A, { timeout: 10000 }).catch(() => {});
    const selo = await page.evaluate(c => { const tr = document.querySelector(`#projetos-body tr[data-nav="projeto/${c}"] .mt-selo`); return tr ? tr.textContent : '' }, A);
    chk(srv && selo === `objetivos ${srv.feitas}/${srv.total}`, '(A) lista de Projetos: selo "' + selo + '"');
    await ctx.close();
    // 7) celular (390 px): sem rolagem lateral, quadro de objetivos e Publicar visíveis
    const m = await entrar(390, 844);
    await abrir(m.page, A);
    const larg = await m.page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
      metas: (() => { const s = document.querySelector('#pj-status .metas'); if (!s) return null; const r = s.getBoundingClientRect(); return { l: r.left, r: r.right } })() }));
    chk(larg.sw <= larg.cw + 1, `(390 px) sem rolagem lateral (scrollWidth ${larg.sw} × ${larg.cw})`);
    chk(!!larg.metas && larg.metas.l >= 0 && larg.metas.r <= larg.cw + 1, '(390 px) o quadro de objetivos cabe na tela ' + JSON.stringify(larg.metas));
    const pub390 = await m.page.$('#pj-status [data-pjs-publicar]');
    chk(!!pub390 && !(await pub390.isDisabled()), '(390 px) "Publicar como está" habilitado');
    if (PRINTS) { await m.page.$eval('#pj-status', e => e.scrollIntoView()); await m.page.screenshot({ path: PRINTS + '/ux73_390.png', fullPage: false }) }
    await m.ctx.close();
  } catch (e) { problemas.push('exceção: ' + e.message); linhas.push('FALHA exceção: ' + e.message) }
  chk(!erros.length, 'nenhum erro no console: ' + erros.slice(0, 3).join(' | '));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
