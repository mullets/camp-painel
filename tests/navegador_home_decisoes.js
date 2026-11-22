// CAMP-HOME-UX (decisões do Rafael, 22/11/2026) no navegador de verdade (Playwright + Chromium):
//  1. o Ranking da equipe (mês) aparece LIGADO por padrão na Home (coluna da direita) e em Problemas: posição, nome e pontos do mês,
//     com o "?" dizendo que não serve para avaliar desempenho;
//  2. um admin desliga em Configurações (a caixa "Mostrar o Ranking da equipe…") e ele some das duas telas; religa e volta;
//  3. os cartões da Home mostram folhas E lotes: "folhas para conferir" + "em N lotes" e "folhas esperam um admin" + "em N lotes: …",
//     com os números da rota (/api/pendencias); "folhas conferidas hoje" continua em folhas.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/x/hd.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/x/hd.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8960)
//   CAMP_DB_PATH=/tmp/x/hd.db CAMP_BASE=http://127.0.0.1:8960 node tests/navegador_home_decisoes.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8960', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// um lote PARA APROVAR com 4 folhas conferidas NESTE mês (3 de Rafael, 1 da Estagiária): dá ao cartão "esperam um admin" folhas e lotes
// diferentes, e ao ranking posição, nome e pontos (idempotente)
py(`
if not con.execute("SELECT 1 FROM lista_processamento WHERE nome='[home-decisoes]'").fetchone():
    p=con.execute("SELECT codigo, COALESCE(ano,1970) FROM projeto WHERE codigo NOT LIKE 'F000%' ORDER BY codigo LIMIT 1").fetchone()
    lote=con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('[home-decisoes]',?,'/hd','revisao')",(p[0],)).lastrowid
    for n in range(1,5):
        con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,lote_id,revisao,revisado_por,revisado_em,origem) VALUES (?,?,?,?,?,?,'conferida',?,datetime('now'),'campvision')",
                    ('%s-%s-S01-D09%03d'%(p[0],p[1],n),p[0],'S01',9000+n,'Folha %d'%n,lote,'rafael@camp.arq.br' if n<4 else 'operador@camp.arq.br'))
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } }); const P = await ctx.newPage();
  P.on('pageerror', e => erros.push(e.message)); P.on('dialog', d => d.dismiss().catch(() => {}));
  const api = (url) => P.evaluate(u => fetch(u, { credentials: 'same-origin' }).then(r => r.json()), url);
  const home = async () => { await P.evaluate(() => nav('painel')); await P.waitForSelector('#v-painel .ini-kpi[data-ini-rota="filas/conferir"]', { timeout: 15000 });
    await P.waitForFunction(() => typeof PAINEL_PG !== 'undefined' && PAINEL_PG !== null, null, { timeout: 15000 }); await P.waitForTimeout(500); };
  const problemasTela = async () => { await P.evaluate(() => nav('erros')); await P.waitForFunction(() => { const l = document.getElementById('cp-lateral'); return l && /Atividade recente/.test(l.textContent); }, null, { timeout: 15000 }); await P.waitForTimeout(300); };
  try {
    await P.goto(BASE + '/'); await P.fill('#lg-email', 'rafael@camp.arq.br'); await P.fill('#lg-senha', 'senha-bem-longa-123'); await P.press('#lg-senha', 'Enter');
    await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await home();
    // ---------- 1. Ranking da equipe (mês) na Home ----------
    const pg = await api('/api/painel/progresso');
    chk(Array.isArray(pg.equipe) && pg.equipe.length >= 2 && pg.equipe_periodo === 'mes', `ranking ligado por padrão: o servidor manda o ranking do mês (${JSON.stringify(pg.equipe)})`);
    const rh = await P.evaluate(() => { const r = document.getElementById('ini-ranking'); if (!r) return null; const b = r.getBoundingClientRect();
      return { t: r.querySelector('h3').textContent.replace(/\s+/g, ' ').trim(), vis: b.width > 0 && b.height > 0, col: !!r.closest('.ini-col:not(.ini-col-princ), aside, .ini-lado') || !r.closest('.ini-col-princ'),
        li: [...r.querySelectorAll('ol.cp-rank li')].map(li => ({ n: li.querySelector('.cp-rank-n').textContent.trim(), nome: li.children[1].textContent.trim(), pts: li.querySelector('b').textContent.trim() })) }; });
    chk(rh && rh.vis && rh.t === 'Ranking da equipe (mês)', `Home: o cartão "Ranking da equipe (mês)" aparece (${rh && rh.t})`);
    chk(rh && rh.col, 'Home: o ranking fica na coluna da direita (fora da coluna principal)');
    chk(rh && rh.li.length === pg.equipe.length && rh.li.every((x, i) => x.n === String(i + 1) && x.nome === pg.equipe[i].nome && x.pts === `${pg.equipe[i].pontos} ${pg.equipe[i].pontos === 1 ? 'ponto' : 'pontos'}`),
      `Home: posição, nome e pontos do mês, na ordem do servidor (${JSON.stringify(rh && rh.li)})`);
    if (await P.$('#ini-ranking .rank-q > summary')) await P.click('#ini-ranking .rank-q > summary');
    const qh = await P.evaluate(() => { const d = document.querySelector('#ini-ranking .rank-q'); const n = d && d.querySelector('[role=note]'); return { open: !!(d && d.open), vis: !!n && n.getBoundingClientRect().height > 0, t: n ? n.textContent : '' }; });
    chk(qh.open && qh.vis && /não serve para avaliar desempenho/.test(qh.t) && /neste mês/.test(qh.t), `Home: o "?" do ranking diz que é do mês e que não serve para avaliar desempenho ("${qh.t.slice(0, 120)}")`);
    if (qh.open) await P.click('#ini-ranking .rank-q > summary');
    // ---------- 3. cartões: folhas E lotes ----------
    const pend = await api('/api/pendencias');
    const ks = await P.evaluate(() => Object.fromEntries([...document.querySelectorAll('#v-painel .ini-kpi')].map(b => [b.dataset.iniRota || b.id, { v: b.querySelector('.v').textContent.trim(), l: b.querySelector('.l').textContent.trim(), d: b.querySelector('.d').textContent.trim() }])));
    const n = s => +String(s).replace(/\D/g, '');
    const kc = ks['filas/conferir'], ka = ks['filas/admin'], kh = ks['ini-kpi-hoje'];
    const lotes = q => `em ${q} ${q === 1 ? 'lote' : 'lotes'}`;
    chk(kc && n(kc.v) === pend.folhas_conferir && /^folhas? para conferir$/.test(kc.l) && kc.d === lotes(pend.lotes_conferir),
      `"Para conferir": número grande = folhas (${pend.folhas_conferir}), embaixo "${lotes(pend.lotes_conferir)}" (mostra ${JSON.stringify(kc)})`);
    chk(pend.lotes_aprovar >= 1 && pend.folhas_aprovar >= 4 && pend.folhas_esperam_admin > pend.esperam_admin, `há um lote para aprovar com folhas (lotes ${pend.esperam_admin}, folhas ${pend.folhas_esperam_admin})`);
    chk(typeof pend.folhas_esperam_admin === 'number' && ka && n(ka.v) === pend.folhas_esperam_admin && /^folhas? esperam? um admin$/.test(ka.l)
      && ka.d === `${lotes(pend.esperam_admin)}: ${pend.lotes_aprovar} para aprovar, ${pend.lotes_publicar} para publicar`,
      `"Esperam um admin": folhas (${pend.folhas_esperam_admin}) e "${lotes(pend.esperam_admin)}: ${pend.lotes_aprovar} para aprovar, ${pend.lotes_publicar} para publicar" (mostra ${JSON.stringify(ka)})`);
    chk(kh && /conferidas? hoje/.test(kh.l), `"Folhas conferidas hoje" continua em folhas (${kh && kh.l})`);
    chk(!ks.decisoes || /decis/.test(ks.decisoes.l), 'Decisões continuam decisões (quando há)');
    // ---------- 1. o mesmo ranking em Problemas ----------
    await problemasTela();
    const rp = await P.evaluate(() => { const r = document.getElementById('cp-ranking'); if (!r) return null; return { t: r.querySelector('h2').textContent.replace(/\s+/g, ' ').trim(), nomes: [...r.querySelectorAll('ol.cp-rank li')].map(li => li.children[1].textContent.trim()), aviso: !!r.querySelector('.rank-q') }; });
    chk(rp && /Ranking da equipe \(mês\)$/.test(rp.t) && JSON.stringify(rp.nomes) === JSON.stringify(pg.equipe.map(x => x.nome)), `Problemas: o card "Ranking da equipe (mês)" com as mesmas pessoas, na mesma ordem (${JSON.stringify(rp)})`);
    if (await P.$('#cp-ranking .rank-q > summary')) await P.click('#cp-ranking .rank-q > summary');
    chk(await P.evaluate(() => { const n = document.querySelector('#cp-ranking .rank-q [role=note]'); return !!n && /não serve para avaliar desempenho/.test(n.textContent); }), 'Problemas: o "?" do ranking diz que não serve para avaliar desempenho');
    // ---------- 2. um admin desliga em Configurações ----------
    await P.evaluate(() => nav('config')); await P.waitForSelector('#cfg-ranking', { timeout: 15000 });
    chk(await P.isChecked('#cfg-ranking') && await P.isEnabled('#cfg-ranking'), 'Configurações: a caixa "Mostrar o Ranking da equipe (mês)" vem marcada e o admin pode mexer');
    await P.click('#cfg-ranking'); await P.waitForFunction(() => { const c = document.getElementById('cfg-ranking'); return c && !c.checked && !c.disabled; }, null, { timeout: 10000 });
    const cfg = (await api('/api/config')).find(x => x.chave === 'jogo.ranking_equipe');
    chk(cfg && cfg.valor === '0' && cfg.atualizado_por === 'rafael@camp.arq.br', `desmarcar grava jogo.ranking_equipe = 0 com quem mudou (${JSON.stringify(cfg && { v: cfg.valor, por: cfg.atualizado_por })})`);
    await home();
    chk(!(await P.$('#ini-ranking')), 'desligado: o ranking some da Home');
    await problemasTela();
    chk(!(await P.$('#cp-ranking')), 'desligado: o ranking some de Problemas');
    await P.evaluate(() => nav('config')); await P.waitForSelector('#cfg-ranking', { timeout: 15000 });
    await P.click('#cfg-ranking'); await P.waitForFunction(() => { const c = document.getElementById('cfg-ranking'); return c && c.checked && !c.disabled; }, null, { timeout: 10000 });
    await home();
    chk(!!(await P.$('#ini-ranking')), 'religado: o ranking volta à Home');
    chk(!(await P.evaluate(() => typeof temAlteracoes === 'function' && temAlteracoes())), 'a caixa do ranking não deixa "alterações não salvas" pendentes');
    chk(erros.length === 0, 'nenhum erro de JavaScript' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  } catch (e) { chk(false, 'exceção: ' + e.message); }
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
