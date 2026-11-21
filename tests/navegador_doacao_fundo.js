// CAMP-DOA-FUNDO (21/11/2026): "Acervo recebido pela CAMP" cria o fundo e o arquiteto, no navegador de verdade (Playwright + Chromium).
// Rafael: "e precisa criar quando terminar o fundo e arquiteto automaticamente."
//  [A] escolher a etapa "Acervo recebido pela CAMP" mostra a caixa "Criar fundo e arquiteto agora" (marcada) e a prévia com o PRÓXIMO código
//  [B] desmarcar esconde a prévia (caminho de sempre: código digitado); outra etapa tira o bloco
//  [C] Salvar abre a confirmação com a frase; sem a senha do site o erro fica na janela e NADA é criado
//  [D] arquiteto de mesmo nome (sem acento/caixa): "Usar o existente" vem marcado; "Criar novo" com o mesmo nome explica o porquê
//  [E] nomes só como texto (nada em onclick), sem erro de JavaScript
//  [F] vínculo dos dois lados: a doação mostra o fundo; a página do fundo mostra "Origem: doação de acervo …" e o link abre a doação
// Uso (servidor PRÓPRIO na porta 8860; nada vai ao site):
//   CAMP_DB_PATH=/dev/shm/doafundo/m.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/dev/shm/doafundo/m.db CAMP_COOKIE_SECURE=false python3 -m uvicorn app.main:app --port 8860)
//   CAMP_DB_PATH=/dev/shm/doafundo/m.db CAMP_BASE=http://127.0.0.1:8860 node tests/navegador_doacao_fundo.js
const fs = require('fs');
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8860', DB = process.env.CAMP_DB_PATH;
let CHROME = process.env.CHROME || '/opt/pw-browsers/chromium';
if (fs.existsSync(CHROME) && fs.statSync(CHROME).isDirectory()) {
  const cands = [CHROME + '/chrome-linux64/chrome', CHROME + '/chrome-linux/chrome', CHROME + '/chrome'];
  CHROME = cands.find(c => fs.existsSync(c)) || (() => { const d = fs.readdirSync('/opt/pw-browsers').filter(x => /^chromium-\d+$/.test(x)).sort().pop(); return `/opt/pw-browsers/${d}/chrome-linux64/chrome`; })();
}
const problemas = [], linhas = [], erros = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo, ...a) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, ...a], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const conta = () => py('print(con.execute("SELECT (SELECT COUNT(*) FROM fundo)||\'/\'||(SELECT COUNT(*) FROM agente)").fetchone()[0])');
const REG = (id, autor) => ({ id, protocolo: 'CAMP-2026-000' + id, recebida_em: '2026-11-20T12:00:00+00:00', nome: 'Pessoa <b>Doadora</b>', email: 'doa' + id + '@exemplo.com',
  autor, periodo: '1960–1990', caixas: 6, etapa: 'paga', etapa_nome: 'Contribuição paga · Amigo por 12 meses', valor: 2500, notas: [], historico: [], avisos: [] });

async function abrir(P, id) {
  await P.goto(BASE + '/#doacoes');
  await P.waitForTimeout(300);
  if (await P.locator('#conf-ov [data-conf="sim"]').count()) await P.click('#conf-ov [data-conf="sim"]');   // "descartar as alterações" do detalhe anterior
  await P.waitForSelector(`#doa-lista tr[data-doa-abrir="${id}"]`, { timeout: 15000 });
  await P.click(`#doa-lista tr[data-doa-abrir="${id}"]`);
  await P.waitForTimeout(300);
  if (await P.locator('#conf-ov [data-conf="sim"]').count()) await P.click('#conf-ov [data-conf="sim"]');
  await P.waitForSelector(`.doa-det[data-doa-id="${id}"] #doa-etapa-sel`, { timeout: 10000 });
}
(async () => {
  for (const [id, autor] of [[631, 'Ana Exemplo <i>Lima</i>'], [632, 'OSCAR EXEMPLO']]) {
    py(`r=json.loads(sys.argv[2])\ncon.execute("INSERT OR REPLACE INTO doacao_acervo (site_id, protocolo, recebida_em, nome, email, autor, etapa, valor, dados) VALUES (?,?,?,?,?,?,?,?,?)",(r['id'],r['protocolo'],'2026-11-20 12:00:00',r['nome'],r['email'],r['autor'],'paga',2500,json.dumps(r)))`, JSON.stringify(REG(id, autor)));
  }
  py('con.execute("INSERT OR IGNORE INTO agente (tipo, forma_autorizada) VALUES (\'pessoa\', \'Oscar Exemplo\')")\ncon.execute("DELETE FROM doacao_fundo WHERE site_id IN (631, 632)")');   // banco de teste: rodar de novo começa igual
  const browser = await chromium.launch({ executablePath: CHROME });
  try {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    const P = await ctx.newPage();
    P.on('pageerror', e => erros.push('pageerror: ' + e.message));
    await P.goto(BASE + '/');
    await P.fill('#lg-email', 'rafael@camp.arq.br'); await P.fill('#lg-senha', 'senha-bem-longa-123'); await P.press('#lg-senha', 'Enter');
    await P.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    const prox = await P.evaluate(() => API('/api/fundos/proximo').then(r => r.codigo));
    await abrir(P, 631);
    chk(await P.locator('#doa-receber').isHidden(), '[A] antes de escolher a etapa, nada de fundo');
    // [A]
    await P.selectOption('#doa-etapa-sel', 'recebido');
    await P.waitForSelector('.doa-rec-frase', { timeout: 10000 });
    const frase = (await P.locator('.doa-rec-frase').textContent()).trim();
    chk(await P.isChecked('#doa-rec-criar'), '[A] "Criar fundo e arquiteto agora" vem marcada');
    chk(frase === `Vai criar o fundo ${prox} · Ana Exemplo <i>Lima</i> e o arquiteto Ana Exemplo <i>Lima</i>`, `[A] prévia com o próximo código (${prox}) e os nomes: "${frase}"`);
    chk(await P.inputValue('#doa-rec-fundo-nome') === 'Ana Exemplo <i>Lima</i>' && await P.inputValue('#doa-rec-arq-nome') === 'Ana Exemplo <i>Lima</i>' && await P.locator('#doa-receber i').count() === 0,
      '[A] nomes editáveis, como texto (o <i> do nome não vira HTML)');
    chk(/Período: 1960–1990/.test(await P.locator('#doa-rec-previa').innerText()), '[A] a prévia mostra o período dos documentos (datas extremas do fundo)');
    // [B]
    await P.uncheck('#doa-rec-criar');
    chk(await P.locator('#doa-rec-previa').isHidden(), '[B] desmarcar esconde a prévia (o código vai digitado, como sempre)');
    await P.check('#doa-rec-criar');
    chk(await P.locator('#doa-rec-previa').isVisible(), '[B] marcar de novo mostra a prévia');
    // [C]
    const antes = conta();
    await P.click('[data-doa-acao="salvar"]');
    await P.waitForSelector('#conf-ov', { timeout: 5000 });
    chk((await P.locator('#conf-x').innerText()).startsWith(`Vai criar o fundo ${prox} · Ana Exemplo <i>Lima</i>`) && (await P.locator('[data-conf="sim"]').textContent()).trim() === 'Criar e salvar',
      '[C] a confirmação repete a frase da prévia, botão "Criar e salvar"');
    await P.click('[data-conf="sim"]');
    await P.waitForFunction(() => /senha do site/.test((document.getElementById('conf-err') || {}).textContent || ''), null, { timeout: 10000 })
      .then(() => chk(true, '[C] sem a senha do site: o erro aparece na janela'), () => chk(false, '[C] sem a senha do site: o erro aparece na janela'));
    chk(conta() === antes, `[C] nada criado (fundos/arquitetos ${antes} → ${conta()})`);
    await P.click('[data-conf="nao"]');
    // outra etapa tira o bloco
    await P.waitForSelector('#doa-etapa-sel', { timeout: 10000 });
    await P.selectOption('#doa-etapa-sel', 'arquivada');
    chk(await P.locator('#doa-receber').isHidden(), '[B] outra etapa: o bloco do fundo some');
    // [D]
    await abrir(P, 632);
    await P.selectOption('#doa-etapa-sel', 'recebido');
    await P.waitForSelector('.doa-rec-frase', { timeout: 10000 });
    const r1 = P.locator('input[name="doa-rec-arq"][value="existente"]');
    chk(await r1.count() === 1 && await r1.isChecked() && /Usar o existente: Oscar Exemplo/.test(await P.locator('#doa-rec-previa').innerText())
      && /com o arquiteto Oscar Exemplo \(já cadastrado\)/.test(await P.locator('.doa-rec-frase').textContent()), '[D] OSCAR EXEMPLO × Oscar Exemplo: "Usar o existente" marcado');
    chk(!(await P.locator('input[name="doa-rec-arq"]').first().getAttribute('onclick')), '[D] o id do arquiteto vai em data-*');
    await P.check('input[name="doa-rec-arq"][value="novo"]');
    await P.waitForFunction(() => /Já existe o arquiteto/.test(document.getElementById('doa-rec-previa').innerText), null, { timeout: 10000 })
      .then(() => chk(true, '[D] "Criar novo" com o mesmo nome: a prévia explica (usar o existente ou mudar o nome)'), () => chk(false, '[D] "Criar novo" com o mesmo nome: a prévia explica'));
    await P.fill('#doa-rec-arq-nome', 'Oscar Exemplo Filho');
    await P.click('[data-doa-acao="rec-previa"]');
    await P.waitForFunction(() => /e o arquiteto Oscar Exemplo Filho/.test((document.querySelector('.doa-rec-frase') || {}).textContent || ''), null, { timeout: 10000 })
      .then(() => chk(true, '[D] com outro nome, a prévia passa a criar o arquiteto novo'), () => chk(false, '[D] com outro nome, a prévia passa a criar o arquiteto novo'));
    // [F] vínculo dos dois lados (doação ↔ fundo)
    const f1 = py('print(con.execute("SELECT codigo FROM fundo WHERE codigo<>\'F000\' ORDER BY codigo LIMIT 1").fetchone()[0])');
    py(`con.execute("INSERT OR REPLACE INTO doacao_fundo (site_id, fundo_codigo, agente_id, fundo_criado, agente_criado, criado_por) VALUES (632, ?, (SELECT id FROM agente WHERE forma_autorizada='Oscar Exemplo'), 0, 0, 't')", (sys.argv[2],))`, f1);
    await abrir(P, 632);
    await P.waitForSelector('.doa-fundo', { timeout: 10000 });
    chk(new RegExp('^Fundo: ' + f1 + ' · .+ · arquiteto Oscar Exemplo$').test((await P.locator('.doa-fundo').innerText()).trim()) && await P.locator(`.doa-fundo a[href="#fundo/${f1}"]`).count() === 1,
      '[F] a doação mostra o fundo (link) e o arquiteto');
    await P.goto(BASE + '/#fundo/' + f1);
    await P.waitForTimeout(300);
    if (await P.locator('#conf-ov [data-conf="sim"]').count()) await P.click('#conf-ov [data-conf="sim"]');
    await P.waitForSelector('[data-doa-origem]', { timeout: 15000 });
    chk((await P.locator('[data-doa-origem]').textContent()).trim() === 'doação de acervo CAMP-2026-000632', '[F] a página do fundo mostra "Origem: doação de acervo CAMP-2026-000632"');
    await P.click('[data-doa-origem]');
    await P.waitForSelector('.doa-det[data-doa-id="632"]', { timeout: 15000 }).then(() => chk(true, '[F] o link da origem abre a doação'), () => chk(false, '[F] o link da origem abre a doação'));
    // [E]
    const oc = await P.evaluate(() => [...document.querySelectorAll('[onclick]')].map(e => e.getAttribute('onclick')).join(' '));
    chk(!/Oscar|Exemplo|doa63/.test(oc), '[E] nenhum nome dentro de onclick');
    await ctx.close();
  } catch (e) { chk(false, 'erro no teste: ' + e.message); }
  finally { await browser.close(); }
  chk(!erros.length, 'sem erro de JavaScript na página' + (erros.length ? ': ' + erros.join(' | ') : ''));
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
