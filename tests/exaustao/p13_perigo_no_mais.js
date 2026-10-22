// CAMP-152 (Trello, 22/10): "Despublicar" e "Voltar para rascunho" do projeto só no "Mais ⋯", em vermelho, com a confirmação dizendo o alvo e
// a consequência (padrao-de-tela §1). A aba Publicação fica só com o Publicar. Admin que não é master vê os itens apagados, e o clique explica.
// Rodar: EXAUSTAO_PORTA=8994 bash tests/rodar_exaustao.sh tests/exaustao/p13_perigo_no_mais.js
const path = require('path'), { execFileSync } = require('child_process');
const T = require('./_comum');
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'f_montar.py'), ...a], { encoding: 'utf-8' }).trim();

T.rodar(async () => {
  T.passo('cenário: um projeto publicado (3 folhas)');
  const P = T.cv2('reservar', T.BASE, 'F026', 'CASA PERIGO', '1972'); montar('processando', T.BASE, T.RAIZ, P, 'CASA PERIGO'); montar('pronto', T.BASE, T.RAIZ, P, '3');
  T.sql("UPDATE item SET revisao='conferida' WHERE projeto_codigo=?", P);
  const ad = await T.entrar('admin');
  const r = await ad.evaluate(async P => {
    const lote = (await (await fetch(`/api/projetos/${P}/revisao`)).json()).lotes[0].id;
    const a = (await fetch(`/api/lotes/${lote}/aprovar`, { method: 'POST' })).status;
    const p = (await fetch(`/api/projetos/${P}/publicar-tudo`, { method: 'POST' })).status;
    return [a, p];
  }, P);
  T.chk(r[0] === 200 && T.um('SELECT status_site FROM projeto WHERE codigo=?', P) === 'no_ar', 'projeto publicado', JSON.stringify(r));

  T.passo('a aba Publicação não tem mais Despublicar nem Voltar para rascunho');
  await T.abrirProjeto(ad, P);
  await ad.evaluate(c => showProjeto(c, 'publicacao'), P); await ad.waitForTimeout(1500);
  const acoes = await T.txt(ad, '#pd-pub-acoes');
  T.chk(!/Despublicar|Voltar para rascunho/.test(acoes), 'aba Publicação: sem botões de perigo', acoes);

  T.passo('"Mais ⋯": os dois, em vermelho, numa seção "Tirar do público"');
  await ad.click('#pd .pj-mais-menu > summary');
  const itens = await ad.$$eval('#pd .pj-mais-menu [role="menuitem"]', bs => bs.map(b => ({ t: b.textContent.trim(), cor: getComputedStyle(b).color, perigo: b.classList.contains('perigo-txt') })));
  const desp = itens.find(x => /^Despublicar…$/.test(x.t)), rasc = itens.find(x => /^Voltar para rascunho…$/.test(x.t));
  T.chk(!!desp && !!rasc && desp.perigo && rasc.perigo, 'no "Mais ⋯": "Despublicar…" e "Voltar para rascunho…" com a classe de perigo', JSON.stringify(itens.map(x => x.t)));
  T.chk(desp && /^rgb\((1[5-9]\d|2\d\d), ?\d{1,2}, ?\d{1,2}\)$/.test(desp.cor), 'em vermelho', desp && desp.cor);
  T.chk(/Tirar do público/i.test(await T.txt(ad, '#pd .pj-mais-menu')), 'na seção "Tirar do público"');
  await T.print(ad, 'mais_perigo');

  T.passo('a confirmação diz o alvo e a consequência; cancelar não muda nada');
  await ad.evaluate(() => [...document.querySelectorAll('#pd .pj-mais-menu [role="menuitem"]')].find(b => /^Despublicar…$/.test(b.textContent.trim())).click());
  await ad.waitForSelector('#conf-ov', { state: 'visible', timeout: 8000 });
  const conf = await T.txt(ad, '#conf-ov');
  T.chk(conf.includes(P) && /deixam de ser públicas/.test(conf), 'a confirmação: o código do projeto e o que acontece', conf.slice(0, 200));
  await ad.click('#conf-ov [data-conf="nao"]').catch(async () => { await ad.keyboard.press('Escape') });
  await ad.waitForTimeout(800);
  T.chk(T.um('SELECT status_site FROM projeto WHERE codigo=?', P) === 'no_ar', 'cancelou: continua publicado');

  T.passo('confirmar: despublica');
  await T.abrirProjeto(ad, P);
  await ad.click('#pd .pj-mais-menu > summary');
  await ad.evaluate(() => [...document.querySelectorAll('#pd .pj-mais-menu [role="menuitem"]')].find(b => /^Despublicar…$/.test(b.textContent.trim())).click());
  await ad.waitForSelector('#conf-ov [data-conf="sim"]', { state: 'visible', timeout: 8000 });
  await ad.click('#conf-ov [data-conf="sim"]');
  T.chk(await T.espera(() => T.um('SELECT status_site FROM projeto WHERE codigo=?', P) === 'fora_do_ar', 30000), 'confirmou: o projeto foi despublicado', T.um('SELECT status_site FROM projeto WHERE codigo=?', P));
});
