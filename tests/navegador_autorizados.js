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
  await br.close();
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
