// CAMP-UX (26/11/2026). Rafael: "Revise a usabilidade de todo painel" — área Visão geral + Acervo.
// Confere os consertos de layout feitos nesta revisão, a 1440×900 (e a página sem rolagem lateral também a 2000 e 390):
//  1. Início: os tipos da fila ("Melhorar a base 42") cabem no quadro (antes: cortados numa rolagem lateral sem aviso).
//  2. Início: "O caminho do material" não corta o texto dos passos (antes: 7 colunas de ~90 px, "esperanc", "aguar...").
//  3. Início: o cartão "folhas esperam um admin" sem lote não repete "em 0 lotes: 0 para aprovar, 0 para publicar".
//  4. Problemas: "nº 33" não quebra linha separando o "nº" do número.
//  5. Material novo: o botão principal de cada linha alinha à direita, com ou sem o "⋯".
//  6. Projetos: a coluna Arquitetos diz "sem autoria registrada" (antes "não registrada", no feminino, sob "Arquitetos").
//  7. Projeto: "Onde estão as folhas" com a etiqueta "faltam guardar" na borda direita e sem "…." no texto.
//  8. Projeto: Grade/Lista e P/M/G na mesma linha (o P M G ficava sozinho numa linha).
//  9. Fundos: a coluna Pendências tem largura para ler (antes uma palavra por linha).
// 10. Fundos, Arquitetos, Onde está guardado e Empréstimos: o campo de busca mostra o texto de ajuda inteiro.
// Uso (servidor PRÓPRIO, portas 9150–9159; banco de tests/semear_banco_teste.py + tests/semear_problemas_real.py + tests/semente_ordem_pdf.py):
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9151 node tests/navegador_ux_acervo.js
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9151';
const PROJ = process.env.UX_PROJETO || 'F001-P0001', PROJ2 = process.env.UX_PROJETO2 || 'F026-P0001';
const problemas = [];
const chk = (ok, msg) => { console.log((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
async function entrar(br, w, h) {
  const pg = await (await br.newContext({ viewport: { width: w, height: h } })).newPage();
  const erros = []; pg.on('pageerror', e => erros.push(e.message)); pg.on('dialog', d => d.dismiss().catch(() => {}));
  await pg.goto(BASE + '/'); await pg.fill('#lg-email', 'rafael@camp.arq.br'); await pg.fill('#lg-senha', 'senha-bem-longa-123'); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { pg, erros };
}
const ir = async (pg, r, ms = 2500) => { await pg.goto(BASE + '/#' + r); await pg.waitForTimeout(ms); };
(async () => {
  const br = await chromium.launch();
  const { pg, erros } = await entrar(br, 1440, 900);
  // 1–3 Início
  await ir(pg, 'painel', 3500);
  const f = await pg.evaluate(() => { const bar = document.querySelector('#v-painel .ini-filtros'); if (!bar) return null; const r = bar.getBoundingClientRect(); const bs = [...bar.querySelectorAll('.btn')].map(b => b.getBoundingClientRect()); return { n: bs.length, fora: bs.filter(b => b.right > r.right + 1 || b.left < r.left - 1).length, sw: bar.scrollWidth, cw: bar.clientWidth }; });
  chk(f && f.n > 0 && f.fora === 0 && f.sw <= f.cw + 1, `1. tipos da fila cabem no quadro (${JSON.stringify(f)})`);
  const c = await pg.evaluate(() => { const st = [...document.querySelectorAll('#v-painel .ini-flow .ini-step')]; const cort = []; st.forEach(s => s.querySelectorAll('.st,.nm,.w').forEach(e => { if (e.scrollWidth > e.clientWidth + 1) cort.push(e.textContent.trim().slice(0, 20)); })); return { n: st.length, larg: st.length ? Math.round(st[0].getBoundingClientRect().width) : 0, cort }; });
  chk(c.n === 7 && c.larg >= 130 && c.cort.length === 0, `2. caminho do material sem texto cortado (${JSON.stringify(c)})`);
  const k = await pg.evaluate(() => [...document.querySelectorAll('#v-painel .ini-kpis *,#v-painel [class*="kpi"] *')].map(e => e.textContent).join(' '));
  chk(!/em 0 lotes: 0 para aprovar, 0 para publicar/.test(k), '3. cartão de admin sem "em 0 lotes: 0 para aprovar, 0 para publicar"');
  // 4 Problemas
  await ir(pg, 'erros', 3500);
  const n = await pg.evaluate(() => { const ids = [...document.querySelectorAll('.cp-id')].filter(e => e.offsetParent); return { n: ids.length, quebrados: ids.filter(e => e.getClientRects().length > 1).length, ws: ids[0] ? getComputedStyle(ids[0]).whiteSpace : '' }; });
  chk(n.n > 0 && n.quebrados === 0 && n.ws === 'nowrap', `4. "nº" e o número na mesma linha (${JSON.stringify(n)})`);
  // 5 Material novo
  await ir(pg, 'filas', 3000);
  const fa = await pg.evaluate(() => [...document.querySelectorAll('.fila-acao .acao-cel')].filter(c => c.offsetParent).map(c => Math.round(c.querySelector('.btn').getBoundingClientRect().right)));
  chk(fa.length >= 2 && Math.max(...fa) - Math.min(...fa) <= 1, `5. botão principal alinhado em todas as linhas (${fa.join(', ')})`);
  // 6 Projetos
  await ir(pg, 'projetos', 3000);
  const pr = await pg.evaluate(() => document.querySelector('#v-projetos table')?.innerText || '');
  chk(!/\bnão registrada\b/.test(pr) && /sem autoria registrada/.test(pr), '6. coluna Arquitetos: "sem autoria registrada"');
  // 7–8 Projeto
  await ir(pg, 'projeto/' + PROJ, 3500);
  const g = await pg.evaluate(() => { const el = document.getElementById('pj-guardados'); if (!el) return null; const ph = el.querySelector('.ph'), tag = ph.querySelector(':scope>.tag'); const t = el.querySelector('.ph-resumo').textContent; return { dir: tag ? Math.round(ph.getBoundingClientRect().right - tag.getBoundingClientRect().right) : null, pontos: /…\.$/.test(t.trim()) }; });
  chk(g && g.dir != null && g.dir <= 24 && !g.pontos, `7. "faltam guardar" na borda direita e sem "…." (${JSON.stringify(g)})`);
  const v = await pg.evaluate(() => { const a = document.querySelector('#pd .fb-vista'), b = document.querySelector('#pd .fb-tam'); if (!a || !b) return null; return { topA: Math.round(a.getBoundingClientRect().top), topB: Math.round(b.getBoundingClientRect().top) }; });
  chk(v && Math.abs(v.topA - v.topB) <= 2, `8. Grade/Lista e P/M/G na mesma linha (${JSON.stringify(v)})`);
  await ir(pg, 'projeto/' + PROJ2, 3500);
  const v2 = await pg.evaluate(() => { const a = document.querySelector('#pd .fb-vista'), b = document.querySelector('#pd .fb-tam'); return a && b ? Math.abs(a.getBoundingClientRect().top - b.getBoundingClientRect().top) : 99; });
  chk(v2 <= 2, `8b. idem num projeto com disciplinas (${v2})`);
  // 9–10 Fundos e listas
  await ir(pg, 'fundos', 3000);
  const fp = await pg.evaluate(() => { const td = [...document.querySelectorAll('#fundos-body td.fd-pend')].filter(e => e.offsetParent && e.textContent.trim()); return td.length ? Math.round(td[0].getBoundingClientRect().width) : 0; });
  chk(fp >= 200, `9. coluna Pendências com largura para ler (${fp}px)`);
  for (const r of ['fundos', 'arquitetos', 'localizacao', 'emprestimos']) {
    await ir(pg, r, 2200);
    const i = await pg.evaluate(() => { const el = [...document.querySelectorAll('.content.on .filterbar input')].find(x => x.offsetParent && x.placeholder); if (!el) return null; const cv = document.createElement('canvas').getContext('2d'); const cs = getComputedStyle(el); cv.font = `${cs.fontSize} ${cs.fontFamily}`; const pad = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight) + 4; return { w: Math.round(el.clientWidth), precisa: Math.round(cv.measureText(el.placeholder).width + pad) }; });
    chk(i && i.w >= i.precisa, `10. ${r}: o texto de ajuda da busca cabe (${JSON.stringify(i)})`);
  }
  chk(erros.length === 0, 'nenhum erro de JS ' + erros.join(' | ').slice(0, 200));
  // sem rolagem lateral nas telas da área, nas três larguras
  for (const [w, h] of [[2000, 1100], [1440, 900], [390, 844]]) {
    const { pg: p2 } = await entrar(br, w, h);
    const ruins = [];
    for (const r of ['painel', 'filas', 'erros', 'decisoes', 'projetos', 'fundos', 'arquitetos', 'localizacao', 'estante', 'etiquetas', 'emprestimos', 'projeto/' + PROJ, 'projeto/' + PROJ2, 'fundo/F001']) {
      await ir(p2, r, 2000);
      const o = await p2.evaluate(() => { const m = document.querySelector('.main'); return { d: document.documentElement.scrollWidth - document.documentElement.clientWidth, m: m ? m.scrollWidth - m.clientWidth : 0 }; });
      if (o.d > 2 || o.m > 2) ruins.push(`${r} (${o.d}/${o.m})`);
    }
    chk(ruins.length === 0, `sem rolagem lateral a ${w}px ${ruins.join(', ')}`);
  }
  await br.close();
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
