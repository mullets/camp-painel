// CAMP-ENTREGA (25/11/2026). Rafael: "Dentro de um projeto, no painel preciso conseguir baixar o arquivo em TIFF em alguma aba, ou o seu
// original em alta. Além disso, caso alguém solicite acesso a algum, fazer uma resposta para download com link temporário e uma cobrança,
// além de justificar o porquê da cobrança ou ausência dela."
// Prova, a 1440 e 390 px: aba "Arquivos originais" do projeto (lista, Baixar TIFF baixa de verdade, .zip com as escolhidas, sem rolagem
// lateral); "Enviar link de download a alguém" cria o pedido e abre o envio com a seção Cobrança (com/sem, motivos, valor sugerido,
// liberar após pagamento); sem escolher cobrança o envio não sai (o teste NUNCA clica em Aprovar e enviar de verdade: o "Aprovar" só é
// clicado sem escolha, quando o painel recusa antes de falar com alguém); página pública "Aguardando pagamento". Leitura não vê a aba.
// Uso (servidor PRÓPRIO, portas 9110–9139; banco: tests/semear_banco_teste.py + tests/semente_originais.py <qnap>):
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9133 PRINTS=<pasta> TOKEN=<impresso pela semente> node tests/navegador_originais.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9133';
const PRINTS = process.env.PRINTS || '/dev/shm';
const TOKEN = process.env.TOKEN || 'tokenDeTesteDaPaginaAguardandoPagamento0123';
const P = 'F026-P0001';
const problemas = [];
const chk = (ok, msg) => { console.log((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
const semToast = pg => pg.addStyleTag({ content: '#toast,.toast{display:none!important}' }).catch(() => {});
async function login(br, w, email, senha) {
  const ctx = await br.newContext({ viewport: { width: w, height: w > 600 ? 900 : 844 }, acceptDownloads: true });
  const pg = await ctx.newPage(); const erros = []; pg.on('pageerror', e => erros.push(e.message)); pg.on('dialog', d => d.dismiss().catch(() => {}));
  await pg.goto(BASE + '/'); await pg.fill('#lg-email', email); await pg.fill('#lg-senha', senha); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, pg, erros };
}
const semRolagem = pg => pg.evaluate(() => { const m = document.querySelector('.main') || document.documentElement; return document.documentElement.scrollWidth <= window.innerWidth + 1 && m.scrollWidth <= m.clientWidth + 1; });
(async () => {
  fs.mkdirSync(PRINTS, { recursive: true });
  const br = await chromium.launch();
  for (const w of [1440, 390]) {
    const { ctx, pg, erros } = await login(br, w, 'rafael@camp.arq.br', 'senha-bem-longa-123');
    await pg.goto(`${BASE}/#projeto/${P}`); await pg.waitForSelector('[data-pj-tab="originais"]', { timeout: 20000 });
    await pg.click('[data-pj-tab="originais"]');
    await pg.waitForSelector('#pj-originais .po-folha', { timeout: 15000 });
    const n = await pg.locator('#pj-originais .po-folha').count();
    chk(n === 6, `[${w}] aba Arquivos originais lista as 6 folhas (${n})`);
    chk(await pg.locator('#pj-originais a:has-text("Baixar TIFF")').count() === 5 && await pg.locator('#pj-originais a:has-text("Baixar JPG original")').count() === 2
      && await pg.locator('#pj-originais :text("sem TIFF registrado")').count() === 1, `[${w}] Baixar TIFF (5), Baixar JPG original (2), "sem TIFF registrado" (1)`);
    chk(await semRolagem(pg), `[${w}] sem rolagem lateral`);
    const [dl] = await Promise.all([pg.waitForEvent('download', { timeout: 15000 }), pg.locator('#pj-originais a:has-text("Baixar TIFF")').first().click()]);
    const tam = fs.statSync(await dl.path()).size;
    chk(/\.tif$/.test(dl.suggestedFilename()) && tam > 1000, `[${w}] Baixar TIFF baixa o arquivo (${dl.suggestedFilename()}, ${tam} bytes)`);
    chk(await pg.locator('#po-zip').isDisabled() && await pg.locator('#po-enviar').isDisabled(), `[${w}] sem escolha: .zip e Enviar desabilitados`);
    const cbs = pg.locator('#pj-originais [data-po-sel]'); await cbs.nth(0).check(); await cbs.nth(1).check();
    chk((await pg.locator('#po-conta').textContent()).includes('2 folhas escolhidas'), `[${w}] contador: 2 folhas escolhidas`);
    await semToast(pg);
    await pg.screenshot({ path: `${PRINTS}/originais-aba-${w}.png`, fullPage: true });
    const [dz] = await Promise.all([pg.waitForEvent('download', { timeout: 15000 }), pg.click('#po-zip')]);
    chk(/\.zip$/.test(dz.suggestedFilename()) && fs.statSync(await dz.path()).size > 2000, `[${w}] Baixar selecionadas (.zip): ${dz.suggestedFilename()}`);
    await pg.click('#po-enviar'); await pg.waitForSelector('#po-ped', { timeout: 10000 });
    await pg.fill('#po-nome', 'Carla Lima'); await pg.fill('#po-email', 'carla@editora.exemplo'); await pg.selectOption('#po-fin', 'publicacao');
    await semToast(pg); await pg.screenshot({ path: `${PRINTS}/originais-pedido-${w}.png`, fullPage: false });
    await pg.click('#po-ped button[type=submit]');
    await pg.waitForSelector('#se-cob', { timeout: 15000 });
    chk(await pg.locator('#se-cob input[value="sem"]').isEnabled() && await pg.locator('#se-cob input[value="com"]').isEnabled(), `[${w}] envio abre com a seção Cobrança (admin pode cobrar)`);
    await pg.click('[data-se-enviar]');
    chk((await pg.locator('#se-err').textContent()).includes('Escolha se o envio tem cobrança'), `[${w}] Aprovar sem escolher cobrança: o painel recusa antes de enviar`);
    await pg.check('#se-cob input[value="com"]');
    chk(await pg.locator('#se-cob-com').isVisible() && await pg.inputValue('#se-cob-valor') === '300' && await pg.isChecked('#se-cob-lib'),
      `[${w}] Com cobrança: valor sugerido 2 × R$ 150 = 300 e "Liberar o download só depois do pagamento" marcado`);
    await pg.fill('#se-cob-txt', 'livro à venda, tiragem 2.000');
    await pg.locator('#se-cob').scrollIntoViewIfNeeded(); await semToast(pg);
    await pg.screenshot({ path: `${PRINTS}/originais-envio-cobranca-${w}.png`, fullPage: false });
    await pg.check('#se-cob input[value="sem"]');
    chk(await pg.locator('#se-cob-sem').isVisible() && !(await pg.locator('#se-cob-com').isVisible()), `[${w}] Sem cobrança: mostra "Por que não cobrar"`);
    chk(await semRolagem(pg), `[${w}] envio sem rolagem lateral`);
    chk(erros.length === 0, `[${w}] nenhum erro de JS ${erros.join(' | ').slice(0, 200)}`);
    // página pública aguardando pagamento
    const pub = await br.newPage({ viewport: { width: w, height: 800 } });
    await pub.goto(`${BASE}/entrega/${TOKEN}`);
    chk((await pub.textContent('body')).includes('Aguardando pagamento') && await pub.locator('a:has-text("Pagar R$ 300,00 pelo Mercado Pago")').count() === 1
      && await pub.locator('text=Baixar tudo').count() === 0, `[${w}] página do link: Aguardando pagamento com o botão Pagar, sem downloads`);
    await pub.screenshot({ path: `${PRINTS}/entrega-aguardando-pagamento-${w}.png`, fullPage: true }); await pub.close();
    await ctx.close();
  }
  const { ctx, pg } = await login(br, 1440, 'leitor@camp.arq.br', 'senha-leitor-1234');
  await pg.goto(`${BASE}/#projeto/${P}`); await pg.waitForSelector('[data-pj-tab="itens"]', { timeout: 20000 });
  chk(await pg.locator('[data-pj-tab="originais"]').count() === 0, 'papel leitura não vê a aba Arquivos originais');
  await ctx.close(); await br.close();
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
