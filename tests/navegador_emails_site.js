// CAMP-SENDER 20/11/2026 · E-mails do site (Rafael: "uma página de configuração de TODOS os e-mails transacionais do site"): números do
// topo, modelos por área, variáveis com copiar, salvar ID (e deixar sem ID), enviar teste, guia .zip, link em Configurações e em E-mails
// enviados, só admin/master, sem rolar de lado. Usa um SITE FALSO (servidor http deste teste): nada sai de verdade.
// Uso: CHROME=/opt/pw-browsers/chromium bash tests/rodar_um.sh tests/navegador_emails_site.js
// (CAMP_BASE para outro endereço do painel; CAMP_SITE_PORTA para a porta do site falso, padrão 8796; CAMP_PRINT=<arquivo.png> = print em 1366 px, tema claro)
const http = require('http');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765';
const PORTA = +(process.env.CAMP_SITE_PORTA || 8796);
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
const login = (pg, email, senha) => pg.evaluate(([e, s]) => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: e, senha: s }) }).then(r => r.status), [email, senha]);
const lado = pg => pg.evaluate(() => { const m = document.querySelector('.main'); return Math.max(m.scrollWidth - m.clientWidth, document.scrollingElement.scrollWidth - innerWidth) });
// ---- site falso: GET/POST /painel/sender e /painel/sender/teste (contrato 1.23)
const M = (tr, chave, area, nome, vars, sem, critico = false) => ({ tr, chave, area, nome, quando: 'Quando acontece ' + nome.toLowerCase() + '.', para: 'Quem pediu', variaveis: vars, sem_id: sem, sem_id_texto: { simples: 'sai o e-mail simples do site', nao_sai: 'não sai nada (o painel avisa qual modelo falta)', login: 'o link de entrada não sai e a área do Amigo não abre' }[sem] || '', critico });
const CAT = [M('TR04', 'solicitacao_recebida', 'Pedidos e visitas', 'Pedido recebido', ['nome', 'protocolo'], 'simples'), M('TR07', 'visita_confirmada', 'Pedidos e visitas', 'Visita confirmada', ['nome', 'local', 'data', 'horario', 'grupo', 'protocolo'], 'simples'),
  M('TR08', 'inscricao_recebida', 'Cursos e inscrições', 'Inscrição recebida', ['nome', 'curso', 'protocolo'], 'simples'), M('TR15', 'amigo_cobranca', 'Amigos da CAMP', 'Cobrança', ['nome', 'categoria', 'valor', 'vence', 'pagamento', 'link', 'pix', 'protocolo'], 'nao_sai', true),
  M('TR22', 'amigo_acesso', 'Área do Amigo', 'Link de acesso à área do Amigo', ['nome', 'link', 'validade_link', 'protocolo'], 'login', true), M('TR23', 'ingresso_visita', 'Ingressos', 'Ingresso da visita (Residência João Marino)', ['nome', 'visita', 'data', 'quantidade', 'codigo', 'link', 'qr', 'endereco', 'protocolo'], 'simples'),
  M('TR27', 'cobranca_avulsa', 'Cobranças e doações', 'Cobrança avulsa', ['nome', 'valor', 'descricao', 'finalidade', 'vence', 'link', 'protocolo'], 'nao_sai', true), M('TR29', 'ingresso_cobranca', 'Ingressos', 'Ingresso da visita: link de pagamento', ['nome', 'visita', 'data', 'quantidade', 'valor', 'link', 'validade', 'protocolo'], 'nao_sai')];
const TPL = { solicitacao_recebida: 'egx4Z6', visita_confirmada: 'elv4x6', inscricao_recebida: 'bm24O0', amigo_cobranca: '', amigo_acesso: '', ingresso_visita: 'ing23A', cobranca_avulsa: '', ingresso_cobranca: '' };
const recebidos = [];
const estado = () => ({ ok: true, ativo: false, token_preenchido: true, token_origem: 'site', emergencia: false, teste: true, templates: TPL, token: 'SEGREDO-NAO-PODE-APARECER',
  catalogo: CAT.map(m => ({ ...m, id: TPL[m.chave], id_padrao: '', situacao: TPL[m.chave] ? 'ativo' : 'sem_id' })) });
const site = http.createServer((req, res) => { let b = ''; req.on('data', d => b += d); req.on('end', () => {
  const j = b ? JSON.parse(b) : {}; const env = (st, o) => { res.writeHead(st, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(o)) };
  if (req.url.startsWith('/wp-json/camp/v1/painel/sender/teste')) { recebidos.push(['teste', j]); return TPL[j.chave] ? env(200, { ok: true, enviado: true, tr: 'TR', email_id: 'tst-9' }) : env(409, { ok: false, motivo: 'sem_template', erro: 'O modelo está sem ID: cole o ID e tente de novo.' }) }
  if (req.url.startsWith('/wp-json/camp/v1/painel/sender')) { if (req.method === 'POST') { recebidos.push(['salvar', j]); for (const [k, v] of Object.entries(j.templates || {})) TPL[k] = v === '__limpar__' ? '' : v } return env(200, estado()) }
  env(404, { code: 'rest_no_route' }) }) });
(async () => {
  await new Promise(r => site.listen(PORTA, '127.0.0.1', r));
  const br = await chromium.launch({ executablePath: process.env.CHROME || undefined }); const erros = [];
  const ctx = await br.newContext({ viewport: { width: 1366, height: 900 }, colorScheme: 'light', acceptDownloads: true });
  const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/'); await login(pg, 'rafael@camp.arq.br', 'senha-bem-longa-123');
  for (const [k, v] of [['wp.url', `http://127.0.0.1:${PORTA}`], ['wp.app_password', 'senha-do-site-falso']])   // o painel fala só com o site falso
    await pg.evaluate(([k, v]) => fetch('/api/config/' + k, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ valor: v }) }).then(r => r.status), [k, v]);
  await pg.goto(BASE + '/#emails/modelos'); await pg.reload();   // CAMP-EMAIL 20/11: agora é a aba Modelos do Sender da tela E-mails
  await pg.waitForSelector('#es-lista tr[data-es-chave]', { timeout: 10000 }).catch(() => {});
  await pg.waitForTimeout(400);
  chk(await pg.$eval('#v-emails h1', e => e.childNodes[0].textContent.trim()) === 'E-mails' && await pg.$eval('#em-tab-modelos', b => b.getAttribute('aria-selected')) === 'true' && await pg.$eval('#em-p-modelos', p => !p.hidden), 'tela E-mails, aba Modelos do Sender aberta');
  chk(/Administração/.test(await pg.$eval('#gcrumb', e => e.textContent).catch(() => '')), 'trilha: Administração');
  const kpis = await pg.$$eval('#es-kpis .hoje-kpi', ks => ks.map(k => k.querySelector('.v').textContent + ' ' + k.querySelector('.l').textContent));
  chk(JSON.stringify(kpis.slice(0, 3)) === JSON.stringify(['4 ativos', '4 faltando', '3 críticos']) && /^\d+ falhas em 30 dias$/.test(kpis[3] || ''), 'números do topo: ativos, faltando, críticos, falhas em 30 dias', JSON.stringify(kpis));
  chk(/saiu pelo e-mail simples|enviado|nenhum em 30 dias/.test(await pg.$eval('tr[data-es-chave="solicitacao_recebida"] .es-env', e => e.textContent)), 'último envio do TR04 vem de E-mails → Enviados');
  chk(/TR15, TR22, TR27/.test(await pg.$eval('#es-kpis', e => e.textContent)), 'críticos listados: TR15, TR22, TR27');
  const areas = await pg.$$eval('#es-lista tr.es-area th', t => t.map(x => x.textContent));
  chk(JSON.stringify(areas) === JSON.stringify(['Pedidos e visitas', 'Cursos e inscrições', 'Amigos da CAMP', 'Área do Amigo', 'Ingressos', 'Cobranças e doações']), 'modelos agrupados por área, na ordem', JSON.stringify(areas));
  const aviso = await pg.$eval('#es-aviso', e => e.textContent);
  chk(/Chave do Sender: configurada — a do site/.test(aviso), 'topo: chave do Sender configurada e de onde vem', aviso);
  const html = await pg.content();
  chk(!/SEGREDO-NAO-PODE-APARECER/.test(html), 'o token nunca aparece na tela');
  const sit22 = await pg.$eval('tr[data-es-chave="amigo_acesso"] .es-sit', e => e.textContent);
  chk(/Sem ID — login não abre/.test(sit22) && /crítico/.test(sit22), 'TR22 sem ID: "Sem ID — login não abre" + crítico', sit22);
  chk(/Ativo/.test(await pg.$eval('tr[data-es-chave="solicitacao_recebida"] .es-sit', e => e.textContent)), 'TR04 com ID: Ativo');
  chk(/Sem ID — sai e-mail simples/.test(await pg.$eval('tr[data-es-chave="ingresso_cobranca"] .es-sit', e => e.textContent)) === false && /Sem ID — não sai/.test(await pg.$eval('tr[data-es-chave="ingresso_cobranca"] .es-sit', e => e.textContent)), 'TR29 (ingresso: link de pagamento) sem ID: não sai');
  chk(await pg.$eval('#es-para', e => e.value) === 'rafael@camp.arq.br', 'testes vão por padrão ao e-mail de quem está no painel');
  chk(await lado(pg) <= 0, '1366 px: a tela não rola de lado', String(await lado(pg)));
  if (process.env.CAMP_PRINT) await pg.screenshot({ path: process.env.CAMP_PRINT, fullPage: false });
  // copiar variáveis
  await ctx.grantPermissions(['clipboard-read', 'clipboard-write']).catch(() => {});
  await pg.click('tr[data-es-chave="amigo_acesso"] [data-es-copiar]'); await pg.waitForTimeout(300);
  chk(await pg.$eval('tr[data-es-chave="amigo_acesso"] [data-es-copiar]', b => b.dataset.esCopiar) === '{{nome}} {{link}} {{validade_link}} {{protocolo}}', 'Copiar leva a lista exata de variáveis do TR22');
  // salvar ID
  const inp = 'tr[data-es-chave="amigo_acesso"] input';
  await pg.fill(inp, 'a b'); await pg.click('tr[data-es-chave="amigo_acesso"] [data-es-salvar]'); await pg.waitForTimeout(300);
  chk(/Só letras e números/.test(await pg.$eval('tr[data-es-chave="amigo_acesso"] .cfg-err', e => e.textContent)) && !recebidos.some(r => r[0] === 'salvar'), 'ID inválido: erro ao lado e nada vai ao site');
  await pg.fill(inp, 'aCe22X'); await pg.click('tr[data-es-chave="amigo_acesso"] [data-es-salvar]'); await pg.waitForTimeout(800);
  const salvo = recebidos.filter(r => r[0] === 'salvar').pop();
  chk(salvo && JSON.stringify(salvo[1]) === '{"templates":{"amigo_acesso":"aCe22X"}}', 'Salvar manda ao site só o ID do TR22', JSON.stringify(salvo));
  chk(/Ativo/.test(await pg.$eval('tr[data-es-chave="amigo_acesso"] .es-sit', e => e.textContent)), 'depois de salvar, o TR22 fica Ativo');
  // deixar sem ID (pede confirmação)
  await pg.fill('tr[data-es-chave="ingresso_visita"] input', ''); await pg.click('tr[data-es-chave="ingresso_visita"] [data-es-salvar]'); await pg.waitForTimeout(400);
  const conf = await pg.$('#m-confirmar.open, .modal.open, [role="dialog"]:not([hidden])');
  const btn = await pg.$('button:has-text("Deixar sem ID")');
  chk(!!btn, 'deixar sem ID pede confirmação', String(!!conf));
  if (btn) { await btn.click(); await pg.waitForTimeout(800) }
  chk(JSON.stringify((recebidos.filter(r => r[0] === 'salvar').pop() || [])[1]) === '{"templates":{"ingresso_visita":"__limpar__"}}', 'sem ID vai como "__limpar__"');
  chk(/Sem ID — sai e-mail simples/.test(await pg.$eval('tr[data-es-chave="ingresso_visita"] .es-sit', e => e.textContent)), 'TR23 sem ID: sai e-mail simples');
  // enviar teste
  await pg.click('tr[data-es-chave="amigo_acesso"] [data-es-teste]'); await pg.waitForTimeout(900);
  const t1 = recebidos.filter(r => r[0] === 'teste').pop();
  chk(t1 && t1[1].chave === 'amigo_acesso' && t1[1].para === 'rafael@camp.arq.br', 'Enviar teste: TR22 para o e-mail do admin', JSON.stringify(t1));
  chk(/teste enviado para rafael@camp.arq.br/.test(await pg.$eval('#toast', e => e.textContent)), 'aviso: teste enviado');
  await pg.fill('#es-para', 'outra@exemplo.org'); await pg.click('tr[data-es-chave="cobranca_avulsa"] [data-es-teste]'); await pg.waitForTimeout(900);
  chk(/o teste não saiu — O modelo está sem ID/.test(await pg.$eval('#toast', e => e.textContent)) && recebidos.filter(r => r[0] === 'teste').pop()[1].para === 'outra@exemplo.org', 'teste sem ID: diz que não saiu e por quê (e-mail editável)');
  // busca
  await pg.fill('#es-q', 'validade_link'); await pg.waitForTimeout(300);
  chk(JSON.stringify(await pg.$$eval('#es-lista tr[data-es-chave]', r => r.map(x => x.dataset.esChave))) === '["amigo_acesso"]', 'busca por variável acha o TR22');
  await pg.fill('#es-q', ''); await pg.waitForTimeout(200);
  // guia
  const g = await pg.evaluate(() => fetch('/api/emails-site/guia.zip').then(async r => [r.status, r.headers.get('content-type'), (await r.arrayBuffer()).byteLength]));
  chk(g[0] === 200 && /zip/.test(g[1]) && g[2] > 1000, 'Baixar guia dos modelos: .zip', JSON.stringify(g));
  // links de entrada
  await pg.goto(BASE + '/#emails'); await pg.waitForTimeout(800);
  chk(await pg.$eval('#em-tab-modelos', a => !a.hidden && a.textContent.trim() === 'Modelos do Sender').catch(() => false), 'E-mails tem a aba "Modelos do Sender"');
  await pg.goto(BASE + '/#config'); await pg.waitForTimeout(1200);
  chk(await pg.$eval('.cfg-sender-modelos a[href="#emails/modelos"]', a => !!a).catch(() => false), 'Configurações → E-mail e avisos aponta para E-mails → Modelos do Sender');
  chk(!(await pg.$('input[data-cfg-chave="sender.tr04_solicitacao_recebida"]')), 'Configurações não mostra mais os IDs TR04–TR09 (uma fonte só)');
  // celular
  const cel = await (await br.newContext({ viewport: { width: 390, height: 800 } })).newPage();
  cel.on('pageerror', e => erros.push('pageerror (390): ' + e.message));
  await cel.goto(BASE + '/'); await login(cel, 'rafael@camp.arq.br', 'senha-bem-longa-123'); await cel.goto(BASE + '/#emails/modelos'); await cel.reload();
  await cel.waitForSelector('#es-lista tr[data-es-chave]', { timeout: 10000 }).catch(() => {}); await cel.waitForTimeout(400);
  chk(await lado(cel) <= 0, '390 px: a tela não rola de lado', String(await lado(cel)));
  // operador não vê
  const op = await (await br.newContext({ viewport: { width: 1366, height: 900 } })).newPage();
  await op.goto(BASE + '/'); await login(op, 'operador@camp.arq.br', 'senha-operador-123'); await op.reload(); await op.waitForTimeout(1200);
  const st = await op.evaluate(() => fetch('/api/emails-site').then(r => r.status));
  await op.goto(BASE + '/#emails/modelos'); await op.waitForTimeout(800);
  chk(st === 403 && !(await op.$eval('#v-emails', e => e.classList.contains('on'))), 'operador: 403 na API e o endereço #emails/modelos não abre a tela', String(st));
  await op.goto(BASE + '/#emailsite'); await op.waitForTimeout(800);
  chk(!(await op.$eval('#v-emails', e => e.classList.contains('on'))), 'operador: o endereço antigo #emailsite também não abre');
  await op.goto(BASE + '/#config'); await op.waitForTimeout(1200);
  chk(await op.$eval('.cfg-sender-modelos', e => e.hidden).catch(() => true), 'operador: o link para E-mails → Modelos do Sender some em Configurações');
  chk(!erros.length, 'sem erro de JavaScript', erros.join(' | '));
  await br.close(); site.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
