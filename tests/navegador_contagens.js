// UX-05 no navegador de verdade (Playwright + Chromium): a MESMA métrica mostra o MESMO número em todas as telas.
// Prova: o número do menu "Precisa de você" = o da saudação = /api/pendencias.precisa_de_voce; o cartão "lotes para conferir" da Home
// = lotes_conferir; em Material novo o filtro "Chegando" e o resumo ("N chegando") dizem o mesmo número, "Precisam de você" = as linhas
// mostradas e "N registros" não conta as linhas de grupo; Máquinas diz o mesmo material novo; o topo herda o pior estado
// (QNAP com 12% livre deixa o ponto do topo em atenção, não "ok"); Home e Material novo dizem "atualizado há X". Nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux05.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux05.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8942)
//   CAMP_DB_PATH=/tmp/ux05.db CAMP_BASE=http://127.0.0.1:8942 node tests/navegador_contagens.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8942', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || undefined;
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// o QNAP com 12% livre (atenção) e um projeto descartado com lote em revisão (não pode contar em lugar nenhum)
py(`
import tempfile, os
raiz = tempfile.mkdtemp(); os.mkdir(os.path.join(raiz, "ACERVOS_CAMP"))     # QNAP "conectado" (pasta com conteúdo)
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.raiz'", (raiz,))
con.execute("DELETE FROM qnap_snapshot")   # sem a série da semana: o nível vem só dos 12% (UX-02: o ritmo também conta)
con.execute("INSERT INTO qnap_snapshot (montado, total_gb, livre_gb, entrada_bruta, prontos) VALUES (1, 1000, 120, 3, 4)")
f = con.execute("SELECT codigo FROM fundo ORDER BY codigo LIMIT 1").fetchone()[0]
n = con.execute("SELECT COALESCE(MAX(numero),0)+1 FROM numero_p WHERE fundo_codigo=?", (f,)).fetchone()[0]
con.execute("INSERT INTO numero_p (fundo_codigo,numero) VALUES (?,?)", (f, n))
cod = "%s-P%04d" % (f, n)
con.execute("INSERT INTO projeto (codigo,fundo_codigo,numero,titulo,ano,descartado_em) VALUES (?,?,?,'Descartado de teste',1970,datetime('now'))", (cod, f, n))
con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote descartado', ?, '/x', 'revisao')", (cod,))
`);

(async () => {
  const browser = await chromium.launch(CHROME ? { executablePath: CHROME } : {});
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=|\/api\/analytics/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  const api = (url) => page.evaluate(async u => { const r = await fetch(u, { credentials: 'same-origin' }); return r.json().catch(() => null); }, url);
  const txt = sel => page.evaluate(s => { const e = document.querySelector(s); return e ? e.textContent.replace(/\s+/g, ' ').trim() : ''; }, sel);
  const num = t => { const m = String(t || '').replace(/\./g, '').match(/\d+/); return m ? +m[0] : 0; };
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => nav('painel'));
    await page.waitForSelector('#ini-saud', { timeout: 15000 }); await page.waitForTimeout(1200);
    const pend = await api('/api/pendencias');
    chk(pend && pend.precisa_de_voce === (pend.pedem_acao || {}).precisa_de_voce && !!pend.medido_em, '/api/pendencias: "precisa_de_voce" é o mesmo número de pedem_acao (a regra única do menu, UX-19) e traz "medido_em": ' + JSON.stringify(pend && { p: pend.precisa_de_voce, pa: (pend.pedem_acao || {}).precisa_de_voce, m: pend.medido_em }));
    const badge = num(await txt('#n-gente')), saud = await txt('#ini-saud');
    chk(badge === pend.precisa_de_voce, `menu "Precisa de você" = ${pend.precisa_de_voce} (mostra ${badge})`);
    chk(pend.precisa_de_voce ? new RegExp('\\b' + pend.precisa_de_voce + ' coisas? pedem? você').test(saud) : /Tudo em dia/.test(saud), `a saudação diz o MESMO número do menu: "${saud}"`);
    const kpi = await page.evaluate(() => { const b = document.querySelector('.ini-kpi[data-ini-rota="filas/conferir"] .v'); return b ? b.textContent : ''; });
    chk(num(kpi) === pend.lotes_conferir, `cartão "lotes para conferir" da Home = ${pend.lotes_conferir} (mostra ${kpi})`);
    chk(/atualizado (agora|há)/.test(await txt('#v-painel .ph')), 'Home: "atualizado há X" ao lado dos números de "O que fazer agora"');

    // ---- topo: o pior estado ----
    await page.waitForFunction(() => !!document.querySelector('#machine-status .ms-ponto'), null, { timeout: 20000 });
    const est = await api('/api/estacoes');
    const ponto = await page.evaluate(() => { const p = document.querySelector('#machine-status .ms-ponto'); return { cls: p.className, nivel: p.dataset.estadoGeral }; });
    chk(est.estado_geral && ['atencao', 'critico'].includes(est.estado_geral.nivel), 'com QNAP em 12% livre o estado geral não é "ok": ' + JSON.stringify(est.estado_geral && est.estado_geral.nivel));
    chk(ponto.nivel === est.estado_geral.nivel && !/\bon\b/.test(ponto.cls), `o ponto do topo herda o pior estado (${est.estado_geral.nivel}): classe "${ponto.cls}"`);
    const topo = await txt('#machine-status .ms-resumo');
    chk(/QNAP em atenção/.test(topo) && !/QNAP ok/.test(topo), `o topo não diz mais "QNAP ok" com o QNAP em atenção: "${topo}"`);
    chk(new RegExp(`${est.estacoes_resumo.ligadas} de ${est.estacoes_resumo.total} estações ligadas`).test(topo), `topo: estações de captura pela mesma conta da Home (${est.estacoes_resumo.ligadas} de ${est.estacoes_resumo.total}): "${topo}"`);

    // ---- Material novo ----
    await page.evaluate(() => nav('filas')); await page.waitForSelector('#fila-chips [data-fila-filtro]', { timeout: 15000 }); await page.waitForTimeout(800);
    const filas = await api('/api/filas');
    chk(Array.isArray(filas) && !filas.some(l => /Descartado de teste/.test(l.projeto_titulo || '')), 'a Fila não mostra o lote do projeto descartado');
    const chipN = async k => num(await page.evaluate(k_ => { const b = document.querySelector(`#fila-chips [data-fila-filtro="${k_}"] b`); return b ? b.textContent : ''; }, k));
    const resumo = await txt('#fila-resumo');
    const cheg = (resumo.match(/(\d+) chegando/) || [])[1];
    chk(await chipN('chegando') === (cheg ? +cheg : 0), `filtro "Chegando" (${await chipN('chegando')}) = resumo "${resumo}"`);
    chk(await chipN('chegando') === pend.lotes_processando + pend.lotes_importar, `"Chegando" = CAMP Vision lendo + falta importar das contagens (${pend.lotes_processando}+${pend.lotes_importar})`);
    const conf = (resumo.match(/(\d+) para conferir/) || [])[1];
    chk((conf ? +conf : 0) === pend.lotes_conferir, `resumo "para conferir" = ${pend.lotes_conferir} (o cartão da Home)`);
    await page.click('#fila-chips [data-fila-filtro="gente"]'); await page.waitForTimeout(400);
    const vis = await page.locator('#filas-body tr[data-fase]').count();
    chk(await chipN('gente') === vis, `"Precisam de você" (${await chipN('gente')}) = as linhas mostradas (${vis})`);
    const cnt = await txt('#v-filas .cnt');
    chk(!cnt || num(cnt) === vis, `"N registros" não conta as linhas de grupo: "${cnt}" × ${vis} linhas`);
    chk(/atualizado (agora|há)/.test(resumo), 'Material novo: "atualizado há X" no resumo: "' + resumo + '"');

    // ---- Máquinas ----
    await page.evaluate(() => nav('estacoes')); await page.waitForFunction(() => /esperando importar e conferir/.test(document.getElementById('est-body').textContent), null, { timeout: 25000 });
    const parado = await page.evaluate(() => { const li = [...document.querySelectorAll('#est-body .est-parado li')].find(x => /esperando importar e conferir/.test(x.textContent)); return li ? li.textContent : ''; });
    chk(num(parado) === pend.material_novo, `Máquinas: "lotes lidos esperando importar e conferir" = material novo do menu (${pend.material_novo}): "${parado.slice(0, 80)}"`);
    await page.setViewportSize({ width: 390, height: 800 }); await page.evaluate(() => nav('filas')); await page.waitForTimeout(1200);
    chk(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'celular: Material novo sem rolagem lateral');
  } catch (e) { chk(false, 'o teste quebrou: ' + e.message); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma resposta de erro do servidor' + (falhas.length ? ': ' + falhas.slice(0, 5).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
