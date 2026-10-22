// CAMP-147 (Trello, 22/10): a página do projeto tem UM bloco "Próximo passo" (uma frase + UM botão azul) logo abaixo do título.
// Conta os botões azuis VISÍVEIS na página em cada fase: Chegando, Para conferir, Pronto para publicar (aprovar e publicar), No site e
// Com problema. Exatamente 1 quando há algo a fazer; nenhum quando só resta esperar (o CAMP Vision lendo).
// Rodar: EXAUSTAO_PORTA=8986 bash tests/rodar_exaustao.sh tests/exaustao/p9_um_botao_azul.js
const path = require('path'), { execFileSync } = require('child_process');
const T = require('./_comum');
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'p3_montar.py'), ...a], { encoding: 'utf-8' }).trim();

// os botões azuis que a pessoa VÊ na página do projeto (sem as gavetas e janelas, que não fazem parte da página)
const azuis = pg => pg.evaluate(() => [...document.querySelectorAll('#pd .btn.pri')].filter(b => b.offsetParent !== null).map(b => ({ txt: b.textContent.trim(), noBloco: !!b.closest('#pj-status') })));
const umBloco = async (pg) => {
  const r = await pg.evaluate(() => ({ blocos: document.querySelectorAll('#pd #pj-status').length, fora: !!document.querySelector('#pd > #pj-proximo, #pd .pp:not(#pj-status .pp)'),
    caminho: !!document.querySelector('#pd #pj-status .steps'), tit: (document.querySelector('#pj-status .pjs-tit') || {}).textContent || '' }));
  return r.blocos === 1 && !r.fora && !r.caminho && /Próximo passo/.test(r.tit);
};
async function fase(pg, P, nome, espera, esperado) {
  await T.abrirProjeto(pg, P);
  await T.espera(async () => espera.test(await T.txt(pg, '#pj-status')), 15000);
  await pg.waitForTimeout(600);
  const a = await azuis(pg), st = await T.txt(pg, '#pj-status');
  if (esperado === 0) T.chk(a.length === 0 && espera.test(st), `${nome}: nada a fazer, nenhum botão azul (o bloco diz o que acontece)`, JSON.stringify(a) + ' | ' + st.slice(0, 160));
  else T.chk(a.length === 1 && a[0].noBloco && esperado.test(a[0].txt) && espera.test(st), `${nome}: exatamente 1 botão azul, no Próximo passo ("${a[0] && a[0].txt}")`, JSON.stringify(a) + ' | ' + st.slice(0, 160));
  T.chk(await umBloco(pg), `${nome}: um bloco só ("Próximo passo"), sem o caminho de 7 passos nem um segundo painel`);
  await T.print(pg, nome.replace(/\W+/g, '_').toLowerCase());
}

T.rodar(async () => {
  T.passo('cenário: um projeto com 34 folhas importadas, um que o CAMP Vision lê e um com erro do CAMP Vision');
  const NOME = 'CASA UM BOTAO';
  const P = T.cv2('reservar', T.BASE, 'F026', NOME, '1972'); T.cv2('processando', T.BASE, T.RAIZ, P, NOME);
  const av = JSON.parse(montar(T.BASE, T.RAIZ, P, NOME));
  T.chk((av.importacao || {}).criadas === 34, 'o aviso do CAMP Vision importa as 34 folhas', JSON.stringify(av).slice(0, 200));
  const P2 = T.cv2('reservar', T.BASE, 'F026', 'CASA LENDO', '1980'); T.cv2('processando', T.BASE, T.RAIZ, P2, 'CASA LENDO');
  const P3 = T.cv2('reservar', T.BASE, 'F026', 'CASA ERRO', '1981'); T.cv2('processando', T.BASE, T.RAIZ, P3, 'CASA ERRO');
  T.sql("UPDATE lista_processamento SET etapa='erro' WHERE projeto_codigo=?", P3);
  const ad = await T.entrar('admin');

  T.passo('Chegando: o CAMP Vision ainda lê');
  await fase(ad, P2, 'Chegando', /CAMP Vision está lendo|fila do CAMP Vision/, 0);

  T.passo('Para conferir');
  await fase(ad, P, 'Para conferir', /Faltam conferir 34/, /Começar a conferir/);

  T.passo('Pronto para publicar (falta aprovar o lote)');
  const lote = await ad.evaluate(async P => (await (await fetch(`/api/projetos/${P}/revisao`)).json()).lotes[0].id, P);
  const c = await ad.evaluate(async l => (await fetch(`/api/lotes/${l}/conferir-todas`, { method: 'POST' })).status, lote);
  T.chk(c === 200, 'conferidas', c);
  await fase(ad, P, 'Pronto (aprovar)', /Falta aprovar o lote/, /Aprovar o lote/);

  T.passo('Pronto para publicar (aprovado)');
  const a = await ad.evaluate(async l => (await fetch(`/api/lotes/${l}/aprovar`, { method: 'POST' })).status, lote);
  T.chk(a === 200, 'aprovado', a);
  await fase(ad, P, 'Pronto (publicar)', /Publicar 34 folhas/, /Publicar 34 folhas/);

  T.passo('No site');
  await ad.click('#pj-status [data-pjs-publicar]');
  T.chk(await T.espera(async () => /Publicado ✓/.test(await T.txt(ad, '#pj-status').catch(() => '')), 90000), 'publicado com um clique');
  await fase(ad, P, 'No site', /publicado/, /Atualizar no site/);

  T.passo('Com problema: o CAMP Vision parou com erro');
  await fase(ad, P3, 'Com problema', /parou com erro/, /Ver o erro/);
  await ad.click('#pj-status [data-pjc-gav="folhas"]');
  T.chk(await T.espera(async () => !!(await ad.$('#pj-gav-erro [data-releitura-projeto]')), 8000) && (await ad.$$('#pd [data-releitura-projeto]')).length === 1, 'Com problema: "Ver o erro" abre a mensagem com o ÚNICO "Pedir releitura" (CAMP-128)');

  T.passo('quem só lê não vê botão azul nenhum');
  const lt = await T.entrar('leitura');
  await T.abrirProjeto(lt, P); await lt.waitForTimeout(1500);
  T.chk((await azuis(lt)).length === 0, 'leitura: nenhum botão azul', JSON.stringify(await azuis(lt)));
});
