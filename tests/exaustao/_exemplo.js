// Modelo de arquivo de exaustão (não roda: arquivos com _ na frente são ignorados pelo executor).
const T = require('./_comum');
T.rodar(async () => {
  T.passo('CAMP-0xx: título do cenário');
  const { P, D } = T.loteReal('CASA EXEMPLO');
  const op = await T.entrar('operador'); await T.abrirProjeto(op, P);
  T.chk(/Folhas/i.test(await T.txt(op, '#pj-cards')), 'CAMP-0xx: os cartões aparecem');
  await T.print(op, 'exemplo');
});
