// CAMP-HOME-UX (22/11/2026, documento do Rafael "Redesenho do painel inicial / Precisa de você"), no navegador de verdade:
//  - a Home em três partes, nesta ordem: Ação (saudação + meta da semana + 4 indicadores + "O que fazer agora"), Operação (caminho do material)
//    e Resultados (ritmo, visitas); coluna da direita na ordem do documento (alertas, progresso, qualidade, publicação, sistemas…);
//  - os indicadores abrem a lista que contam e dizem a regra da contagem;
//  - abas Minha fila · Todos · Críticos · Sem responsável; "Pegar para mim" leva a tarefa para a Minha fila; no máximo 5 linhas + "Ver todas";
//  - cada linha com prioridade + o porquê, miniatura, responsável e UM botão principal;
//  - gargalo do caminho pela espera acumulada (amarelo, com "aguardando há");
//  - sistemas: uma linha verde quando tudo está normal; o que falha aparece aberto;
//  - nível e conquistas com "Ocultar conquistas"; o Ranking da equipe (mês) ligado por padrão (decisão do Rafael, 22/11/2026);
//  - a barra do topo é a MESMA do main (marcação idêntica, mesmos ids); 390 px sem rolagem lateral; nenhum erro de JavaScript.
// CAMP-HOME-UX maquete (22/11/2026, "tá faltando um monte de elemento"): a mesma Home no desenho da maquete do Rafael — "Entenda esta página"
//  fechada numa linha; indicadores com ícone; linha da fila curta ("Há 19 dias", a frase da prioridade na dica); caminho em 7 cartões LADO A
//  LADO com ✓ verde no que está zerado; coluna da direita na ordem da maquete (nível azul-marinho, 3 selos, sistemas com "Online", qualidade,
//  donut do site, melhorias de hoje); visitas sem dados = aviso compacto.
// Uso (servidor PRÓPRIO, porta 8931):
//   CAMP_DB_PATH=/dev/shm/t/h.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/dev/shm/t/h.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8931)
//   CAMP_DB_PATH=/dev/shm/t/h.db CAMP_BASE=http://127.0.0.1:8931 node tests/navegador_home_redesenho.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8931', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const TOPO_SHA = 'd16698c156c1c43c';   // sha256 (16 primeiros) da marcação de <div class="top"> no main de 22/11/2026 (9319c38): "não mude o menu superior"
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

async function entrar(browser, email, senha, erros, largura) {
  const ctx = await browser.newContext({ viewport: { width: largura || 1366, height: largura && largura < 500 ? 844 : 900 } });
  const page = await ctx.newPage();
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=|\/api\/pedidos\/coleta$/.test(u);
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(email + ': ' + m.text()); });
  page.on('pageerror', e => erros.push(email + ': pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  await page.evaluate(() => { try { localStorage.removeItem('camp.ini.aba'); localStorage.removeItem('camp.ini.fila') } catch (_) {} });
  return { ctx, page };
}
async function abrirHome(page) {
  await page.evaluate(() => { nav('painel'); carregarPainel() });
  await page.waitForSelector('#v-painel .ini-grid #ini-tarefas', { timeout: 15000 });
  await page.waitForFunction(() => !!document.querySelector('#ini-jogo .ini-jogo, #ini-jogo .ini-jogo-oculto, #ini-jogo .pb'), null, { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(700);
}
const api = (P, url, op) => P.evaluate(async ([u, o]) => { const r = await fetch(u, Object.assign({ credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } }, o || {})); return { status: r.status, json: await r.json().catch(() => null) }; }, [url, op]);

(async () => {
  // mais trabalho na fila (para passar de 5 linhas) e um lote parado há 19 dias em Conferir (o gargalo pela espera)
  py("for n in ('Pesquisadora A','Editora B','Museu C'):\n  con.execute(\"INSERT INTO solicitacao (solicitante,finalidade,situacao) VALUES (?, 'pesquisa','aguarda_resposta')\", (n,))");
  py("con.execute(\"UPDATE lista_processamento SET etapa_desde=datetime('now','-19 days') WHERE id IN (SELECT l.id FROM lista_processamento l JOIN item i ON i.lote_id=l.id WHERE i.revisao='pendente' AND l.aprovado_em IS NULL)\")");
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const adm = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    const P = adm.page;
    // ---------- barra do topo igual ao main ----------
    const topo = await P.evaluate(async () => { const s = await (await fetch('/')).text(); const a = s.indexOf('<div class="top">'); let b = s.indexOf('id="system-banner-when"', a); b = s.indexOf('</div>', b);
      const h = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s.slice(a, b))); return [...new Uint8Array(h)].map(x => x.toString(16).padStart(2, '0')).join('').slice(0, 16); });
    chk(topo === TOPO_SHA, `a marcação da barra do topo é a mesma do main (${topo})`);
    await abrirHome(P);
    const idsTopo = await P.evaluate(() => [...document.querySelectorAll('.top [id]')].map(e => e.id).filter(i => /^(nav-gaveta|q|qres|where|clima-topo|tarefas-chip|machine-status|who-menu|system-banner)$/.test(i)));
    chk(['nav-gaveta', 'q', 'qres', 'where', 'clima-topo', 'tarefas-chip', 'machine-status', 'who-menu', 'system-banner'].every(i => idsTopo.includes(i)) && !(await P.$('.top #ini-meta, .top .ini-kpi')), `o topo tem os mesmos ids (${idsTopo.join(', ')}) e a Home não entra nele`);

    // ---------- ordem: Ação · Operação · Resultados; coluna da direita pela prioridade do documento ----------
    const ordem = await P.evaluate(() => { const pos = s => { const e = document.querySelector(s); return e ? [...document.querySelectorAll('#v-painel *')].indexOf(e) : -1 };
      return { hello: pos('#ini-saud'), meta: pos('#ini-meta'), kpis: pos('.ini-kpis'), acao: pos('[data-ini-parte="acao"]'), op: pos('[data-ini-parte="operacao"]'), res: pos('[data-ini-parte="resultados"]'),
        ritmo: pos('#ini-ritmo'), jogo: pos('#ini-jogo'), qb: pos('#ini-qualidade'), site: pos('#ini-cobertura'), saude: pos('#ini-saude'), mh: pos('#ini-melhorias'), hoje: pos('#ini-t-hoje'),
        princ: !!document.querySelector('.ini-col-princ [data-ini-parte="acao"]') && !!document.querySelector('.ini-col-princ [data-ini-parte="resultados"] #ini-ritmo'), lat: !!document.querySelector('.ini-lateral #ini-jogo') } });
    const crescente = a => a.every((v, i) => v >= 0 && (!i || a[i - 1] < v));
    chk(crescente([ordem.hello, ordem.meta, ordem.kpis, ordem.acao, ordem.op, ordem.res, ordem.ritmo]) && ordem.princ, `Ação → Operação → Resultados, nesta ordem, na coluna principal: ${JSON.stringify(ordem)}`);
    chk(ordem.lat && crescente([ordem.jogo, ordem.saude, ordem.qb, ordem.site, ordem.mh, ordem.hoje]), 'coluna da direita na ordem da maquete: progresso, sistemas, qualidade, publicação, melhorias, hoje');
    // ---------- maquete: ajuda fechada, ícones, caminho horizontal, donut, selos, nível ----------
    const mq = await P.evaluate(() => { const r = e => e.getBoundingClientRect(), aj = document.querySelector('#v-painel > .ajuda-caixa');
      const passos = [...document.querySelectorAll('#ini-caminho .ini-step')].map(b => { const x = r(b); return [Math.round(x.top), Math.round(x.width)]; });
      const nc = document.querySelector('#ini-jogo .ini-nivel-card');
      return { aj: aj ? { rec: aj.classList.contains('ajuda-recolhida'), open: aj.open, alt: Math.round(r(aj).height) } : null,
        icones: [...document.querySelectorAll('#v-painel .ini-kpi .ini-kpi-ic svg')].length, kpiTop: [...new Set([...document.querySelectorAll('#v-painel .ini-kpi')].map(k => Math.round(r(k).top)))].length,
        passos, ok: [...document.querySelectorAll('#ini-caminho .ini-passo')].map(l => [l.classList.contains('zero'), !!l.querySelector('.ini-passo-ok svg')]),
        donut: (() => { const d = document.querySelector('#ini-cobertura [data-cob="folhas"].ini-donut-row'); return d ? { pct: +d.dataset.pct, txt: d.querySelector('.ini-cob-pct').textContent, n: d.querySelector('.ini-cob-n').textContent, leg: [...d.querySelectorAll('.ini-donut-leg li')].map(x => x.textContent.trim()), arcos: d.querySelectorAll('circle.ini-donut-s').length } : null; })(),
        selos: [...document.querySelectorAll('#ini-jogo .ini-selos .ini-selo')].map(x => x.textContent.trim().replace(/\s+/g, ' ')),
        nivel: nc ? { fundo: getComputedStyle(nc).backgroundColor, txt: nc.innerText } : null,
        mh: document.querySelector('#ini-melhorias #ini-mh-hoje') ? document.querySelector('#ini-melhorias #ini-mh-hoje').innerText : null,
        ordemNaAba: !!document.querySelector('#ini-tarefas .ini-abas-linha #ini-ordem'),
        abaAtiva: getComputedStyle(document.querySelector('#ini-tarefas .ini-abas [aria-pressed="true"]')).backgroundColor,
        linhaAlt: Math.round(r(document.querySelector('#ini-lista .ini-task')).height), espera: (document.querySelector('#ini-lista .ini-task .ini-espera [aria-hidden]') || {}).textContent || '',
        motivoVisivel: (() => { const m = document.querySelector('#ini-lista .ini-task .ini-prio-motivo,#ini-lista .ini-task .ini-motivo'); return m ? r(m).width > 2 : null; })() }; });
    const pa0 = (await api(P, '/api/painel?fila=prioridade')).json, pg0 = (await api(P, '/api/painel/progresso')).json, ns0 = pa0.no_site.folhas;
    chk(mq.aj && mq.aj.rec && !mq.aj.open && mq.aj.alt < 60, `"Entenda esta página" chega fechada numa linha (${JSON.stringify(mq.aj)})`);
    chk(mq.icones === 4 && mq.kpiTop === 1, `4 indicadores com ícone, numa linha só (${mq.icones}, linhas ${mq.kpiTop})`);
    chk(mq.passos.length === 7 && new Set(mq.passos.map(x => x[0])).size === 1 && Math.max(...mq.passos.map(x => x[1])) - Math.min(...mq.passos.map(x => x[1])) <= 2, `caminho HORIZONTAL: 7 cartões iguais na mesma linha ${JSON.stringify(mq.passos)}`);
    chk(mq.ok.every(([z, ic]) => z === ic) && mq.ok.some(([z]) => z), `passo zerado tem o ✓ verde (e só ele) ${JSON.stringify(mq.ok)}`);
    const pctEsp = 100 * ns0.no_ar / ns0.total;
    chk(mq.donut && Math.abs(mq.donut.pct - pctEsp) < .01 && mq.donut.n.includes(`${ns0.no_ar.toLocaleString('pt-BR')} de ${ns0.total.toLocaleString('pt-BR')} folhas publicadas`) && mq.donut.leg.length === 3 && /^No site/.test(mq.donut.leg[0]) && /^Em preparo/.test(mq.donut.leg[1]) && /^A publicar/.test(mq.donut.leg[2])
      && ns0.no_ar + ns0.a_publicar + ns0.em_preparo === ns0.total, `donut do site com o % e "N de M folhas publicadas" no meio e a legenda No site · Em preparo · A publicar ${JSON.stringify([mq.donut, ns0])}`);
    const ct = pg0.eu.contagens;
    chk(mq.selos.length === 3 && mq.selos[0].startsWith(String(ct.folha_conferida)) && mq.selos[1].startsWith(String(ct.lote_aprovado)) && mq.selos[2].startsWith(String(pg0.eu.dias_seguidos)) && /folhas? conferidas?/.test(mq.selos[0]) && /lotes? aprovados?/.test(mq.selos[1]),
      `3 selos com os números de verdade do progresso ${JSON.stringify([mq.selos, ct, pg0.eu.dias_seguidos])}`);
    chk(mq.nivel && mq.nivel.fundo !== 'rgba(0, 0, 0, 0)' && mq.nivel.fundo !== 'rgb(255, 255, 255)' && new RegExp(`Faltam ${pg0.eu.ate - pg0.eu.xp} XP para o nível ${pg0.eu.nivel + 1}`).test(mq.nivel.txt), `nível num cartão escuro, com "Faltam N XP para o nível N+1" ${JSON.stringify(mq.nivel)}`);
    const fhoje = (pg0.hoje || {}).folha_conferida || 0;
    chk(mq.mh !== null && (fhoje ? new RegExp(`${fhoje} folhas? conferidas?`).test(mq.mh) : /Nenhuma melhoria registrada hoje|edições? na base/.test(mq.mh)), `melhorias de hoje com o que a equipe fez hoje (${JSON.stringify(mq.mh)}, hoje=${fhoje})`);
    chk(mq.ordemNaAba && mq.abaAtiva !== 'rgba(0, 0, 0, 0)', `"Ordenar" na linha das abas; a aba ativa tem fundo azul-claro (${mq.abaAtiva})`);
    chk(mq.linhaAlt <= 80 && /^Há (menos de 1 h|\d+ h|\d+ dias)$/.test(mq.espera) && mq.motivoVisivel === false, `linha curta: "Há N dias" e a frase da prioridade na dica, não na linha (${mq.linhaAlt}px, "${mq.espera}")`);
    const acima = await P.evaluate(() => { const r = document.querySelector('[data-ini-parte="acao"] .ph').getBoundingClientRect(); return r.top < innerHeight; });
    chk(acima, '"O que fazer agora" começa acima da dobra (1366×900)');

    // ---------- indicadores: abrem a lista e dizem a regra ----------
    const ks = await P.evaluate(() => [...document.querySelectorAll('#v-painel .ini-kpi')].map(b => ({ rota: b.dataset.iniRota || null, rolar: b.dataset.iniRolar || null, botao: b.tagName === 'BUTTON', regra: (b.querySelector('.ini-kpi-regra') || {}).textContent || '', lab: b.getAttribute('aria-label') || '' })));
    chk(ks.length === 4 && ks.every(k => k.botao && (k.rota || k.rolar) && /Como conta/.test(k.lab)), `4 indicadores, todos clicáveis e com a regra no rótulo: ${JSON.stringify(ks.map(k => k.rota || k.rolar))}`);
    chk(ks.filter(k => k.rota).every(k => /Como conta:/.test(k.regra)), 'cada indicador de lista tem a dica "Como conta"');
    await P.hover('#v-painel .ini-kpi[data-ini-rota="filas/conferir"]');
    chk(await P.isVisible('#v-painel .ini-kpi[data-ini-rota="filas/conferir"] .ini-kpi-regra'), 'a regra aparece ao passar o mouse');
    for (const [rota, sel, re] of [['filas/conferir', '#filas-body tr[data-fase]', /^filas\/conferir/], ['decisoes', '#dec-body tr[data-abrir]', /^decisoes/], ['filas/admin', null, /^filas\/admin/]]) {
      await abrirHome(P); await P.click(`#v-painel .ini-kpi[data-ini-rota="${rota}"]`); await P.waitForTimeout(1300);
      chk(re.test(await P.evaluate(() => rotaAtual())), `o indicador "${rota}" abre a lista filtrada`);
    }
    await abrirHome(P);
    await P.click('#ini-kpi-hoje'); await P.waitForTimeout(900);
    chk(await P.evaluate(() => document.activeElement && document.activeElement.id === 'ini-t-ritmo'), '"Folhas conferidas hoje" leva ao gráfico de Resultados');

    // ---------- fila: abas, 5 linhas, prioridade, responsável ----------
    await abrirHome(P);
    const pa = (await api(P, '/api/painel?fila=prioridade')).json, ab = pa.fila.abas;
    const abasTela = await P.evaluate(() => [...document.querySelectorAll('#ini-tarefas .ini-abas [data-ini-aba]')].map(b => [b.dataset.iniAba, +b.querySelector('b').textContent.replace(/\D/g, ''), b.getAttribute('aria-pressed')]));
    chk(JSON.stringify(abasTela.map(a => a[0])) === '["minha","todos","criticos","sem_responsavel"]' && abasTela.find(a => a[0] === 'sem_responsavel')[1] === ab.sem_responsavel && abasTela.find(a => a[0] === 'criticos')[1] === ab.criticos,
      `abas Minha fila · Todos · Críticos · Sem responsável com os números do servidor: ${JSON.stringify(abasTela)}`);
    chk(ab.minha === 0 && abasTela.find(a => a[0] === 'todos')[2] === 'true', 'sem nada atribuído, a Home abre em Todos');
    chk(await P.evaluate(() => document.getElementById('ini-ordem').value) === 'prioridade', 'a ordem padrão é "Prioridade"');
    let n = await P.locator('#ini-lista .ini-task').count();
    const nTodos = pa.fila.itens.filter(i => i.filtro !== 'base').length;
    chk(nTodos > 5 && n === 5 && /Ver todas as \d+ tarefas/.test(await P.innerText('#ini-lista [data-ini-vertodos]')), `no máximo 5 linhas (${n} de ${nTodos}) e "Ver todas as N tarefas"`);
    await P.click('#ini-lista [data-ini-vertodos]');
    chk(await P.locator('#ini-lista .ini-task').count() === nTodos, '"Ver todas" mostra todas as linhas');
    await P.click('#ini-lista [data-ini-vertodos]');
    const l0 = await P.evaluate(() => { const t = document.querySelector('#ini-lista .ini-task'); return { prio: (t.querySelector('.ini-prio') || {}).textContent || '', motivo: ((t.querySelector('.ini-motivo,.ini-prio-motivo') || {}).textContent || ''), mini: !!t.querySelector('.mini'), resp: (t.querySelector('.ini-resp') || {}).textContent || '', pri: t.querySelectorAll('.btn.pri').length, mais: !!t.querySelector('.ini-ignorar > summary') }; });
    chk(/Crítico|Alto|Médio|Baixo/.test(l0.prio) && /^Prioridade (crítica|alta|média|baixa)( porque .+)?$/.test(l0.motivo) && l0.mini && /Sem responsável/.test(l0.resp) && l0.pri === 1 && l0.mais,
      `a linha tem prioridade + o porquê, miniatura, responsável, UM botão principal e o "⋯": ${JSON.stringify(l0)}`);
    const notas = pa.fila.itens.filter(i => i.meu && i.filtro !== 'base').map(i => i.prioridade.nota);
    chk(notas.every((v, i) => !i || notas[i - 1] >= v), `a fila vem pela nota, da maior para a menor: ${notas.join(', ')}`);
    await P.click('#ini-tarefas [data-ini-aba="criticos"]');
    const crit = await P.evaluate(() => [...document.querySelectorAll('#ini-lista .ini-task')].map(t => t.dataset.prio));
    chk(crit.length === Math.min(5, ab.criticos) && crit.every(x => x === 'critico'), `aba Críticos: só as linhas críticas (${crit.length})`);
    await P.click('#ini-tarefas [data-ini-aba="minha"]');
    chk(/Nada está com você/.test(await P.innerText('#ini-lista')) && await P.locator('#ini-lista [data-ini-aba="todos"]').count() === 1, 'Minha fila vazia diz o próximo passo ("Pegar para mim") e leva a Todos');
    await P.click('#ini-lista [data-ini-aba="todos"]');
    const alvo = pa.fila.itens.find(i => i.filtro !== 'base' && i.adiar && /^(lote|pedido|decisao|erro):/.test(i.adiar));
    await P.click(`#ini-lista .ini-task:has([data-ini-adiar="${alvo.adiar}"]) .ini-ignorar > summary`);
    await P.click(`#ini-lista .ini-task:has([data-ini-adiar="${alvo.adiar}"]) [data-ini-atribuir="eu"]`);
    await P.waitForFunction(() => /Você ficou com/.test((document.getElementById('ini-fila-status') || {}).textContent || '') || !!document.querySelector('#ini-tarefas .ini-abas [data-ini-aba="minha"] b'), null, { timeout: 8000 });
    await P.waitForTimeout(1500);
    const minhaN = await P.evaluate(() => +document.querySelector('#ini-tarefas .ini-abas [data-ini-aba="minha"] b').textContent.replace(/\D/g, ''));
    await P.click('#ini-tarefas [data-ini-aba="minha"]');
    const minhas = await P.evaluate(() => [...document.querySelectorAll('#ini-lista .ini-task .ini-resp .ini-resp-n')].map(x => x.textContent.trim()));
    const evAtr = py("print(con.execute(\"SELECT COUNT(*) FROM evento WHERE tipo='tarefa_atribuida' AND ator='rafael@camp.arq.br'\").fetchone()[0])");
    chk(minhaN === 1 && minhas.length === 1 && minhas[0] === 'Você' && +evAtr === 1, `"Pegar para mim": a tarefa vai para a Minha fila com "Você" e fica no Histórico (${minhaN}, ${JSON.stringify(minhas)}, eventos ${evAtr})`);
    await P.click('#ini-tarefas [data-ini-aba="todos"]');

    // ---------- gargalo ----------
    const cam = await P.evaluate(() => { const b = document.querySelector('#ini-caminho [data-gargalo]'); return b ? { id: b.id, cls: b.closest('li').className, st: (b.querySelector('.st') || {}).textContent || '', esp: (b.querySelector('.ini-aguarda') || {}).textContent || '', cor: getComputedStyle(b).borderColor } : null; });
    chk(cam && cam.id === 'ini-passo-conferir' && /stuck/.test(cam.cls) && /gargalo/.test(cam.st) && /aguardando há 19 dias/.test(cam.esp), `o gargalo (espera acumulada) fica em amarelo, com "aguardando há 19 dias": ${JSON.stringify(cam)}`);
    chk(await P.locator('#ini-caminho .ini-passo.stuck').count() === 1, 'só um passo em amarelo');

    // ---------- sistemas: compacto quando saudável ----------
    const saude = await P.evaluate(() => { const o = window.iniSaudeLinhas;
      window.iniSaudeLinhas = () => [{ id: 'qnap', nome: 'QNAP', c: 'g', frase: 'ok' }, { id: 'campvision', nome: 'CAMP Vision', c: 'g', frase: 'ok' }, { id: 'site', nome: 'Site público', c: 'g', frase: 'ok' }, { id: 'estacoes', nome: 'Estações de captura', c: 'g', frase: 'ok' }];
      PAINEL_EST = PAINEL_EST || {}; iniSaudeAtualizar(); const el = document.getElementById('ini-saude'), vis = [...el.querySelectorAll('.ini-srv')].filter(x => x.checkVisibility()).length;
      const r1 = { vis, online: [...el.querySelectorAll('.ini-srv .ini-pill')].filter(x => x.textContent === 'Online').length, frases: [...el.querySelectorAll('.ini-srv-t p')].filter(x => x.getBoundingClientRect().width > 2).length, alt: Math.round(el.querySelector('.ini-saude-lista').getBoundingClientRect().height) };
      window.iniSaudeLinhas = () => [{ id: 'qnap', nome: 'QNAP', c: 'r', frase: 'desconectado' }, { id: 'site', nome: 'Site público', c: 'g', frase: 'ok' }];
      iniSaudeAtualizar(); const q = el.querySelector('.ini-srv[data-srv="qnap"]'); const r2 = { vis: [...el.querySelectorAll('.ini-srv')].filter(x => x.checkVisibility()).map(x => x.dataset.srv), frase: /desconectado/.test(q.innerText), pill: q.querySelector('.ini-pill').textContent };
      window.iniSaudeLinhas = o; iniSaudeAtualizar(); return { r1, r2 }; });
    chk(saude.r1.vis === 4 && saude.r1.online === 4 && saude.r1.frases === 0 && saude.r1.alt < 170, `tudo normal: uma linha por sistema com ✓ e "Online", sem frase (na dica): ${JSON.stringify(saude.r1)}`);
    chk(JSON.stringify(saude.r2.vis) === '["qnap","site"]' && saude.r2.frase && saude.r2.pill === 'crítico', `com falha: o que falha vem primeiro, com o selo e a frase: ${JSON.stringify(saude.r2)}`);

    // ---------- progresso e conquistas ----------
    chk(/Meta da semana/.test(await P.innerText('#ini-meta')) && /de 100 pontos validados/.test(await P.innerText('#ini-meta')), 'meta coletiva da semana no alto ("de 100 pontos validados")');
    chk(/Nível 1/.test(await P.innerText('#ini-jogo')) && /XP/.test(await P.innerText('#ini-jogo')) && !!(await P.$('#ini-jogo #ini-ranking')), 'nível pessoal com XP; Ranking da equipe (mês) ligado por padrão');
    await P.click('#ini-jogo .ini-conq-todas > summary'); await P.click('#ini-jogo [data-ini-conquistas="1"]'); await P.waitForTimeout(1200);
    chk(/ocultou/.test(await P.innerText('#ini-jogo')) && !/Nível 1/.test(await P.innerText('#ini-jogo')), '"Ocultar conquistas" esconde o nível e as conquistas');
    await P.click('#ini-jogo [data-ini-conquistas="0"]'); await P.waitForTimeout(1200);
    chk(/Nível 1/.test(await P.innerText('#ini-jogo')), '"Mostrar de novo" traz de volta');

    // ---------- Resultados: período comum ----------
    const pedRitmo = []; P.on('request', r => { if (/\/api\/painel\/ritmo\?dias=30/.test(r.url())) pedRitmo.push(1); });
    await P.selectOption('#ini-per', '30'); await P.waitForTimeout(1500);
    chk(pedRitmo.length >= 1 && /últimos 30 dias/.test(await P.innerText('#ini-t-ritmo')), 'o período dos Resultados (30 dias) muda o ritmo');
    await P.selectOption('#ini-per', '14'); await P.waitForTimeout(600);
    // visitas sem dados do Google Analytics (semente): aviso compacto, não a caixa vermelha grande
    const vis = await P.evaluate(() => { const v = document.querySelector('#ini-visitas .ini-vazio-c'); return v ? { alt: Math.round(v.getBoundingClientRect().height), t: v.innerText, tentar: !!v.querySelector('[data-vm-tentar]') } : null; });
    chk(!vis || (vis.alt < 140 && /Dados de audiência temporariamente indisponíveis/.test(vis.t) && vis.tentar), `visitas indisponíveis: aviso compacto com "Tentar de novo" ${JSON.stringify(vis)}`);

    // ---------- teclado ----------
    await P.focus('#ini-tarefas [data-ini-aba="todos"]'); await P.keyboard.press('Tab');
    chk(await P.evaluate(() => document.activeElement && document.activeElement.matches('#ini-tarefas [data-ini-aba]')), 'as abas andam com Tab');

    // ---------- leitura: sem Minha fila e sem "⋯" ----------
    const le = await entrar(browser, 'leitor@camp.arq.br', 'senha-leitor-1234', erros).catch(() => null);
    if (le) {
      await abrirHome(le.page);
      chk(!(await le.page.$('#ini-tarefas [data-ini-aba="minha"]')) && !(await le.page.$('#ini-lista .ini-ignorar')) && !(await le.page.$('#ini-lista [data-ini-acao]')), 'leitura: sem "Minha fila", sem "⋯" e sem botão de ação');
      await le.ctx.close();
    } else chk(true, '(semente sem usuário de leitura: pulado)');

    // ---------- celular 390 ----------
    const cel = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros, 390);
    await abrirHome(cel.page);
    const ov = await cel.page.evaluate(() => ({ doc: document.documentElement.scrollWidth - innerWidth, v: (() => { const v = document.getElementById('v-painel'); return v.scrollWidth - v.clientWidth })(),
      largos: [...document.querySelectorAll('#v-painel *')].filter(e => e.checkVisibility() && e.getBoundingClientRect().right > innerWidth + 1 && !e.closest('.abas-sit,.rt-g,.vm-graf,.vm')).slice(0, 5).map(e => (e.className || e.tagName) + ':' + (e.textContent || '').slice(0, 40)) }));
    chk(ov.doc <= 0 && ov.v <= 0 && !ov.largos.length, `390 px: nenhuma rolagem lateral ${JSON.stringify(ov)}`);
    const pilha = await cel.page.evaluate(() => { const a = document.querySelector('.ini-col-princ').getBoundingClientRect(), b = document.querySelector('.ini-lateral').getBoundingClientRect(); return b.top >= a.bottom - 1; });
    chk(pilha, '390 px: a coluna da direita desce para baixo (tudo empilhado)');
    await cel.ctx.close();
    chk(!erros.length, 'nenhum erro de JavaScript: ' + erros.slice(0, 5).join(' | '));
  } catch (e) { chk(false, 'exceção: ' + (e && e.stack || e)); }
  finally { await browser.close(); }
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
