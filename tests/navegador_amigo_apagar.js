// CAMP-AMIGO-APAGAR (21/11/2026, Rafael: "opção de desativar um amigo, apagar também por favor"): as duas confirmações da tela Amigos da CAMP.
// Desativar: prévia ("Fica inativo…"), motivo opcional, some da lista e aparece em Inativos; com o site sem resposta, a confirmação diz que não
// conferiu e o erro aparece na própria janela (nada muda). Apagar: prévia do que sai e do que fica, botão apagado até digitar o nome ou APAGAR,
// some do painel. Amigo de teste registrado só no painel: nenhuma chamada ao site.  Uso: CAMP_BASE=http://127.0.0.1:8880 node tests/navegador_amigo_apagar.js
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
const login = (pg, email, senha) => pg.evaluate(([e, s]) => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: e, senha: s }) }).then(r => r.status), [email, senha]);
(async () => {
  const br = await chromium.launch({ executablePath: process.env.CHROME || undefined }); const erros = [];
  const pg = await (await br.newContext({ viewport: { width: 1366, height: 900 }, colorScheme: 'light' })).newPage();
  pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
  await pg.goto(BASE + '/'); await login(pg, 'rafael@camp.arq.br', 'senha-bem-longa-123');
  const novo = await pg.evaluate(() => fetch('/api/amigos', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nome: 'Zeca Teste Apagar', email: 'zeca@exemplo.com', categoria: 'amigo' }) }).then(r => r.json()));
  const Z = novo.id;
  await pg.goto(BASE + '/#amigos'); await pg.reload();
  await pg.waitForSelector(`#am-lista [data-am-abrir="${Z}"]`, { timeout: 10000 }).catch(() => {});
  // ---------- Desativar ----------
  await pg.click(`#am-lista [data-am-abrir="${Z}"] td:nth-child(2)`); await pg.waitForSelector('[data-am-desativar]');
  chk(!!(await pg.$('[data-am-apagar]')) && /Desativar ou apagar/.test(await pg.$eval('#d-body', e => e.textContent)), 'detalhe: bloco "Desativar ou apagar" com Desativar e Apagar');
  await pg.click('[data-am-desativar]'); await pg.waitForSelector('#conf-ov');
  const t1 = await pg.$eval('#conf-ov', e => e.textContent);
  chk(/Desativar\?/.test(t1) && /Zeca Teste Apagar/.test(t1) && /Fica inativo/.test(t1) && /Sem assinatura mensal ativa/.test(t1) && !!(await pg.$('#conf-motivo')), 'confirmação de desativar: quem, o que acontece, sem assinatura e o motivo opcional', t1.slice(0, 300));
  await pg.fill('#conf-motivo', 'pediu para sair'); await pg.click('#conf-ov [data-conf="sim"]');
  await pg.waitForSelector('#conf-ov', { state: 'detached', timeout: 5000 }).catch(() => {}); await pg.waitForTimeout(700);
  chk(!(await pg.$(`#am-lista [data-am-abrir="${Z}"]`)), 'desativado: some da lista padrão');
  await pg.click('#am-abas [data-am-sit="inativos"]'); await pg.waitForTimeout(600);
  const lin = await pg.$eval(`#am-lista [data-am-abrir="${Z}"]`, e => e.textContent).catch(() => '');
  chk(/inativo/.test(lin), 'filtro Inativos: aparece com a etiqueta "inativo"', lin.slice(0, 160));
  chk(await pg.$eval('#am-desat-sel', b => b.hidden) && !(await pg.$eval('#am-reat-sel', b => b.hidden)), 'em Inativos, a seleção oferece Reativar (e não Desativar)');
  // ---------- Desativar com o site sem resposta (Amigo do site): a janela diz e nada muda ----------
  await pg.click('#am-abas [data-am-sit="todos"]'); await pg.waitForTimeout(600);
  const ana = await pg.$$eval('#am-lista [data-am-abrir]', rs => (rs.find(r => r.textContent.includes('Ana Teste Lima')) || {}).dataset.amAbrir);
  await pg.check(`#am-lista [data-am-abrir="${ana}"] .am-ck`); await pg.click('[data-am-acao="desativar-sel"]'); await pg.waitForSelector('#conf-ov');
  chk(/Não consegui conferir com o site/.test(await pg.$eval('#conf-ov', e => e.textContent)), 'site sem resposta: a confirmação avisa que não conferiu a assinatura');
  await pg.click('#conf-ov [data-conf="sim"]'); await pg.waitForFunction(() => (document.getElementById('conf-err') || {}).textContent, null, { timeout: 5000 }).catch(() => {});
  const err = await pg.$eval('#conf-err', e => e.textContent).catch(() => '');
  chk(/^Não foi desativado:/.test(err) && !!(await pg.$('#conf-ov')), 'site sem resposta: o erro aparece na janela e ela fica aberta', err);
  await pg.click('#conf-ov [data-conf="nao"]');
  const da = await pg.evaluate(id => fetch('/api/amigos/' + id).then(r => r.json()), ana);
  chk(!da.inativo_em, 'site sem resposta: nada mudou');
  await pg.click('[data-am-acao="limpar-sel"]'); await pg.waitForTimeout(400);
  // ---------- Apagar ----------
  await pg.click('#am-abas [data-am-sit="inativos"]'); await pg.waitForTimeout(600);
  await pg.click(`#am-lista [data-am-abrir="${Z}"] td:nth-child(2)`); await pg.waitForSelector('[data-am-apagar]');
  chk(/pediu para sair/.test(await pg.$eval('#d-body', e => e.textContent)) && !!(await pg.$('[data-am-reativar]')), 'detalhe do inativo: desde quando, motivo e Reativar');
  await pg.click('[data-am-apagar]'); await pg.waitForSelector('#conf-campo');
  const t2 = await pg.$eval('#conf-ov', e => e.textContent);
  chk(/Apagar este Amigo\?/.test(t2) && /Sai, no painel e no site/.test(t2) && /Fica, sem dados pessoais/.test(t2) && /pagamentos/.test(t2) && /Não dá para desfazer/.test(t2), 'confirmação de apagar: prévia do que sai e do que fica', t2.slice(0, 300));
  const sim = () => pg.$eval('#conf-ov [data-conf="sim"]', b => b.disabled);
  const b0 = await sim(); await pg.fill('#conf-campo', 'Zeca'); const b1 = await sim();
  await pg.fill('#conf-campo', '  zeca teste APAGAR '); const b2 = await sim();
  chk(b0 && b1 && !b2, 'Apagar fica apagado até digitar o nome (ou APAGAR)', JSON.stringify([b0, b1, b2]));
  await pg.click('#conf-ov [data-conf="sim"]'); await pg.waitForSelector('#conf-ov', { state: 'detached', timeout: 5000 }).catch(() => {}); await pg.waitForTimeout(700);
  chk(!(await pg.$(`#am-lista [data-am-abrir="${Z}"]`)) && await pg.evaluate(id => fetch('/api/amigos/' + id).then(r => r.status), Z) === 404, 'apagado: some do painel (Inativos e detalhe)');
  await pg.click('#am-abas [data-am-sit="todos"]'); await pg.waitForTimeout(600);
  chk(!(await pg.$eval('#am-lista', e => e.textContent)).includes('Zeca'), 'apagado: não está na lista');
  chk(erros.length === 0, 'sem erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
