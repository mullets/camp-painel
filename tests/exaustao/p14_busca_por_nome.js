// CAMP-153 (Trello, 22/10): nada de código para digitar. Mover, mesclar e Nova lista escolhem o projeto por busca (nome, arquiteto ou código),
// com a lista mostrando "F026-P0233 · Casa Bittencourt". O caminho do QNAP some para o operador (só admin, em "Avançado"); "Varrer QNAP" também.
// Rodar: EXAUSTAO_PORTA=8996 bash tests/rodar_exaustao.sh tests/exaustao/p14_busca_por_nome.js
const T = require('./_comum');
const opcoes = (pg, id) => pg.$$eval(`#${id}-lista option`, os => os.map(o => ({ v: o.value, t: o.textContent })));

T.rodar(async () => {
  T.passo('cenário: dois projetos do mesmo fundo');
  const A = T.cv2('reservar', T.BASE, 'F026', 'CASA ORIGEM BUSCA', '1972');
  const B = T.cv2('reservar', T.BASE, 'F026', 'RESIDENCIA DESTINO BITTENCOURT', '1974');
  const ad = await T.entrar('admin');

  T.passo('mesclar: o destino se escolhe pelo nome');
  await T.abrirProjeto(ad, A);
  await ad.click('#pd .pj-mais-menu > summary');
  await ad.click('#pd .pj-mais-menu [data-pj-mais]');
  await ad.waitForSelector('[data-mais="mesclar"]:not([disabled])', { timeout: 10000 });
  await ad.click('[data-mais="mesclar"]');
  await ad.waitForSelector('#mx-dest', { timeout: 8000 });
  const ph = await ad.$eval('#mx-dest', i => i.placeholder + ' | ' + (i.closest('label') || {}).textContent);
  T.chk(/nome do projeto, arquiteto ou código/.test(ph) && !/F026-P0113/.test(ph), 'o campo pede nome, arquiteto ou código (não "digite o código")', ph);
  await ad.type('#mx-dest', 'bittenc', { delay: 30 });
  T.chk(await T.espera(async () => (await opcoes(ad, 'mx-dest')).some(o => o.v === B), 6000), 'escrever parte do nome lista o projeto', JSON.stringify(await opcoes(ad, 'mx-dest')));
  const op = (await opcoes(ad, 'mx-dest')).find(o => o.v === B) || {};
  T.chk(new RegExp(`^${B} · RESIDENCIA DESTINO BITTENCOURT`, 'i').test(op.t || ''), `a lista mostra "${B} · Residencia Destino Bittencourt"`, op.t);
  T.chk(!(await opcoes(ad, 'mx-dest')).some(o => o.v === A), 'o próprio projeto não aparece como destino');
  await ad.fill('#mx-dest', B);       // escolher na lista põe o código no campo
  await ad.dispatchEvent('#mx-dest', 'input');
  T.chk(await T.espera(async () => new RegExp(`Destino: ${B}`).test(await T.txt(ad, '#mx-dest-ok')), 6000), 'escolhido: "Destino: <código> <nome>"', await T.txt(ad, '#mx-dest-ok'));
  if (await ad.$('#mx-motivo')) await ad.fill('#mx-motivo', 'cadastrado duas vezes');
  await ad.check('#mx-ok'); await ad.click('#mx-go'); await T.confirmar(ad);
  T.chk(await T.espera(() => T.um('SELECT mesclado_em FROM projeto WHERE codigo=?', A) === B, 15000), 'mesclou no projeto escolhido pela busca', T.um('SELECT mesclado_em FROM projeto WHERE codigo=?', A));

  T.passo('a busca acha pelo nome do arquiteto');
  const r = await ad.evaluate(async () => (await (await fetch('/api/busca?' + new URLSearchParams({ q: 'Bussab', so: 'projeto', limite: 40 }))).json()).resultados);
  T.chk(r.length > 0 && r.every(x => x.tipo === 'projeto') && r.some(x => x.codigo === B), '"Bussab" (o arquiteto) traz projetos do fundo dele', JSON.stringify(r.slice(0, 3)));

  T.passo('Nova lista: projeto por busca; o caminho do QNAP só para admin');
  const opr = await T.entrar('operador');
  await opr.evaluate(() => openModal('m-lista')); await opr.waitForTimeout(500);
  T.chk(await opr.$eval('#nl-proj', i => i.classList.contains('busca-proj')), 'Nova lista: o projeto é um campo de busca');
  T.chk(!(await opr.isVisible('#nl-pasta')) && !(await opr.isVisible('#m-lista .nl-avancado')), 'operador: o caminho do QNAP não aparece');
  await opr.evaluate(() => closeModal());
  await opr.evaluate(() => nav('filas/todas')); await opr.waitForTimeout(1500);
  T.chk(!!(await opr.$('#v-filas [data-qnap]:not([hidden])')), 'operador, importação automática desligada: "Varrer QNAP" continua (é o caminho do aviso perdido, CAMP-075)');
  T.sql("UPDATE configuracao SET valor='1' WHERE chave='importacao.automatica'");
  const opr2 = await T.entrar('operador');
  await opr2.evaluate(() => nav('filas/todas')); await opr2.waitForTimeout(2000);
  T.chk(!(await opr2.$('#v-filas [data-qnap]:not([hidden])')), 'operador, importação automática ligada: sem "Varrer QNAP" (o painel importa sozinho)');
  T.sql("UPDATE configuracao SET valor='0' WHERE chave='importacao.automatica'");
  await ad.evaluate(() => openModal('m-lista')); await ad.waitForTimeout(500);
  T.chk(await ad.isVisible('#m-lista .nl-avancado'), 'admin: "Avançado" com o caminho do QNAP');
});
