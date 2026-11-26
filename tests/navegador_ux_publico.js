// CAMP-UX (26/11/2026). Rafael: "Revise a usabilidade de todo painel" — área Público e processos.
// Confere os consertos: finalidade com rótulo (lista e detalhe do pedido); trilha com o grupo em Ingressos, Cobranças avulsas, Doações de
// acervo e Patrocínios; um só "?" no título de Ingressos; caixa "só Amigos" no tamanho certo; faixa "Pedidos feitos no site" com margem;
// CNPJ sem "·" solto em Patrocínios; filtros de data das cobranças com rótulo; Amigos "Todos" = total da lista; Amigo sem situação NÃO vira
// "Pago" ao salvar; pedidos no celular com Finalidade/Recebido/Situação visíveis; "Sem acesso" na trilha; recebida sem data diz "sem data".
// Uso (servidor PRÓPRIO, portas 9160–9169; banco de tests/semear_banco_teste.py + tests/semente_financeiro.py + tests/semente_originais.py,
// com pedidos, um Amigo sem situação e uma doação/patrocínio sem data de recebimento):
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9161 node tests/navegador_ux_publico.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9161';
const PRINTS = process.env.PRINTS || '';
const problemas = [];
const chk = (ok, msg) => { console.log((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
async function entrar(br, w, h, email, senha) {
  const ctx = await br.newContext({ viewport: { width: w, height: h } });
  const pg = await ctx.newPage();
  pg.on('dialog', d => d.dismiss().catch(() => {}));
  pg.erros = []; pg.on('pageerror', e => pg.erros.push(e.message));
  await pg.route(/\/api\/[a-z-]+\/(sincronizar|coletar|buscar)$/, r => r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' }));
  await pg.goto(BASE + '/');
  await pg.fill('#lg-email', email); await pg.fill('#lg-senha', senha); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, pg };
}
const ir = async (pg, t) => { await pg.goto(BASE + '/#' + t); await pg.waitForTimeout(1800); };
const print = async (pg, nome) => { if (!PRINTS) return; await pg.evaluate(() => document.querySelectorAll('#toast,.toast').forEach(x => x.style.display = 'none')); await pg.screenshot({ path: `${PRINTS}/${nome}.png` }); };
(async () => {
  const br = await chromium.launch();
  let { ctx, pg } = await entrar(br, 1440, 900, 'rafael@camp.arq.br', 'senha-bem-longa-123');
  // pedidos
  await ir(pg, 'solicitacoes');
  const fins = await pg.$$eval('#v-solicitacoes tbody tr[data-abrir] td:nth-child(3)', ts => ts.map(t => t.textContent.trim()));
  chk(fins.length > 0 && fins.every(f => !/^(exposicao|publicacao|pesquisa|familia|editorial|outro)$/.test(f)) && fins.some(f => /Exposição|Publicação|Pesquisa/.test(f)), `pedidos: finalidade com rótulo (${fins.join(', ')})`);
  const pad = await pg.evaluate(() => { const p = document.querySelector('#sol-coleta .help'); const c = document.getElementById('sol-coleta'); if (!p || c.hidden) return null; return p.getBoundingClientRect().left - c.getBoundingClientRect().left + parseFloat(getComputedStyle(p).paddingLeft); });
  chk(pad === null || pad >= 12, `pedidos: "Pedidos feitos no site" com margem à esquerda (${pad})`);
  await pg.click('#v-solicitacoes tbody tr[data-abrir] td:first-child', { timeout: 5000 }).catch(() => {}); await pg.waitForTimeout(900);
  const finDet = await pg.evaluate(() => { const dt = [...document.querySelectorAll('#drawer dt')].find(x => x.textContent.trim() === 'Finalidade'); return dt ? dt.nextElementSibling.textContent.trim() : null; });
  chk(finDet && !/^(exposicao|publicacao|pesquisa)$/.test(finDet), `pedido aberto: finalidade com rótulo (${finDet})`);
  await print(pg, 'pedido-detalhe-1440');
  await pg.keyboard.press('Escape');
  // trilha
  for (const t of ['ingressos', 'cobrancas', 'doacoes', 'patrocinios']) {
    await ir(pg, t);
    const tr = await pg.evaluate(() => (document.getElementById('gcrumb') || {}).textContent || '');
    chk(/Público e processos/.test(tr), `${t}: trilha com "Público e processos" (${tr.trim().replace(/\s+/g, ' ')})`);
  }
  // ingressos: um só "?" no título
  await ir(pg, 'ingressos');
  const interr = await pg.$$eval('#v-ingressos h1 summary, #v-ingressos h1 .ajuda-btn, #v-ingressos .hdr h1 button', xs => xs.filter(x => x.textContent.trim() === '?').length);
  chk(interr <= 1, `ingressos: no máximo um "?" no título (${interr})`);
  await pg.click('#v-ingressos tbody tr', { timeout: 5000 }).catch(() => {}); await pg.waitForTimeout(1200);
  const cx = await pg.evaluate(() => { const i = document.getElementById('ig-l-amigo'); if (!i) return null; const l = i.closest('label').getBoundingClientRect(), r = i.getBoundingClientRect(); return { w: Math.round(r.width), lw: Math.round(l.width) }; });
  chk(cx && cx.w <= 24 && cx.lw <= 160, `ingressos: caixa "só Amigos" no tamanho de uma caixa (${JSON.stringify(cx)})`);
  await print(pg, 'ingressos-lista-1440');
  // patrocínios: sem "·" solto
  await ir(pg, 'patrocinios');
  const sm = await pg.$$eval('#v-patrocinios tbody small', xs => xs.map(x => x.textContent.trim()).filter(t => /^·/.test(t)));
  chk(sm.length === 0, `patrocínios: nenhuma linha começa com "·" (${sm.join(' | ')})`);
  const sd = await pg.$$eval('#v-patrocinios td.pat-dt', xs => xs.map(x => x.textContent.trim()));
  chk(sd.every(t => !/^CAMP-/.test(t)), `patrocínios: recebida sem data diz "sem data" (${sd.join(' | ')})`);
  // cobranças: datas com rótulo
  await ir(pg, 'cobrancas');
  const lb = await pg.$$eval('#v-cobrancas .cob-dt-lbl', xs => xs.map(x => x.textContent.trim()));
  chk(lb.length === 2 && /criadas de/.test(lb[0]) && /até/.test(lb[1]), `cobranças: filtros de data com rótulo (${lb.join(' | ')})`);
  // amigos: Todos = total da lista
  await ir(pg, 'amigos');
  const tod = await pg.evaluate(() => { const b = document.querySelector('[data-am-sit="todos"] b'); const n = document.querySelectorAll('#v-amigos tbody tr[data-am-abrir], #v-amigos tbody tr').length; return { todos: b && +b.textContent.replace(/\D/g, ''), linhas: AM && AM.d ? AM.d.itens.length : n }; });
  chk(tod.todos === tod.linhas, `amigos: "Todos" (${tod.todos}) = registros da lista (${tod.linhas})`);
  // Amigo sem situação: salvar não marca "Pago"
  const sem = await pg.evaluate(() => (AM.d.itens.find(x => !x.situacao) || {}).id);
  if (sem) {
    await pg.evaluate(id => abrirAmigo(id), sem); await pg.waitForTimeout(1000);
    const v = await pg.$eval('#am-f-sit', s => s.value).catch(() => 'sem campo');
    chk(v === '', `Amigo sem situação: o campo Situação vem vazio, não "Pago" (${v})`);
    await print(pg, 'amigo-sem-situacao-1440');
    const nt = await pg.$('#am-f-notas'); if (nt) await nt.fill('nota de teste UX');
    await pg.click('[data-am-salvar]', { timeout: 5000 }).catch(() => {}); await pg.waitForTimeout(1200);
    const sit = await pg.evaluate(async id => { const r = await fetch('/api/amigos/' + id); const j = await r.json(); return (j.amigo || j).situacao ?? null; }, sem);
    chk(!sit, `Amigo sem situação: salvar uma nota não marca como pago (situação: ${sit})`);
  } else chk(false, 'Amigo sem situação no banco de teste');
  chk(pg.erros.length === 0, 'nenhum erro de JS (1440) ' + pg.erros.join(' | ').slice(0, 200));
  await ctx.close();
  // celular: pedidos com as colunas visíveis
  ({ ctx, pg } = await entrar(br, 390, 844, 'rafael@camp.arq.br', 'senha-bem-longa-123'));
  await ir(pg, 'solicitacoes');
  const cel = await pg.evaluate(() => { const td = (document.querySelector('#v-solicitacoes tbody tr td[data-l="Situação"]') || document.querySelector('#v-solicitacoes tbody tr td:nth-child(5)')); if (!td) return null; const r = td.getBoundingClientRect(); return { right: Math.round(r.right), vis: r.width > 0 && r.right <= window.innerWidth, antes: getComputedStyle(td, '::before').content }; });
  chk(cel && cel.vis && /Situação/.test(cel.antes), `celular: situação do pedido visível na tela, com rótulo (${JSON.stringify(cel)})`);
  await print(pg, 'pedidos-390');
  await ctx.close();
  // operador: "Sem acesso" na trilha
  ({ ctx, pg } = await entrar(br, 1440, 900, 'operador@camp.arq.br', 'senha-operador-123'));
  await ir(pg, 'cobrancas');
  const tr = await pg.evaluate(() => (document.getElementById('gcrumb') || {}).textContent || '');
  chk(/Sem acesso/.test(tr) && !/Não encontrado/.test(tr), `operador em Cobranças: trilha diz "Sem acesso" (${tr.trim()})`);
  await ctx.close();
  await br.close();
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
