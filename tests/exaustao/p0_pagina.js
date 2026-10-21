// P0 (Trello, 21/10, "a página do projeto virou uma lista sem fim"): um projeto como o do print (F026-P0009): 34 folhas, 8 códigos de
// unidade, 23 propostas + 1 sugestão, 6 releituras do projeto inteiro. Aceite do card:
//  - numa tela de 1080 px a grade de folhas começa na primeira dobra; nenhuma seção abre sozinha;
//  - nenhuma lista à vista passa de 10 linhas sem "ver mais"; a mesma coisa não aparece duas vezes (a sugestão "UF: SP" 1 vez);
//  - cada pendência da barra "O que falta" abre um PAINEL LATERAL, um passo por vez (propostas → unidades → releituras), e resolver
//    tudo por ele não muda a rolagem da página.
const path = require('path'), { execFileSync } = require('child_process');
const T = require('./_comum');
const p4 = (P) => execFileSync('python3', [path.join(__dirname, 'p4_montar.py'), 'pronto', T.BASE, T.RAIZ, P], { encoding: 'utf-8' });
const p1 = (...a) => execFileSync('python3', [path.join(__dirname, 'p1_montar.py'), ...a], { encoding: 'utf-8' });

const medir = pg => pg.evaluate(() => {
  const vis = e => e && e.checkVisibility && e.checkVisibility();
  const g = document.querySelector('.thumb[data-rev-abrir]');
  const listas = [...document.querySelectorAll('#pd ul, #pd tbody, #pd ol')].filter(vis).map(l => [l.className || l.tagName, [...l.children].filter(vis).length]).filter(x => x[1] > 10);
  const uf = [...document.querySelectorAll('#pd [data-cv-resp="sugestao"][data-chave="uf"][data-acao="usar"]')].filter(vis).length;
  const sc = document.querySelector('main') || document.scrollingElement;
  return { grade: g ? Math.round(g.getBoundingClientRect().top) : -1, listas, uf, gaveta: !document.getElementById('pj-gaveta') || document.getElementById('pj-gaveta').hidden ? null : 'aberta',
           botoes: [...document.querySelectorAll('#pd button')].filter(vis).length, rolagem: Math.round((document.getElementById('main') || sc).scrollTop || window.scrollY) };
});
const rolagem = pg => pg.evaluate(() => { const els = [document.scrollingElement, ...document.querySelectorAll('main, #main, .main')]; return els.map(e => e ? e.scrollTop : 0).join(',') });

T.rodar(async () => {
  T.passo('preparo: projeto como o do print (unidades, propostas, sugestão, 6 releituras)');
  const P = T.cv2('reservar', T.BASE, 'F026', 'CRASA PAGINA', '1972'); T.cv2('processando', T.BASE, T.RAIZ, P, 'CRASA PAGINA'); p4(P);
  p1('muitas', T.RAIZ, P, '1972');
  T.chk(T.um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', P) === 34, 'montagem: 34 folhas');
  const op = await T.entrar('operador');
  await op.setViewportSize({ width: 1440, height: 1080 });
  await T.abrirProjeto(op, P); await op.waitForTimeout(1500);
  const ent = await op.$('#pd button:has-text("Entendi")'); if (ent) { await ent.click(); await op.waitForTimeout(300) }   // a ajuda da página, fechada como a pessoa deixa
  await T.abrirProjeto(op, P); await op.waitForTimeout(3000);

  T.passo('P0: a página recolhida');
  const m = await medir(op);
  T.chk(m.gaveta === null, 'P0: nenhuma seção abre sozinha (Detalhes dos lotes, Problemas e Dados fechados)', JSON.stringify(m));
  T.chk(m.grade > 0 && m.grade <= 1080, `P0: numa tela de 1080 px a grade de folhas começa na primeira dobra (topo em ${m.grade} px)`, JSON.stringify(m));
  T.chk(!m.listas.length, 'P0: nenhuma lista à vista com mais de 10 linhas', JSON.stringify(m.listas));
  T.chk(m.uf <= 1, `P0: a sugestão "UF: SP" aparece no máximo 1 vez (${m.uf})`);
  const falta = await T.txt(op, '#pj-falta');
  T.chk(/Responder 23 propostas e 1 sugestão/.test(falta) && /códigos de unidade/.test(falta) && /17 mudanças da releitura/.test(falta), 'P0: a barra "O que falta" lista propostas, unidades e releituras, 1 linha cada', falta.slice(0, 400));
  await T.print(op, 'p0_recolhida');
  await op.click('#pj-cards [data-pjc-gav="folhas"]').catch(() => {}); await op.waitForTimeout(2500);
  const m2 = await medir(op);
  T.chk(!m2.listas.length, 'P0: com "Detalhes dos lotes" aberto, nenhuma lista à vista passa de 10 linhas', JSON.stringify(m2.listas));
  T.chk(m2.uf <= 1, `P0: com "Detalhes dos lotes" aberto, a sugestão continua 1 vez (${m2.uf})`);
  T.chk(await op.$$eval('#pj-cv [data-cv-obra]', l => l.filter(x => x.checkVisibility()).length) === 0 && /8 códigos de unidade/.test(await T.txt(op, '#pj-cv [data-cv-obras]')),
    'P0: as unidades ocupam 1 linha na página ("8 códigos de unidade"), sem as miniaturas', await T.txt(op, '#pj-cv [data-cv-obras]'));
  await T.print(op, 'p0_detalhes_abertos');
  await op.click('#pj-cards [data-pjc-gav="folhas"]').catch(() => {}); await op.waitForTimeout(800);

  T.passo('P0: resolver tudo pelo painel lateral, sem mexer na rolagem da página');
  const r0 = await rolagem(op);
  const clk = async (sel, nome) => { const ok = await op.waitForSelector(sel, { timeout: 10000 }).then(() => true, () => false); T.chk(ok, 'clique: ' + nome, (await T.txt(op, '#d-title').catch(() => '?')) + ' | ' + (await T.txt(op, '#d-body').catch(() => '?')).slice(0, 400)); if (ok) await op.click(sel); return ok };
  const verItem = async rx => { const li = (await op.$$('#pj-falta li')); for (const l of li) if (rx.test(await l.innerText())) { await (await l.$('button')).click(); return true } return false };
  T.chk(await verItem(/propostas/), 'P0: "Ver" nas propostas');
  T.chk(await T.espera(async () => /Propostas/.test(await T.txt(op, '#d-title').catch(() => ''))), 'P0: abre o painel lateral "Propostas e sugestões do CAMP Vision"', await T.txt(op, '#d-title').catch(() => ''));
  T.chk(/Passo 2 de 4/.test(await T.txt(op, '#d-body .passo-nav')), 'P0: o painel diz em que passo está ("Passo 2 de 4": decisão, propostas, unidades, releituras)', await T.txt(op, '#d-body .passo-nav'));
  await op.click('#d-body [data-cv-sug-todas], #d-body [data-cv-resp="sugestao"][data-acao="usar"]'); await op.waitForTimeout(2500);
  T.chk(await T.espera(() => T.um('SELECT uf FROM projeto WHERE codigo=?', P) === 'SP'), 'P0: "Usar" a sugestão no painel lateral grava a UF');
  const temLote = await op.waitForSelector('#d-body [data-cvp-lote="vazias"]', { timeout: 10000 }).then(() => true, () => false);
  T.chk(temLote, 'P0: depois de usar a sugestão, o painel lateral continua no passo das propostas', (await T.txt(op, '#d-title').catch(() => '?')) + ' | ' + (await T.txt(op, '#d-body').catch(() => '?')).slice(0, 300));
  await clk('#d-body [data-cvp-lote="vazias"]', 'Aceitar as vazias'); await op.waitForTimeout(1500);
  if (await clk('#d-body [data-cvp-lote="resto"]', 'Recusar as restantes')) await T.confirmar(op);
  T.chk(await T.espera(() => T.um("SELECT COUNT(*) FROM cv_resposta WHERE tipo='proposta' AND projeto_codigo=? AND chave NOT LIKE 'releitura:%' AND chave NOT LIKE 'obras:%'", P) === 23), 'P0: as 23 propostas respondidas em 2 cliques no painel lateral');
  await clk('#d-body [data-passo-ir="obras"]', 'Próximo: códigos de unidade');
  T.chk(await T.espera(async () => /Códigos de unidade/.test(await T.txt(op, '#d-title').catch(() => ''))), '"Próximo" leva aos códigos de unidade');
  T.chk(await op.$$eval('#d-body [data-cv-obra]', l => l.length) === 8, 'P0: no painel lateral os 8 grupos aparecem (com as miniaturas)');
  await clk('#d-body [data-obras-decidir="mesmo_conjunto"]', 'São partes do mesmo conjunto');
  T.chk(await T.espera(() => T.um("SELECT valor FROM cv_resposta WHERE chave='obras:decisao' AND projeto_codigo=?", P) === 'mesmo_conjunto'), 'P0: "São partes do mesmo conjunto" decide');
  await clk('#d-body [data-passo-ir="releituras"]', 'Próximo: releituras');
  T.chk(await T.espera(async () => /Releituras/.test(await T.txt(op, '#d-title').catch(() => ''))), '"Próximo" leva às releituras');
  const tudo = await op.waitForSelector('#d-body .rl-tudo [data-rl-todas="aceitar"]', { timeout: 10000 }).catch(() => null);
  T.chk(!!tudo && /Aceitar todas as 17 mudanças/.test(await tudo.innerText()), 'P0: "Aceitar todas as 17 mudanças" no topo das releituras', tudo ? await tudo.innerText() : '');
  if (tudo) { await tudo.click(); await T.confirmar(op) }
  T.chk(await T.espera(() => T.um("SELECT COUNT(*) FROM cv_resposta WHERE chave LIKE 'releitura:%' AND projeto_codigo=?", P) === 17, 20000), 'P0: as 17 mudanças gravadas de uma vez');
  T.chk((await rolagem(op)) === r0, 'P0: resolver tudo pelo painel lateral não mudou a rolagem da página', `${r0} → ${await rolagem(op)}`);
  await op.waitForTimeout(2500);
  const f2 = await T.txt(op, '#pj-falta');
  T.chk(!/propostas|códigos de unidade|releitura/.test(f2), 'P0: resolvidas, as três saem da barra "O que falta"', f2.slice(0, 300));
  await T.print(op, 'p0_resolvida');
});
