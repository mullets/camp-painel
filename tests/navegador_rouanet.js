// CAMP-ROUANET (24/11/2026): aba Projeto incentivado no navegador de verdade (Playwright + Chromium). Rafael: "A CAMP emitirá nota para cobrar o
// projeto de Rouanet do livro". Banco de TESTE semeado (tests/semear_banco_teste.py + tests/semente_rouanet.py); nada vai ao site nem à prefeitura.
//  [A] a aba Projeto incentivado aparece; tabela do orçamento agrupada como no SALIC, com barras, total R$ 163.475,31, aviso de valores solicitados
//  [B] avisos: item 16 com 90% (âmbar) e item 14 acima do orçado (vermelho), também nas linhas
//  [C] ligar uma despesa do extrato a um item: no painel lateral, o campo "Item do orçamento" (buscável) com a sugestão; sem item não salva;
//      com o item, o gasto do item 12 sobe no orçamento
//  [D] Preparar nota do mês: linhas do plano (7 e 27), total, texto para a NFS-e com PRONAC; Criar nota planejada; Marcar como emitida
//      (número, data, PDF); Marcar como paga casando com o débito do extrato; a nota fica "paga" e o gasto do item 7 sobe
//  [E] o cuidado da Lei Rouanet na tela; celular (390 px) sem rolagem lateral da página
// Uso (servidor PRÓPRIO, portas 9090–9099):
//   CAMP_DB_PATH=/dev/shm/rou/n.db python3 tests/semear_banco_teste.py && python3 tests/semente_rouanet.py /dev/shm/rou/n.db
//   (cd backend && CAMP_DB_PATH=/dev/shm/rou/n.db CAMP_COOKIE_SECURE=false python3 -m uvicorn app.main:app --port 9091)
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9091 SHOTS=/dev/shm/rou node tests/navegador_rouanet.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9091';
const SHOTS = process.env.SHOTS || '';
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
const foto = async (P, nome, sel) => { if (!SHOTS) return; const o = { path: `${SHOTS}/${nome}.jpg`, type: 'jpeg', quality: 60 }; if (sel) await P.locator(sel).first().screenshot(o); else await P.screenshot(o); };

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const PDF = Buffer.from('%PDF-1.4\n%teste\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n');
  try {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1, acceptDownloads: true });
    const P = await ctx.newPage();
    P.on('pageerror', e => erros.push('pageerror: ' + e.message));
    P.on('console', m => { if (m.type() === 'error' && !/status of 40[39]|favicon|\/api\/auth\/eu/.test(m.text() + ((m.location() || {}).url || ''))) erros.push(m.text()); });
    P.on('dialog', d => d.accept());
    await P.goto(BASE + '/');
    await P.fill('#lg-email', 'rafael@camp.arq.br'); await P.fill('#lg-senha', 'senha-bem-longa-123'); await P.press('#lg-senha', 'Enter');
    await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await P.goto(BASE + '/#financeiro');
    await P.waitForFunction(() => document.getElementById('v-financeiro')?.classList.contains('on') && FIN.d && FIN.desp && FIN.projLista, null, { timeout: 20000 });
    // ---------- [A] ----------
    chk(await P.locator('#fin-aba-projeto').isVisible(), '[A] aba "Projeto incentivado" visível');
    await P.click('#fin-aba-projeto');
    await P.waitForFunction(() => FIN.proj && document.querySelector('#fin-p-projeto .fin-orc'), null, { timeout: 15000 });
    const tx = await P.locator('#fin-p-projeto').innerText();
    chk(tx.includes('PRONAC 2613864') && tx.includes('Edição do livro Arquitetura Moderna Paulista: Acervo Karazawa'), '[A] PRONAC e título');
    chk(tx.includes('Valores solicitados: atualize com a planilha aprovada'), '[A] aviso de valores solicitados');
    chk(await P.locator('.fin-orc tr.g0').count() === 4 && (await P.locator('.fin-orc tr.it').count()) === 28, '[A] 4 produtos e 28 itens agrupados');
    chk((await P.locator('.fin-orc tfoot').innerText()).includes('R$ 163.475,31'), '[A] total do projeto R$ 163.475,31');
    chk(await P.locator('.fin-orc .fin-pbar').count() >= 28, '[A] barras de uso');
    // ---------- [B] ----------
    chk(await P.locator('.fin-orc tr.it.ambar').count() === 1 && (await P.locator('.fin-orc tr.it.ambar').innerText()).includes('Impressão'), '[B] item 16 âmbar (90%)');
    chk(await P.locator('.fin-orc tr.it.vermelho').count() === 1 && (await P.locator('.fin-orc tr.it.vermelho').innerText()).includes('acima do orçado'), '[B] item 14 vermelho');
    const al = await P.locator('.fin-proj-al').innerText();
    chk(al.includes('Perto do limite: item 16') && al.includes('Acima do orçamento: item 14'), '[B] avisos no topo');
    await P.evaluate(() => document.querySelector('#fin-p-projeto .fin-proj-kpis').scrollIntoView({ block: 'center' })); await P.waitForTimeout(2500); await P.waitForTimeout(200); await foto(P, 'rouanet-orcamento'); await P.evaluate(() => document.querySelector('.fin-orc tr.it.ambar').scrollIntoView({ block: 'center' })); await P.waitForTimeout(200); await foto(P, 'rouanet-orcamento-itens');
    // ---------- [C] ----------
    await P.click('[data-fin-aba="despesas"]');
    const idSedex = await P.evaluate(() => (FIN.desp.itens || []).concat(FIN.desp.precisa_justificar || []).find(x => /Sedex/.test(x.contraparte)).id);
    await P.evaluate(id => finLadoDesp(id), idSedex);
    await P.waitForSelector('#fin-d-item', { timeout: 10000 });
    const lado = await P.locator('#fin-lado').innerText();
    chk(lado.includes('Projeto incentivado: nota fiscal obrigatória'), '[C] aviso de nota fiscal obrigatória');
    chk(lado.includes('12 · Correios') && lado.includes('sedex'), '[C] sugestão do item com o porquê');
    await P.selectOption('#fin-d-cat', 'frete');
    await P.click('[data-fin-acao="salvar-desp"]');
    await P.waitForTimeout(400);
    chk(await P.locator('#fin-lado').isVisible(), '[C] sem item não salva (o painel continua aberto)');
    await P.fill('#fin-d-item', '12 · Correios');
    await P.fill('#fin-d-nf', '998877');
    await foto(P, 'rouanet-despesa-item', '#fin-lado');
    await P.click('[data-fin-acao="salvar-desp"]');
    await P.waitForFunction(() => document.getElementById('fin-lado').hidden, null, { timeout: 10000 });
    await P.click('#fin-aba-projeto');
    await P.waitForFunction(() => FIN.proj && FIN.proj.itens.find(i => i.item === 12).gasto === 1200, null, { timeout: 10000 }).then(() => chk(true, '[C] item 12 com gasto de R$ 1.200 depois de ligar a despesa'), () => chk(false, '[C] gasto do item 12 não subiu'));
    // ---------- [D] ----------
    await P.click('[data-fin-pj="preparar"]');
    await P.waitForSelector('#fin-prep-txt', { timeout: 10000 });
    const pr = await P.locator('#fin-prep').innerText();
    chk(pr.includes('7 · Coordenação Editorial') && pr.includes('R$ 2.600,00') && pr.includes('R$ 3.665,68'), '[D] rascunho com itens 7 e 27 e total');
    const txt = await P.locator('#fin-prep-txt').inputValue();
    chk(txt.includes('Projeto PRONAC 2613864') && txt.includes('Valor total dos serviços: R$ 3.665,68') && txt.includes('Prestador: Centro de Arquitetura (teste)'), '[D] texto para a NFS-e');
    chk((await P.locator('#fin-notas-camp').innerText()).includes('Pagamentos do projeto à própria proponente seguem as regras da Lei Rouanet e do MinC'), '[E] cuidado da Lei Rouanet na tela');
    await foto(P, 'rouanet-preparar-nota', '#fin-notas-camp');
    await P.click('[data-fin-pj="criar-nota"]');
    await P.waitForSelector('.fin-nota [data-fin-pj="emitir"]', { timeout: 10000 });
    chk((await P.locator('.fin-nota').first().innerText()).includes('planejada'), '[D] nota planejada');
    await P.click('.fin-nota [data-fin-pj="emitir"]');
    const nid = await P.locator('.fin-nota').first().getAttribute('data-fin-nota-id');
    await P.fill(`#fin-ne-num-${nid}`, '57');
    await P.setInputFiles(`#fin-ne-pdf-${nid}`, { name: 'nfse-57.pdf', mimeType: 'application/pdf', buffer: PDF });
    await P.click('[data-fin-pj="emitir-ok"]');
    await P.waitForSelector('.fin-nota [data-fin-pj="pagar"]', { timeout: 10000 });
    chk((await P.locator('.fin-nota').first().innerText()).includes('nota nº 57'), '[D] nota emitida com número');
    await P.click('.fin-nota [data-fin-pj="pagar"]');
    await P.waitForSelector('[data-fin-pj="pagar-ok"]', { timeout: 10000 });
    chk((await P.locator('.fin-casar').innerText()).includes('R$ 3.665,68'), '[D] débito do extrato com o mesmo valor sugerido');
    await P.click('[data-fin-pj="pagar-ok"]');
    await P.waitForFunction(() => FIN.proj && FIN.proj.notas[0].situacao === 'paga', null, { timeout: 10000 });
    const nt = await P.locator('.fin-nota').first().innerText();
    chk(nt.includes('paga') && FIN_OK(nt), '[D] nota paga');
    chk(await P.evaluate(() => FIN.proj.itens.find(i => i.item === 7).gasto === 2600 && FIN.proj.itens.find(i => i.item === 27).gasto === 1065.68), '[D] gasto dos itens 7 e 27 pela nota paga');
    await foto(P, 'rouanet-nota-paga', '#fin-notas-camp');
    // ---------- [E] celular ----------
    await P.setViewportSize({ width: 390, height: 844 });
    await P.waitForTimeout(300);
    chk(await P.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), '[E] celular sem rolagem lateral da página');
    await ctx.close();
  } catch (e) { chk(false, 'erro: ' + e.message); }
  await browser.close();
  chk(!erros.length, 'sem erros no console: ' + erros.slice(0, 3).join(' | '));
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} problema(s)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
function FIN_OK(t) { return t.includes('paga em'); }
