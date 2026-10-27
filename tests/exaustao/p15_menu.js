// CAMP-154 (22/10) → UX-28 (27/10): menu pela ordem do trabalho — topo com as filas do dia à vista; Fundos, Arquitetos, Pedidos de alta resolução e
// Máquinas também; o resto em "Mais". As teclas não mudaram: 1–5 e D N P (Decisões, Material novo, Problemas) e as outras letras com o "Mais" fechado.
// Conferindo uma folha, as letras do menu não valem (R gira, K recorta).
// Rodar: EXAUSTAO_PORTA=8998 bash tests/rodar_exaustao.sh tests/exaustao/p15_menu.js
const T = require('./_comum');
const visiveis = pg => pg.$$eval('#nav button', bs => bs.filter(b => b.offsetParent !== null).map(b => (b.dataset.v || b.id) + ':' + b.textContent.replace(/\s+/g, ' ').trim()));

T.rodar(async () => {
  const ad = await T.entrar('admin');
  await ad.evaluate(() => { try { localStorage.removeItem('camp.nav.mais') } catch (_) {} ; nav('painel') }); await ad.waitForTimeout(1200);

  T.passo('itens sempre à vista e o "Mais"');
  const v0 = await visiveis(ad);
  const dest = v0.filter(x => !/^nav-(mais|busca)/.test(x)).map(x => x.split(':')[0]);
  T.chk(dest.join(',') === 'painel,filas,erros,decisoes,projetos,fundos,arquitetos,solicitacoes,estacoes', 'o menu mostra, na ordem do trabalho, as filas do dia e os destinos', JSON.stringify(v0));
  const nome = v => (v0.find(x => x.startsWith(v + ':')) || '').split(':')[1] || '';
  T.chk(/^Precisa de você/.test(nome('painel')) && /^Fundos/.test(nome('fundos')) && /^Pedidos de alta resolução/.test(nome('solicitacoes')) && /^Máquinas/.test(nome('estacoes')), 'os nomes: Precisa de você · Fundos · Pedidos de alta resolução · Máquinas', JSON.stringify(v0));
  T.chk(v0.some(x => /^nav-mais-pc:Mais/.test(x)), 'e o "Mais"');
  T.chk(!v0.some(x => /^(config|relatorios|glossario):/.test(x)), 'Configurações, Relatórios e Glossário ficam no "Mais" (fechado)');
  await T.print(ad, 'menu_fechado');

  T.passo('"Mais" abre e fecha');
  await ad.click('#nav-mais-pc');
  const v1 = await visiveis(ad);
  T.chk(['localizacao', 'etiquetas', 'uso', 'relatorios', 'config', 'glossario'].every(k => v1.some(x => x.startsWith(k + ':'))), 'aberto: os itens secundários aparecem', JSON.stringify(v1.map(x => x.split(':')[0])));
  T.chk(await ad.getAttribute('#nav-mais-pc', 'aria-expanded') === 'true', 'aria-expanded=true');
  await T.print(ad, 'menu_aberto');
  await ad.click('#nav-mais-pc');
  T.chk(!(await visiveis(ad)).some(x => x.startsWith('relatorios:')), 'fechado de novo');

  T.passo('teclas: 1–5 os destinos; D N P com o "Mais" fechado');
  const tecla = async k => { await ad.evaluate(() => document.activeElement && document.activeElement.blur && document.activeElement.blur()); await ad.keyboard.press(k); await ad.waitForTimeout(500); return ad.evaluate(() => rotaAtual().split('/')[0]) };
  T.chk(await tecla('2') === 'projetos' && await tecla('3') === 'fundos' && await tecla('4') === 'solicitacoes' && await tecla('5') === 'estacoes' && await tecla('1') === 'painel', '1–5 abrem os 5 destinos');
  T.chk(await tecla('d') === 'decisoes', 'D abre Decisões');
  T.chk(await tecla('l') === 'relatorios', 'L abre Relatórios (com o "Mais" fechado)');
  T.chk((await visiveis(ad)).some(x => /^relatorios:/.test(x)) && await ad.$eval('#nav button[data-v="relatorios"]', b => b.classList.contains('on')), 'a tela aberta é do "Mais": ele aparece aberto, com o item marcado');
  T.chk(await tecla('n') === 'filas' && await tecla('p') === 'erros' && await tecla('i') === 'arquitetos', 'N, P e I abrem Material novo, Problemas e Arquitetos');

  T.passo('o número do "Precisa de você" soma decisões, material novo e problemas que bloqueiam');
  const r = await ad.evaluate(async () => { const p = await (await fetch('/api/pendencias')).json(); atualizarContadoresMenu(p); const el = document.getElementById('n-gente'); return { p: (+p.decisoes || 0) + (+p.material_novo || 0) + (+p.erros_bloqueantes || 0), tela: el.hidden ? 0 : +el.textContent.replace(/\D/g, '') } });
  T.chk(r.p === r.tela, `o número bate com a fonte única (${r.tela})`, JSON.stringify(r));

  T.passo('operador: Máquinas não aparece; Pedidos de alta resolução sim');
  const op = await T.entrar('operador');
  await op.evaluate(() => nav('painel')); await op.waitForTimeout(1000);
  const vo = await visiveis(op);
  T.chk(!vo.some(x => x.startsWith('estacoes:')) && vo.some(x => x.startsWith('solicitacoes:')), 'operador: sem Máquinas; com Pedidos de alta resolução', JSON.stringify(vo));
  T.chk(await op.evaluate(async () => { document.activeElement && document.activeElement.blur(); document.dispatchEvent(new KeyboardEvent('keydown', { key: '5', bubbles: true })); await new Promise(r => setTimeout(r, 400)); return rotaAtual().split('/')[0] }) !== 'estacoes', 'operador: a tecla 5 não abre Máquinas');
});
