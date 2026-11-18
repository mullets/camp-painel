// 18/11/2026 · Amigos da CAMP no painel (Rafael: "controlar quem já pagou ou não, alterar status etc. Disparar e-mail etc."): lista com os
// números do topo, filtros, selecionar todos, prévia do e-mail (sem envio configurado o botão Enviar fica apagado: nenhum e-mail sai),
// registrar pagamento à mão, aba Adoções, só admin/master, sem rolar de lado.  Uso: bash tests/rodar_um.sh tests/navegador_amigos.js
// (CAMP_PRINT=<arquivo.png> guarda o print da lista em 1366 px, tema claro)
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
const login = (pg, email, senha) => pg.evaluate(([e, s]) => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: e, senha: s }) }).then(r => r.status), [email, senha]);
(async () => {
  const br = await chromium.launch({ executablePath: process.env.CHROME || undefined }); const erros = [];
  const ctx = await br.newContext({ viewport: { width: 1366, height: 900 }, colorScheme: 'light' });
  const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/'); await login(pg, 'rafael@camp.arq.br', 'senha-bem-longa-123');
  await pg.goto(BASE + '/#amigos'); await pg.reload();
  await pg.waitForSelector('[data-am-abrir]', { timeout: 10000 }).catch(() => {});
  await pg.waitForTimeout(600);
  chk(await pg.$eval('#v-amigos h1', e => e.childNodes[0].textContent.trim()) === 'Amigos da CAMP', 'título da página: Amigos da CAMP');
  chk(await pg.$eval('#nav button[data-v="amigos"]', b => !b.hidden && getComputedStyle(b).display !== 'none'), 'item "Amigos da CAMP" no menu para o master');
  const kpis = await pg.$$eval('#am-kpis .hoje-kpi .l', ls => ls.map(l => l.textContent));
  chk(kpis.length === 4 && kpis[0] === 'Amigos ativos' && /^receita de \d{4}/.test(kpis[1]) && kpis[2] === 'pendente' && kpis[3] === 'vencendo', 'números do topo: ativos, receita do ano, pendente, vencendo', JSON.stringify(kpis));
  const ativos = await pg.$eval('#am-kpis .hoje-kpi .v', v => v.textContent);
  chk(ativos === '2', '2 Amigos ativos (os pagos dentro da validade)', ativos);
  const nomes = await pg.$$eval('#am-lista [data-am-abrir]', rs => rs.length);
  chk(nomes === 4, 'lista com os 4 Amigos', String(nomes));
  const venc = await pg.$eval('#am-lista', t => t.textContent);
  chk(/vence em 1[12] dias/.test(venc), 'quem vence em até 30 dias tem a etiqueta "vence em N dias"', venc.slice(0, 200));
  const lado = await pg.evaluate(() => { const m = document.querySelector('.main'); return Math.max(m.scrollWidth - m.clientWidth, document.scrollingElement.scrollWidth - innerWidth) });
  chk(lado <= 0, '1366 px: a tela não rola de lado', String(lado));
  if (process.env.CAMP_PRINT) await pg.screenshot({ path: process.env.CAMP_PRINT, fullPage: false });
  // filtro por situação
  await pg.click('#am-abas [data-am-sit="vencido"]'); await pg.waitForTimeout(500);
  chk((await pg.$$eval('#am-lista [data-am-abrir]', rs => rs.map(r => r.textContent))).join('|').includes('Davi Teste Melo') && (await pg.$$('#am-lista [data-am-abrir]')).length === 1, 'filtro Vencido: só o Davi');
  await pg.click('#am-abas [data-am-sit="todos"]'); await pg.waitForTimeout(500);
  // selecionar todos → mandar e-mail → prévia (sem envio configurado: Enviar apagado)
  await pg.check('#am-todos'); await pg.waitForTimeout(200);
  chk(await pg.$eval('#am-seln', e => e.textContent) === '4 selecionados' && await pg.$eval('#am-selbar', e => !e.hidden), 'selecionar todos: "4 selecionados" e a barra de ações');
  await pg.click('[data-am-acao="email-sel"]'); await pg.waitForSelector('#am-e-mod');
  await pg.selectOption('#am-e-mod', 'lembrete_renovacao');
  await pg.click('[data-am-acao="previa"]'); await pg.waitForSelector('#am-e-prev .am-bloco', { timeout: 5000 }).catch(() => {});
  const prev = await pg.$eval('#am-e-prev', e => e.textContent);
  chk(/envio não configurado/.test(prev) && /4 pessoas recebem/.test(prev) && /vence em/i.test(prev), 'prévia: diz quem recebe e mostra o e-mail; sem envio configurado avisa', prev.slice(0, 240));
  chk(await pg.$eval('[data-am-acao="enviar"]', b => b.disabled), 'sem envio configurado, "Enviar" fica apagado (nenhum e-mail sai)');
  await pg.evaluate(() => closeDrawer(true)); await pg.waitForTimeout(300);
  await pg.click('[data-am-acao="limpar-sel"]'); await pg.waitForTimeout(400);
  // registrar pagamento à mão no Bruno
  const bruno = await pg.$$eval('#am-lista [data-am-abrir]', rs => (rs.find(r => r.textContent.includes('Bruno')) || {}).dataset.amAbrir);
  await pg.click(`#am-lista [data-am-abrir="${bruno}"] td:nth-child(2)`); await pg.waitForSelector('[data-am-pagar]');
  chk(/Registrar pagamento/.test(await pg.$eval('#d-body', e => e.textContent)) && /Histórico/.test(await pg.$eval('#d-body', e => e.textContent)), 'detalhe: registrar pagamento e histórico');
  chk(!!(await pg.$('#am-f-cat')) && !!(await pg.$('[data-am-cobrar]')) && !!(await pg.$('[data-am-email]')), 'detalhe: mudar categoria/modalidade, "Enviar e-mail" e "Enviar cobrança"');
  await pg.click('[data-am-cobrar]'); await pg.waitForSelector('#am-cb [data-am-acao="cobrar"], #am-cb .tag', { timeout: 5000 }).catch(() => {});
  const cbt = await pg.$eval('#am-cb', e => e.textContent);
  chk(/Mercado Pago/.test(cbt) && /envio não configurado/.test(cbt) && await pg.$eval('[data-am-acao="cobrar"]', b => b.disabled), 'cobrança: prévia explica Mercado Pago/Pix; sem envio configurado o botão fica apagado', cbt.slice(0, 200));
  await pg.click(`#am-lista [data-am-abrir="${bruno}"] td:nth-child(2)`); await pg.waitForSelector('[data-am-pagar]');
  await pg.fill('#am-p-valor', '1500'); await pg.selectOption('#am-p-meio', 'pix');
  await pg.click('[data-am-pagar]'); await pg.waitForSelector('[data-conf="sim"]'); await pg.click('[data-conf="sim"]');
  await pg.waitForTimeout(1200);
  const det = await pg.evaluate(id => fetch('/api/amigos/' + id).then(r => r.json()), bruno);
  const hoje = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
  chk(det.situacao === 'pago' && det.pagamentos.some(p => p.origem === 'manual' && p.valor === 1500) && det.validade > hoje, 'pagamento registrado: pago, com a validade estendida', JSON.stringify({ s: det.situacao, v: det.validade }));
  chk(det.historico.some(h => h.tipo === 'pagamento_manual'), 'o pagamento entra no histórico');
  // aba Adoções
  await pg.click('#am-tabs [data-am-aba="adocoes"]'); await pg.waitForTimeout(500);
  chk((await pg.$eval('#am-lista', t => t.textContent)).includes('Construtora Exemplo'), 'aba Adoções: o pedido de Adote um arquiteto');
  // celular
  const cel = await (await br.newContext({ viewport: { width: 390, height: 800 } })).newPage();
  cel.on('pageerror', e => erros.push('pageerror (390): ' + e.message));
  await cel.goto(BASE + '/'); await login(cel, 'rafael@camp.arq.br', 'senha-bem-longa-123'); await cel.goto(BASE + '/#amigos'); await cel.reload();
  await cel.waitForSelector('[data-am-abrir]', { timeout: 10000 }).catch(() => {}); await cel.waitForTimeout(500);
  const lado2 = await cel.evaluate(() => { const m = document.querySelector('.main'); return Math.max(m.scrollWidth - m.clientWidth, document.scrollingElement.scrollWidth - innerWidth) });
  chk(lado2 <= 0, '390 px: a tela não rola de lado', String(lado2));
  // operador não vê
  const op = await (await br.newContext({ viewport: { width: 1366, height: 900 } })).newPage();
  await op.goto(BASE + '/'); await login(op, 'operador@camp.arq.br', 'senha-operador-123'); await op.reload(); await op.waitForTimeout(1200);
  const vis = await op.$eval('#nav button[data-v="amigos"]', b => !b.hidden && getComputedStyle(b).display !== 'none').catch(() => false);
  const st = await op.evaluate(() => fetch('/api/amigos').then(r => r.status));
  chk(!vis && st === 403, 'operador: sem o item no menu e 403 na API (dados pessoais)', JSON.stringify({ vis, st }));
  await op.keyboard.press('h'); await op.waitForTimeout(500);
  chk(!(await op.$eval('#v-amigos', e => e.classList.contains('on'))), 'operador: a tecla H não abre os Amigos');
  await op.goto(BASE + '/#amigos'); await op.waitForTimeout(1200);
  chk(!(await op.$eval('#v-amigos', e => e.classList.contains('on'))) && /Sem acesso/.test(await op.$eval('main', e => e.textContent)), 'operador: o endereço #amigos mostra "Sem acesso"');
  chk(erros.length === 0, 'sem erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
