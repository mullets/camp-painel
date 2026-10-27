// UX-22 (26/10): o aviso "F009-P0019 publicado…" ficava preso no topo; números carregando apareciam como "0".
// Prova no navegador de verdade (Playwright + Chromium):
//  - todo toast fecha sozinho em até 8 s (mesmo pedido com ms maior) e fica em "Tarefas e avisos recentes" (menu do avatar);
//  - o chip de tarefa concluída com sucesso some sozinho em 8 s e continua na lista de tarefas; o de falha (✖) fica até fechar;
//  - lista carregando mostra esqueleto no contador (nunca "0 registros"), e depois o número de verdade;
//  - topo: estação ainda não medida = esqueleto (nunca "0 de N máquinas ligadas"); abas de Fundos antes da lista = esqueleto;
//  - nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ux22.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux22.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8945)
//   CAMP_DB_PATH=/tmp/ux22.db CAMP_BASE=http://127.0.0.1:8945 node tests/navegador_ux22_avisos.js
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8945';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  const toastOn = () => page.evaluate(() => document.getElementById('toast').classList.contains('on'));
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU && AJUDA_VISTAS !== null, null, { timeout: 15000 });
    await page.waitForTimeout(1500);
    await page.evaluate(() => clearTimeout(TAREFAS_TIMER));   // sem consulta periódica no meio do teste

    // ---- toasts: fecham em até 8 s, até o pedido com ms maior; ficam no histórico ----
    await page.evaluate(() => toast('F009-P0019 publicado com 12 folhas', { ms: 20000 }));
    chk(await toastOn(), 'o toast aparece');
    await page.waitForTimeout(8600);
    chk(!(await toastOn()), 'o toast fecha sozinho em até 8 s (mesmo pedido com ms: 20000)');
    await page.evaluate(() => toast('Salvo'));
    await page.waitForTimeout(3000);
    chk(!(await toastOn()), 'toast simples continua fechando rápido');
    await page.click('.who'); await page.click('[data-who="avisos"]');
    await page.waitForSelector('#d-body [data-avisos-hist] .toast-hist', { timeout: 5000 });
    const hist = await page.evaluate(() => document.querySelector('#d-body [data-avisos-hist]').textContent);
    chk(/F009-P0019 publicado com 12 folhas/.test(hist) && /Salvo/.test(hist) && hist.indexOf('Salvo') < hist.indexOf('F009-P0019'), 'menu do avatar › Tarefas e avisos recentes: os avisos desta sessão, o mais novo primeiro');
    await page.evaluate(() => closeDrawer(true)); await page.waitForTimeout(300);
    await page.reload(); await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU && AJUDA_VISTAS !== null, null, { timeout: 15000 }); await page.waitForTimeout(800);
    chk(await page.evaluate(() => TOAST_HIST.some(a => /F009-P0019/.test(a.m))), 'o histórico sobrevive a recarregar a página (mesma aba)');
    await page.evaluate(() => clearTimeout(TAREFAS_TIMER));

    // ---- chip de tarefa concluída ----
    const tarefa = (id, estado, quando) => ({ id, tipo: 'publicar', projeto_codigo: 'F009-P0019', ator: 'rafael@camp.arq.br', estado, etapa: 'fim', feitas: 12, total: 12, iniciada_em: quando, terminada_em: quando, log: [], falhas: [], resultado: { mensagem: 'F009-P0019 publicado' } });
    await page.evaluate(t => { TAREFAS_EST = { rodando: [], terminadas: [t] }; desenharChipTarefas(); }, tarefa(9101, 'ok', '2099-01-01 10:00:00'));
    const chipVisivel = () => page.evaluate(() => !document.getElementById('tarefas-chip').hidden);
    chk(await chipVisivel(), 'tarefa concluída: o chip "✔ …" aparece no topo');
    await page.waitForTimeout(8700);
    chk(!(await chipVisivel()), 'e some sozinho em 8 s (antes ficava preso até clicar)');
    chk(await page.evaluate(() => { abrirTarefas(); clearTimeout(TAREFAS_TIMER); return /F009-P0019/.test(document.querySelector('#d-body [data-tarefas-lista]').textContent); }), 'a tarefa continua na lista "Suas tarefas das últimas 24 h"');
    await page.waitForTimeout(500); await page.evaluate(() => clearTimeout(TAREFAS_TIMER));
    await page.evaluate(() => closeDrawer(true));
    await page.evaluate(t => { TAREFAS_EST = { rodando: [], terminadas: [t] }; desenharChipTarefas(); }, tarefa(9102, 'erro', '2099-01-02 10:00:00'));
    await page.waitForTimeout(9000);
    chk(await chipVisivel(), 'tarefa que FALHOU (✖): o chip fica até a pessoa fechar');
    await page.evaluate(() => marcarTarefasVistas());

    // ---- números carregando: esqueleto, nunca 0 ----
    await page.route('**/api/filas**', async r => { await new Promise(x => setTimeout(x, 3500)); try { await r.continue(); } catch (_) {} });
    await page.evaluate(() => { document.querySelector('#filas-body').innerHTML = '<tr><td colspan="4" class="empty">Carregando…</td></tr>'; nav('filas'); carregarFilas(); });
    await page.waitForTimeout(900);
    const cntCarregando = await page.evaluate(() => { const c = document.querySelector('#v-filas .cnt'); return { skel: !!c.querySelector('.num-skel'), txt: c.textContent }; });
    chk(cntCarregando.skel && !/^0/.test(cntCarregando.txt), 'lista carregando: o contador mostra esqueleto, não "0 registros" (' + JSON.stringify(cntCarregando) + ')');
    await page.waitForFunction(() => !document.querySelector('#v-filas .cnt .num-skel'), null, { timeout: 15000 }).catch(() => {});
    const cntDepois = await page.evaluate(() => document.querySelector('#v-filas .cnt').textContent);
    chk(/registro/.test(cntDepois), 'carregada: o número de verdade (' + cntDepois + ')');
    await page.unroute('**/api/filas**');

    const topo = await page.evaluate(() => { atualizarTopoEstacoes({ maquinas: [{ tipo: 'foto', nome: 'Estação Foto 1', ip: '192.0.2.1', online: null, config_chave: 'estacao.foto1.ip' }, { tipo: 'armazenamento', nome: 'QNAP', ip: null, online: null }], site: { http: null } });
      const r = document.querySelector('#machine-status .ms-resumo'); return { skel: r.querySelectorAll('.num-skel').length, txt: r.textContent }; });
    chk(topo.skel === 2 && !/0 de 1/.test(topo.txt), 'topo: estação e site ainda não medidos = esqueleto, nunca "0 de 1 máquinas ligadas" (' + JSON.stringify(topo) + ')');
    const topo2 = await page.evaluate(() => { atualizarTopoEstacoes({ maquinas: [{ tipo: 'foto', nome: 'Estação Foto 1', ip: '192.0.2.1', online: false, config_chave: 'estacao.foto1.ip' }], site: { http: { estado: 'online', ok: true } } });
      return document.querySelector('#machine-status .ms-resumo').textContent; });
    chk(/0 de 1/.test(topo2), 'medida e desligada: aí sim "0 de 1" (' + topo2.trim() + ')');
    const ff = await page.evaluate(() => { const g = FUNDOS_API; FUNDOS_API = null; atualizarContadoresFundos(); const r = !!document.querySelector('#ffc-todos .num-skel'); FUNDOS_API = g; atualizarContadoresFundos(); return [r, document.getElementById('ffc-todos').textContent]; });
    chk(ff[0] && /^\d+$/.test(ff[1]), 'Fundos: abas antes da lista chegar = esqueleto; depois o número (' + JSON.stringify(ff) + ')');
    chk(erros.length === 0, 'nenhum erro no console: ' + erros.slice(0, 3).join(' | '));
  } catch (e) {
    chk(false, 'o teste quebrou: ' + (e && e.stack || e));
  } finally {
    await browser.close();
    console.log(linhas.join('\n'));
    console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
    process.exit(problemas.length ? 1 : 0);
  }
})();
