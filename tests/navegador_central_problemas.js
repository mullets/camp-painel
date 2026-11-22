// CAMP-PROB-UX (22/11/2026): Central de Problemas no navegador de verdade (Playwright + Chromium). Documento do Rafael "Redesenho da
// Central de Problemas": os cartões abrem a lista filtrada; abas e filtros rápidos funcionam e ficam no endereço; abrir e fechar o painel
// lateral mantém a posição e os filtros; resolver atualiza os contadores; o topo (usuário, situação, temperatura) não muda; no celular
// (390 px) nada passa da largura e o painel vira tela cheia; "/" busca; link permanente abre o problema; nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/x/cp.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x/cp.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8940)
//   CAMP_DB_PATH=/tmp/x/cp.db CAMP_BASE=http://127.0.0.1:8940 node tests/navegador_central_problemas.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8940', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// 60 problemas abertos de vários tipos e severidades, espalhados pelas folhas do banco de teste (idempotente)
py(`
import random
random.seed(11)
if not con.execute("SELECT 1 FROM erro WHERE descricao LIKE '[central]%' LIMIT 1").fetchone():
    itens=[r[0] for r in con.execute("SELECT codigo FROM item WHERE codigo NOT LIKE 'F000%' ORDER BY codigo")]
    cats=[('autoria_divergente','bloqueia','Aflalo & Gasperini ou Pilon & Gasperini?'),('duplicata','corrigir','Registro duplicado'),('metadado','corrigir','Documento sem data identificada'),('orientacao','aviso','Folha de lado'),('codigo','bloqueia','Folhas sem numeração sequencial')]
    for n in range(60):
        c,g,d=cats[n%5]
        con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao,criado_em) VALUES (?,?,?,?,?,datetime('now',?))",(g,c,'operador',itens[(n*3)%len(itens)],'[central] '+d,'-%d days'%random.randint(0,50)))
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const nova = async (w, h) => { const ctx = await browser.newContext({ viewport: { width: w, height: h } }); const page = await ctx.newPage();
    page.on('pageerror', e => erros.push(e.message)); page.on('dialog', d => d.dismiss().catch(() => {}));
    await page.goto(BASE + '/'); await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await page.waitForTimeout(600); return { ctx, page }; };
  // espera a lista ser desenhada DE NOVO depois da ação (o contador data-render sobe a cada desenho)
  const RN = new WeakMap();
  const espera = async (page) => { const n0 = RN.get(page) || 0; await page.waitForFunction(n => +(document.getElementById('err-body').dataset.render || 0) > n && document.getElementById('err-body').getAttribute('aria-busy') === 'false', n0, { timeout: 15000 });
    RN.set(page, await page.$eval('#err-body', el => +el.dataset.render)); };
  const num = (page, k) => page.$eval(`[data-cp-cartao="${k}"] .cp-c-n`, el => +el.textContent.replace(/\D/g, ''));
  try {
    const { ctx, page } = await nova(1366, 900);
    // o topo (usuário, situação das coisas, temperatura) é o mesmo em outra tela e em Problemas: nada da Central entra nele
    await page.goto(BASE + '/#projetos'); await page.waitForTimeout(1200);
    const topo = () => page.evaluate(() => { const t = document.querySelector('.top'); const f = el => el.tagName + '#' + (el.id || '') + '.' + [...el.classList].sort().join('.') + '[' + [...el.children].map(f).join(',') + ']'; return t ? f(t) : null; });
    const topoAntes = await topo();
    await page.goto(BASE + '/#erros'); await espera(page);
    const topoDepois = await topo();
    chk(topoAntes && topoAntes === topoDepois && !(await page.$('.top [class*="cp-"]')), 'o topo (usuário, situação, temperatura) é o mesmo em Projetos e em Problemas');
    chk(await page.$eval('h1', () => document.querySelector('#v-erros h1').textContent.trim()) === 'Problemas', 'o título da página continua o nome do menu (Problemas)');
    // cartões
    chk((await page.$$('#cp-cartoes [data-cp-cartao]')).length === 5, 'cinco cartões: Em aberto, Críticos, Em análise, Aguardando revisão, Resolvidos');
    const crit0 = await num(page, 'criticos');
    await page.click('[data-cp-cartao="criticos"]'); await espera(page);
    let h = await page.evaluate(() => decodeURIComponent(location.hash));
    const sev = await page.$$eval('#err-body [data-err-linha]', ls => ls.map(l => l.className));
    chk(/aba=todos/.test(h) && /chip=critico/.test(h) && sev.length > 0 && sev.every(c => /sev-critico/.test(c)), `cartão Críticos abre a lista só de críticos e o endereço guarda o filtro (${h})`);
    chk(await page.$eval('#err-cnt', el => el.textContent).then(t => +t.replace(/\D/g, '') === crit0), 'o número do cartão Críticos é o total da lista que ele abre');
    await page.click('[data-cp-cartao="aguardando_revisao"]'); await espera(page);
    h = await page.evaluate(() => decodeURIComponent(location.hash));
    chk(/fase=aguardando_revisao/.test(h) && await page.$eval('#err-filtro-ativo', el => /Aguardando revisão/.test(el.textContent)), 'cartão Aguardando revisão filtra pela fase e mostra o chip do filtro ativo');
    await page.click('[data-err-limpar-tudo]'); await espera(page);
    chk(await page.$eval('#err-filtro-ativo', el => el.hidden), '"Limpar filtros" tira todos os filtros');
    // abas e filtros rápidos
    await page.click('#err-abas [data-err-sit="prioridades"]'); await espera(page);
    chk(await page.$eval('#err-abas [data-err-sit="prioridades"]', b => b.getAttribute('aria-pressed') === 'true'), 'aba Prioridades fica marcada');
    const avisosEmPrior = await page.$$eval('#err-body [data-err-linha]', ls => ls.filter(l => /sev-baixo/.test(l.className)).length);
    chk(avisosEmPrior === 0, 'Prioridades não mostra avisos (é o número do menu)');
    const menuN = await page.$eval('#n-err', el => +el.textContent.replace(/\D/g, '') || 0).catch(() => -1);
    const abaN = await page.$eval('#err-abas [data-err-sit="prioridades"] b', el => +el.textContent.replace(/\D/g, ''));
    chk(menuN === abaN, `número do menu (${menuN}) = aba Prioridades (${abaN})`);
    await page.click('#err-abas [data-err-sit="todos"]'); await espera(page);
    await page.click('[data-cp-chip="sem_responsavel"]'); await espera(page);
    const semResp = await page.$$eval('#err-body [data-err-linha] .cp-resp', rs => rs.every(r => /Não atribuído/.test(r.textContent)));
    chk(semResp && await page.$eval('[data-cp-chip="sem_responsavel"]', b => b.getAttribute('aria-pressed') === 'true'), 'filtro rápido Sem responsável: todas as linhas "Não atribuído" e o chip marcado');
    await page.click('[data-cp-chip="critico"]'); await espera(page);
    const ambos = await page.$$eval('#err-body [data-err-linha]', ls => ls.every(l => /sev-critico/.test(l.className) && /Não atribuído/.test(l.querySelector('.cp-resp').textContent)));
    chk(ambos, 'Críticos + Sem responsável: toda linha satisfaz os dois');
    // busca e paginação
    await page.click('[data-cp-tirar="chip:critico"]'); await espera(page);
    await page.keyboard.press('Escape');
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    await page.keyboard.press('/');
    chk(await page.evaluate(() => document.activeElement && document.activeElement.id === 'err-q'), 'tecla "/" leva para a busca');
    await page.keyboard.type('sequencial'); await page.waitForTimeout(700); await espera(page);
    chk(await page.$$eval('#err-body [data-err-linha] .cp-desc', ds => ds.length > 0 && ds.every(d => /sequencial/i.test(d.textContent))) && /q=sequencial/.test(await page.evaluate(() => location.hash)), 'busca filtra no servidor e fica no endereço');
    await page.fill('#err-q', ''); await page.waitForTimeout(700); await espera(page);
    await page.click('[data-err-limpar-tudo]').catch(() => {}); await espera(page);
    await page.click('#err-abas [data-err-sit="todos"]'); await espera(page);
    chk(await page.$eval('#err-mais', el => !el.hidden && /Mostrando 1–25 de/.test(el.textContent)), 'paginação: "Mostrando 1–25 de N"');
    await page.click('#err-mais [data-cp-pag="2"]'); await espera(page);
    chk(/pagina=2/.test(await page.evaluate(() => location.hash)) && await page.$eval('#err-mais', el => /Mostrando 26–/.test(el.textContent)), 'página 2 fica no endereço');
    // painel: abre sem perder a posição; Esc fecha e volta ao mesmo lugar e com os mesmos filtros
    await page.click('[data-cp-chip="sem_responsavel"]'); await espera(page);
    await page.evaluate(() => { mainEl.scrollTop = 600; }); await page.waitForTimeout(200);
    const pos0 = await page.evaluate(() => mainEl.scrollTop), h0 = await page.evaluate(() => location.hash);
    const alvo = await page.$eval('#err-body [data-err-linha]:nth-child(3)', l => +l.dataset.errLinha);
    await page.click(`#err-body [data-err-linha="${alvo}"] .cp-cta`); await page.waitForSelector('#d-body .cp-ident');
    const posAberto = await page.evaluate(() => mainEl.scrollTop);   // o clique rola a linha para a vista: a posição que vale é a da lista com o painel aberto
    chk(new RegExp('p=' + alvo).test(await page.evaluate(() => location.hash)), 'abrir o painel põe o problema no endereço (link permanente)');
    chk(await page.$eval('#d-body', b => ['Qual é o problema?', 'O que precisa ser decidido?', 'Resposta', 'Histórico', 'Contexto'].every(t => b.textContent.includes(t))), 'painel tem identificação, contexto, "Qual é o problema?", "O que precisa ser decidido?", resposta e histórico');
    await page.keyboard.press('Escape'); await page.waitForTimeout(500);
    const pos1 = await page.evaluate(() => mainEl.scrollTop), h1 = await page.evaluate(() => location.hash);
    chk(!(await page.evaluate(() => mainEl.classList.contains('with-drawer'))) && Math.abs(pos1 - posAberto) < 40 && h1.replace(/&?p=\d+/, '') === h0, `Esc fecha o painel e a lista fica no mesmo lugar (${posAberto}→${pos1}) e com os mesmos filtros`);
    // resolver atualiza os contadores (crítico com fonte: autoria pede fonte)
    await page.click('[data-err-limpar-tudo]'); await espera(page);
    await page.click('[data-cp-cartao="criticos"]'); await espera(page);
    const c1 = await num(page, 'criticos');
    await page.click('#err-body [data-err-linha] .cp-cta'); await page.waitForSelector('#cp-conclusao');
    await page.click('[data-cp-fase="resolvido"]'); await page.waitForFunction(() => document.getElementById('cp-erro').textContent.length > 0, null, { timeout: 5000 }).catch(() => {});
    chk(/conclusão/i.test(await page.textContent('#cp-erro')), 'resolver sem conclusão mostra o que falta (na tela)');
    await page.fill('#cp-conclusao', 'Conferido na prancha original'); await page.waitForTimeout(1400);
    chk(/Rascunho salvo/.test(await page.textContent('#cp-rasc-st')), 'o rascunho é salvo sozinho');
    await page.fill('#cp-ev', 'Carimbo da prancha original, caixa 3'); await page.click('[data-cp-evidencia]'); await page.waitForSelector('#d-body .cp-ev'); await page.waitForTimeout(300);
    chk(await page.inputValue('#cp-conclusao') === 'Conferido na prancha original', 'adicionar evidência não apaga a conclusão escrita');
    await page.click('[data-cp-fase="resolvido"]'); await espera(page); await page.waitForTimeout(400);
    chk(await num(page, 'criticos') === c1 - 1, `resolver atualiza o cartão Críticos (${c1} → ${await num(page, 'criticos')})`);
    chk(await page.$eval('[data-cp-cartao="resolvidos"] .cp-c-n', el => +el.textContent.replace(/\D/g, '')) >= 1, 'o cartão Resolvidos conta a resolução');
    await page.keyboard.press('Escape'); await page.waitForTimeout(300);
    // link permanente abre direto o problema
    const id = await page.$eval('#err-body [data-err-linha]', l => +l.dataset.errLinha);
    await page.goto(BASE + '/#erros/~p=' + id); await page.waitForSelector('#d-body .cp-ident', { timeout: 10000 });
    chk(await page.evaluate(i => window.ERR_ATUAL && window.ERR_ATUAL.id === i, id), 'link permanente (#erros/~p=N) abre o problema');
    await page.keyboard.press('Escape'); await page.waitForTimeout(300);
    // J/K na lista (fora de campo de texto)
    await page.evaluate(() => document.activeElement && document.activeElement.blur());
    await page.keyboard.press('j'); await page.keyboard.press('j');
    chk(await page.evaluate(() => { const k = document.querySelector('#err-body .kb-atual'); return !!k && k === document.querySelectorAll('#err-body [data-err-linha]')[1]; }), 'J desce na lista (fora de campo de texto)');
    // coluna da direita e gráficos de dados reais; sem ranking por padrão
    chk(await page.$eval('#cp-lateral', el => /Seu progresso na resolução/.test(el.textContent) && /Meta da semana/.test(el.textContent) && /Conquistas/.test(el.textContent) && /Atividade recente/.test(el.textContent) && !/Ranking da equipe/.test(el.textContent)), 'progresso, meta, conquistas e atividade recente; ranking escondido (desligado por padrão)');
    chk(await page.$eval('#cp-graf-tipo', el => !!el.querySelector('svg.cp-donut')) && await page.$eval('#cp-graf-sem', el => /Evolução de resolução/.test(el.textContent)), 'gráficos "Problemas por tipo" e "Evolução de resolução"');
    await ctx.close();
    // celular 390
    const m = await nova(390, 844);
    await m.page.goto(BASE + '/#erros'); await espera(m.page);
    const ov = await m.page.evaluate(() => Math.max(document.documentElement.scrollWidth, document.querySelector('.main').scrollWidth) - window.innerWidth);
    chk(ov <= 0, `390 px: nada passa da largura (${ov})`);
    await m.page.click('#cp-filtros-btn'); await m.page.waitForTimeout(200);
    const gav = await m.page.$eval('#cp-filtros-mais', el => { const r = el.getBoundingClientRect(); return !el.hidden && r.width >= window.innerWidth - 1 && getComputedStyle(el).position === 'fixed'; });
    chk(gav, '390 px: os filtros abrem numa gaveta de tela cheia');
    await m.page.click('#cp-filtros-mais .cp-gaveta-fim [data-cp-filtros-fechar]');
    await m.page.click('#err-body [data-err-linha] .cp-cta'); await m.page.waitForSelector('#d-body .cp-ident');
    const cheio = await m.page.$eval('#drawer', d => d.getBoundingClientRect().width >= window.innerWidth - 1);
    const ov2 = await m.page.evaluate(() => document.getElementById('drawer').scrollWidth - document.getElementById('drawer').clientWidth);
    chk(cheio && ov2 <= 0, `390 px: o painel vira tela de detalhe (tela cheia, sem rolar para o lado: ${ov2})`);
    await m.ctx.close();
    chk(!erros.length, 'nenhum erro de JavaScript' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  } catch (e) { chk(false, 'o teste quebrou: ' + (e.stack || e.message).slice(0, 400)); }
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
