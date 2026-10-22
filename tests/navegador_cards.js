// Página do projeto com QUATRO cartões de situação (proposta B, 19/10: "B e C são muito legais"; antes: "UX muito ruim e confusa",
// "decisões iguais", quadros empilhados). Playwright + Chromium de verdade, servidor PRÓPRIO (porta 8993). Dois projetos montados aqui:
//  A) como o F009-P0092: 19 folhas conferidas em 2 lotes aprovados, 7 sem imagem (a prévia não abre), 5 erros bloqueantes + 10 avisos
//     + 3 autorias não confirmadas, o cliente do carimbo ("LUIZ SALLES") diferente do cadastro ("Luiz Marcelo Sales"), não publicado.
//  B) como o F026-P0009: 34 folhas todas a conferir, lote parado por erro do CAMP Vision, 27 sem ano, 1 diz outro ano.
// Prova:
//  1) quatro cartões na ordem Folhas · Problemas · Dados do projeto · Site, com os números e a cor certos (A: 19 / 19 verde; 5 vermelho;
//     1 pergunta âmbar com "cliente: … (carimbo) × … (cadastro)"; Não publicado, "libera quando os problemas forem resolvidos");
//  2) nada empilhado por padrão: sem "Situação do lote", sem Revisão do lote/Consenso/CAMP Vision/QNAP/passo a passo visíveis;
//  3) a grade das folhas começa nos primeiros 760px (1366×900: a primeira fileira de miniaturas aparece sem rolar; 20/10: +barra "O que falta" do CAMP-123 e chips por tipo do CAMP-127); filtro "Sem imagem (7)";
//  4) "Decidir" abre UMA gaveta com uma linha por pergunta (sem botão repetido por folha); "Manter o do projeto" deixa o cartão "Em ordem";
//  5) só uma gaveta aberta por vez; "Detalhes dos lotes" mostra a Revisão do lote; "Resolver" abre a aba Problemas;
//  6) B: Folhas vermelho "0 / 34", "34 a conferir" e o motivo do lote parado; Dados com 1 pergunta (Ano) e UM botão "Usar 1978 nas 28 folhas";
//     "Conferir" leva a #conferir/<código>;
//  7) lote todo conferido e não aprovado: o botão do cartão Folhas é "Aprovar o lote";
//  8) 768px: 2 × 2; 390px: uma coluna, sem rolagem lateral; nenhum erro no console.
// Uso:
//   CAMP_DB_PATH=/tmp/cards.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/cards.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8993)
//   CAMP_DB_PATH=/tmp/cards.db CAMP_BASE=http://127.0.0.1:8993 node tests/navegador_cards.js
const { execFileSync } = require('child_process');
const fs = require('fs'), os = require('os'), path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8993', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const JPG = Buffer.from('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=', 'base64');
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// ---------- A) F009-P0092 ----------
const A = 'F003-P9300', pastaA = fs.mkdtempSync(path.join(os.tmpdir(), 'cards-')) + '/' + A + ' - Residencia';
fs.mkdirSync(pastaA + '/01 - Desenhos e pranchas/JPG', { recursive: true });
for (let n = 31; n <= 33; n++) fs.writeFileSync(`${pastaA}/01 - Desenhos e pranchas/JPG/${A}-0000-S01-D000${n}.jpg`, Buffer.from([0xff, 0xd8, 0xff, 0xd9]));
py(`
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F003', 9300)")
con.execute("INSERT INTO projeto (codigo, fundo_codigo, numero, titulo, ano, cidade, cliente) VALUES ('${A}', 'F003', 9300, 'Residência Sr. Luiz Marcelo Sales', 1981, 'São Paulo', 'Luiz Marcelo Sales')")
l1 = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, aprovado_em, aprovado_por, criado_em) VALUES ('${A} - RESIDENCIA LUIZ SALLES - TUBO 118', '${A}', ?, 'revisao', datetime('now'), 'rafael@camp.arq.br', '2026-09-02 10:00:00')", (${JSON.stringify(pastaA)},)).lastrowid
l2 = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, aprovado_em, aprovado_por, criado_em) VALUES ('complemento de 19/10', '${A}', ?, 'revisao', datetime('now'), 'rafael@camp.arq.br', '2026-10-19 09:00:00')", (${JSON.stringify(pastaA)},)).lastrowid
pend = json.dumps({"previa": "x.jpg", "sinais": []})
for n in range(1, 8):    # a série "0000": a prévia não abre
    con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, titulo, tipo_documento, origem, lote_id, revisao, pendencias, cliente_folha) VALUES (?,?,?,?,?,?,'campvision',?,'conferida',?,'LUIZ SALLES')",
                ('${A}-0000-S01-D%05d' % n, '${A}', 'S01', n, 'Planta %d' % n, 'Planta', l1, pend))
for n in range(8, 20):
    con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, titulo, tipo_documento, origem, lote_id, revisao, pendencias, autoria_divergente, cliente_folha) VALUES (?,?,?,?,?,?,'campvision',?,'conferida',?,?,'LUIZ SALLES')",
                ('${A}-1981-S02-D%05d' % n, '${A}', 'S02', n, 'Corte %d' % n, 'Corte', l2, pend, 1 if n in (8, 9, 10) else 0))
for k in range(5):
    con.execute("INSERT INTO erro (gravidade, categoria, origem, codigo, descricao) VALUES ('bloqueia','arquivo_corrompido','campvision',?, 'Arquivo TIF corrompido')", ('${A}-1981-S02-D%05d' % (11 + k),))
for k in range(10):
    con.execute("INSERT INTO erro (gravidade, categoria, origem, codigo, descricao) VALUES ('aviso','metadado','campvision',?, 'Escala não lida')", ('${A}-1981-S02-D%05d' % (8 + k),))
con.execute("UPDATE configuracao SET valor='0' WHERE chave='publicacao.exige_direitos'")
`);

// ---------- B) F026-P0009 ----------
const B = 'F003-P9301';
py(`
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F003', 9301)")
con.execute("INSERT INTO projeto (codigo, fundo_codigo, numero, titulo) VALUES ('${B}', 'F003', 9301, 'CRASA Santo André')")
lb = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, status_json) VALUES ('${B} - CRASA', '${B}', '/nao/existe/cards', 'erro', ?)", (json.dumps({"erro": "Falha ao ler o carimbo da folha D00020"}),)).lastrowid
pend = json.dumps({"previa": "x.jpg", "sinais": ["orientação incerta"]})
for n in range(1, 35):
    ano = 1978 if n <= 6 else (1979 if n == 14 else None)
    con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, titulo, tipo_documento, origem, lote_id, revisao, pendencias, ano_folha) VALUES (?,?,?,?,?,?,'campvision',?,'pendente',?,?)",
                ('${B}-1978-S01-D%05d' % n, '${B}', 'S01', n, 'Planta %d' % n, 'Planta', lb, pend, ano))
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|\/previa|\/miniatura|folhas-qnap\/arquivo/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  await ctx.route('**/api/itens/*/previa*', rt => /-0000-/.test(decodeURIComponent(rt.request().url())) ? rt.fulfill({ status: 404, body: 'não' }) : rt.fulfill({ status: 200, contentType: 'image/jpeg', body: JPG }));
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO((m.location() || {}).url || '')) erros.push(m.text() + ' @' + ((m.location() || {}).url || '')); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  const txt = async s => ((await page.$(s)) ? (await page.textContent(s)).replace(/\s+/g, ' ').trim() : '');
  const card = k => page.evaluate(k => { const c = document.querySelector(`#pj-cards .pjc[data-pjc="${k}"]`); if (!c) return null; const q = s => (c.querySelector(s) || {}).textContent || '';
    return { cls: c.className, k: q('.pjc-k').trim(), v: q('.pjc-v').replace(/\s+/g, ' ').trim(), d: q('.pjc-d').replace(/\s+/g, ' ').trim(), bts: [...c.querySelectorAll('.pjc-act button, .pjc-act a')].map(b => b.textContent.trim()) } }, k);
  const abrir = async c => {
    await page.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, c);
    await page.waitForSelector('#pj-cards .pjc[data-pjc="folhas"]', { timeout: 15000 });
    await page.waitForFunction(() => { const v = [...document.querySelectorAll('#pj-cards .pjc-v')].map(x => x.textContent); return v.length === 4 && !v.includes('…') }, null, { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(1500);
    for (const sel of ['.ajuda-caixa [data-ajuda-fechar]', '[data-faixa-fechar]']) { const b = await page.$(sel); if (b && await b.isVisible()) { await b.click(); await page.waitForTimeout(300) } } };   // como quem usa todo dia
  const visiveis = () => page.evaluate(() => ['#pj-gaveta', '#pj-revisao', '#pj-consenso', '#pj-cv', '#pj-qnap', '#pj-qnap-fim', '#pj-proximo .pp', '#pj-situacao', '.sl-card', '#pj-proximo .steps']
    .filter(s => [...document.querySelectorAll(s)].some(e => e.checkVisibility() && e.getBoundingClientRect().height > 0)));
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    for (const sel of ['.ajuda-caixa [data-ajuda-fechar]', '[data-faixa-fechar]']) { const b = await page.$(sel); if (b && await b.isVisible()) { await b.click(); await page.waitForTimeout(300) } }

    // ================= A =================
    await abrir(A);
    const ordem = await page.$$eval('#pj-cards .pjc .pjc-k', l => l.map(x => x.textContent.trim()));
    chk(JSON.stringify(ordem) === JSON.stringify(['Folhas', 'Problemas', 'Dados do projeto', 'Site']), '(1) quatro cartões na ordem Folhas · Problemas · Dados do projeto · Site: ' + JSON.stringify(ordem));
    const f = await card('folhas'), p = await card('problemas'), d = await card('dados'), s = await card('site');
    chk(f && f.v === '19 / 19' && /\bok\b/.test(f.cls) && /conferidas · lotes aprovados/.test(f.d) && /7 sem imagem/.test(f.d) && f.bts.includes('Ver folhas'), '(1) Folhas: "19 / 19", verde, "conferidas · lotes aprovados · 7 sem imagem", "Ver folhas": ' + JSON.stringify(f));
    chk(p && p.v === '5' && /\bbl\b/.test(p.cls) && /impedem publicar \(arquivo corrompido\)/.test(p.d) && /13 avisos/.test(p.d) && p.bts.includes('Resolver'), '(1) Problemas: "5" vermelho, "impedem publicar (arquivo corrompido) · 13 avisos", "Resolver": ' + JSON.stringify(p));
    chk(d && d.v === '1 pergunta' && /\bat\b/.test(d.cls) && /cliente: “LUIZ SALLES” \(carimbo\) × “Luiz Marcelo Sales” \(cadastro\)/.test(d.d) && d.bts.includes('Decidir'), '(1) Dados: "1 pergunta" âmbar, cliente carimbo × cadastro, "Decidir": ' + JSON.stringify(d));
    chk(s && s.v === 'Não publicado' && !/\b(ok|at|bl)\b/.test(s.cls.replace('pjc', '')) && /libera quando os problemas forem resolvidos/.test(s.d) && s.bts.includes('Publicar'), '(1) Site: "Não publicado", neutro, "libera quando os problemas forem resolvidos", "Publicar": ' + JSON.stringify(s));
    chk(await page.$eval('#pj-cards [data-pjc-publicar]', b => b.getAttribute('aria-disabled') === 'true' && !!b.title), '(1) "Publicar" fica apagado e diz o porquê');
    chk((await page.$$('#pj-cards .btn.pri')).length === 1 && /Resolver/.test(await txt('#pj-cards .btn.pri')), '(1) um botão azul só, o do cartão mais urgente (Resolver)');
    // (9) P0 (Trello 21/10): nada abre sozinho; o cartão abre o detalhe (aqui: 5 problemas que impedem publicar); fechado, não reabre
    chk(await page.isHidden('#pj-gaveta'), '(9) P0: com problema que impede publicar, nenhuma gaveta abre sozinha');
    await page.click('#pj-cards [data-pjc-gav="problemas"]'); await page.waitForTimeout(600);
    const ga = await page.evaluate(() => ({ probs: (document.querySelector('.pj-gav[data-gav="problemas"]') || {}).checkVisibility && document.querySelector('.pj-gav[data-gav="problemas"]').checkVisibility(),
      n: document.querySelectorAll('#pj-probs .pj-probs li').length, outras: [...document.querySelectorAll('.pj-gav:not([data-gav="problemas"])')].some(x => x.checkVisibility()) }));
    chk(ga.probs && ga.n === 5 && !ga.outras, '(9) o cartão abre a gaveta "Problemas que impedem publicar" com os 5: ' + JSON.stringify(ga));
    if (process.env.FOTOS) await page.screenshot({ path: process.env.FOTOS + '/cartoes_A_auto.png' });
    await page.click('.pj-gav[data-gav="problemas"] [data-pjc-fechar]'); await page.waitForTimeout(200);
    await page.evaluate(c => desenharCartoes(c), A); await page.waitForTimeout(200);
    chk(await page.isHidden('#pj-gaveta'), '(9) fechada pela pessoa, a gaveta não reabre sozinha quando os cartões se redesenham');
    chk(JSON.stringify(await visiveis()) === '[]', '(2) nada empilhado por padrão (Situação/Revisão/Consenso/CAMP Vision/QNAP/passo a passo escondidos): ' + JSON.stringify(await visiveis()));
    chk(!(await page.evaluate(() => [...document.querySelectorAll('#pd h2')].some(h => h.checkVisibility() && /Situação do lote|Revisão do lote|Consenso do lote|O que o CAMP Vision entregou/.test(h.textContent)))), '(2) nenhum título de quadro antigo visível');
    await page.evaluate(() => window.scrollTo(0, 0));
    const y = await page.evaluate(() => document.querySelector('#pd .thumb').getBoundingClientRect().top);
    chk(y < 760, '(3) a grade das folhas começa nos primeiros 760px (topo em ' + Math.round(y) + 'px)');
    chk(/Sem imagem \(7\)/.test(await txt('.folhas-bar [data-fl-f="semimg"]')), '(3) filtro "Sem imagem (7)": ' + await txt('.folhas-bar [data-fl-f="semimg"]'));
    await page.click('.folhas-bar [data-fl-f="semimg"]'); await page.waitForTimeout(200);
    chk((await page.$$eval('#pd .thumb', l => l.filter(t => !t.hidden).length)) === 7, '(3) "Sem imagem" mostra só as 7');
    await page.click('.folhas-bar [data-fl-f=""]');
    if (process.env.FOTOS) await page.screenshot({ path: process.env.FOTOS + '/cartoes_A.png' });

    // (4) Decidir: uma gaveta, uma linha por pergunta
    await page.click('#pj-cards [data-pjc="dados"] [data-pjc-gav="dados"]'); await page.waitForTimeout(300);
    const gq = await page.evaluate(() => ({ vis: document.querySelector('.pj-gav[data-gav="dados"]').checkVisibility(), folhasVis: document.querySelector('.pj-gav[data-gav="folhas"]').checkVisibility(),
      n: document.querySelectorAll('#pj-perguntas > .pjq-lista > .pjq').length, campos: [...document.querySelectorAll('#pj-perguntas > .pjq-lista > .pjq')].map(x => x.dataset.pjq),
      usar: [...document.querySelectorAll('[data-cs-usar]')].filter(b => b.checkVisibility()).length, proj: !!document.querySelector('#pj-perguntas [data-cs-proj="cliente"]'), manter: !!document.querySelector('#pj-perguntas [data-cs-manter="cliente"]'),
      cons: document.getElementById('pj-consenso').checkVisibility() }));
    chk(gq.vis && !gq.folhasVis && gq.n === 1 && gq.campos[0] === 'cliente' && gq.proj && gq.manter && gq.usar === 0 && !gq.cons, '(4) "Decidir" abre uma gaveta com UMA pergunta (cliente) e os botões "Usar no projeto" / "Manter o do projeto", sem botão por folha: ' + JSON.stringify(gq));
    if (process.env.FOTOS) await page.screenshot({ path: process.env.FOTOS + '/cartoes_A_decidir.png' });
    // (5) uma gaveta por vez
    await page.click('#pj-cards [data-pjc-gav="folhas"]'); await page.waitForTimeout(300);
    const g2 = await page.evaluate(() => ({ dados: document.querySelector('.pj-gav[data-gav="dados"]').checkVisibility(), folhas: document.querySelector('.pj-gav[data-gav="folhas"]').checkVisibility(), rev: document.getElementById('pj-revisao').checkVisibility() && /Revisão do lote/.test(document.getElementById('pj-revisao').textContent) }));
    chk(!g2.dados && g2.folhas && g2.rev, '(5) "Detalhes dos lotes" fecha a outra gaveta e mostra a Revisão do lote: ' + JSON.stringify(g2));
    await page.click('.pj-gav[data-gav="folhas"] [data-pjc-fechar]'); await page.waitForTimeout(200);
    chk(await page.isHidden('#pj-gaveta'), '(5) "Fechar" esconde a gaveta');
    // (4) Manter o do projeto: a pergunta some
    await page.click('#pj-cards [data-pjc-gav="dados"]'); await page.waitForTimeout(200);
    await page.click('#pj-perguntas [data-cs-manter="cliente"]');
    await page.waitForFunction(() => /Em ordem/.test((document.querySelector('#pj-cards [data-pjc="dados"] .pjc-v') || {}).textContent || ''), null, { timeout: 10000 }).catch(() => {});
    const d2 = await card('dados');
    chk(d2.v === 'Em ordem' && /\bok\b/.test(d2.cls) && !(await page.$('#pj-perguntas [data-cs-manter]')), '(4) "Manter o do projeto": a pergunta some e o cartão fica "Em ordem" (verde): ' + JSON.stringify(d2));
    // (5) Resolver: aba Problemas
    await page.click('#pj-cards [data-pjc-resolver]'); await page.waitForTimeout(1500);
    chk(/Problemas/.test(await txt('.pj-tabs [aria-selected="true"]')) && !!(await page.$('#pd [data-abrir^="erro:"]')), '(5) "Resolver" abre a aba Problemas do projeto: ' + await txt('.pj-tabs [aria-selected="true"]'));
    chk((await page.$$('#pj-cards .pjc')).length === 4, '(5) os cartões continuam no topo em outra aba');

    // (7) lote todo conferido e não aprovado
    py(`con.execute("UPDATE lista_processamento SET aprovado_em=NULL, aprovado_por=NULL WHERE projeto_codigo='${A}' AND nome LIKE 'complemento%'")`);
    await page.evaluate(() => { pdTab = 'itens' }); await abrir(A);
    const f3 = await card('folhas');
    chk(/\bat\b/.test(f3.cls) && /falta aprovar o lote/.test(f3.d) && f3.bts[0] === 'Aprovar o lote' && !!(await page.$('#pj-cards [data-pjc="folhas"] [data-pp="aprovar"][data-lote]')), '(7) lote conferido e não aprovado: o botão do cartão Folhas é "Aprovar o lote": ' + JSON.stringify(f3));
    py(`con.execute("UPDATE lista_processamento SET aprovado_em=datetime('now'), aprovado_por='rafael@camp.arq.br' WHERE projeto_codigo='${A}'")`);
  } catch (e) { problemas.push('exceção (A): ' + e.message.split('\n')[0]); linhas.push('FALHA exceção (A): ' + e.message.split('\n')[0]) }
  try {
    // ================= B =================
    await abrir(B);
    await page.waitForFunction(() => /bl/.test((document.querySelector('#pj-cards [data-pjc="folhas"]') || {}).className || ''), null, { timeout: 8000 }).catch(() => {});
    const f = await card('folhas'), d = await card('dados');
    chk(f.v === '0 / 34' && /\bbl\b/.test(f.cls) && /34 a conferir/.test(f.d) && /Lote parado por erro do CAMP Vision/.test(f.d) && !/Falha ao ler/.test(f.d) && f.bts[0] === 'Conferir' && !f.bts.includes('Pedir releitura') && f.bts.includes('Detalhes dos lotes'), '(6) B: Folhas vermelho "0 / 34", "34 a conferir", "Lote parado por erro" em 1 linha (CAMP-128: a mensagem e o "Pedir releitura" ficam uma vez, em Detalhes dos lotes): ' + JSON.stringify(f));
    chk(d.v === '1 pergunta' && /ano: “1978” em 6 folhas; 1 diz outra coisa/.test(d.d), '(6) B: Dados "1 pergunta" (ano), sem contar folha sem ano nem grafia diferente: ' + JSON.stringify(d));
    const gb = await page.evaluate(() => ({ folhas: document.querySelector('.pj-gav[data-gav="folhas"]').checkVisibility(), rev: !!document.getElementById('pj-revisao') }));
    chk(!gb.folhas, '(9) B (P0): lote parado por erro do CAMP Vision: "Detalhes dos lotes" NÃO abre sozinho (o aviso fica na barra "O que falta"): ' + JSON.stringify(gb));
    chk(JSON.stringify(await visiveis()) === '[]', '(2) B: depois de fechar, nada empilhado: ' + JSON.stringify(await visiveis()));
    await page.evaluate(() => window.scrollTo(0, 0));
    const y = await page.evaluate(() => document.querySelector('#pd .thumb').getBoundingClientRect().top);
    chk(y < 760, '(3) B: a grade das folhas começa nos primeiros 760px (topo em ' + Math.round(y) + 'px)');
    if (process.env.FOTOS) await page.screenshot({ path: process.env.FOTOS + '/cartoes_B.png' });
    await page.click('#pj-cards [data-pjc-gav="dados"]'); await page.waitForTimeout(300);
    const q = await page.evaluate(() => ({ n: document.querySelectorAll('#pj-perguntas > .pjq-lista > .pjq').length, todas: [...document.querySelectorAll('#pj-perguntas [data-cs-todas]')].filter(b => b.checkVisibility()).map(b => b.textContent.trim()), usar: [...document.querySelectorAll('[data-cs-usar]')].filter(b => b.checkVisibility()).length }));
    chk(q.n === 1 && q.todas.length === 1 && q.todas[0] === 'Usar 1978 nas 28 folhas' && q.usar === 0, '(4/6) B: uma pergunta (Ano) com UM botão "Usar 1978 nas 28 folhas", nenhum botão por folha: ' + JSON.stringify(q));
    await page.click('#pj-cards [data-pjc-conferir]'); await page.waitForTimeout(500);
    chk(/#conferir\/[^/]+(\/[^/]+)?$/.test(page.url()) && page.url().includes('#conferir/' + B), '(6) "Conferir" leva a #conferir/<código>: ' + page.url().replace(BASE, ''));

    // (8) larguras
    await page.setViewportSize({ width: 768, height: 900 }); await abrir(A);
    const c768 = await page.$$eval('#pj-cards .pjc', l => l.map(c => Math.round(c.getBoundingClientRect().top)));
    chk(c768.length === 4 && c768[0] === c768[1] && c768[2] === c768[3] && c768[2] > c768[0], '(8) 768px: cartões em 2 × 2 ' + JSON.stringify(c768));
    await page.setViewportSize({ width: 390, height: 844 }); await abrir(A);
    const c390 = await page.$$eval('#pj-cards .pjc', l => l.map(c => Math.round(c.getBoundingClientRect().left)));
    chk(new Set(c390).size === 1, '(8) 390px: uma coluna ' + JSON.stringify(c390));
    chk(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), '(8) 390px: sem rolagem lateral');
    if (process.env.FOTOS) await page.screenshot({ path: process.env.FOTOS + '/cartoes_A_390.png', fullPage: false });
  } catch (e) { problemas.push('exceção (B): ' + e.message.split('\n')[0]); linhas.push('FALHA exceção (B): ' + e.message.split('\n')[0]) }
  chk(!erros.length, 'nenhum erro no console: ' + erros.slice(0, 3).join(' | '));
  chk(!falhas.length, 'nenhuma resposta 4xx/5xx inesperada: ' + falhas.slice(0, 5).join(' | '));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
