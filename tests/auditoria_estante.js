// Modo estante no celular (390px): ler etiqueta DIGITANDO o código (sem câmera) e conferir uma caixa, sem erro no console.
// Uso: CAMP_BASE=http://127.0.0.1:8850 ZXING_LOCAL=/caminho/index.min.js node tests/auditoria_estante.js
// O banco precisa do semear_banco_teste.py; o teste cria as próprias caixas (CX-9xx) pela API.
// Sem ZXING_LOCAL, o pedido do leitor ZXing ao unpkg é respondido com um stub (o teste não depende de internet).
const fs = require('fs');
let pw; try { pw = require('playwright'); } catch (_) { pw = require('/opt/node22/lib/node_modules/playwright'); }
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const SHOTS = process.env.SHOTS || '';
const problemas = [], linhas = [];
const chk = (ok, m) => { linhas.push(`${ok ? 'ok   ' : 'ERRO '} ${m}`); if (!ok) problemas.push(m); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await pw.chromium.launch({ executablePath: fs.existsSync(CHROME) ? CHROME : undefined });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  const erros = [];
  const semZX = !(process.env.ZXING_LOCAL && fs.existsSync(process.env.ZXING_LOCAL));   // sem o arquivo local, o 404 do stub do ZXing não conta como erro
  page.on('console', m => { if (m.type() !== 'error') return; if (semZX && /unpkg\.com\/@zxing/.test((m.location() || {}).url || '')) return; erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  // nada sai para a internet: imagens do site (camp.arq.br, exemplo.test do banco de teste) recebem um PNG vazio de 1 px
  const PNG1 = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');
  const externos = new Set();
  await ctx.route(u => !String(u).startsWith(BASE) && !/unpkg\.com\/@zxing/.test(String(u)), route => { externos.add(new URL(route.request().url()).host); return route.fulfill({ status: 200, contentType: 'image/png', body: PNG1 }); });
  let pedidosZX = 0;
  await ctx.route(/unpkg\.com\/@zxing\/library@0\.21\.3\//, route => {
    pedidosZX++;
    const local = process.env.ZXING_LOCAL;
    if (local && fs.existsSync(local)) return route.fulfill({ status: 200, contentType: 'application/javascript', headers: { 'Access-Control-Allow-Origin': '*' }, body: fs.readFileSync(local) });
    return route.fulfill({ status: 404, headers: { 'Access-Control-Allow-Origin': '*' }, body: '' });
  });

  // login (operador) e as caixas do teste
  const login = await ctx.request.post(BASE + '/api/auth/login', { data: { email: 'operador@camp.arq.br', senha: 'senha-operador-123' } });
  chk(login.ok(), 'login do operador');
  const ids = {};
  for (const [ident, fundo] of [['CX-901', 'F026'], ['CX-902', 'F023']]) {
    let r = await ctx.request.post(BASE + '/api/localizacoes', { data: { tipo: 'caixa', identificador: ident, fundo_codigo: fundo } });
    if (r.status() === 409) { const ls = await (await ctx.request.get(BASE + '/api/localizacoes')).json(); ids[ident] = ls.find(l => l.identificador === ident && l.fundo_codigo === fundo).id; }
    else ids[ident] = (await r.json()).id;
  }
  await ctx.request.post(BASE + '/api/localizacoes/alocar', { data: { localizacao_id: ids['CX-901'], codigos: [1, 2, 3, 4].map(s => `F026-P0001-1968-S01-D0000${s}`) } });
  await ctx.request.post(BASE + '/api/localizacoes/alocar', { data: { localizacao_id: ids['CX-902'], codigos: ['F023-P0011-1959-S01-D00001'] } });

  await page.goto(BASE + '/#painel'); await page.waitForSelector('#v-painel.on', { timeout: 15000 }); await sleep(1500);
  chk(pedidosZX === 0, 'o leitor ZXing NÃO é baixado ao abrir o painel (só ao abrir a tela da estante)');
  const bt = page.locator('#nav > button[data-v="estante"]');
  chk(await bt.isVisible(), 'celular: "Ler etiqueta" aparece na barra de baixo, entre os itens principais');
  const caber = await page.evaluate(() => { const m = document.getElementById('nav-mais').getBoundingClientRect(); return { mais: m.right, larg: innerWidth, rolagem: document.documentElement.scrollWidth } });
  chk(caber.mais <= caber.larg + 0.5 && caber.rolagem <= caber.larg, `celular: barra de baixo cabe (Mais termina em ${Math.round(caber.mais)} de ${caber.larg}px) e a página não rola para o lado (${caber.rolagem})`);
  await bt.click(); await page.waitForSelector('#v-estante.on'); await sleep(600);
  chk(page.url().endsWith('#estante'), 'tocar em "Ler etiqueta" abre #estante');
  const temDetector = await page.evaluate(() => 'BarcodeDetector' in window);
  chk(temDetector || pedidosZX === 1, `sem BarcodeDetector neste navegador, o ZXing é pedido ao abrir a tela (${pedidosZX} pedido)`);
  if (SHOTS) await page.screenshot({ path: SHOTS + '/estante_390_leitura.png', fullPage: true });

  const digitar = async (cod) => { await page.fill('#estn-cod', cod); await page.press('#estn-cod', 'Enter'); await sleep(900); };
  const voltaEstante = async () => { await page.evaluate(() => nav('estante')); await page.waitForSelector('#v-estante.on'); await sleep(300); };
  await digitar('f026-p0001-1968-s01-d00002');
  chk(decodeURIComponent(page.url()).endsWith('#item/F026-P0001-1968-S01-D00002'), 'folha digitada (minúsculas) abre a página da folha: ' + page.url());
  await voltaEstante(); await digitar('F026-P0001');
  chk(page.url().endsWith('#projeto/F026-P0001'), 'código do projeto abre o projeto: ' + page.url());
  await voltaEstante(); await digitar('F026');
  chk(page.url().endsWith('#fundo/F026'), 'código do fundo abre o fundo: ' + page.url());
  await voltaEstante(); await digitar('XYZ-1');
  chk(page.url().endsWith('#estante') && /Não achei/.test(await page.textContent('#estn-res')), 'código desconhecido: fica na tela e explica');
  await digitar('F026-CX-901');
  chk(page.url().endsWith('#estante/caixa/' + ids['CX-901']), 'etiqueta da caixa abre a conferência: ' + page.url());
  await page.waitForSelector('#estn-conf .estn-lista');
  const nEsp = () => page.locator('#estn-conf .estn-lista li.falta, #estn-conf .estn-lista li.ok').count();
  chk(await nEsp() === 4 && /Falta ler 4/.test(await page.textContent('#estn-conf .estn-totais')), 'conferência mostra a lista esperada (4 folhas, todas "falta ler")');
  chk(await page.isDisabled('#estn-conf button[onclick="estnRegistrar()"]'), '"Registrar conferência" fica desligado antes da primeira leitura');
  await digitar('F026-P0001-1968-S01-D00001');
  chk(/conferida/.test(await page.textContent('#estn-res')) && await page.locator('#estn-conf li.ok').count() === 1, 'leitura de folha da caixa marca "conferida"');
  await digitar('F026-P0001-1968-S01-D00001');
  chk(/já foi lida/.test(await page.textContent('#estn-res')), 'a mesma leitura duas vezes avisa e não conta de novo');
  await digitar('F023-P0011-1959-S01-D00001');
  chk(await page.locator('#estn-conf li.outro').count() === 1 && /está em CX-902/.test(await page.textContent('#estn-conf li.outro')), 'folha de outra caixa fica em destaque, dizendo onde está cadastrada');
  await digitar('F026');
  chk(/fundo/.test(await page.textContent('#estn-res')), 'etiqueta de fundo na conferência: "não reconhecida", com o motivo');
  if (SHOTS) await page.screenshot({ path: SHOTS + '/estante_390_conferencia.png', fullPage: true });
  await page.click('#estn-conf li.outro button'); await sleep(1200);
  chk(await nEsp() === 5 && await page.locator('#estn-conf li.ok').count() === 2 && await page.locator('#estn-conf li.outro').count() === 0, '"Mover para cá": a folha passa a ser desta caixa e já conta como conferida');
  await page.click('#estn-conf button[onclick="estnRegistrar()"]'); await sleep(1200);
  const msg = await page.textContent('#estn-res');
  chk(/Conferência de CX-901 registrada: 2 de 5 folhas conferidas, 3 faltando/.test(msg), 'registrar: mensagem com os totais (' + msg.trim().slice(0, 90) + ')');
  chk(/Última conferência/.test(await page.textContent('#estn-conf')) && /Faltaram 3/.test(await page.textContent('#estn-conf .estn-totais')), 'depois de registrar: "Última conferência" e o que faltou em destaque');
  // câmera: sem câmera no navegador de teste, a mensagem diz o que fazer e nada quebra
  await page.click('#estn-cam-btn'); await sleep(1500);
  chk(/(câmera|Digite)/.test(await page.textContent('#estn-msg')), 'sem câmera: a tela explica e oferece digitar (' + (await page.textContent('#estn-msg')).trim().slice(0, 80) + ')');
  if (SHOTS) await page.screenshot({ path: SHOTS + '/estante_390_registrada.png', fullPage: true });
  const largura = await page.evaluate(() => document.documentElement.scrollWidth);
  chk(largura <= 390, 'conferência no celular sem rolagem para o lado (' + largura + 'px)');
  // histórico de ações (só admin vê): entra como admin numa sessão à parte
  const adm = await pw.request.newContext({ baseURL: BASE });
  await adm.post('/api/auth/login', { data: { email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' } });
  const ev = await (await adm.get('/api/eventos?tipo=conferencia_caixa&entidade=localizacao')).json();
  const det = ev.eventos && ev.eventos[0] ? JSON.parse(ev.eventos[0].detalhe || '{}') : {};
  chk(ev.total >= 1 && det.identificador === 'CX-901' && det.conferidos === 2 && det.faltando === 3 && det.esperados === 5, 'a conferência está no histórico de ações, com os totais: ' + JSON.stringify(det).slice(0, 120));
  await adm.dispose();
  chk(erros.length === 0, 'sem erro no console' + (erros.length ? ': ' + erros.slice(0, 5).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n')); console.log(`\n=== ESTANTE: ${problemas.length} problema(s) ===`); process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
