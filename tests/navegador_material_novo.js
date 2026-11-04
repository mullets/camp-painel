// Redesenho da tela "Material novo" (documento do Rafael, 04/11/2026, §4–7 e §10–13), no navegador de verdade (Playwright + Chromium).
// Critérios de aceite da §13 que cabem à tela:
//  [A] a próxima ação de cada lote se reconhece sem abrir a linha (o botão é a etapa atual e respeita o papel; nunca "Conferir" universal)
//  [B] achar um projeto por nome ou código (sem acento, código parcial com zeros, com ou sem hífen)
//  [C] cartões, abas e menu da MESMA fonte (contagens.py / /api/pendencias); as situações não se sobrepõem
//  [D] filtros combinados, ordenação e paginação ("Mostrando 1–25 de N") funcionam; voltar do projeto restaura filtros e página
//  [E] o progresso diz o que mede (arquivos recebidos × folhas conferidas × aprovação); 100% de arquivos não vira "pronto"
//  [F] o que existia continua: Varrer QNAP, Novo lote, Importar todas, Parado há, Verificar destino pelo painel (Ferramentas avançadas),
//      pasta no QNAP, caminho dos 7 passos, histórico — e nada é gravado por filtrar ou abrir detalhes
//  [G] teclado (detalhe abre com Enter, nomes acessíveis), celular (cartões, sem rolagem lateral), zoom 200%, status não só por cor
//  [H] desempenho: 2.000 lotes a mais e a tela só desenha a página
//  [I] miniatura só de imagem do próprio lote, com loading=lazy; autoria só a registrada no projeto
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/x/m.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x/m.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8984)
//   CAMP_DB_PATH=/tmp/x/m.db CAMP_BASE=http://127.0.0.1:8984 node tests/navegador_material_novo.js
const { execFileSync } = require('child_process');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8984', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...a) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...a], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
execFileSync('python3', [path.join(__dirname, 'fixtures', 'material_novo_semente.py'), DB], { stdio: 'ignore' });
const foto = () => py("print(json.dumps([con.execute('SELECT COUNT(*), COALESCE(SUM(etapa=\\'revisao\\'),0) FROM lista_processamento').fetchone(), con.execute('SELECT COUNT(*), COALESCE(SUM(revisao=\\'conferida\\'),0) FROM item').fetchone(), con.execute(\"SELECT COUNT(*) FROM evento WHERE tipo NOT IN ('login','projeto_fechado')\").fetchone()]))");   // login e a marca de 'projeto fechado' que a PÁGINA do projeto grava ao abrir não são desta tela

async function entrar(browser, email, senha, erros, o = {}) {
  const ctx = await browser.newContext({ viewport: { width: o.w || 1366, height: o.h || 900 }, colorScheme: o.tema || 'light', deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?|\/api\/pedidos\/coleta$/.test(u);
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(email + ': ' + m.text()); });
  page.on('pageerror', e => erros.push(email + ': pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, page };
}
async function filas(page, aba) {
  await page.evaluate(a => { try { sessionStorage.removeItem('camp.fila.estado'); } catch (_) {} nav(a ? 'filas/' + a : 'filas'); }, aba || '');
  await page.waitForFunction(() => typeof FILAS_OK !== 'undefined' && FILAS_OK && document.querySelector('#filas-body tr'), null, { timeout: 15000 });
  await page.waitForTimeout(500);
}
const linha = (page, cod) => page.locator(`#filas-body tr[data-nav="projeto/${cod}"]`);
const num = t => +String(t || '').replace(/\D/g, '') || 0;

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const antes = foto();
    const { ctx, page: P } = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    await filas(P, 'todas');

    // ---------------- [A] a ação da linha é a etapa atual (admin) ----------------
    const ESP = { 'F075-P0004': 'Importar folhas', 'F075-P0005': 'Conferir folhas', 'F075-P0007': 'Aprovar lote', 'F075-P0008': 'Publicar', 'F075-P0010': 'Ler de novo esta pasta' };
    for (const [cod, rot] of Object.entries(ESP)) {
      const azuis = await linha(P, cod).locator('button.pri').allTextContents();
      chk(azuis.length === 1 && azuis[0] === rot, `[A] ${cod}: um só botão azul, "${rot}" (${JSON.stringify(azuis)})`);
    }
    const semAcao = await P.evaluate(() => [...document.querySelectorAll('#filas-body tr[data-fase]')].filter(r => ['processando', 'publicado'].includes(r.dataset.fase) && !/leitura interrompida/.test(r.textContent)).map(r => r.querySelectorAll('button.pri').length));
    chk(semAcao.every(n => n === 0), '[A] CAMP Vision lendo e No site: nenhuma ação azul (nada para a pessoa fazer)');
    const conferirErrado = await P.evaluate(() => [...document.querySelectorAll('#filas-body tr[data-fase]')].filter(r => r.dataset.fase !== 'conferir' && /Conferir folhas/.test(r.querySelector('.c-acao').textContent)).length);
    chk(conferirErrado === 0, '[A] "Conferir folhas" só aparece em lote que está para conferir (nunca universal)');

    // ---------------- [C] mesma fonte: cartões, abas, menu, /api/pendencias ----------------
    const pend = await P.evaluate(() => API('/api/pendencias'));
    await P.waitForFunction(() => /\d/.test((document.querySelector('[data-fila-card="no_site"] .v') || {}).textContent || ''), null, { timeout: 10000 });
    const C = await P.evaluate(() => {
      const card = k => (document.querySelector(`[data-fila-card="${k}"] .v`) || {}).textContent || '', aba = k => (document.querySelector(`#fila-chips [data-fila-filtro="${k}"] b`) || {}).textContent || '';
      const L = FILAS_SRV, vis = l => !l.dispensado && !l.adiado;
      return { cGente: card('gente'), cFolhas: card('conferir'), cParados: card('parado48'), cSite: card('no_site'), aGente: aba('gente'), aCheg: aba('chegando'), aConf: aba('conferir'), aPronto: aba('pronto'), aProb: aba('problema'), aSite: aba('publicado'), aTodos: aba('todas'),
        menu: (document.getElementById('n-filas') || {}).textContent || '', total: L.length, vivos: L.filter(vis).length, parados: L.filter(l => vis(l) && (+l.parado_h || 0) > 48 && (['erro', 'importar', 'conferir', 'aprovar', 'publicar'].includes(l.fase) || l.leitura_interrompida)).length };
    });
    chk(num(C.cGente) === num(C.aGente) && num(C.aGente) === pend.pedem_acao.material_novo && num(C.menu) === pend.pedem_acao.material_novo,
      `[C] "lotes precisam de você" = aba "Precisam de você" = menu = /api/pendencias (${C.cGente} · ${C.aGente} · ${C.menu} · ${pend.pedem_acao.material_novo})`);
    chk(num(C.cFolhas) === pend.folhas_conferir && num(C.aConf) === pend.lotes_conferir, `[C] "folhas para conferir" = ${pend.folhas_conferir} e aba "Para conferir" = ${pend.lotes_conferir} (contagens do servidor): ${C.cFolhas} · ${C.aConf}`);
    chk(num(C.cSite) === pend.projetos_no_site, `[C] "projetos no site" = contagens.projetos_no_site (${C.cSite} × ${pend.projetos_no_site}), que é outra coisa que a aba "No site" (lotes: ${C.aSite})`);
    chk(num(C.aCheg) + num(C.aConf) + num(C.aPronto) + num(C.aProb) + num(C.aSite) === C.vivos && num(C.aTodos) === C.total,
      `[C] as 5 situações não se sobrepõem: ${C.aCheg}+${C.aConf}+${C.aPronto}+${C.aProb}+${C.aSite} = ${C.vivos} lotes (Todos = ${C.aTodos})`);
    chk(num(C.cParados) === C.parados && C.parados >= 1, `[C] "parados há mais de 48 h" conta os lotes de uma pessoa parados na mesma etapa (${C.cParados})`);

    // ---------------- [E] o progresso diz o que mede ----------------
    const prog = async cod => (await linha(P, cod).locator('.c-prog').innerText()).replace(/\s+/g, ' ').trim();
    const pr = { lendo: await prog('F075-P0001'), imp: await prog('F075-P0004'), conf: await prog('F075-P0005'), apr: await prog('F075-P0007'), pub: await prog('F075-P0008') };
    chk(/^ARQUIVOS RECEBIDOS 9 de 24 arquivos esperados/i.test(pr.lendo), `[E] CAMP Vision lendo: "Arquivos recebidos · 9 de 24 arquivos esperados": "${pr.lendo}"`);
    chk(/^IMPORTAÇÃO 0 de 12 folhas no painel/i.test(pr.imp), `[E] falta importar: "Importação · 0 de 12 folhas no painel": "${pr.imp}"`);
    chk(/^CONFERÊNCIA 3 de 9 folhas conferidas 33%/i.test(pr.conf), `[E] para conferir: "Conferência · 3 de 9 folhas conferidas · 33%": "${pr.conf}"`);
    chk(/^APROVAÇÃO 10 folhas conferidas · falta aprovar o lote$/i.test(pr.apr), `[E] falta aprovar: "Aprovação · 10 folhas conferidas · falta aprovar o lote" (sem barra 100% azul): "${pr.apr}"`);
    chk(/^PUBLICAÇÃO 0 de 8 folhas no site/i.test(pr.pub), `[E] falta publicar: "Publicação · 0 de 8 folhas no site": "${pr.pub}"`);
    const cheio = await P.evaluate(() => [...document.querySelectorAll('#filas-body tr[data-fase="processando"]')].map(r => [r.querySelector('.sit').textContent, r.querySelector('.prog-pct') && r.querySelector('.prog-pct').textContent]));
    chk(cheio.some(([s, p]) => p === '100%' && s === 'Chegando'), `[E] 100% dos arquivos recebidos continua "Chegando" (não vira pronto): ${JSON.stringify(cheio)}`);
    const ariaOk = await P.evaluate(() => [...document.querySelectorAll('#filas-body progress.pg')].every(p => /^(Arquivos recebidos|Importação|Conferência|Publicação|Leitura parada): /.test(p.getAttribute('aria-label') || '')));
    chk(ariaOk, '[E] toda barra tem nome acessível com o que mede e o valor completo');

    // ---------------- [B] busca local ----------------
    const busca = async q => { await P.fill('#fila-q', q); await P.waitForTimeout(400); return P.$$eval('#filas-body tr[data-fase] .c-proj .code', l => l.map(x => x.textContent)); };
    let r = await busca('0006');
    chk(JSON.stringify(r) === '["F075-P0006"]', `[B] código parcial com zeros ("0006"): ${JSON.stringify(r)}`);
    r = await busca('f075p0006');
    chk(JSON.stringify(r) === '["F075-P0006"]', `[B] código sem hífen ("f075p0006"): ${JSON.stringify(r)}`);
    r = await busca('geriatrico vila');
    chk(JSON.stringify(r) === '["F075-P0006"]', `[B] nome sem acento, palavras em qualquer ordem ("geriatrico vila"): ${JSON.stringify(r)}`);
    const cnt = await P.textContent('#fila-cnt');
    chk(/^1 de \d+ registros$/.test(cnt.trim()) && !(await P.locator('#fila-limpar').isHidden()), `[D] com filtro: "1 de N registros" e "Limpar filtros" à vista: "${cnt}"`);
    await P.click('#fila-limpar'); await P.waitForTimeout(300);
    chk((await P.inputValue('#fila-q')) === '' && await P.locator('#fila-limpar').isHidden(), '[D] "Limpar filtros" limpa a busca');

    // ---------------- [D] filtros combinados, ordenação, paginação ----------------
    let pg = await P.textContent('#fila-pag');
    chk(new RegExp(`Mostrando 1–25 de ${C.total}`).test(pg) && (await P.locator('#filas-body tr[data-fase]').count()) === 25, `[D] "Mostrando 1–25 de ${C.total}" e só 25 linhas no DOM: "${pg.replace(/\s+/g, ' ').slice(0, 80)}"`);
    await P.click('#fila-pag [data-pg="prox"]'); await P.waitForTimeout(300);
    pg = await P.textContent('#fila-pag');
    chk(new RegExp(`Mostrando 26–${Math.min(50, C.total)} de ${C.total}`).test(pg), `[D] Próxima: "Mostrando 26–${Math.min(50, C.total)} de ${C.total}"`);
    await P.selectOption('#fila-pag select[data-pg="por"]', '50'); await P.waitForTimeout(300);
    chk((await P.locator('#filas-body tr[data-fase]').count()) === Math.min(50, C.total) && /Mostrando 1–/.test(await P.textContent('#fila-pag')), '[D] 50 por página volta para a página 1');
    await P.selectOption('#fila-pag select[data-pg="por"]', '25'); await P.waitForTimeout(300);
    await P.selectOption('#fila-f-fundo', 'F075'); await P.selectOption('#fila-f-etapa', 'conferir'); await P.waitForTimeout(300);
    r = await P.$$eval('#filas-body tr[data-fase]', l => l.map(x => x.querySelector('.code').textContent + ':' + x.dataset.fase));
    chk(r.length === 3 && r.every(x => /^F075-.*:conferir$/.test(x)), `[D] Fundo F075 + Etapa "Falta conferir" combinados: ${JSON.stringify(r)}`);
    await P.selectOption('#fila-f-arq', 'Arnaldo Martino'); await P.waitForTimeout(300);
    r = await P.$$eval('#filas-body tr[data-fase] .c-proj .code', l => l.map(x => x.textContent));
    chk(JSON.stringify(r.sort()) === '["F075-P0006","F075-P0011"]', `[D] + Autoria "Arnaldo Martino" (os três filtros somam): ${JSON.stringify(r)}`);
    await P.click('#fila-limpar'); await P.waitForTimeout(300);
    chk((await P.inputValue('#fila-f-fundo')) === '' && (await P.inputValue('#fila-f-etapa')) === '' && (await P.inputValue('#fila-f-arq')) === '', '[D] "Limpar filtros" limpa os selects também');
    await P.click('[data-fila-ordem]'); await P.waitForTimeout(300);
    const ph = await P.evaluate(() => { const pos = new Map([...document.querySelectorAll('#filas-body tr[data-fase] .c-proj .code')].map((c, i) => [c.textContent, i])); return FILAS_SRV.filter(l => pos.has(l.projeto_codigo)).sort((a, b) => pos.get(a.projeto_codigo) - pos.get(b.projeto_codigo)).map(l => +l.parado_h || 0); });
    chk(ph.every((v, i) => !i || ph[i - 1] >= v) && (await P.getAttribute('[data-fila-ordem]', 'aria-pressed')) === 'true' && (await P.inputValue('#fila-f-ordem')) === 'parado',
      '[D] "Parado há" ordena do mais parado (aria-pressed, e o seletor diz "Parado há mais tempo")');
    await P.selectOption('#fila-f-ordem', 'projeto'); await P.waitForTimeout(300);
    const tit = await P.$$eval('#filas-body tr[data-fase] .proj-tit', l => l.map(x => x.textContent));
    chk(tit.every((t, i) => !i || tit[i - 1].localeCompare(t, 'pt-BR', { sensitivity: 'base', numeric: true }) <= 0) && (await P.getAttribute('th:has([data-fila-ord="projeto"])', 'aria-sort')) === 'ascending', '[D] "Projeto (A–Z)" ordena pelo nome e o cabeçalho diz aria-sort');
    // voltar do projeto restaura
    await P.selectOption('#fila-f-ordem', 'trabalho'); await P.selectOption('#fila-f-fundo', 'F075'); await P.fill('#fila-q', 'edif'); await P.waitForTimeout(400);
    await P.click('#fila-pag [data-pg="prox"]'); await P.waitForTimeout(300);
    const est0 = await P.evaluate(() => JSON.stringify({ a: FILA_FILTRO, q: FILA_EST.q, f: FILA_EST.fundo, p: FILA_EST.pagina }));
    await P.locator('#filas-body tr[data-fase] .proj-tit').first().click(); await P.waitForFunction(() => /^#projeto\//.test(location.hash), null, { timeout: 10000 }); await P.waitForTimeout(800);
    await P.goBack(); await P.waitForFunction(() => /^#filas/.test(location.hash), null, { timeout: 10000 }); await P.waitForTimeout(1500);
    const est1 = await P.evaluate(() => JSON.stringify({ a: FILA_FILTRO, q: FILA_EST.q, f: FILA_EST.fundo, p: FILA_EST.pagina }));
    chk(est0 === est1 && JSON.parse(est1).p === 2 && (await P.inputValue('#fila-q')) === 'edif' && (await P.inputValue('#fila-f-fundo')) === 'F075' && /Mostrando 26–/.test(await P.textContent('#fila-pag')),
      `[D] ao abrir um projeto e voltar, aba, busca, filtro e página voltam (${est0} → ${est1})`);
    await P.evaluate(() => nav('filas/conferir')); await P.waitForTimeout(1200);
    chk(await P.evaluate(() => FILA_FILTRO === 'conferir' && !FILA_EST.q && !FILA_EST.fundo && FILA_EST.pagina === 1), '[D] vindo de um link com filtro (#filas/conferir), a lista começa limpa nesse filtro');

    // ---------------- [F] o que existia continua ----------------
    await filas(P, 'todas');
    chk(await P.locator('#fila-acoes [data-qnap]').isVisible() && /Novo lote/.test(await P.textContent('#fila-acoes')), '[F] Varrer QNAP e Novo lote no cabeçalho (admin)');
    chk(/Importar todas \(\d+\)/.test(await P.textContent('#fila-resumo')), '[F] "Importar todas (N)" continua ao lado do número de registros');
    const av = P.locator('#fila-avancado');
    chk(await av.count() === 1 && !(await av.evaluate(d => d.open)) && /Ferramentas avançadas/.test(await av.locator('summary').textContent()) && /Verificar destino pelo painel · modo Simular/.test(await av.locator('summary').textContent()),
      '[F] "Verificar destino pelo painel" em Ferramentas avançadas, recolhido e com o modo no resumo: "' + (await av.locator('summary').textContent()).replace(/\s+/g, ' ') + '"');
    await av.locator('summary').click(); await P.waitForTimeout(200);
    chk(await P.locator('#da-painel [data-da-modo]').count() === 3 && /Funções operacionais sensíveis/.test(await av.textContent()), '[F] aberto: os 3 modos (Desligado, Simular, Aplicar sozinho) e o aviso');
    await av.locator('summary').click();
    // detalhe pelo teclado
    const exp = linha(P, 'F075-P0006').locator('[data-fila-exp]');
    await exp.focus(); await P.keyboard.press('Enter'); await P.waitForTimeout(400);
    const det = P.locator('#filas-body .fila-det').first();
    await P.waitForFunction(() => { const h = document.querySelector('#filas-body .fila-hist'); return h && !h.querySelector('.esq-lista'); }, null, { timeout: 10000 }).catch(() => {});
    const tdet = (await det.innerText()).replace(/\s+/g, ' ');
    chk((await P.locator('#filas-body [data-fila-exp][aria-expanded="true"]').getAttribute('aria-controls')) === (await det.getAttribute('id')) && /^#?filas/.test(await P.evaluate(() => location.hash.replace(/^#/, ''))),
      '[G] Enter no ▸ abre o detalhe (aria-expanded/aria-controls) sem sair da tela');
    chk(/Identificação/.test(tdet) && /F075-P0006/.test(tdet) && /nº \d+/.test(tdet) && /Fundo F075 Fundo Material Novo/.test(tdet) && /Arnaldo Martino/.test(tdet) && /Chegou/.test(tdet) && /Nesta etapa desde/.test(tdet),
      '[F] detalhe: identificação completa (projeto, lote nº, fundo, autoria registrada, datas): "' + tdet.slice(0, 200) + '"');
    chk(await det.locator('.steps.caminho').count() === 1 && /Folhas no painel: 23/.test(tdet) && /Conferidas: 0 de 23 · faltam 23/.test(tdet), '[F] detalhe: os 7 passos e as folhas por etapa');
    chk(/Parado há \d+ (dias|h)/i.test(tdet), '[F] detalhe: pendências e alertas (parado há mais de 48 h)');
    chk(await det.locator('details.fila-pasta').count() === 1 && /ACERVOS_CAMP/.test(await det.locator('details.fila-pasta').textContent()), '[F] detalhe (admin): a pasta de origem no QNAP, recolhida');
    chk(/Último evento:/.test(tdet) || /Sem eventos registrados/.test(tdet), '[F] detalhe: último evento e histórico do projeto: "' + tdet.slice(-160) + '"');
    await exp.focus(); await P.keyboard.press('Enter'); await P.waitForTimeout(300);
    chk(await P.locator('#filas-body .fila-det').count() === 0, '[G] Enter de novo fecha o detalhe');
    // menu secundário
    const lErro = linha(P, 'F075-P0010');
    await lErro.locator('details.lista-mais > summary').click(); await P.waitForTimeout(200);
    chk(/^#?filas/.test(await P.evaluate(() => location.hash.replace(/^#/, ''))) && JSON.stringify(await lErro.locator('.mais-lista button').allTextContents()) === '["Tentar de novo","Dispensar este lote"]'
      && /Mais ações: F075-P0010/.test(await lErro.locator('details.lista-mais > summary').getAttribute('aria-label')), '[F] "⋯ Mais ações": Tentar de novo e Dispensar este lote (a linha não navega ao abrir o menu)');
    await P.keyboard.press('Escape');
    // status não só por cor
    chk(await P.evaluate(() => [...document.querySelectorAll('#filas-body tr[data-fase]')].every(r => { const t = r.querySelector('.tag.sit'); return t && t.textContent.trim().length > 3; })), '[G] toda linha tem a situação em texto');
    chk(await P.evaluate(() => [...document.querySelectorAll('#v-filas button, #v-filas select, #v-filas input, #v-filas summary, #v-filas a')].filter(e => e.offsetParent).every(e => (e.getAttribute('aria-label') || e.textContent || e.title || (e.labels && e.labels[0] && e.labels[0].textContent) || '').trim())), '[G] todo controle à vista tem nome acessível');

    // ---------------- [I] miniatura e autoria ----------------
    // (sem QNAP no teste a prévia dá 404 e o onerror tira a <img>, deixando o quadro neutro: confere-se a marcação que a linha gera)
    const imgs = await P.evaluate(() => FILAS_SRV.filter(l => l.miniatura).map(l => { const t = document.createElement('tbody'); t.innerHTML = linhaFila(l); const i = t.querySelector('.mini img'); return i ? { src: i.getAttribute('src'), lazy: i.getAttribute('loading'), cod: l.projeto_codigo, mini: l.miniatura } : { cod: l.projeto_codigo, src: '' }; }));
    chk(imgs.length >= 1 && imgs.every(i => i.lazy === 'lazy' && i.src.includes('/api/itens/' + encodeURIComponent(i.cod) + '-') && i.mini.startsWith(i.cod + '-') && /t=120/.test(i.src)), `[I] miniatura só da folha do próprio lote, pequena e com loading=lazy: ${JSON.stringify(imgs.slice(0, 2))}`);
    chk(await linha(P, 'F075-P0004').locator('.mini img').count() === 0 && await linha(P, 'F075-P0004').locator('.mini').count() === 1, '[I] lote sem folha com imagem: quadro neutro, sem foto');
    const arqs = await P.$$eval('#fila-f-arq option', l => l.map(o => o.textContent));
    chk(JSON.stringify(arqs) === '["Todas","Arnaldo Martino","Sem autoria registrada"]', `[I] filtro de autoria só com a autoria registrada no projeto (o fundo não vira autor): ${JSON.stringify(arqs)}`);
    chk(/autoria: Arnaldo Martino/.test(await linha(P, 'F075-P0006').locator('.c-fundo').textContent()) && !/autoria/.test(await linha(P, 'F075-P0005').locator('.c-fundo').textContent()), '[I] coluna Fundo / autoria: "autoria:" só quando registrada');
    const depois = foto();
    chk(depois === antes, `[F] filtrar, ordenar, paginar e abrir detalhes não gravou nada no banco (${antes} → ${depois})`);
    await ctx.close();

    // ---------------- [A] operador e leitura ----------------
    const op = await entrar(browser, 'operador@camp.arq.br', 'senha-operador-123', erros);
    await filas(op.page, 'todas');
    chk(JSON.stringify(await linha(op.page, 'F075-P0007').locator('.c-acao').innerText()) === '"Falta um admin aprovar"' && await linha(op.page, 'F075-P0004').locator('button.pri').textContent() === 'Importar folhas',
      '[A] operador: importa e confere; "Falta um admin aprovar" no lote que espera um admin');
    await op.ctx.close();
    const lei = await entrar(browser, 'leitor@camp.arq.br', 'senha-leitor-1234', erros);
    await filas(lei.page, 'todas');
    const azLei = [...new Set(await lei.page.locator('#filas-body button.pri').allTextContents())];
    chk(azLei.every(t => t === 'Conferir folhas') && !(await lei.page.locator('#fila-acoes [data-qnap]').isVisible().catch(() => false)) && !(await lei.page.locator('#fila-acoes [data-pode="lote.novo"]').isVisible())
      && await lei.page.locator('#filas-body [data-fila-acao], #filas-body [data-fila-dispensar], #filas-body [data-fila-apagar], #filas-body [data-releitura-projeto]').count() === 0,
      `[A] quem só lê: nada que mude o lote (só "Conferir folhas", que abre a conferência para ver, como antes); sem Varrer QNAP nem Novo lote: ${JSON.stringify(azLei)}`);
    await lei.ctx.close();

    // ---------------- [G] celular, zoom 200%, tablet ----------------
    for (const [w, nome] of [[390, 'celular'], [683, 'zoom 200% (1366 px)'], [1024, 'tablet']]) {
      const m = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros, { w, h: 800 });
      await filas(m.page, 'gente');
      const g = await m.page.evaluate(() => {
        const rows = [...document.querySelectorAll('#filas-body tr[data-fase]')].slice(0, 6), sobre = [];
        rows.forEach(r => { const cs = [...r.children].filter(c => c.offsetParent && c.getBoundingClientRect().width); for (let i = 0; i < cs.length; i++) for (let j = i + 1; j < cs.length; j++) { const a = cs[i].getBoundingClientRect(), b = cs[j].getBoundingClientRect(); if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) sobre.push(r.querySelector('.code').textContent); } });
        return { sw: document.documentElement.scrollWidth, iw: window.innerWidth, mainSw: document.querySelector('.main').scrollWidth, mainW: document.querySelector('.main').clientWidth, thead: getComputedStyle(document.querySelector('.fila-tab thead')).display,
          fundo: getComputedStyle(document.querySelector('#filas-body tr[data-fase] .c-fundo')).display, acao: [...document.querySelectorAll('#filas-body tr[data-fase] .c-acao')].every(c => c.offsetParent), sobre };
      });
      chk(g.sw <= g.iw + 1 && g.mainSw <= g.mainW + 1, `[G] ${nome}: sem rolagem lateral (${g.sw}/${g.iw}, main ${g.mainSw}/${g.mainW})`);
      chk(!g.sobre.length, `[G] ${nome}: nenhuma célula por cima de outra ${JSON.stringify(g.sobre)}`);
      chk(g.acao, `[G] ${nome}: a ação de toda linha continua à vista`);
      if (w < 721) chk(g.thead === 'none', `[G] ${nome}: as linhas viram cartões (sem cabeçalho de tabela)`);
      if (w === 1024) chk(g.fundo === 'none' && g.thead !== 'none', `[G] ${nome}: tabela, sem a coluna secundária "Fundo / autoria" (o fundo vai para baixo do projeto)`);
      await m.ctx.close();
    }

    // ---------------- [H] desempenho com milhares de lotes ----------------
    py(`
con.execute("INSERT OR IGNORE INTO fundo (codigo,titulo,sigla,ativo) VALUES ('F076','Fundo Volume','FVO',1)")
for n in range(1, 2001):
    P = 'F076-P%04d' % n
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo,numero) VALUES ('F076',?)", (n,))
    con.execute("INSERT OR IGNORE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,status_site) VALUES (?,'F076',?,?,1970,'no_ar')", (P, n, 'Projeto volume %d' % n))
    con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES (?,?,?, 'publicado')", (P, P, '/v/' + P))
`);
    const v = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    const t0 = Date.now(); await filas(v.page, 'todas'); const tTela = Date.now() - t0;
    const perf = await v.page.evaluate(async () => { const a = performance.now(); const r = await fetch('/api/filas?leve=1'); const j = await r.json(); const b = performance.now(); desenharFilas(); const c = performance.now(); return { api: Math.round(b - a), n: j.length, desenho: Math.round(c - b), dom: document.querySelectorAll('#filas-body tr[data-fase]').length }; });
    chk(perf.n > 2000 && perf.dom === 25 && perf.desenho < 400 && perf.api < 8000, `[H] ${perf.n} lotes: só 25 linhas no DOM; /api/filas?leve=1 em ${perf.api} ms; desenhar em ${perf.desenho} ms; tela pronta em ${tTela} ms`);
    await v.ctx.close();
    py("con.execute(\"DELETE FROM lista_processamento WHERE projeto_codigo LIKE 'F076-%'\")\ncon.execute(\"DELETE FROM projeto WHERE codigo LIKE 'F076-%'\")\ncon.execute(\"DELETE FROM numero_p WHERE fundo_codigo='F076'\")");
  } catch (e) { chk(false, 'o teste quebrou: ' + (e.stack || e.message)); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
