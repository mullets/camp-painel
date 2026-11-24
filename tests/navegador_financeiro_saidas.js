// CAMP-FIN-CONSERTOS (24/11/2026). Rafael: "ele pegou a saída de dinheiro do Mercado Pago? não consigo achar lá para justificar… saída de
// Pix, boleto, transferências". Navegador de verdade contra um SITE FALSO (servidor http deste script, porta FAKE_WP_PORT, padrão 9118) que
// imita as rotas /painel/mp/* do plugin (contrato 1.34): sem a configuração do relatório o pedido volta 502 camp_mp_sem_config; com ela, o
// relatório fica pronto e traz as saídas do Extrato real do Rafael. Nenhuma chamada ao site nem ao Mercado Pago de verdade.
//  [A] Despesas mostra a linha "Saídas do Mercado Pago" (nada pedido ainda) com "Buscar saídas agora"
//  [B] Buscar → erro exato "Falta configurar…" com a resposta do Mercado Pago e o botão "Configurar relatório no Mercado Pago"
//  [C] Configurar: o painel lateral mostra as colunas (simulação; o site recebe simular=true); "Configurar agora" aplica (simular=false)
//      e já pede o relatório: a linha diz que está esperando o Mercado Pago gerar
//  [D] Buscar de novo: baixa, a linha mostra "recebido" e as saídas importadas; a lista mostra Pagamento com Pix (DSC…), Pix enviado,
//      Pagamento de boleto/conta e Compra no cartão de débito, com "Movimento …"; a fila "Precisa justificar" mostra quem recebeu
//  [E] Importar Extrato do Mercado Pago (CSV): simular → importar; o nome de quem recebeu completa o que veio do relatório
// Uso (servidor PRÓPRIO, portas 9110–9119; o banco com tests/semear_banco_teste.py + tests/semente_financeiro.py):
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9113 FAKE_WP_PORT=9118 node tests/navegador_financeiro_saidas.js
const fs = require('fs');
const http = require('http');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9113';
const FPORT = +(process.env.FAKE_WP_PORT || 9118);
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };

// ---- site falso
const hoje = new Date(Date.now() - 3 * 3600e3).toISOString().slice(0, 10), mes0 = hoje.slice(0, 8) + '01';
const SITE = { configurado: false, pedido: false, cfg: [], pedidos: [] };
const SAIDAS = [
  { linha: 2, data: hoje + 'T10:00:00.000-03:00', source_id: '132300X97RZ', descricao: 'payment', debito: 69.0, meio_tipo: 'bank_transfer', meio: 'pix', tags: '["PIX","QR"]' },
  { linha: 3, data: hoje + 'T11:00:00.000-03:00', source_id: '1323MTY5PX', descricao: 'payout', debito: 750.0, tags: '["PIX"]' },
  { linha: 4, data: hoje + 'T09:00:00.000-03:00', source_id: '1323TRBPVW', descricao: 'payment', debito: 472.24, meio_tipo: 'ticket', meio: 'bolbradesco' },
  { linha: 5, data: hoje + 'T09:30:00.000-03:00', source_id: '1323XAN6MT', descricao: 'payment', debito: 569.25, meio_tipo: 'debit_card', meio: 'debmaster' },
];
const json = (res, code, d) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(d)); };
const site = http.createServer((req, res) => {
  let corpo = ''; req.on('data', c => { corpo += c; }); req.on('end', () => {
    const u = new URL(req.url, 'http://x'), p = u.pathname;
    if (p === '/wp-json/camp/v1/painel/mp/relatorios') return json(res, 200, { itens: SITE.configurado && SITE.pedido ? [{ arquivo: 'camp-liberacoes-' + mes0 + '.csv', begin_date: mes0 + 'T03:00:00Z', status: 'processed', criado: new Date().toISOString() }] : [] });
    if (p === '/wp-json/camp/v1/painel/mp/relatorio' && req.method === 'POST') {
      SITE.pedidos.push(JSON.parse(corpo || '{}'));
      if (!SITE.configurado) return json(res, 502, { code: 'camp_mp_sem_config', message: 'Falta configurar o relatório de liberações no Mercado Pago.', data: { status: 502, mp_http: 404, mp_mensagem: 'report config not found' } });
      SITE.pedido = true; return json(res, 202, { ok: true, pedido: true });
    }
    if (p === '/wp-json/camp/v1/painel/mp/relatorio') return json(res, 200, { arquivo: u.searchParams.get('arquivo'), itens: SAIDAS });
    if (p === '/wp-json/camp/v1/painel/mp/relatorio/config' && req.method === 'POST') {
      const b = JSON.parse(corpo || '{}'); SITE.cfg.push(b); if (b.simular === false) SITE.configurado = true;
      return json(res, 200, { acao: 'criar', existia: false, simulado: b.simular !== false, prefixo: 'camp-liberacoes', colunas: ['DATE', 'SOURCE_ID', 'EXTERNAL_REFERENCE', 'RECORD_TYPE', 'DESCRIPTION', 'NET_DEBIT_AMOUNT', 'PAYMENT_METHOD_TYPE', 'OPERATION_TAGS'] });
    }
    if (p === '/wp-json/camp/v1/painel/mp/pagamentos') return json(res, 200, { itens: [], mais: false });
    return json(res, 404, { code: 'rest_no_route', message: 'Nenhuma rota' });
  });
});
const CSV = 'INITIAL_BALANCE;CREDITS;DEBITS;FINAL_BALANCE\n5.000,00;210,00;-1.860,49;6.204,80\n\nRELEASE_DATE;TRANSACTION_TYPE;REFERENCE_ID;TRANSACTION_NET_AMOUNT;PARTIAL_BALANCE\n'
  + `${hoje.split('-').reverse().join('-')};Pagamento com Pix DSC - MATERIAIS PARA CONSTRUCAO LTDA;132300X97RZ;-69,00;6.931,00\n`
  + `${hoje.split('-').reverse().join('-')};Danilo Machado Barbalaco · Pix enviado;1323MTY5PX;-750,00;6.181,00\n`
  + `${hoje.split('-').reverse().join('-')};Anthropic* claude sub · Pagamento;1323XAN6MT;-569,25;5.611,75\n`
  + `${hoje.split('-').reverse().join('-')};Liberação de dinheiro;1323LIB001;150,00;5.761,75\n`
  + `${hoje.split('-').reverse().join('-')};Venda com Pix Visita guiada ingressos;1323VEN001;60,00;5.821,75\n`;

(async () => {
  await new Promise(ok => site.listen(FPORT, '127.0.0.1', ok));
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const ctx = await browser.newContext({ viewport: { width: 2000, height: 1100 } });
    const P = await ctx.newPage();
    P.on('console', m => { if (m.type() === 'error' && !/status of (40[0-9]|50[0-9])|Failed to load resource|favicon/.test(m.text())) erros.push(m.text().slice(0, 200)); });
    P.on('pageerror', e => erros.push('pageerror: ' + e.message));
    await P.goto(BASE + '/');
    await P.fill('#lg-email', 'rafael@camp.arq.br'); await P.fill('#lg-senha', 'senha-bem-longa-123'); await P.press('#lg-senha', 'Enter');
    await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    for (const [k, v] of [['wp.url', `http://127.0.0.1:${FPORT}`], ['wp.usuario', 'painel'], ['wp.app_password', 'senha-de-teste'], ['financeiro.mp_coleta_min', '0'], ['financeiro.mp_inicio', mes0]])
      await P.evaluate(([k, v]) => API('/api/config/' + k, { method: 'PUT', body: JSON.stringify({ valor: v }) }), [k, v]);
    await P.goto(BASE + '/#financeiro/despesas'); await P.reload();
    await P.waitForFunction(() => document.getElementById('v-financeiro')?.classList.contains('on') && FIN.desp && !FIN.carregando, null, { timeout: 20000 });
    const linha = () => P.locator('#fin-saidas').innerText();
    let t = await linha();
    chk(/Saídas do Mercado Pago:/.test(t) && /ainda nenhum relatório pedido/.test(t) && await P.locator('#fin-saidas [data-fin-acao="saidas-buscar"]').isVisible(), '[A] linha "Saídas do Mercado Pago" com "Buscar saídas agora": ' + t.replace(/\s+/g, ' ').slice(0, 160));
    // [B]
    await P.click('#fin-saidas [data-fin-acao="saidas-buscar"]');
    await P.waitForFunction(() => /Falta configurar/.test(document.getElementById('fin-saidas').innerText), null, { timeout: 15000 }).catch(() => {});
    t = await linha();
    chk(/Falta configurar o relatório de liberações no Mercado Pago/.test(t) && /HTTP 404/.test(t) && /report config not found/.test(t), '[B] erro exato, com a resposta do Mercado Pago: ' + t.replace(/\s+/g, ' ').slice(0, 200));
    chk(await P.locator('#fin-saidas [data-fin-acao="saidas-config"]').isVisible(), '[B] botão "Configurar relatório no Mercado Pago"');
    chk(SITE.pedidos.length === 1 && SITE.pedidos[0].desde === mes0, '[B] pediu o mês corrente uma vez e parou (sem configuração os outros meses não adiantam): ' + JSON.stringify(SITE.pedidos));
    // [C]
    await P.click('#fin-saidas [data-fin-acao="saidas-config"]');
    await P.waitForSelector('#fin-lado:not([hidden]) [data-fin-acao="saidas-config-aplicar"]', { timeout: 10000 });
    const lado = await P.locator('#fin-lado').innerText();
    chk(/OPERATION_TAGS/.test(lado) && /Nada muda até você confirmar/.test(lado) && SITE.cfg.length === 1 && SITE.cfg[0].simular === true && !SITE.configurado, '[C] simulação: colunas no painel lateral; o site recebeu simular=true');
    await P.click('#fin-lado [data-fin-acao="saidas-config-aplicar"]');
    await P.waitForFunction(() => /esperando o Mercado Pago gerar/.test(document.getElementById('fin-saidas').innerText), null, { timeout: 15000 }).catch(() => {});
    t = await linha();
    chk(SITE.configurado && SITE.cfg[1] && SITE.cfg[1].simular === false && /esperando o Mercado Pago gerar/.test(t) && /último relatório pedido/.test(t), '[C] "Configurar agora" aplica (simular=false) e já pede o relatório: ' + t.replace(/\s+/g, ' ').slice(0, 200));
    chk(await P.locator('#fin-lado').isHidden(), '[C] o painel lateral fecha');
    // [D]
    await P.click('#fin-saidas [data-fin-acao="saidas-buscar"]');
    await P.waitForFunction(() => /saídas importadas|saída importada/.test(document.getElementById('fin-saidas')?.innerText || '') && /recebido (?!ainda)/.test(document.getElementById('fin-saidas').innerText), null, { timeout: 20000 }).catch(() => {});
    await P.waitForTimeout(1500);
    t = await linha();
    chk(/recebido (?!ainda)/.test(t) && /\d+ saídas importadas/.test(t) && !/Falta configurar/.test(t), '[D] a linha mostra recebido e quantas saídas: ' + t.replace(/\s+/g, ' ').slice(0, 200));
    const lista = await P.locator('#fin-p-despesas .fin-lista').innerText();
    chk(/Pagamento com Pix/.test(lista) && /Pix enviado/.test(lista) && /Pagamento de boleto\/conta/.test(lista) && /Compra no cartão de débito/.test(lista) && /Movimento …0X97RZ/.test(lista), '[D] a lista mostra os tipos do Extrato e "Movimento …0X97RZ"');
    // [E] Extrato CSV
    await P.click('#fin-p-despesas [data-fin-acao="extrato-mp"]');
    await P.setInputFiles('#fin-x-arq', { name: 'extrato.csv', mimeType: 'text/csv', buffer: Buffer.from(CSV, 'utf-8') });
    await P.click('#fin-lado [data-fin-acao="extrato-simular"]');
    await P.waitForSelector('#fin-x-res table', { timeout: 10000 });
    const sim = await P.locator('#fin-x-res').innerText();
    chk(/Simulação:/.test(sim) && /0 saídas novas/.test(sim) && /3 completadas/.test(sim) && /2 entradas \(não entram\)/.test(sim) && /DSC - MATERIAIS PARA CONSTRUCAO LTDA/.test(sim), '[E] simular: completa as 3 que vieram do relatório, entradas fora: ' + sim.replace(/\s+/g, ' ').slice(0, 220));
    await P.click('#fin-lado [data-fin-acao="extrato-importar"]');
    await P.waitForFunction(() => /Importado:/.test(document.getElementById('fin-x-res')?.innerText || ''), null, { timeout: 10000 }).catch(() => {});
    await P.keyboard.press('Escape');
    await P.waitForFunction(() => FIN.desp && !FIN.carregando && /DSC - MATERIAIS/.test(document.querySelector('#fin-p-despesas .fin-lista')?.innerText || ''), null, { timeout: 15000 }).catch(() => {});
    const l2 = await P.locator('#fin-p-despesas .fin-lista').innerText();
    chk(/DSC - MATERIAIS PARA CONSTRUCAO LTDA/.test(l2) && /Anthropic\* claude sub/.test(l2) && /Danilo Machado Barbalaco/.test(l2), '[E] importar: a lista mostra quem recebeu, como no Extrato');
    await P.click('#fin-kpis [data-fin-acao="fila"]');
    await P.waitForSelector('#fin-fila:not([hidden]) #fin-f-just', { timeout: 10000 });
    let viu = '';
    for (let i = 0; i < 12; i++) { const f = await P.locator('#fin-fila').innerText(); viu += f; if (/DSC - MATERIAIS/.test(f)) break; await P.click('#fin-fila [data-fin-acao="fila-pular"]').catch(() => {}); await P.waitForTimeout(400); }
    chk(/DSC - MATERIAIS PARA CONSTRUCAO LTDA/.test(viu) && /Pagamento com Pix/.test(viu) && /Movimento …0X97RZ/.test(viu), '[E] a fila "Precisa justificar" mostra quem recebeu, o tipo e o movimento');
    await P.click('#fin-fila [data-fin-acao="fila-fechar"]').catch(() => {});
    await ctx.close();
  } catch (e) {
    chk(false, 'o teste quebrou: ' + (e.stack || e.message).slice(0, 400));
  } finally {
    await browser.close(); site.close();
  }
  chk(erros.length === 0, 'nenhum erro de JS: ' + erros.slice(0, 5).join(' | '));
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
