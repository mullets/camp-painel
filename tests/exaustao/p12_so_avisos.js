// CAMP-150 (22/10, decidido pelo Rafa): conferir só as folhas com aviso. Com revisao.conferir_so_avisos ligado, a folha sem aviso entra
// conferida sozinha ao importar; o modo conferir abre direto na 1ª folha com aviso e diz "Folha 1 de N com aviso (M sem aviso já
// conferidas)"; o painel da folha começa por "Por que você está vendo esta folha"; some o "Aprovar todas". Quem quiser ainda abre qualquer folha.
// Rodar: EXAUSTAO_PORTA=8992 bash tests/rodar_exaustao.sh tests/exaustao/p12_so_avisos.js
const path = require('path'), { execFileSync } = require('child_process');
const T = require('./_comum');
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'p3_montar.py'), ...a], { encoding: 'utf-8', env: { ...process.env, P3_AVISOS: '5,18,30' } }).trim();
const AUTO = 'painel (sem aviso: conferida sozinha)';

T.rodar(async () => {
  T.passo('ligado: o lote chega e as folhas sem aviso entram conferidas sozinhas');
  T.sql("UPDATE configuracao SET valor='1' WHERE chave='revisao.conferir_so_avisos'");
  const NOME = 'CASA SO AVISOS';
  const P = T.cv2('reservar', T.BASE, 'F026', NOME, '1972'); T.cv2('processando', T.BASE, T.RAIZ, P, NOME);
  const av = JSON.parse(montar(T.BASE, T.RAIZ, P, NOME));
  const total = T.um('SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND lote_id IS NOT NULL', P);
  const auto = T.um('SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND revisado_por=?', P, AUTO);
  const N = T.um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND revisao='pendente'", P);
  T.chk(total > 0 && auto > 0 && N > 0 && auto + N === total, `importou ${total}: ${auto} sem aviso conferidas sozinhas, ${N} com aviso esperam`, JSON.stringify(av.importacao || av).slice(0, 200));
  T.chk(T.um("SELECT COUNT(*) FROM evento WHERE tipo='conferida_automaticamente' AND codigo=?", P) === 1, 'fica no histórico do projeto ("conferida_automaticamente")');
  const op = await T.entrar('operador');

  T.passo('o Próximo passo: só as com aviso, sem "Aprovar todas"');
  await T.abrirProjeto(op, P);
  await T.espera(async () => /com aviso/.test(await T.txt(op, '#pj-status')), 15000);
  const st = await T.txt(op, '#pj-status');
  T.chk(new RegExp(`Faltam conferir ${N} folhas? com aviso`).test(st) && !/Aprovar todas/.test(await T.txt(op, '#pd')), `"Faltam conferir ${N} folha(s) com aviso", sem "Aprovar todas" na página`, st);

  T.passo('o modo conferir abre na 1ª folha com aviso');
  await op.click('#pj-status [data-pp="conferir"]');
  T.chk(await T.espera(async () => /Revisar folha/.test(await T.txt(op, '#d-title').catch(() => '')), 8000) && T.um('SELECT revisao FROM item WHERE codigo=?', (await T.txt(op, '#d-sub')).trim()) === 'pendente',
    '"Começar a conferir" abre uma folha com aviso', await T.txt(op, '#d-sub').catch(() => ''));
  await op.evaluate(() => closeDrawer(true));
  await T.abrirConferir(op, P);
  await op.waitForSelector('#cf-pane h2', { timeout: 15000 });
  await T.espera(async () => /Folha 1 de/.test(await T.txt(op, '#cf-prog')), 10000);
  const prog = await T.txt(op, '#cf-prog');
  T.chk(new RegExp(`Folha 1 de ${N} com aviso`).test(prog) && new RegExp(`${auto} sem aviso já conferidas?`).test(prog), `"Folha 1 de ${N} com aviso (${auto} sem aviso já conferidas)"`, prog);
  const atual = await op.evaluate(() => CONF.atual);
  T.chk(T.um('SELECT revisao FROM item WHERE codigo=?', atual) === 'pendente', 'a folha aberta é uma das com aviso', atual);
  T.chk(/Por que você está vendo esta folha/i.test(await T.txt(op, '#cf-pane')), 'o painel da folha começa por "Por que você está vendo esta folha"', (await T.txt(op, '#cf-pane')).slice(0, 200));
  const lista = await op.$$eval('#cf-linhas [data-cf-folha]', xs => xs.length);
  T.chk(lista === N, `a lista mostra só as ${N} com aviso (filtro "A conferir")`, lista);
  await T.print(op, 'conferir_so_avisos');

  T.passo('quem quiser ainda abre qualquer folha');
  await op.click('#cf-filtros [data-cf-filtro="todas"]');
  await T.espera(async () => (await op.$$eval('#cf-linhas [data-cf-folha]', xs => xs.length)) === total, 5000);
  T.chk((await op.$$eval('#cf-linhas [data-cf-folha]', xs => xs.length)) === total, `"Todas" mostra as ${total} folhas`);

  T.passo('desligado: tudo como antes');
  T.sql("UPDATE configuracao SET valor='0' WHERE chave='revisao.conferir_so_avisos'");
  const P2 = T.cv2('reservar', T.BASE, 'F026', 'CASA COMO ANTES', '1973'); T.cv2('processando', T.BASE, T.RAIZ, P2, 'CASA COMO ANTES');
  montar(T.BASE, T.RAIZ, P2, 'CASA COMO ANTES');
  T.chk(T.um('SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND revisado_por=?', P2, AUTO) === 0 && T.um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND revisao='pendente'", P2) > N, 'desligado: nenhuma entra conferida sozinha');
});
