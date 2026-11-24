// CAMP-FIN (24/11/2026): pedir nota fiscal ao fornecedor, no navegador de verdade (Playwright + Chromium). Rafael: "preparar para criar
// cobrança de nota fiscal para algum fornecedor". Despesas SEMEADAS (tests/semente_financeiro.py); o painel do teste NÃO tem SMTP: nenhum e-mail sai.
//  [A] despesa sem comprovante: "Pedir nota fiscal" no painel lateral
//  [B] dados da CAMP vazios: a tela pede uma vez (nada inventado) e guarda
//  [C] formulário: contato do fornecedor, descrição, valor, data, referência do Mercado Pago, prévia do texto que muda ao digitar, link do WhatsApp;
//      sem SMTP, "Enviar por e-mail" apagado com a frase do porquê
//  [D] "Copiar texto" copia a prévia; "Já mandei: marcar como pedida" marca; chip "nota pedida em dd/mm" na lista; filtro "Notas pedidas"
//  [E] Pedir de novo: o contato do fornecedor volta preenchido (memória)
//  [F] despesa da conta do projeto: "Projeto PRONAC 2613864 · Livro Karazawa" e "conforme orientação do projeto"
//  [G] fila "Precisa justificar": "Pedir nota fiscal" abre por cima da fila; Esc fecha o formulário e a fila continua
//  [H] celular (390 px): sem rolagem lateral no formulário; operador recebe 403 na API
// Uso (servidor PRÓPRIO, portas 9080–9089):
//   CAMP_DB_PATH=/dev/shm/nf/n.db python3 tests/semear_banco_teste.py && python3 tests/semente_financeiro.py /dev/shm/nf/n.db
//   (cd backend && CAMP_DB_PATH=/dev/shm/nf/n.db CAMP_COOKIE_SECURE=false python3 -m uvicorn app.main:app --port 9081)
//   TMPDIR=/dev/shm CAMP_BASE=http://127.0.0.1:9081 SHOTS=/dev/shm/nf/shots node tests/navegador_nota_fiscal.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9081';
const SHOTS = process.env.SHOTS || '';
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
const foto = async (P, nome) => { if (!SHOTS) return; try { fs.mkdirSync(SHOTS, { recursive: true }); await P.screenshot({ path: `${SHOTS}/${nome}.png` }); } catch (e) { linhas.push('aviso  print ' + nome + ': ' + e.message); } };

async function entrar(browser, email, senha, erros, o = {}) {
  const ctx = await browser.newContext({ viewport: { width: o.w || 1366, height: o.h || 900 }, deviceScaleFactor: 1 });
  await ctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: BASE });
  const page = await ctx.newPage();
  page.on('console', m => { const url = ((m.location() || {}).url || ''); if (m.type() === 'error' && !/\/api\/auth\/eu$|\/favicon\.ico$/.test(url) && !/status of 40[039]|ERR_INSUFFICIENT_RESOURCES/.test(m.text())) erros.push(email + ': ' + m.text() + ' @' + url); });
  page.on('pageerror', e => erros.push(email + ': pageerror: ' + e.message));
  await page.goto(BASE + '/');
  await page.fill('#lg-email', email); await page.fill('#lg-senha', senha); await page.press('#lg-senha', 'Enter');
  await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  return { ctx, page };
}
const abrirFin = async P => { await P.evaluate(() => go('financeiro')); await P.waitForFunction(() => document.getElementById('v-financeiro')?.classList.contains('on') && FIN.d && FIN.desp && !FIN.carregando, null, { timeout: 15000 }); };
const lado = P => P.locator('#fin-lado');

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  try {
    const { ctx, page: P } = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros);
    await abrirFin(P);
    await P.click('[data-fin-aba="despesas"]');
    const ids = await P.evaluate(() => { const m = {}; for (const x of FIN.desp.itens) m[x.contraparte] = x.id; return m; });
    const dT = ids['Transportadora Litoral'], dP = ids['Papelaria Arte Final'], dA = ids['Ana Restauradora'];
    chk(dT && dP && dA, '[A] as despesas semeadas estão na lista: ' + JSON.stringify(ids));
    // ---------- [A] ----------
    await P.click(`[data-fin-desp="${dT}"]`);
    await P.waitForSelector('#fin-lado:not([hidden]) [data-fin-nf="abrir"]', { timeout: 10000 });
    chk((await lado(P).locator('[data-fin-nf="abrir"]').textContent()).trim() === 'Pedir nota fiscal', '[A] despesa sem comprovante: botão "Pedir nota fiscal" no painel lateral');
    await foto(P, '1-despesa-sem-comprovante');
    // ---------- [B] ----------
    await lado(P).locator('[data-fin-nf="abrir"]').click();
    await P.waitForFunction(() => /Dados da CAMP para a nota fiscal/.test(document.getElementById('fin-lado-tit')?.textContent || ''), null, { timeout: 10000 });
    const tb = await lado(P).innerText();
    chk(/Falta: razão social, CNPJ, endereço, e-mail que recebe as notas/.test(tb) && /O painel não inventa nenhum destes dados/.test(tb)
      && (await P.inputValue('#fin-nf-rs')) === '' && (await P.inputValue('#fin-nf-cnpj')) === '', '[B] dados da CAMP vazios: a tela pede uma vez e não inventa');
    await foto(P, '2-dados-da-camp');
    await P.fill('#fin-nf-rs', 'Associação Teste'); await P.fill('#fin-nf-cnpj', '11.111.111/1111-11'); await P.fill('#fin-nf-end', 'Rua Teste, 1 · São Paulo'); await P.fill('#fin-nf-em', 'financeiro@camp.arq.br');
    await P.click('[data-fin-nf="salvar-dados"]');
    await P.waitForTimeout(500);
    chk(/Dados da CAMP/.test(await P.locator('#fin-lado-tit').textContent()) && /CNPJ inválido/.test(await P.locator('body').innerText()), '[B] CNPJ inválido: não guarda e diz o porquê');
    await P.fill('#fin-nf-cnpj', '11.222.333/0001-81'); await P.click('[data-fin-nf="salvar-dados"]');
    await P.waitForFunction(() => /^Pedir nota fiscal$/.test(document.getElementById('fin-lado-tit')?.textContent || ''), null, { timeout: 10000 });
    chk(true, '[B] dados guardados: abre o formulário do pedido');
    // ---------- [C] ----------
    chk((await P.inputValue('#fin-nf-valor')) === '320,00' && (await P.inputValue('#fin-nf-data')) === '2026-11-06' && (await P.inputValue('#fin-nf-ref')) === 'S0', '[C] valor, data do pagamento e referência do Mercado Pago preenchidos');
    const env = lado(P).locator('[data-fin-nf="enviar"]');
    chk(await env.isDisabled() && /O e-mail do painel \(SMTP\) não está configurado/.test(await lado(P).innerText()), '[C] sem SMTP: "Enviar por e-mail" apagado, com a frase do porquê');
    await P.fill('#fin-nf-desc', 'Frete das caixas do acervo doado');
    await P.fill('#fin-nf-email', 'contato@litoral.com.br'); await P.fill('#fin-nf-wa', '(11) 98765-4321');
    await P.waitForFunction(() => /Frete das caixas do acervo doado/.test(document.getElementById('fin-nf-previa').textContent) && !document.getElementById('fin-nf-walink').hidden, null, { timeout: 10000 });
    const pv = await P.locator('#fin-nf-previa').textContent();
    chk(/^Assunto: Pedido de nota fiscal · CAMP · pagamento de 06\/11\/2026 \(R\$ 320,00\)/.test(pv) && pv.includes('Olá, Transportadora Litoral,') && pv.includes('- CNPJ: 11.222.333/0001-81')
      && pv.includes('- Referência do Mercado Pago: S0') && pv.includes('envie a nota fiscal para financeiro@camp.arq.br') && !pv.includes('PRONAC'), '[C] prévia do texto: assunto, fornecedor, dados da CAMP, referência; muda ao digitar a descrição');
    const wa = await P.getAttribute('#fin-nf-walink', 'href');
    chk(wa.startsWith('https://wa.me/5511987654321?text=Pedido%20de%20nota%20fiscal'), '[C] link do WhatsApp com o número e o texto: ' + wa.slice(0, 60));
    await foto(P, '3-previa');
    // ---------- [D] ----------
    chk(await lado(P).locator('#fin-nf-marcar').isHidden(), '[D] "Já mandei: marcar como pedida" só aparece depois de copiar');
    await P.click('[data-fin-nf="copiar"]');
    await P.waitForTimeout(400);
    const clip = await P.evaluate(() => navigator.clipboard.readText());
    chk(clip.startsWith('Assunto: Pedido de nota fiscal') && clip.includes('Frete das caixas do acervo doado'), '[D] Copiar texto: a prévia vai para a área de transferência');
    chk(await lado(P).locator('#fin-nf-marcar').isVisible(), '[D] depois de copiar aparece "Já mandei: marcar como pedida"');
    await foto(P, '4-copiado');
    await P.click('#fin-nf-marcar');
    await P.waitForFunction(() => document.getElementById('fin-lado').hidden && !FIN.carregando && FIN.desp.notas_pedidas && FIN.desp.notas_pedidas.length === 1, null, { timeout: 10000 });
    const linha = P.locator(`[data-fin-desp="${dT}"]`);
    const hoje = await P.evaluate(() => new Date().toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }));
    chk((await linha.innerText()).includes('nota pedida em ' + hoje), '[D] chip "nota pedida em ' + hoje + '" na linha da despesa');
    const fch = P.locator('[data-fin-cat="nota"]');
    chk(/Notas pedidas\s*1/.test(await fch.innerText()), '[D] filtro "Notas pedidas" com 1');
    await fch.click();
    chk((await P.locator('#fin-p-despesas .fin-linha').count()) === 1, '[D] o filtro mostra só a despesa com nota pedida');
    await foto(P, '5-chip-e-filtro');
    // ---------- [E] ----------
    await linha.click();
    await P.waitForSelector('#fin-lado:not([hidden]) [data-fin-nf="abrir"]', { timeout: 10000 });
    chk((await lado(P).locator('[data-fin-nf="abrir"]').textContent()).trim() === 'Pedir de novo' && (await lado(P).innerText()).includes('nota pedida em ' + hoje), '[E] já pedida: chip e "Pedir de novo" no painel lateral');
    await lado(P).locator('[data-fin-nf="abrir"]').click();
    await P.waitForFunction(() => /Pedir de novo a nota fiscal/.test(document.getElementById('fin-lado-tit')?.textContent || ''), null, { timeout: 10000 });
    chk((await P.inputValue('#fin-nf-email')) === 'contato@litoral.com.br' && (await P.inputValue('#fin-nf-wa')) === '11987654321' && /Contato guardado/.test(await lado(P).innerText()), '[E] Pedir de novo: e-mail e WhatsApp do fornecedor voltam preenchidos');
    chk((await P.inputValue('#fin-nf-desc')) === 'Frete das caixas do acervo doado', '[E] Pedir de novo: a descrição do pedido anterior volta (a despesa não tem justificativa)');
    await P.keyboard.press('Escape');
    await P.click('[data-fin-cat=""]');
    // ---------- [F] ----------
    await P.evaluate(async id => { await API('/api/financeiro/despesas/' + id, { method: 'PUT', body: JSON.stringify({ conta_id: 2, justificativa: 'Restauro das pranchas do livro' }) }); }, dA);
    await abrirFin(P);
    await P.click(`[data-fin-desp="${dA}"]`);
    await P.waitForSelector('#fin-lado:not([hidden]) [data-fin-nf="abrir"]', { timeout: 10000 });
    await lado(P).locator('[data-fin-nf="abrir"]').click();
    await P.waitForFunction(() => /^Pedir nota fiscal$/.test(document.getElementById('fin-lado-tit')?.textContent || ''), null, { timeout: 10000 });
    const tf = await lado(P).innerText(), pvf = await P.locator('#fin-nf-previa').textContent();
    chk((await P.inputValue('#fin-nf-desc')) === 'Restauro das pranchas do livro · Projeto PRONAC 2613864 · Livro Karazawa' && /Despesa de projeto: a descrição leva “Projeto PRONAC 2613864 · Livro Karazawa”, conforme orientação do projeto/.test(tf)
      && pvf.includes('Conforme orientação do projeto'), '[F] conta do projeto: a descrição leva o PRONAC e o texto diz "conforme orientação do projeto"');
    await foto(P, '6-pronac');
    await P.keyboard.press('Escape');
    // ---------- [G] ----------
    await P.evaluate(() => finFilaAbrir());
    await P.waitForSelector('#fin-fila:not([hidden]) [data-fin-nf="abrir"]', { timeout: 10000 });
    const bf = P.locator('#fin-fila [data-fin-nf="abrir"]');
    chk(/^(Pedir nota fiscal|Pedir de novo)$/.test((await bf.textContent()).trim()), '[G] fila "Precisa justificar": botão de pedir a nota na despesa sem comprovante');
    await bf.click();
    await P.waitForSelector('#fin-lado.sobre-fila:not([hidden])', { timeout: 10000 });
    const cima = await P.evaluate(() => { const r = document.getElementById('fin-lado').getBoundingClientRect(); const el = document.elementFromPoint(r.left + r.width / 2, r.top + 40); return !!el && !!el.closest('#fin-lado'); });
    chk(cima, '[G] o formulário abre POR CIMA da fila');
    await foto(P, '7-fila');
    await P.keyboard.press('Escape');
    await P.waitForTimeout(300);
    chk(await P.locator('#fin-lado').isHidden() && await P.locator('#fin-fila').isVisible(), '[G] Esc fecha o formulário e a fila continua aberta');
    await P.keyboard.press('Escape');
    await ctx.close();
    // ---------- [H] ----------
    const { ctx: c2, page: M } = await entrar(browser, 'rafael@camp.arq.br', 'senha-bem-longa-123', erros, { w: 390, h: 844 });
    await abrirFin(M); await M.click('[data-fin-aba="despesas"]');
    await M.click(`[data-fin-desp="${dP}"]`); await M.waitForSelector('#fin-lado:not([hidden]) [data-fin-nf="abrir"]', { timeout: 10000 });
    await M.locator('#fin-lado [data-fin-nf="abrir"]').click();
    await M.waitForSelector('#fin-nf-previa', { timeout: 10000 });
    const lat = await M.evaluate(() => { const l = document.getElementById('fin-lado'); return [document.documentElement.scrollWidth <= window.innerWidth + 1, l.scrollWidth <= l.clientWidth + 1]; });
    chk(lat[0] && lat[1], '[H] celular (390 px): sem rolagem lateral no formulário ' + JSON.stringify(lat));
    await foto(M, '8-celular');
    await c2.close();
    const { ctx: c3, page: O } = await entrar(browser, 'operador@camp.arq.br', 'senha-operador-123', erros);
    const st = await O.evaluate(async id => (await fetch('/api/financeiro/notas/' + id)).status + ',' + (await fetch('/api/financeiro/notas/' + id + '/pedir', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"canal":"copiado"}' })).status, dT);
    chk(st === '403,403', '[H] operador: a API responde 403 (' + st + ')');
    await c3.close();
  } catch (e) {
    chk(false, 'erro no teste: ' + e.message);
  } finally {
    await browser.close();
  }
  chk(!erros.length, 'sem erro no console: ' + erros.slice(0, 3).join(' | '));
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : `\nTUDO OK (${linhas.length} verificações)`);
  process.exit(problemas.length ? 1 : 0);
})();
