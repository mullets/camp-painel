// Página do projeto (aba Folhas), segunda rodada (19/10, Rafael: "continua ruim, melhorou, mas meu deus"; "olha isso.."; "decisões iguais").
// Playwright + Chromium de verdade, servidor PRÓPRIO (porta 8991). Dois projetos montados aqui:
//  A) como o F009-P0092: 2 lotes aprovados da mesma pasta (o original e o "complemento"), 7 números que colidem, 7 folhas "0000" sem prévia,
//     3 folhas com autoria não confirmada, 5 erros bloqueantes + 10 avisos, 7 arquivos na pasta que não viraram folhas.
//  B) como o F026-P0009 (CRASA, Sto. André): 34 folhas todas a conferir, lote parado por erro do CAMP Vision, 27 folhas sem ano no carimbo,
//     1 diz outro ano, endereço só com pontuação diferente, cliente abreviado.
// Prova (cada número é um ponto da conversa):
//  1) o passo a passo diz "Lote aprovado, mas há 5 erros bloqueantes para resolver antes de publicar" (sem "Sem erros bloqueantes"), e o
//     cartão Problemas diz "5 impedem publicar · 13 avisos" em vermelho (19/10, proposta B: os cartões substituem a "Situação do lote");
//  2) com 2 lotes, a revisão é UM quadro, uma linha de resumo por lote, detalhes fechados;
//  3) os números que colidem viram uma frase ("7 folhas deste lote não entraram porque o número (D00001–D00007) já existe…") + tabela fechada;
//  4) "7 arquivos na pasta do QNAP…" aparece UMA vez (depois das folhas);
//  5) folha sem prévia: "Sem imagem" do mesmo tamanho das outras, com "Pedir releitura" (nada de "sem prévia" no canto);
//  6) "autoria não confirmada" pequeno no rodapé do cartão (não em cima da imagem) e "Com problema (N)" = cartões com aviso;
//  8) consenso conta FOLHAS distintas e separa "sem valor" e grafia/abreviação de diferença de verdade;
//  9) por campo, uma linha e UM botão "Usar 1978 nas 28"; só a folha que diz outra coisa vira chip; "ver quais" mostra as sem valor;
// 10) lote parado por erro: o cartão Folhas fica vermelho com o erro e "Pedir releitura" (sem "CAMP Vision ✔");
// 11) lote inteiro a conferir: o selo "a conferir" não se repete em cada cartão; "orientação incerta" fica pequeno (UX-27: no mínimo de 12 px).
// Uso:
//   CAMP_DB_PATH=/tmp/pj2.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/pj2.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8991)
//   CAMP_DB_PATH=/tmp/pj2.db CAMP_BASE=http://127.0.0.1:8991 node tests/navegador_pj2.js
const { execFileSync } = require('child_process');
const fs = require('fs'), os = require('os'), path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8991', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const JPG = Buffer.from('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=', 'base64');
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// ---------- A) F009-P0092 ----------
const A = 'F003-P9200', pastaA = fs.mkdtempSync(path.join(os.tmpdir(), 'pj2-')) + '/' + A + ' - Residencia';
fs.mkdirSync(pastaA + '/01 - Desenhos e pranchas/JPG', { recursive: true });
for (let n = 31; n <= 37; n++) fs.writeFileSync(`${pastaA}/01 - Desenhos e pranchas/JPG/${A}-0000-S01-D000${n}.jpg`, Buffer.from([0xff, 0xd8, 0xff, 0xd9]));
const colide = [1, 2, 3, 4, 5, 6, 7].map(n => `${A}-1981-S01-D0000${n}: o número D0000${n} já é de ${A}-0000-S01-D0000${n}`);
py(`
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F003', 9200)")
con.execute("INSERT INTO projeto (codigo, fundo_codigo, numero, titulo) VALUES ('${A}', 'F003', 9200, 'Residência Luiz Salles')")
l1 = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, aprovado_em, aprovado_por, criado_em) VALUES ('${A} - RESIDENCIA LUIZ SALLES - TUBO 118 - PRANCHAS ORIGINAIS', '${A}', ?, 'revisao', datetime('now'), 'rafael@camp.arq.br', '2026-09-02 10:00:00')", (${JSON.stringify(pastaA)},)).lastrowid
l2 = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, aprovado_em, aprovado_por, resultado, criado_em) VALUES ('complemento de 19/10 (19 folhas)', '${A}', ?, 'revisao', datetime('now'), 'rafael@camp.arq.br', ?, '2026-10-19 09:00:00')", (${JSON.stringify(pastaA)}, json.dumps({"importacao": {"problemas": ${JSON.stringify(colide)}}}))).lastrowid
pend = json.dumps({"previa": "x.jpg", "sinais": []})
for n in range(1, 8):    # a série "0000": a prévia não abre
    con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, titulo, tipo_documento, origem, lote_id, revisao, pendencias) VALUES (?,?,?,?,?,?,'campvision',?,'conferida',?)",
                ('${A}-0000-S01-D%05d' % n, '${A}', 'S01', n, 'Planta %d' % n, 'Planta', l1, pend))
for n in range(8, 20):
    con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, titulo, tipo_documento, origem, lote_id, revisao, pendencias, autoria_divergente) VALUES (?,?,?,?,?,?,'campvision',?,'conferida',?,?)",
                ('${A}-1981-S02-D%05d' % n, '${A}', 'S02', n, 'Corte %d' % n, 'Corte', l2, pend, 1 if n in (8, 9, 10) else 0))
for k in range(5):
    con.execute("INSERT INTO erro (gravidade, categoria, origem, codigo, descricao) VALUES ('bloqueia','arquivo_corrompido','campvision',?, 'Arquivo TIF corrompido')", ('${A}-1981-S02-D%05d' % (11 + k),))
for k in range(10):
    con.execute("INSERT INTO erro (gravidade, categoria, origem, codigo, descricao) VALUES ('aviso','metadado','campvision',?, 'Escala não lida')", ('${A}-1981-S02-D%05d' % (8 + k),))
con.execute("UPDATE configuracao SET valor='0' WHERE chave='publicacao.exige_direitos'")
`);

// ---------- B) F026-P0009 ----------
const B = 'F003-P9201';
py(`
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F003', 9201)")
con.execute("INSERT INTO projeto (codigo, fundo_codigo, numero, titulo) VALUES ('${B}', 'F003', 9201, 'CRASA Santo André')")
lb = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, status_json) VALUES ('${B} - CRASA', '${B}', '/nao/existe/pj2', 'erro', ?)", (json.dumps({"erro": "Falha ao ler o carimbo da folha D00020"}),)).lastrowid
pend = json.dumps({"previa": "x.jpg", "sinais": ["orientação incerta"]})
for n in range(1, 35):
    ano = 1978 if n <= 6 else (1979 if n == 14 else None)
    vazio = ano is None and n != 14
    end = None if n >= 32 else ('AV DO ESTADO' if n == 12 else 'AV. DO ESTADO, 100')
    if n == 12: end = 'AV DO ESTADO 100'
    cli = None if n >= 32 else ('PREFEITURA MUNICIPAL DE STO ANDRÉ' if n == 20 else 'PREFEITURA MUNICIPAL DE SANTO ANDRÉ')
    con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, titulo, tipo_documento, origem, lote_id, revisao, pendencias, ano_folha, endereco_folha, cliente_folha) VALUES (?,?,?,?,?,?,'campvision',?,'pendente',?,?,?,?)",
                ('${B}-1978-S01-D%05d' % n, '${B}', 'S01', n, 'Planta %d' % n, 'Planta', lb, pend, ano, end, cli))
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|\/previa|\/miniatura|folhas-qnap\/arquivo/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  // a prévia da série 1981 abre (um JPEG); a da série 0000 não existe (404), como no F009-P0092
  await ctx.route('**/api/itens/*/previa*', rt => /-0000-/.test(decodeURIComponent(rt.request().url())) ? rt.fulfill({ status: 404, body: 'não' }) : rt.fulfill({ status: 200, contentType: 'image/jpeg', body: JPG }));
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO((m.location() || {}).url || '')) erros.push(m.text() + ' @' + ((m.location() || {}).url || '')); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  const txt = async s => ((await page.$(s)) ? (await page.textContent(s)).replace(/\s+/g, ' ').trim() : '');
  const abrir = async (c, linha) => { await page.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, c);
    await page.waitForFunction(l => window.SL && SL[l] && SL.revisao && document.querySelector('#pj-cards .pjc[data-pjc="site"]'), linha, { timeout: 15000 }); await page.waitForTimeout(1800) };
  const cartao = k => page.$eval(`#pj-cards .pjc[data-pjc="${k}"]`, c => c.innerText.replace(/\s+/g, ' ').trim()), cor = k => page.$eval(`#pj-cards .pjc[data-pjc="${k}"]`, c => c.className.replace('pjc', '').trim());
  const gaveta = async k => { if (!(await page.isVisible(`.pj-gav[data-gav="${k}"]`))) { await page.click(`#pj-cards [data-pjc-gav="${k}"]`); await page.waitForTimeout(300) } };
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    for (const sel of ['.ajuda-caixa [data-ajuda-fechar]', '[data-faixa-fechar]']) { const b = await page.$(sel); if (b && await b.isVisible()) { await b.click(); await page.waitForTimeout(300) } }

    // ================= A =================
    await abrir(A, 'revisao');
    await page.waitForFunction(() => /Lote aprovado/.test((document.getElementById('pj-proximo') || {}).textContent || ''), null, { timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(800);
    const pp = await txt('#pj-proximo');
    chk(/Lote aprovado, mas há 5 erros bloqueantes para resolver antes de publicar\./.test(pp) && !/Sem erros bloqueantes/.test(pp), '(1a) passo do topo: "Lote aprovado, mas há 5 erros bloqueantes para resolver antes de publicar." (sem "Sem erros bloqueantes"): "' + pp.slice(0, 160) + '"');
    const sp = await cartao('problemas');
    chk(await cor('problemas') === 'bl' && /5 impedem publicar/.test(sp) && /13 avisos/.test(sp) && !!(await page.$('#pj-cards [data-pjc="problemas"] [data-pjc-resolver]')), '(1b) cartão Problemas vermelho: "5 impedem publicar … 13 avisos" com "Resolver": "' + sp + '"');
    const site = await cartao('site');
    chk(/Não publicado/.test(site) && /libera quando os problemas forem resolvidos/.test(site) && !/pronto/.test(site), '(1b) o cartão Site não diz "pronto" quando algo bloqueia: "' + site + '"');
    const aba = await txt('.pj-tabs [role="tab"]:nth-child(4)');
    chk(/Problemas \(18\)/.test(aba) && /5 bloqueiam/.test(aba), '(1) a aba diz quantos bloqueiam: "' + aba + '"');

    // (2) dois lotes: um quadro, uma linha por lote, fechados
    const rv = await cartao('folhas');
    chk(await page.isHidden('#pj-revisao') && /19 \/ 19 conferidas · lotes aprovados/.test(rv) && /7 folhas não entraram/.test(rv), '(2) lotes aprovados: a revisão fica fechada e o cartão Folhas resume "19 / 19 … · 7 folhas não entraram": "' + rv + '"');
    await gaveta('folhas');
    const nH2 = await page.$$eval('#pj-revisao h2', l => l.filter(h => /Revisão do lote/.test(h.textContent)).length);
    const lotes = await page.$$eval('#pj-revisao details.rl-lote', l => l.map(d => ({ open: d.open, s: d.querySelector('summary').textContent.replace(/\s+/g, ' ').trim() })));
    chk(nH2 === 1 && lotes.length === 2 && lotes.every(x => !x.open), '(2) "Detalhes dos lotes" abre UM quadro "Revisão do lote" com 2 lotes fechados (' + nH2 + ' quadros, ' + JSON.stringify(lotes.map(x => x.open)) + ')');
    chk(lotes.some(x => /^complemento de 19\/10 /.test(x.s) && !/\(19 folhas\)/.test(x.s) && /12 de 12 conferidas · aprovado por rafael/.test(x.s)) && lotes.some(x => /^RESIDENCIA LUIZ SALLES/.test(x.s) && /7 de 7 conferidas/.test(x.s)), '(2) cada lote numa linha: identificador (UX-04: sem o "(19 folhas)" antigo do nome, que brigava com 12 de 12), data, "12 de 12 conferidas · aprovado por rafael": ' + JSON.stringify(lotes.map(x => x.s)));
    chk(await page.$$eval('#pj-revisao .rl-lote', l => l.every(d => !d.open && !d.querySelector('.rl-corpo').checkVisibility())), '(2) os detalhes de cada lote ficam recolhidos');

    // (3) colisões: uma frase + tabela fechada
    await page.click('#pj-revisao details.rl-lote:nth-of-type(1) > summary'); await page.waitForTimeout(200);
    const nao = await txt('#pj-revisao .rl-nao p');
    chk(/7 folhas deste lote não entraram porque o número \(D00001–D00007\) já existe no projeto/.test(nao) && /não é preciso fazer nada/.test(nao), '(3) frase compacta: "' + nao.slice(0, 200) + '"');
    chk(!(await page.evaluate(() => [...document.querySelectorAll('#pj-revisao p')].some(p => (p.textContent.match(/já é de/g) || []).length > 1))), '(3) nada do parágrafo "…: o número D00001 já é de … · …"');
    chk(!(await page.$eval('#pj-revisao .rl-nao-lista', d => d.open)) && (await page.$$('#pj-revisao .rl-nao-lista tbody tr')).length === 7, '(3) a lista fica numa tabela (7 linhas) atrás de "ver as 7"');
    chk(/aprovado por rafael/.test(await txt('#pj-revisao details.rl-lote:nth-of-type(1) > summary')) && /7 folhas não entraram/.test(await txt('#pj-revisao details.rl-lote:nth-of-type(1) > summary')), '(3) a linha do lote avisa "7 folhas não entraram"');

    // (4) QNAP uma vez só, na gaveta "Detalhes dos lotes" (não empurra a grade)
    await page.waitForSelector('#pj-qnap-fim details.qf-dep', { state: 'attached', timeout: 10000 });
    const qn = await page.$$eval('#pd details.qf-dep summary', l => l.map(s => s.textContent.replace(/\s+/g, ' ').trim()));
    chk(qn.length === 1 && /7 arquivos na pasta do QNAP não viraram folhas do painel/.test(qn[0]), '(4) "7 arquivos na pasta do QNAP…" aparece uma vez: ' + JSON.stringify(qn));
    chk(await page.evaluate(() => !!document.querySelector('.pj-gav[data-gav="folhas"] #pj-qnap-fim details.qf-dep')), '(4/7) a linha "nada a fazer" fica na gaveta dos lotes');
    await page.click('.pj-gav[data-gav="folhas"] [data-pjc-fechar]'); await page.waitForTimeout(200);

    // (5) sem prévia: "Sem imagem" do mesmo tamanho, com Pedir releitura
    await page.waitForTimeout(800);
    const cards = await page.evaluate(() => [...document.querySelectorAll('#pd .thumb')].map(t => { const s = t.querySelector('.sem-imagem'), i = t.querySelector('img.img-real'), r = (s || i || {}).getBoundingClientRect ? (s || i).getBoundingClientRect() : { height: 0 };
      return { c: (t.dataset.revAbrir || ''), sem: !!s, qf: !!t.querySelector('.qf-sem'), txt: s ? s.textContent : '', bt: !!(s && s.querySelector('[data-releitura-item]')), h: Math.round(r.height), w: Math.round(r.width) } }));
    const zeros = cards.filter(x => /-0000-/.test(x.c)), outros = cards.filter(x => !/-0000-/.test(x.c));
    chk(zeros.length === 7 && zeros.every(x => x.sem && !x.qf && /^Sem imagem/.test(x.txt) && x.bt), '(5) as 7 folhas sem prévia mostram "Sem imagem" com "Pedir releitura" (nada de "sem prévia" no canto): ' + JSON.stringify(zeros.slice(0, 2)));
    chk(outros.length === 12 && zeros.every(x => Math.abs(x.h - outros[0].h) <= 2 && x.w === outros[0].w), '(5) o "Sem imagem" tem a mesma altura da imagem das outras folhas (' + zeros[0].h + ' × ' + (outros[0] || {}).h + ')');

    // (6) autoria não confirmada no rodapé; "Com problema" coerente
    const aut = await page.evaluate(() => [...document.querySelectorAll('#pd .thumb .flag')].map(f => ({ t: f.textContent, cap: !!f.closest('.cap'), pos: getComputedStyle(f).position })));
    const autS = aut.filter(x => x.t === 'autoria não confirmada');   // CAMP-081 (20/10): os cartões também marcam "problema" (os problemas abertos da folha)
    chk(autS.length === 3 && aut.every(x => x.cap && x.pos === 'static'), '(6) "autoria não confirmada" é marca pequena no rodapé do cartão, não em cima da imagem: ' + JSON.stringify(aut[0]));
    const nProb = +((await txt('.folhas-bar [data-fl-f="problema"]')).match(/\((\d+)\)/) || [])[1];
    const comAviso = await page.$$eval('#pd .thumb', l => l.filter(t => t.querySelector('.cap-avisos') || t.querySelector('.rev-tag.r')).length);
    // CAMP-081 (20/10): "Com problema" conta também os problemas abertos das folhas (4 que impedem publicar + 3 de metadado), como o conferir; cada um tem a marca no cartão
    chk(nProb === comAviso && nProb === 10, '(6) "Com problema (' + nProb + ')" = cartões com aviso (' + comAviso + ')');

    // (7) folhas perto do topo (como quem usa todo dia: "Como funciona" e a faixa do servidor já fechadas)
    for (const sel of ['.ajuda-caixa [data-ajuda-fechar]', '[data-faixa-fechar]']) { const b = await page.$(sel); if (b && await b.isVisible()) { await b.click(); await page.waitForTimeout(400) } }
    await page.evaluate(() => window.scrollTo(0, 0));
    const y = await page.evaluate(() => document.querySelector('#pd .thumb').getBoundingClientRect().top);
    if (process.env.DEPURAR) { await page.screenshot({ path: process.env.DEPURAR + '/topoA.png' }); await page.evaluate(() => document.querySelector('.folhas-bar').scrollIntoView()); await page.screenshot({ path: process.env.DEPURAR + '/gradeA.png' }); await page.evaluate(() => window.scrollTo(0, 0)) }
    chk(y < 900, '(7) a grade das folhas aparece sem rolar (topo em ' + Math.round(y) + 'px)');

  } catch (e) { problemas.push('exceção (A): ' + e.message.split('\n')[0]); linhas.push('FALHA exceção (A): ' + e.message.split('\n')[0]) }
  try {   // cada projeto num bloco: uma falha no A não esconde o B
    // ================= B =================
    await abrir(B, 'consenso');
    await page.waitForFunction(() => /bl/.test((document.querySelector('#pj-cards [data-pjc="folhas"]') || {}).className || ''), null, { timeout: 6000 }).catch(() => {});
    // (10) parado por erro: o cartão Folhas fica vermelho com o motivo
    const fB = await cartao('folhas');
    chk(await cor('folhas') === 'bl' && /Lote parado por erro do CAMP Vision/.test(fB) && !(await page.$('#pj-cards [data-pjc="folhas"] [data-releitura-projeto]')) && /Falha ao ler o carimbo/.test(await page.evaluate(() => (document.getElementById('pj-gav-erro') || {}).textContent || '')), '(10) o cartão Folhas fica vermelho ("Lote parado por erro"); a mensagem e o "Pedir releitura" ficam uma vez, em Detalhes dos lotes (CAMP-128): "' + fB.slice(0, 200) + '"');
    chk(!/CAMP Vision: (pronto|entregue)/.test(fB), '(10) sem "CAMP Vision ✔ entregue" quando o lote está parado');
    // (8) contas de folhas distintas
    const cs = await page.evaluate(() => (SL.consenso || {}).txt || '');
    const nums = (cs.match(/\d+/g) || []).map(Number);
    chk(/1 folha diz outra coisa/.test(cs) && /27 folhas sem algum dado no carimbo/.test(cs) && nums.every(n => n <= 34), '(8) consenso conta folhas (34 no projeto): "' + cs + '"');
    chk(/1 pergunta/.test(await cartao('dados')), '(8) o cartão Dados faz UMA pergunta (o ano): "' + await cartao('dados') + '"');
    // (9) uma linha por campo, um botão
    await gaveta('dados'); if (!(await page.isVisible('#pj-consenso'))) { await page.click('#pj-gaveta [data-pjc-porfolha]'); await page.waitForTimeout(300) }
    const ano = await page.$eval('#pj-consenso .cs-campo', c => ({ t: c.textContent.replace(/\s+/g, ' '), divs: c.querySelectorAll('.cs-div').length, todas: [...c.querySelectorAll('[data-cs-todas]')].map(b => b.textContent), usar: c.querySelectorAll('[data-cs-usar]').length, li: c.querySelectorAll('li').length }));
    chk(/1978 \(6 de 34 folhas\)/.test(ano.t) && /27 folhas sem ano no carimbo/.test(ano.t) && /1 diz outra coisa/.test(ano.t), '(9) Ano numa linha: "1978 (6 de 34 folhas) · 27 folhas sem ano no carimbo · 1 diz outra coisa": "' + ano.t.slice(0, 200) + '"');
    chk(ano.divs === 1 && /D00014/.test(await txt('#pj-consenso .cs-campo .cs-div')) && /1979/.test(await txt('#pj-consenso .cs-campo .cs-div')) && ano.usar === 1 && ano.li === 0, '(9) só a folha que diz outra coisa vira chip (D00014: 1979), com a própria ação; nenhuma linha por folha "sem valor" (' + ano.divs + ' chips, ' + ano.li + ' linhas)');
    chk(ano.todas.length === 1 && /^Usar 1978 nas 28$/.test(ano.todas[0].trim()), '(9) UM botão "Usar 1978 nas 28": ' + JSON.stringify(ano.todas));
    const total = await page.evaluate(() => ({ usar: document.querySelectorAll('#pj-consenso [data-cs-usar]').length, semValor: (document.getElementById('pj-consenso').textContent.match(/sem valor/g) || []).length }));
    chk(total.usar === 1 && total.semValor === 0, '(9) no painel inteiro: 1 botão por folha (o da que diverge de verdade), nenhum "sem valor" repetido: ' + JSON.stringify(total));
    const end = await txt('#pj-consenso .cs-campo:nth-of-type(2)'), cli = await txt('#pj-consenso .cs-campo:nth-of-type(3)');
    chk(/escreve de outro jeito/.test(end) && !/dizem? outra coisa/.test(end) && /escreve de outro jeito/.test(cli) && !/dizem? outra coisa/.test(cli), '(8) "AV DO ESTADO" × "AV. DO ESTADO" e "STO" × "SANTO" não contam como diferença: "' + end.slice(0, 160) + '" | "' + cli.slice(0, 160) + '"');
    chk(await page.isHidden('[data-cs-quais-box="ano-vazio"]'), '(9) a lista das sem valor fica fechada');
    await page.click('#pj-consenso [data-cs-quais="ano-vazio"]'); await page.waitForTimeout(150);
    chk(await page.isVisible('[data-cs-quais-box="ano-vazio"]') && (await page.$$('[data-cs-quais-box="ano-vazio"] [data-cs-ver]')).length === 27, '(9) "ver quais" mostra os 27 códigos na mesma linha');
    await page.click('#pj-consenso [data-cs-todas="ano"]'); await page.click('#conf-ov [data-conf="sim"]');
    await page.waitForFunction(() => !document.querySelector('#pj-consenso [data-cs-todas="ano"]'), null, { timeout: 10000 }).catch(() => {});
    chk(py(`print(con.execute("SELECT COUNT(*) FROM item WHERE projeto_codigo='${B}' AND ano_folha=1978").fetchone()[0])`) === '34', '(9) "Usar 1978 nas 28" grava 1978 nas 28 folhas (34 com 1978)');
    // (11) lote inteiro a conferir
    const tags = await page.evaluate(() => { const cs = [...document.querySelectorAll('#pd .thumb')]; return { n: cs.length, aConf: cs.filter(t => { const r = t.querySelector('.rev-tag'); return r && getComputedStyle(r).display !== 'none' }).length, or: cs.filter(t => t.querySelector('.or-inc')).length, fs: cs[0] && cs[0].querySelector('.or-inc') ? parseFloat(getComputedStyle(cs[0].querySelector('.or-inc')).fontSize) : 99,
      capFs: cs[0] && cs[0].querySelector('.cap') ? parseFloat(getComputedStyle(cs[0].querySelector('.cap')).fontSize) : 0 } });
    chk(tags.n === 34 && tags.aConf === 0 && /A conferir \(34\)/.test(await txt('.folhas-bar')), '(11) lote inteiro a conferir: o selo "a conferir" não se repete nos 34 cartões (a barra diz "A conferir (34)"): ' + JSON.stringify(tags));
    // UX-27 (WCAG): nada na tela abaixo de 12 px. "Pequeno" agora = no mínimo de 12 px e nunca maior que o texto do cartão (antes ≤ 9,5 px).
    chk(tags.or === 34 && tags.fs >= 12 && tags.fs <= 12 && tags.fs <= tags.capFs, '(11) "orientação incerta" continua, pequeno (' + tags.fs + 'px, no mínimo de 12 px e não maior que o texto do cartão, ' + tags.capFs + 'px)');
    py(`con.execute("UPDATE item SET revisao='conferida' WHERE codigo='${B}-1978-S01-D00001'")`);
    await abrir(B, 'consenso');
    const t2 = await page.evaluate(() => [...document.querySelectorAll('#pd .thumb .rev-tag')].filter(r => getComputedStyle(r).display !== 'none').length);
    chk(t2 === 34, '(11) com uma conferida, cada cartão volta a dizer se está conferido ou não (' + t2 + ')');

    if (process.env.DEPURAR) { await page.evaluate(() => window.scrollTo(0, 0)); await page.screenshot({ path: process.env.DEPURAR + '/topoB.png', fullPage: false }) }
    // celular
    await page.setViewportSize({ width: 390, height: 844 }); await abrir(A, 'revisao');
    chk(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'no celular (390px) não há rolagem lateral');
  } catch (e) { if (process.env.DEPURAR) { await page.screenshot({ path: process.env.DEPURAR + '/falha.png', fullPage: true }); console.log(await page.evaluate(() => JSON.stringify({ rev: (document.getElementById('pj-revisao') || {}).hidden, sl: window.SL && window.SL.abertos, hash: location.hash }))) }
    problemas.push('exceção: ' + e.message); linhas.push('FALHA exceção: ' + e.message) }
  chk(!erros.length, 'nenhum erro no console: ' + erros.slice(0, 3).join(' | '));
  chk(!falhas.length, 'nenhuma resposta 4xx/5xx inesperada: ' + falhas.slice(0, 5).join(' | '));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
