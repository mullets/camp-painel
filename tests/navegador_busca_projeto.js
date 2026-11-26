// CAMP-PROJETO (26/11/2026). Rafael: "acho que dentro do projeto seria bom ter uma busca também.. pq tem projeto com 300 pranchas.. e procurar
// por qualquer dado". Prova, num projeto de 300 folhas (tests/semente_busca_projeto.py, F026-P0002):
// - a caixa "Buscar nas folhas" existe; código (D00041 e o código inteiro), nº da folha ("16A", "16 a", "10 A"/"10a"), título, escala, endereço com e sem
//   acento, cliente, escritório (nome inteiro e abreviação "Parisi"), tipo, situação ("conferida"), tubo (TB001-01), retenção, o que o CAMP Vision leu;
// - várias palavras = todas; "entre aspas" = a frase; contador "N de 300 folhas"; "achado em: …"; nenhuma = aviso com "Limpar a busca";
// - soma com o filtro Tipo; "Escolher todas as visíveis" escolhe só o resultado; "/" foca; Esc limpa;
// - o termo fica no endereço (?q=) e volta ao recarregar; cada filtragem (depois da espera) leva menos de 100 ms.
// Uso (servidor PRÓPRIO, portas 9150–9159; banco com tests/semear_banco_teste.py + tests/semente_busca_projeto.py):
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9152 node tests/navegador_busca_projeto.js
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9152';
const PRINTS = process.env.PRINTS || '';
const P = 'F026-P0002';
const problemas = [];
const chk = (ok, msg) => { console.log((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
(async () => {
  const br = await chromium.launch();
  const pg = await br.newPage({ viewport: { width: 1440, height: 900 } });
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  pg.on('dialog', d => d.dismiss().catch(() => {}));
  await pg.goto(BASE + '/');
  await pg.fill('#lg-email', 'rafael@camp.arq.br'); await pg.fill('#lg-senha', 'senha-bem-longa-123'); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  await pg.evaluate(() => { document.querySelectorAll('#toast,.toast').forEach(t => t.remove()) });
  const abrir = async (hash) => { await pg.evaluate(h => { location.hash = h }, hash); await pg.waitForFunction(p => window.PROJETO_PJ === p && document.querySelectorAll('#pd .project-series .thumb').length >= 290, P, { timeout: 30000 }); await pg.waitForTimeout(400); };
  await abrir('projeto/' + P);
  const temCaixa = await pg.locator('#pd [data-fl-q]').count();
  chk(temCaixa === 1, `a caixa "Buscar nas folhas" existe na barra das folhas (${temCaixa})`);
  if (!temCaixa) { await br.close(); console.log(`\n${problemas.length} FALHA(S)`); process.exit(1); }
  const vis = () => pg.evaluate(() => [...document.querySelectorAll('#pd .project-series .thumb')].filter(t => !t.hidden && !t.hasAttribute('data-copia-de')).map(t => t.dataset.cod.split('-').pop()));
  const buscar = async (q) => {
    await pg.fill('#pd [data-fl-q]', q); await pg.waitForTimeout(260);
    const ms = await pg.evaluate(() => { const t0 = performance.now(); aplicarFiltroFolhas((document.querySelector('.folhas-bar [data-fl-f].on') || { dataset: {} }).dataset.flF || ''); return performance.now() - t0; });
    return { v: await vis(), ms };
  };
  const casos = [
    ['D00041', ['D00041'], 'código curto'], [`${P}-1970-S01-D00042`, ['D00042'], 'código inteiro'],
    ['16A', ['D00041'], 'nº da folha "16A"'], ['16 a', ['D00041'], 'nº da folha com espaço "16 a"'], ['10a', ['D00042'], 'nº "10a" acha a folha "10 A"'],
    ['formas cobertura', ['D00041'], 'título, duas palavras (todas)'], ['"bloco a"', ['D00041'], 'frase entre aspas'],
    ['1:28', ['D00042'], 'escala'], ['fernao cardim', ['D00042'], 'endereço sem acento'], ['FERNÃO', ['D00042'], 'endereço com acento e maiúsculas'],
    ['condominio vitoria', ['D00042'], 'cliente'], ['Parisi', ['D00041'], 'escritório pela abreviação'], ['José Roberto Parisi', ['D00041'], 'escritório pelo nome'],
    ['TB001-01', ['D00043'], 'tubo'], ['umidade', ['D00045'], 'motivo da retenção'], ['lima otero', ['D00044'], 'o que o CAMP Vision leu'],
  ];
  let pior = 0;
  for (const [q, esperado, nome] of casos) {
    const r = await buscar(q); pior = Math.max(pior, r.ms);
    chk(JSON.stringify(r.v) === JSON.stringify(esperado), `${nome}: "${q}" → ${r.v.slice(0, 5).join(', ')}${r.v.length > 5 ? '…' : ''} (esperado ${esperado.join(', ')})`);
  }
  let r = await buscar('estrutura'); pior = Math.max(pior, r.ms);
  chk(r.v.length >= 12, `tipo "estrutura": ${r.v.length} folhas (12 do tipo + a do escritório)`);
  const cont = await pg.locator('#pd [data-fl-q-cont]').innerText();
  chk(/\b\d+ de 300 folhas/.test(cont), `contador: "${cont}"`);
  r = await buscar('formas cobertura');
  const achado = await pg.locator('#pd .thumb:not([hidden]) .fb-achado').first().innerText().catch(() => '');
  chk(/achado em: título/.test(achado), `"achado em" no cartão: "${achado}"`);
  r = await buscar('conferida'); pior = Math.max(pior, r.ms);
  chk(r.v.length === 30, `situação "conferida": ${r.v.length} (30 conferidas)`);
  r = await buscar('xyzsemresultado');
  const nada = await pg.locator('#pd [data-fl-q-cont]').innerText();
  chk(r.v.length === 0 && /Nenhuma folha/.test(nada) && (await pg.locator('#pd [data-fl-q-limpar]').count()) === 1, `sem resultado: aviso "${nada.slice(0, 60)}" com Limpar a busca`);
  await pg.click('#pd [data-fl-q-limpar]'); await pg.waitForTimeout(150);
  chk((await vis()).length >= 299, `Limpar a busca volta todas (${(await vis()).length})`);
  // soma com o filtro Tipo
  await buscar('prancha');
  await pg.selectOption('#pd [data-fl-tipo]', 'Corte'); await pg.waitForTimeout(150);
  const comTipo = await vis();
  const tiposOk = await pg.evaluate(() => [...document.querySelectorAll('#pd .project-series .thumb')].filter(t => !t.hidden).every(t => (t.dataset.tp || '').split('|').includes('Corte')));
  chk(comTipo.length > 0 && comTipo.length < 100 && tiposOk, `busca + Tipo "Corte": ${comTipo.length} folhas, todas Corte`);
  await pg.selectOption('#pd [data-fl-tipo]', ''); await pg.waitForTimeout(150);
  // Escolher todas as visíveis = só o resultado
  await buscar('estrutura');
  const nRes = (await vis()).length;
  await pg.click('#pd [data-pj-escolher]').catch(() => {});
  await pg.waitForTimeout(200);
  await pg.click('[data-pj-esc-todas]').catch(() => {});
  await pg.waitForTimeout(200);
  const nEsc = await pg.evaluate(() => (typeof PJ_ESC !== 'undefined' ? PJ_ESC.size : -1));
  chk(nEsc === nRes, `"Escolher todas as visíveis" escolhe só o resultado (${nEsc} de ${nRes})`);
  await pg.click('[data-pj-escolher]').catch(() => {}); await pg.waitForTimeout(100);
  // endereço e recarregar
  await buscar('fernao');
  const h = await pg.evaluate(() => location.hash);
  chk(/\?q=fernao$/.test(h), `o termo fica no endereço (${h})`);
  if (PRINTS) await pg.screenshot({ path: PRINTS + '/busca-no-projeto-1440.png', fullPage: false });
  await pg.reload(); await pg.waitForFunction(p => window.PROJETO_PJ === p && document.querySelectorAll('#pd .project-series .thumb').length >= 290, P, { timeout: 30000 }); await pg.waitForTimeout(600);
  const val = await pg.inputValue('#pd [data-fl-q]').catch(() => '');
  const vr = await vis();
  chk(val === 'fernao' && JSON.stringify(vr) === '["D00042"]', `recarregar mantém a busca ("${val}" → ${vr.join(', ')})`);
  // Esc limpa; "/" foca
  await pg.focus('#pd [data-fl-q]'); await pg.keyboard.press('Escape'); await pg.waitForTimeout(150);
  chk((await pg.inputValue('#pd [data-fl-q]')) === '' && (await vis()).length >= 299 && !/\?q=/.test(await pg.evaluate(() => location.hash)), 'Esc limpa a busca e o endereço');
  await pg.click('#pd h1, #pd .pd-titulo, body', { position: { x: 5, y: 5 } }).catch(() => {});
  await pg.evaluate(() => document.activeElement && document.activeElement.blur());
  await pg.keyboard.press('/'); await pg.waitForTimeout(100);
  chk(await pg.evaluate(() => document.activeElement && document.activeElement.matches('[data-fl-q]')), 'a tecla "/" vai para a busca');
  chk(pior < 100, `cada filtragem leva menos de 100 ms em 300 folhas (pior: ${pior.toFixed(1)} ms)`);
  // a rota continua sendo o projeto (breadcrumb e comparações de rota)
  chk(await pg.evaluate(p => rotaAtual() === 'projeto/' + p, P), 'rotaAtual() continua "projeto/F026-P0002" com a busca no endereço');
  const lateral = await pg.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  chk(lateral <= 1, `sem rolagem lateral (${lateral})`);
  chk(erros.length === 0, 'nenhum erro de JS ' + erros.join(' | ').slice(0, 200));
  await br.close();
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
