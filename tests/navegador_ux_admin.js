// CAMP-UX (26/11/2026). Rafael: "Revise a usabilidade de todo painel" — parte Administração e casco (topo, menu, busca).
// Prova os consertos desta revisão (cada um falha com o index.html de antes):
//  [1] Configurações sem rolagem lateral (1440 e 390): a tabela de Usuários empurrava a coluna para fora da tela e o "Novo usuário" ficava cortado;
//  [2] Financeiro → Projeto incentivado sem rolagem lateral no celular (select do item do orçamento com rótulos longos);
//  [3] a busca do topo acha as telas ("financ" → Financeiro), só as que a pessoa pode abrir (operador não vê Financeiro);
//  [4] Voltar do navegador depois de abrir o detalhe de uma receita fecha o detalhe e fica em Receitas (antes pulava para Visão geral);
//      fechar o detalhe (Esc) e Voltar não repete a mesma aba;
//  [5] DRE: "Imprimir ou salvar PDF" na mesma linha de "Ver mês a mês", XLSX e CSV;
//  [6] botões lado a lado não ficam colados (Projeto incentivado, Máquinas, Visão geral do Financeiro);
//  [7] aba de Máquinas no endereço (F5 volta nela);
//  [8] trilha "Administração / Projetos da CAMP";
//  [9] Sem acesso: "Busca" e "Mais" não ficam acesos no menu.
// Uso (servidor PRÓPRIO, portas 9170–9179; banco: tests/semear_banco_teste.py + tests/semente_financeiro.py + tests/semente_rouanet.py
//      + tests/semente_projetos_camp.py):  TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9171 node tests/navegador_ux_admin.js
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9171';
const problemas = [];
const chk = (ok, msg) => { console.log((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
async function entrar(br, w, h, email = 'rafael@camp.arq.br', senha = 'senha-bem-longa-123') {
  const pg = await br.newPage({ viewport: { width: w, height: h } });
  pg.erros = []; pg.on('pageerror', e => pg.erros.push(e.message)); pg.on('dialog', d => d.dismiss().catch(() => {}));
  await pg.route(/mercadopago|camp\.arq\.br|sender\.net/, r => r.abort());
  await pg.goto(BASE + '/'); await pg.fill('#lg-email', email); await pg.fill('#lg-senha', senha); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await pg.waitForTimeout(600);
  return pg;
}
const larguraMain = pg => pg.evaluate(() => { const m = document.querySelector('.main'); return { sw: m.scrollWidth, cw: m.clientWidth, doc: document.scrollingElement.scrollWidth, vw: document.documentElement.clientWidth }; });
const semRolagem = r => r.sw <= r.cw + 1 && r.doc <= r.vw + 1;
const finPronto = pg => pg.waitForFunction(() => document.getElementById('v-financeiro')?.classList.contains('on') && FIN.d && FIN.desp && !FIN.carregando, null, { timeout: 20000 });
(async () => {
  const br = await chromium.launch();
  // [1] Configurações
  for (const [w, h] of [[1440, 900], [390, 844]]) {
    const pg = await entrar(br, w, h);
    await pg.goto(BASE + '/#config'); await pg.waitForTimeout(1800);
    const r = await larguraMain(pg);
    chk(semRolagem(r), `[1] Configurações a ${w}px sem rolagem lateral (${r.sw}/${r.cw})`);
    const b = await pg.locator('#usr-panel button:has-text("Novo usuário")').boundingBox();
    chk(b && b.x + b.width <= w + 1, `[1] "Novo usuário" inteiro na tela a ${w}px (${b && Math.round(b.x + b.width)})`);
    await pg.close();
  }
  // [2] Projeto incentivado no celular
  { const pg = await entrar(br, 390, 844); await pg.goto(BASE + '/#financeiro/projeto'); await finPronto(pg); await pg.waitForTimeout(1500);
    const r = await larguraMain(pg); chk(semRolagem(r), `[2] Financeiro → Projeto incentivado a 390px sem rolagem lateral (${r.sw}/${r.cw})`); await pg.close(); }
  // [3] busca acha telas
  { const pg = await entrar(br, 1440, 900);
    await pg.click('#q'); await pg.keyboard.type('financ'); await pg.waitForTimeout(1200);
    const t = await pg.locator('#qres').innerText();
    chk(/Financeiro/.test(t) && /tela/i.test(t) && !/Financeiro\s*\d/.test(t), `[3] buscar "financ" mostra a tela Financeiro (sem o número do atalho grudado) (${t.replace(/\s+/g, ' ').slice(0, 90)})`);
    await pg.locator('#qres [data-search-index]', { hasText: 'Financeiro' }).first().click().catch(() => {});
    await pg.waitForTimeout(1500);
    chk((await pg.evaluate(() => location.hash)).startsWith('#financeiro'), '[3] clicar no resultado abre o Financeiro');
    await pg.close();
    const op = await entrar(br, 1440, 900, 'operador@camp.arq.br', 'senha-operador-123');
    await op.click('#q'); await op.keyboard.type('financ'); await op.waitForTimeout(1200);
    chk(!/Financeiro/.test(await op.locator('#qres').innerText()), '[3] o operador não vê a tela Financeiro na busca (é só de admin)');
    await op.click('#q', { clickCount: 3 }); await op.keyboard.type('gloss'); await op.waitForTimeout(1200);
    chk(/Glossário/.test(await op.locator('#qres').innerText()), '[3] o operador acha a tela Glossário');
    await op.close(); }
  // [4] Voltar no Financeiro
  { const pg = await entrar(br, 1440, 900);
    await pg.goto(BASE + '/#financeiro/geral'); await finPronto(pg);
    await pg.click('[data-fin-aba="receitas"]'); await pg.waitForTimeout(800);
    await pg.locator('#fin-p-receitas [data-fin-rec]').first().click(); await pg.waitForTimeout(900);
    chk(/#financeiro\/receitas\/./.test(await pg.evaluate(() => location.hash)), '[4] detalhe da receita no endereço');
    await pg.goBack(); await pg.waitForTimeout(1000);
    const s = await pg.evaluate(() => ({ h: location.hash, lado: !document.getElementById('fin-lado').hidden }));
    chk(/^#financeiro\/receitas(\?|$)/.test(s.h) && !s.lado, `[4] Voltar fecha o detalhe e fica em Receitas (${s.h}, painel lateral ${s.lado ? 'aberto' : 'fechado'})`);
    await pg.locator('#fin-p-receitas [data-fin-rec]').first().click(); await pg.waitForTimeout(900);
    await pg.keyboard.press('Escape'); await pg.waitForTimeout(800);
    await pg.goBack(); await pg.waitForTimeout(1000);
    const s2 = await pg.evaluate(() => location.hash);
    chk(/^#financeiro\/geral/.test(s2), `[4] fechar o detalhe (Esc) e Voltar vai para a aba anterior, sem repetir Receitas (${s2})`);
    chk(pg.erros.length === 0, '[4] nenhum erro de JS ' + pg.erros.join(' | ').slice(0, 160));
    await pg.close(); }
  // [5] DRE
  { const pg = await entrar(br, 1440, 900); await pg.goto(BASE + '/#financeiro/dre'); await finPronto(pg); await pg.waitForTimeout(1200);
    const y = await pg.evaluate(() => { const p = document.querySelector('#fin-p-dre [data-fin-acao="imprimir"]'), x = [...document.querySelectorAll('#fin-p-dre a.btn')].find(a => /XLSX/.test(a.textContent)); return p && x ? [Math.round(p.getBoundingClientRect().top), Math.round(x.getBoundingClientRect().top)] : null; });
    chk(y && Math.abs(y[0] - y[1]) <= 2, `[5] DRE: "Imprimir ou salvar PDF" na mesma linha do XLSX (${y})`); await pg.close(); }
  // [6] botões colados
  const colados = async (pg, sel) => pg.evaluate(s => { const out = []; document.querySelectorAll(s).forEach(p => { const bs = [...p.children].filter(c => c.matches('.btn') && c.getBoundingClientRect().width); for (let i = 1; i < bs.length; i++) { const a = bs[i - 1].getBoundingClientRect(), b = bs[i].getBoundingClientRect(); if (Math.abs(a.top - b.top) < 4 && b.left - a.right < 4) out.push(bs[i - 1].textContent.trim().slice(0, 20) + '|' + bs[i].textContent.trim().slice(0, 20)); } }); return out; }, sel);
  { const pg = await entrar(br, 1440, 900);
    await pg.goto(BASE + '/#financeiro/projeto'); await finPronto(pg); await pg.waitForTimeout(1500);
    let c = await colados(pg, '#fin-p-projeto .fin-proj-topo>.act'); chk(c.length === 0, `[6] Projeto incentivado: botões com espaço entre eles (${c.join(', ')})`);
    await pg.goto(BASE + '/#financeiro/geral'); await pg.waitForTimeout(1800);
    c = await colados(pg, '#v-financeiro .fin-card>.act'); chk(c.length === 0, `[6] Visão geral do Financeiro: botões com espaço (${c.join(', ')})`);
    await pg.goto(BASE + '/#estacoes'); await pg.waitForTimeout(2200);
    c = await colados(pg, '#v-estacoes .pb>.act'); chk(c.length === 0, `[6] Máquinas: botões com espaço (${c.join(', ')})`);
    // [7] aba de Máquinas no endereço
    await pg.click('#est-abas [data-est-aba="alertas"]'); await pg.waitForTimeout(600);
    chk((await pg.evaluate(() => location.hash)) === '#estacoes/alertas', '[7] aba Alertas de Máquinas no endereço');
    await pg.reload(); await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); await pg.waitForTimeout(2000);
    chk(await pg.evaluate(() => document.querySelector('#est-abas [data-est-aba="alertas"]')?.getAttribute('aria-selected') === 'true'), '[7] F5 volta na aba Alertas');
    // [8] trilha
    await pg.goto(BASE + '/#projetos_camp'); await pg.waitForTimeout(1500);
    chk(/Administração\s*\/\s*Projetos da CAMP/.test(await pg.locator('#gcrumb').innerText()), '[8] trilha "Administração / Projetos da CAMP"');
    await pg.goto(BASE + '/#cobrancas'); await pg.waitForTimeout(1200);
    chk(/Público e processos/.test(await pg.locator('#gcrumb').innerText()), '[8] trilha de Cobranças avulsas com "Público e processos"');
    await pg.close(); }
  // [9] Sem acesso (operador em Configurações): nenhum item do menu aceso ("Busca" e "Mais" acendiam juntos)
  { const op = await entrar(br, 1440, 900, 'operador@camp.arq.br', 'senha-operador-123');
    await op.goto(BASE + '/#config'); await op.waitForTimeout(1500);
    const acesos = await op.evaluate(() => [...document.querySelectorAll('#nav button.on')].map(b => b.dataset.v || b.id));
    chk(acesos.length === 0, `[9] Sem acesso: nenhum item do menu aceso (${acesos.join(', ')})`); await op.close(); }
  await br.close();
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
