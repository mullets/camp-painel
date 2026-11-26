// CAMP-UX/ENTREGA/PROJETO (26/11/2026) — itens autorizados pelo Rafael no quiz da revisão de usabilidade.
// [1] "Situação do projeto" sem rolagem interna; fixa (sticky) só quando cabe inteira; o fim ("Ver requisitos") alcançável rolando a tela.
// [2] item aberto no endereço (#tela/<id>): abrir empilha, Voltar fecha e fica na tela, recarregar reabre, Esc não duplica.
// [5] PDF dos TIFF: acima de exportacao_pdf.aviso_gb pede confirmação com o tamanho estimado.
// Uso (servidor PRÓPRIO, banco com tests/semear_banco_teste.py + semente_financeiro.py + semente_originais.py):
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9180 node tests/navegador_autorizados.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9180';
const PRINTS = process.env.PRINTS || '/dev/shm';
const SO = (process.env.SO || '').split(',').filter(Boolean);
const problemas = [];
const chk = (ok, msg) => { console.log((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
const roda = k => !SO.length || SO.includes(k);
async function entrar(br, w, h) {
  const pg = await br.newPage({ viewport: { width: w, height: h } });
  pg.erros = []; pg.on('pageerror', e => pg.erros.push(e.message)); pg.on('dialog', d => d.dismiss().catch(() => {}));
  await pg.goto(BASE + '/');
  await pg.fill('#lg-email', 'rafael@camp.arq.br'); await pg.fill('#lg-senha', 'senha-bem-longa-123'); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  await pg.addStyleTag({ content: '#toast,.toast{display:none!important}' });
  return pg;
}
(async () => {
  const br = await chromium.launch();
  if (roda('1')) for (const [w, h] of [[1440, 900], [2000, 1100]]) {
    const pg = await entrar(br, w, h);
    await pg.goto(BASE + '/#projeto/F023-P0011');
    await pg.waitForSelector('.pj-vg-lado', { state: 'visible', timeout: 20000 });
    await pg.waitForTimeout(1200);
    // muitas pendências: o bloco "O que falta" fica bem alto (como num projeto real com várias pendências)
    await pg.evaluate(() => { let f = document.getElementById('teste-pend'); if (!f) { f = document.createElement('div'); f.id = 'teste-pend'; f.className = 'pj-falta'; document.querySelector('.pj-vg-lado').appendChild(f); } f.innerHTML = '<b>O que falta para fechar este projeto</b><ol>' + Array.from({ length: 28 }, (_, i) => `<li>Pendência de teste nº ${i + 1}: uma frase de tamanho comum explicando o que falta.</li>`).join('') + '</ol><a id="fim-teste" href="#">Ver requisitos</a>'; });
    await pg.waitForTimeout(400);
    const r = await pg.evaluate(() => { const l = document.querySelector('.pj-vg-lado'); const cs = getComputedStyle(l); return { ov: cs.overflowY, pos: cs.position, mh: cs.maxHeight, fixa: l.classList.contains('pj-lado-fixa'), alto: l.scrollHeight, vis: l.clientHeight }; });
    chk(r.ov === 'visible' && r.mh === 'none', `[1] ${w}px: a coluna não rola por dentro (overflow ${r.ov}, max-height ${r.mh})`);
    chk(!r.fixa && r.pos !== 'sticky', `[1] ${w}px: alta demais para a tela → não fica fixa (${r.pos})`);
    await pg.evaluate(() => { const m = document.querySelector('.main'); m.scrollTop = m.scrollHeight; });
    await pg.waitForTimeout(300);
    const fim = await pg.evaluate(() => { const a = document.getElementById('fim-teste').getBoundingClientRect(); const m = document.querySelector('.main').getBoundingClientRect(); return a.top >= m.top && a.bottom <= m.bottom + 1; });
    chk(fim, `[1] ${w}px: rolando a tela até o fim, "Ver requisitos" aparece`);
    if (w === 1440) await pg.screenshot({ path: PRINTS + '/lateral-projeto-1440.png' });
    // pouca coisa: cabe → fixa ao rolar
    await pg.evaluate(() => { const f = document.getElementById('teste-pend'); f.innerHTML = '<b>O que falta</b><ol><li>Uma pendência.</li></ol>'; [...document.querySelector('.pj-vg-lado').children].forEach(x => { if (x !== f && !x.matches('.pj-lado-tit')) x.style.display = 'none'; }); document.querySelector('.main').scrollTop = 0; });
    await pg.waitForTimeout(400);
    const c = await pg.evaluate(() => { const l = document.querySelector('.pj-vg-lado'); return { fixa: l.classList.contains('pj-lado-fixa'), pos: getComputedStyle(l).position }; });
    chk(c.fixa && c.pos === 'sticky', `[1] ${w}px: cabe inteira → acompanha a rolagem (${c.pos})`);
    chk(!pg.erros.length, `[1] ${w}px: nenhum erro de JS ${pg.erros.join(' | ').slice(0, 160)}`);
    await pg.close();
  }
  if (roda('2')) {
    const pg = await entrar(br, 1440, 900);
    for (const [tela, sel, id] of [['amigos', '#am-lista', 1], ['solicitacoes', null, 1], ['decisoes', null, 1]]) {
      await pg.goto(BASE + '/#' + tela); await pg.waitForTimeout(1500);
      const h0 = await pg.evaluate(() => history.length);
      const fn = { amigos: 'abrirAmigo', solicitacoes: 'abrirSolicitacao', decisoes: 'abrirDecisao' }[tela];
      await pg.evaluate(([f, i]) => window[f](i), [fn, id]); await pg.waitForTimeout(1200);
      const r1 = await pg.evaluate(() => ({ h: location.hash, aberto: document.querySelector('.main').classList.contains('with-drawer'), len: history.length }));
      chk(r1.aberto && r1.h === `#${tela}/${id}`, `[2] ${tela}: abrir o item põe #${tela}/${id} no endereço (${r1.h})`);
      chk(r1.len === h0 + 1, `[2] ${tela}: abrir empilha uma entrada (${h0} → ${r1.len})`);
      await pg.goBack(); await pg.waitForTimeout(900);
      const r2 = await pg.evaluate(() => ({ h: location.hash, aberto: document.querySelector('.main').classList.contains('with-drawer'), vis: !!document.querySelector('#v-' + location.hash.slice(1).split('/')[0] + '.on') }));
      chk(!r2.aberto && r2.h === '#' + tela, `[2] ${tela}: Voltar fecha o painel e fica na tela (${r2.h}, aberto=${r2.aberto})`);
      // link direto / recarregar reabre o mesmo item
      await pg.goto(BASE + `/#${tela}/${id}`); await pg.reload(); await pg.waitForTimeout(2500);
      const r3 = await pg.evaluate(() => ({ h: location.hash, aberto: document.querySelector('.main').classList.contains('with-drawer') }));
      chk(r3.aberto && r3.h === `#${tela}/${id}`, `[2] ${tela}: recarregar o endereço reabre o item (aberto=${r3.aberto}, ${r3.h})`);
      // fechar com Esc não duplica a entrada e volta à tela
      const h3 = await pg.evaluate(() => history.length);
      await pg.keyboard.press('Escape'); await pg.waitForTimeout(700);
      const r4 = await pg.evaluate(() => ({ h: location.hash, aberto: document.querySelector('.main').classList.contains('with-drawer'), len: history.length }));
      chk(!r4.aberto && r4.h === '#' + tela && r4.len === h3, `[2] ${tela}: Esc fecha, volta a #${tela} sem nova entrada (${r4.h}, ${h3} → ${r4.len})`);
      if (tela === 'amigos') { await pg.evaluate(() => abrirAmigo(1)); await pg.waitForTimeout(900); await pg.screenshot({ path: PRINTS + '/item-no-endereco-amigos-1440.png' }); await pg.keyboard.press('Escape'); }
    }
    chk(!pg.erros.length, '[2] nenhum erro de JS ' + pg.erros.join(' | ').slice(0, 200));
    await pg.close();
  }
  if (roda('2b')) {
    const pg = await entrar(br, 1440, 900);
    await pg.goto(BASE + '/#erros'); await pg.waitForTimeout(2000);
    // um grupo e uma linha desenhados lado a lado com as funções da própria tela (dados de mentira, só para medir a grade)
    const m = await pg.evaluate(() => {
      const e = { id: 9001, aberto: true, severidade: 'medio', severidade_rotulo: 'Médio', titulo: 'Folha pode ser de outro projeto', descricao: 'teste', tipo: 'comum', tipo_rotulo: 'Projeto', fase: 'novo', idade_dias: 3, cta: 'Analisar', prioridade: {}, projeto_codigo: 'F001-P0001', projeto_titulo: 'Teste', folha: 'F001-P0001-1970-S01-D00001' };
      const g = { chave: 'F001-P0001|projeto_errado', severidade: 'medio', severidade_rotulo: 'Médio', categoria: 'projeto_errado', n: 3, projeto_codigo: 'F001-P0001', projeto_titulo: 'Teste', tipo_rotulo: 'Projeto', idade_dias: 5, membros: [e], rapido: { acoes: ['deste_projeto', 'fica_fora'] }, prioridade: {} };
      const box = document.getElementById('err-body'); box.innerHTML = cpGrupoHTML(g) + cpLinhaHTML(e);
      const gr = box.querySelector('[data-cp-grupo]'), li = box.querySelector(':scope > [data-err-linha]');
      const pos = (el, s) => { const r = el.querySelector(':scope > ' + s).getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right)]; };
      return { tagG: pos(gr, '.cp-sev-tag'), tagL: pos(li, '.cp-sev-tag'), ctaG: pos(gr, '.cp-acoes'), ctaL: pos(li, '.cp-acoes'), ctaCls: gr.querySelector(':scope > .cp-acoes .cp-cta') ? 'cp-cta' : '', decide: !!gr.querySelector(':scope > .cp-g-decide [data-cp-g="deste_projeto"]') };
    });
    chk(Math.abs(m.tagG[0] - m.tagL[0]) <= 2, `[2b] Problemas: etiqueta de prioridade no mesmo lugar no grupo e na linha (${m.tagG} × ${m.tagL})`);
    chk(Math.abs(m.ctaG[1] - m.ctaL[1]) <= 2 && m.ctaCls === 'cp-cta', `[2b] Problemas: botão principal no mesmo lugar e no mesmo estilo (${m.ctaG} × ${m.ctaL})`);
    chk(m.decide, '[2b] Problemas: as decisões para todas ficam numa faixa abaixo');
    await pg.locator('#err-body').scrollIntoViewIfNeeded(); await pg.locator('#err-body').screenshot({ path: PRINTS + '/problemas-grupo-linha-1440.png' });
    // cartões de números: um estilo só (Amigos, Ingressos, Pedidos comparados com o do Financeiro)
    const est = async (rota, sel) => { await pg.goto(BASE + '/#' + rota); await pg.waitForTimeout(1800); return pg.evaluate(s => { const k = document.querySelector(s); if (!k) return null; const c = getComputedStyle(k), v = getComputedStyle(k.querySelector('.v')); return [c.borderRadius, c.boxShadow !== 'none', c.backgroundColor, v.fontFamily.split(',')[0], v.fontWeight, v.fontSize].join(' | '); }, sel); };
    const fin = await est('financeiro/geral', '.fin-kpi');
    for (const [rota, sel] of [['amigos', '#am-kpis .hoje-kpi'], ['cobrancas', '#cob-kpis .hoje-kpi'], ['ingressos', '#ig-kpis .ig-kpi'], ['solicitacoes', '.sol-stats .stat']]) {
      const x = await est(rota, sel);
      chk(x && x === fin, `[2b] cartão de números em ${rota} igual ao do Financeiro (${x} × ${fin})`);
    }
    chk(!pg.erros.length, '[2b] nenhum erro de JS ' + pg.erros.join(' | ').slice(0, 200));
    await pg.close();
  }
  if (roda('4')) {
    const pg = await entrar(br, 1440, 900);
    await pg.goto(BASE + '/#emails/modelos'); await pg.waitForSelector('#es-cob-vars code', { timeout: 15000 }).catch(() => {});
    const v = await pg.evaluate(() => [...document.querySelectorAll('#es-cob-vars code')].map(x => x.textContent));
    chk(v.includes('{{cobranca}}') && v.includes('{{link_pagamento}}') && v.includes('{{liberacao}}'), `[4] Modelos do Sender: bloco da entrega com cobrança com as variáveis (${v.length})`);
    await pg.waitForTimeout(800); await pg.evaluate(() => document.getElementById('es-cob').scrollIntoView({ block: 'center' })); await pg.waitForTimeout(500); await pg.screenshot({ path: PRINTS + '/sender-entrega-cobranca-1440.png' });
    chk(!pg.erros.length, '[4] nenhum erro de JS ' + pg.erros.join(' | ').slice(0, 200));
    await pg.close();
  }
  await br.close();
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
