// CAMP-146 (22/10, decidido pelo Rafa): as MESMAS 5 situações em todo o painel — Chegando · Para conferir · Pronto para publicar ·
// No site · Com problema — na Fila, em Projetos, na página do projeto e no Painel inicial. Uma coluna de situação na lista de
// Projetos (com a frase do que falta), nenhuma etiqueta antiga, e direitos "não definida" dizendo que não impede publicar.
// Rodar: EXAUSTAO_PORTA=8981 bash tests/rodar_exaustao.sh tests/exaustao/p8_situacoes.js
const path = require('path'), { execFileSync } = require('child_process');
const T = require('./_comum');
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'p3_montar.py'), ...a], { encoding: 'utf-8' }).trim();
const CINCO = ['Chegando', 'Para conferir', 'Pronto para publicar', 'No site', 'Com problema'];
const ANTIGAS = /\b(Em leitura|Na fila|Lendo|Importar folhas|Aprovar lote|Publicada|aguardando importação|em revisão|pronta para aprovar|Erro no CAMP Vision)\b/;
const etiquetas = (pg, sel) => pg.$$eval(`${sel} .tag.sit`, xs => xs.map(x => x.textContent.trim()));

T.rodar(async () => {
  T.passo('cenário: um lote para conferir (34 folhas) e outro que o CAMP Vision ainda está lendo');
  const NOME = 'CASA SITUACOES';
  const P = T.cv2('reservar', T.BASE, 'F026', NOME, '1972'); T.cv2('processando', T.BASE, T.RAIZ, P, NOME);
  const av = JSON.parse(montar(T.BASE, T.RAIZ, P, NOME));
  T.chk((av.importacao || {}).criadas === 34, 'o aviso do CAMP Vision importa as 34 folhas', JSON.stringify(av).slice(0, 200));
  const NOME2 = 'CASA CHEGANDO';
  const P2 = T.cv2('reservar', T.BASE, 'F026', NOME2, '1980'); T.cv2('processando', T.BASE, T.RAIZ, P2, NOME2);
  const ad = await T.entrar('admin');

  T.passo('Fila: a etiqueta de cada linha é uma das 5 situações');
  await ad.evaluate(() => nav('filas/todas')); await ad.waitForSelector('#filas-body tr[data-fase]', { timeout: 15000 }); await ad.waitForTimeout(800);
  const fila = await etiquetas(ad, '#filas-body');
  T.chk(fila.length > 0 && fila.every(t => CINCO.includes(t)), 'Fila: só as 5 situações nas etiquetas', JSON.stringify(fila));
  const linhaP = await T.txt(ad, `#filas-body tr[data-nav="projeto/${P}"]`), linhaP2 = await T.txt(ad, `#filas-body tr[data-nav="projeto/${P2}"]`);
  T.chk(/Para conferir/.test(linhaP) && /Faltam conferir/.test(linhaP), 'Fila: o lote de 34 folhas está "Para conferir", com a frase do que falta', linhaP);
  T.chk(/Chegando/.test(linhaP2), 'Fila: o lote que o CAMP Vision lê está "Chegando"', linhaP2);
  const chips = await T.txt(ad, '#fila-chips');
  T.chk(/Chegando/.test(chips) && /No site/.test(chips) && !/CAMP Vision lendo|Publicadas/.test(chips), 'Fila: os filtros dizem "Chegando" e "No site"', chips);
  const tagsFila = await ad.$$eval('#v-filas .tag', xs => xs.map(x => x.textContent.trim()).join(' | '));
  T.chk(!ANTIGAS.test(tagsFila), 'Fila: nenhuma etiqueta antiga', tagsFila);
  await T.print(ad, 'fila');

  T.passo('Projetos: UMA coluna de situação, com a frase do que falta');
  await ad.evaluate(() => nav('projetos')); await ad.waitForSelector('#projetos-body tr[data-nav]', { timeout: 15000 });
  const cab = await ad.$$eval('#v-projetos thead th', ths => ths.map(t => t.textContent.trim()));
  T.chk(cab.filter(t => t === 'Situação').length === 1 && !cab.includes('Próximo passo'), 'Projetos: uma coluna "Situação" (sem "Próximo passo" repetindo)', JSON.stringify(cab));
  await ad.evaluate(c => carregarProjetosAPI({ q: c }), P);
  const achou = await T.espera(async () => !!(await ad.$(`#projetos-body tr[data-nav="projeto/${P}"]`)), 10000);
  if (achou) {
    const lp = await T.txt(ad, `#projetos-body tr[data-nav="projeto/${P}"]`);
    T.chk(/Para conferir/.test(lp) && /34 folhas faltam conferir/.test(lp), 'Projetos: o projeto está "Para conferir · 34 folhas faltam conferir"', lp);
  } else T.chk(false, 'Projetos: a linha do projeto aparece na lista');
  const proj = await etiquetas(ad, '#projetos-body');
  T.chk(proj.length > 0 && proj.every(t => CINCO.includes(t)), 'Projetos: só as 5 situações', JSON.stringify([...new Set(proj)]));
  await T.print(ad, 'projetos');

  T.passo('Página do projeto: o selo e o bloco do topo dizem a situação');
  await T.abrirProjeto(ad, P);
  await T.espera(async () => /Para conferir/.test(await T.txt(ad, '#pj-selo')), 10000);
  T.chk(/Para conferir/.test(await T.txt(ad, '#pj-selo')), 'projeto: o selo diz "Para conferir"', await T.txt(ad, '#pj-selo'));
  await T.espera(async () => /Para conferir/.test(await T.txt(ad, '#pj-status')), 10000);
  T.chk(/Para conferir/.test(await T.txt(ad, '#pj-status')), 'projeto: o bloco do topo diz "Para conferir"', await T.txt(ad, '#pj-status'));
  const pag = await etiquetas(ad, '#pd');
  T.chk(pag.every(t => CINCO.includes(t)), 'projeto: toda etiqueta de situação é uma das 5', JSON.stringify(pag));
  T.chk(!/aguardando importação|em revisão|pronta para aprovar/.test(await T.txt(ad, '#pd')), 'projeto: a Revisão do lote não usa os rótulos antigos');

  T.passo('Painel inicial: os grupos com os nomes das situações; sem "fundos travados por direitos"');
  await ad.evaluate(() => nav('painel')); await ad.waitForSelector('#v-painel .ini-tg', { timeout: 15000 });
  const ini = await T.txt(ad, '#v-painel');
  T.chk(/Para conferir/i.test(ini) && !/Conferir folhas/i.test(await T.txt(ad, '#v-painel .ini-tg[data-ini-grupo="conferir"] .ini-tgh')), 'Painel: o grupo se chama "Para conferir"', await T.txt(ad, '#v-painel .ini-tg[data-ini-grupo="conferir"] .ini-tgh'));
  T.chk(!/travados? por direitos/.test(ini), 'Painel: saiu o número "fundos travados por direitos"');
  await T.print(ad, 'painel');

  T.passo('conferido e aprovado → "Pronto para publicar"; publicado → "No site"');
  const r = await ad.evaluate(async (P) => {
    const j = async (u, b) => (await fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b || {}) })).status;
    const lote = (await (await fetch(`/api/projetos/${P}/revisao`)).json()).lotes[0].id;
    return [await j(`/api/lotes/${lote}/conferir-todas`), await j(`/api/lotes/${lote}/aprovar`)];
  }, P);
  T.chk(r.every(x => x === 200), 'conferido e aprovado', JSON.stringify(r));
  await T.abrirProjeto(ad, P);
  T.chk(await T.espera(async () => /Pronto para publicar/.test(await T.txt(ad, '#pj-selo')), 10000), 'projeto: "Pronto para publicar"', await T.txt(ad, '#pj-selo'));
  const bt = await ad.waitForSelector('#pj-status [data-pjs-publicar]:not([disabled])', { timeout: 15000 }).catch(() => null);
  if (bt) { await bt.click(); await T.espera(async () => /Publicado ✓/.test(await T.txt(ad, '#pj-status').catch(() => '')), 90000) }
  await T.abrirProjeto(ad, P);
  T.chk(await T.espera(async () => /No site/.test(await T.txt(ad, '#pj-selo')), 10000), 'projeto publicado: "No site"', await T.txt(ad, '#pj-selo'));

  T.passo('Com problema: o CAMP Vision parou com erro');
  T.sql("UPDATE lista_processamento SET etapa='erro' WHERE projeto_codigo=?", P2);
  await ad.evaluate(() => nav('filas/todas')); await ad.waitForSelector('#filas-body tr[data-fase]', { timeout: 15000 }); await ad.waitForTimeout(800);
  T.chk(/Com problema/.test(await T.txt(ad, `#filas-body tr[data-nav="projeto/${P2}"]`)), 'Fila: lote com erro do CAMP Vision está "Com problema"', await T.txt(ad, `#filas-body tr[data-nav="projeto/${P2}"]`));

  T.passo('Direitos "não definida" não impede publicar (padroes.md §12)');
  T.sql("INSERT OR REPLACE INTO direitos_fundo (fundo_codigo,situacao) VALUES ('F026','nao_definida')");
  await ad.evaluate(() => nav('fundo/F026'));
  const viu = await T.espera(async () => /não definida/i.test(await T.txt(ad, '#fd-direitos').catch(() => '')), 15000);
  const dir = await T.txt(ad, '#fd-direitos').catch(() => '');
  T.chk(viu && /não impede publicar/.test(dir) && !/bloqueada até existir/.test(dir), 'fundo: "Não definida — não impede publicar"', dir.slice(0, 300));
});
