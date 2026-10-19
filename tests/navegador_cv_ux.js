// Aba Folhas do projeto no navegador de verdade (Playwright + Chromium), depois de "acho meio confuso isso tudo" e "melhore no geral" (19/10, F009-P0092).
// Prova: (1) lote aprovado e folhas conferidas: o aceite do CAMP Vision que só pedia olho humano aparece VERDE ("Pronto"), sem código cru
// (orientacao_incerta_zerada, publicavel) e sem "reprovado"; (2) tudo em ordem vira UM cartão "Situação do lote" (revisão, consenso, CAMP Vision,
// uma linha cada) e os quadros grandes ficam fechados ("Ver detalhes" abre); (3) as folhas aparecem sem rolar; (4) "orientação incerta" some da
// miniatura de folha já conferida (e continua na pendente); (5) a identificação original no cabeçalho é curta (o texto inteiro no title);
// (6) "N no site" fica na barra das folhas (sem o rodapé solto); seção vazia "(0)" não aparece; consenso × projeto: "Manter o do projeto" e
// "Usar no projeto" no próprio cartão; (7) quando o aceite trava DE VERDADE (contagem), o quadro abre sozinho com o que falta e o passo
// "Publicar" diz o porquê; no celular não há rolagem lateral; nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx):
//   CAMP_DB_PATH=/tmp/cvux_nav.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/cvux_nav.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8941)
//   CAMP_DB_PATH=/tmp/cvux_nav.db CAMP_BASE=http://127.0.0.1:8941 node tests/navegador_cv_ux.js
const { execFileSync } = require('child_process');
const fs = require('fs'), os = require('os'), path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8941', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// Um projeto como o F009-P0092: 7 folhas, todas conferidas, lote aprovado; o CV2 reprovou só pela orientação incerta e mandou as CHAVES nas pendências.
const PJ = 'F003-P9100', pasta = fs.mkdtempSync(path.join(os.tmpdir(), 'cvux-')) + '/' + PJ + ' - Residencia';
fs.mkdirSync(pasta + '/catalogacao/lotes', { recursive: true });
const ACEITE = { contagem_origem_igual_saida: { ok: true }, duplicatas_marcadas: { ok: true }, orientacao_incerta_zerada: { ok: false }, serie_incerta_zerada: { ok: true },
  exif_conferido: true, relatorio_gerado: true, folhas_autoria_nao_confirmada: 0, publicavel: false, pendencias: ['orientacao_incerta_zerada', 'publicavel'] };
const gravarAceite = a => { fs.writeFileSync(pasta + '/catalogacao/lotes/lote-1.json', JSON.stringify({ aceite: a })); py(`con.execute("UPDATE lista_processamento SET aceite_json=? WHERE projeto_codigo='${PJ}'", (${JSON.stringify(JSON.stringify(a))},))`) };
// F009-P0060: a orientacao.txt cita D31 e D37, documentos que NÃO viraram folhas (ficaram só na pasta, fora do pacote); um aviso de quase-duplicata
fs.writeFileSync(pasta + '/catalogacao/orientacao.txt', 'Orientação aplicada: 7\nincerta — conferir: D1, D2, D3, D4, D5, D6, D7, D31, D37\n');
fs.writeFileSync(pasta + '/catalogacao/pacote_tainacan.json', JSON.stringify({ projeto: { capa_sugerida: PJ + '-0000-S01-D00001' }, avisos: ['D40 é quase de D37 — publicar D37'], retirados: [], propostas: {} }));
// a pasta do lote no QNAP: a D1 virou folha; D31 e D37 (TIF + JPG) ficaram fora do pacote
fs.mkdirSync(pasta + '/01 - Desenhos e pranchas/JPG', { recursive: true }); fs.mkdirSync(pasta + '/01 - Desenhos e pranchas/TIF', { recursive: true });
for (const n of ['00001', '00031', '00037']) { fs.writeFileSync(`${pasta}/01 - Desenhos e pranchas/JPG/${PJ}-0000-S01-D${n}.jpg`, Buffer.from([0xff, 0xd8, 0xff, 0xd9])); fs.writeFileSync(`${pasta}/01 - Desenhos e pranchas/TIF/${PJ}-0000-S01-D${n}.tif`, 'x') }
const ORIG = 'Tubos 118 (RESIDÊNCIA SR. LUIZ MARCELO SALES). Pesquisa (Patricia de Souza Gonçalves, Belas Artes): EO-REF-007. Situação da identificação: único. Grupo G092 da planilha F009.';
py(`
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F003', 9100)")
con.execute("INSERT INTO projeto (codigo, fundo_codigo, numero, titulo, cliente, endereco_obra, identificacao_original) VALUES (?, 'F003', 9100, 'Residência Sr. Luiz Marcelo Sales', 'Luiz Marcelo Sales', 'Rua Dr. Alberto Faria', ?)", ('${PJ}', ${JSON.stringify(ORIG)}))
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa, aprovado_em, aprovado_por) VALUES ('F009-P0092 - RESIDENCIA LUIZ SALLES', '${PJ}', ?, 'revisao', datetime('now'), 'rafael@camp.arq.br')", (${JSON.stringify(pasta)},)).lastrowid
for n in range(1, 8):
    con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, titulo, tipo_documento, origem, lote_id, revisao, cliente_folha, endereco_folha) VALUES (?,?,?,?,?,?,'campvision',?,?,'LUIZ SALLES','RUA DR. ALBERTO FARIA')",
                ('${PJ}-0000-S01-D%05d' % n, '${PJ}', 'S01', n, 'Planta %d' % n, 'Planta', lid, 'corrigida' if n == 7 else 'conferida'))
con.execute("UPDATE configuracao SET valor='0' WHERE chave='publicacao.exige_direitos'")
`);
gravarAceite(ACEITE);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa|\/miniatura/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  const txt = async s => ((await page.$(s)) ? (await page.textContent(s)).replace(/\s+/g, ' ').trim() : '');
  const abrir = async () => { await page.evaluate(c => { window.SL = null; nav('projeto/' + c) }, PJ); await page.waitForSelector('#pj-situacao .sl-linha[data-sl="cv"]', { timeout: 15000 }); await page.waitForSelector('#pj-situacao .sl-linha[data-sl="consenso"]', { timeout: 15000 }); await page.waitForTimeout(1200) };
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await abrir();

    // ---- (1)+(2) um cartão, uma linha por quadro; o aceite resolvido pela conferência aparece verde ----
    const card = await txt('#pj-situacao');
    chk(/Situação do lote/.test(card) && (await page.$$('#pj-situacao .sl-linha')).length === 3, 'um cartão "Situação do lote" com 3 linhas (revisão, consenso, CAMP Vision): "' + card.slice(0, 200) + '"');
    chk(/7 de 7 folhas conferidas · lote aprovado/.test(await txt('#pj-situacao [data-sl="revisao"]')) && !!(await page.$('#pj-situacao .sl-linha.ok[data-sl="revisao"]')), 'revisão: "7 de 7 folhas conferidas · lote aprovado" com ✔');
    chk(!!(await page.$('#pj-situacao .sl-linha.ok[data-sl="cv"]')) && /pronto/.test(await txt('#pj-situacao [data-sl="cv"]')), 'CAMP Vision: ✔ pronto (o que pedia olho humano já foi conferido): "' + await txt('#pj-situacao [data-sl="cv"]') + '"');
    chk(await page.isHidden('#pj-revisao') && await page.isHidden('#pj-cv') && await page.isHidden('#pj-consenso'), 'os quadros grandes (revisão, consenso, CAMP Vision) ficam fechados quando estão em ordem');
    const cv = await page.evaluate(() => document.getElementById('pj-cv').textContent.replace(/\s+/g, ' '));
    chk(!/orientacao_incerta_zerada|publicavel|reprovado|não pode ser publicado/.test(cv) && /Pronto do lado do CAMP Vision/.test(cv) && /Isso já foi conferido no painel/.test(cv), 'o quadro do CAMP Vision não mostra código cru nem "reprovado"; diz "Pronto" e que o olho humano já foi feito: "' + cv.slice(0, 260) + '"');
    chk(!(await page.evaluate(() => [...document.querySelectorAll('#pj-cv details > summary')].some(s => /\(0\)/.test(s.textContent)))) && /Nada pendente em: .*sugestões.*retiradas/.test(cv), 'seções vazias "(0)" não aparecem; viram a linha "Nada pendente em: …"');
    await page.click('#pj-situacao [data-sl-ver="cv"]'); await page.waitForTimeout(300);
    chk(await page.isVisible('#pj-cv') && /Esconder detalhes/.test(await txt('#pj-situacao [data-sl-ver="cv"]')), '"Ver detalhes" abre o quadro do CAMP Vision');
    await page.click('#pj-cv #cv-sec-aceite summary'); await page.waitForTimeout(200);
    chk(/Orientação incerta zerada ou revisada conferido no painel/.test(await txt('#pj-cv #cv-sec-aceite')), 'no checklist, o item da orientação aparece como "conferido no painel"');
    await page.click('#pj-situacao [data-sl-ver="cv"]'); await page.waitForTimeout(200);
    chk(await page.isHidden('#pj-cv'), '"Esconder detalhes" fecha de novo');
    const ori = await page.evaluate(() => (document.getElementById('cv-sec-orientacao') || {}).textContent || '');
    chk(!(await page.$('#cv-sec-orientacao .tag.a')) && /D31, D37: estes documentos não viraram folhas do painel/.test(ori) && /7 folhas com orientação incerta já foram conferidas/.test(ori), 'orientação: D31/D37 (fora do painel) explicados como "não viraram folhas", sem a marca "conferir": "' + ori.replace(/\s+/g, ' ').slice(0, 220) + '"');
    await page.waitForSelector('#pj-qnap-fim details.qf-dep', { state: 'attached', timeout: 10000 });
    const qn = await txt('#pj-qnap-fim summary');
    chk(/2 arquivos na pasta do QNAP não viraram folhas do painel/.test(qn) && /nada a fazer/.test(qn) && !(await page.$eval('#pj-qnap-fim details.qf-dep', d => d.open)) && !(await page.isVisible('#pj-qnap-fim .qf')), 'QNAP: uma linha fechada "2 arquivos … não viraram folhas · nada a fazer", miniaturas escondidas: "' + qn + '"');
    await page.click('#pj-qnap-fim details.qf-dep summary'); await page.waitForTimeout(300);
    chk((await page.$$('#pj-qnap-fim .qf')).length === 2 && /Não é preciso fazer nada/.test(await txt('#pj-qnap-fim')), '... ao abrir, mostra os 2 arquivos e explica que não é preciso fazer nada');
    await page.click('#pj-qnap-fim details.qf-dep summary');
    const sem = await txt('#pd .thumb .sem-imagem');
    chk(/^Sem imagem/.test(sem) && !!(await page.$('#pd .thumb .sem-imagem [data-releitura-item]')), 'miniatura sem prévia: "Sem imagem" curto, com "Pedir releitura": "' + sem.slice(0, 80) + '"');
    chk(!/Aceite/.test(await txt('#pj-proximo')), 'o passo "Publicar" não fala de aceite (resolvido): "' + (await txt('#pj-proximo')).slice(0, 140) + '"');

    // ---- (3) folhas visíveis sem rolar; (4) sem "orientação incerta" nas já conferidas; (6) números na barra ----
    // como quem usa todo dia: a caixa "Como funciona" (só na 1ª visita) e a faixa de aviso do servidor já foram fechadas
    for (const sel of ['.ajuda-caixa [data-ajuda-fechar]', '[data-faixa-fechar]']) { const b = await page.$(sel); if (b && await b.isVisible()) { await b.click(); await page.waitForTimeout(400) } }
    await page.evaluate(() => window.scrollTo(0, 0));
    const y = await page.evaluate(() => { const t = document.querySelector('#pd .thumb'); return t ? t.getBoundingClientRect().top : 99999 });
    chk(y < 900, 'as miniaturas das folhas aparecem sem rolar (topo da primeira em ' + Math.round(y) + 'px, tela de 900)');
    chk((await page.$$('#pd .thumb')).length === 7 && !(await page.evaluate(() => [...document.querySelectorAll('#pd .thumb .cap')].some(c => /orientação incerta/.test(c.textContent)))), 'nenhuma miniatura conferida/corrigida mostra "orientação incerta"');
    chk(!(await page.$('.project-source')) && /Conferidas 7 de 7 · 0 no site/.test(await txt('.folhas-bar .fb-cont')), 'sem o rodapé solto: "Conferidas 7 de 7 · 0 no site" na barra das folhas: "' + await txt('.folhas-bar .fb-cont') + '"');

    // ---- (5) identificação original curta no cabeçalho ----
    await page.waitForSelector('#pj-local-topo .pj-orig', { timeout: 8000 });
    const o = await page.textContent('#pj-local-topo .pj-orig'), ot = await page.getAttribute('#pj-local-topo .pj-orig', 'title');
    chk(o.trim() === 'Tubos 118' && ot === ORIG, 'cabeçalho: "original: Tubos 118" (o texto inteiro no title): "' + o + '"');

    // ---- consenso × projeto, no próprio cartão ----
    const cs = await txt('#pj-situacao');
    chk(/Cliente: as folhas dizem LUIZ SALLES; o projeto diz Luiz Marcelo Sales/.test(cs) && !!(await page.$('#pj-situacao [data-cs-proj="cliente"]')) && !!(await page.$('#pj-situacao [data-cs-manter="cliente"]')) && /1 ponto precisa de você/.test(cs), 'consenso: o cartão mostra "as folhas dizem LUIZ SALLES; o projeto diz Luiz Marcelo Sales" com "Usar no projeto" e "Manter o do projeto"');
    await page.click('#pj-situacao [data-cs-manter="cliente"]');
    await page.waitForFunction(() => !document.querySelector('#pj-situacao [data-cs-manter]'), null, { timeout: 8000 }); await page.waitForTimeout(400);
    chk(/tudo certo/.test(await txt('#pj-situacao .ph')) && py(`print(con.execute("SELECT cliente FROM projeto WHERE codigo='${PJ}'").fetchone()[0])`) === 'Luiz Marcelo Sales', '"Manter o do projeto": a pergunta some, o cartão fica "tudo certo" e o projeto não muda');
    py(`con.execute("UPDATE projeto SET endereco_obra='Rua Errada, 1' WHERE codigo='${PJ}'")`);
    await abrir();
    await page.click('#pj-situacao [data-cs-proj="endereco"]'); await page.click('#conf-ov [data-conf="sim"]');
    await page.waitForFunction(() => !document.querySelector('#pj-situacao [data-cs-proj="endereco"]'), null, { timeout: 10000 });
    chk(py(`print(con.execute("SELECT endereco_obra FROM projeto WHERE codigo='${PJ}'").fetchone()[0])`) === 'RUA DR. ALBERTO FARIA', '"Usar no projeto" grava o valor das folhas no projeto (pela edição do projeto)');

    // ---- (4) a folha que ainda espera conferência continua com a marca ----
    py(`con.execute("UPDATE lista_processamento SET aprovado_em=NULL WHERE projeto_codigo='${PJ}'")\ncon.execute("UPDATE item SET revisao='pendente' WHERE codigo='${PJ}-0000-S01-D00002'")`);
    await abrir();
    const marcadas = await page.evaluate(() => [...document.querySelectorAll('#pd .thumb .cap')].filter(c => /orientação incerta/.test(c.textContent)).map(c => c.querySelector('.code').textContent));
    chk(marcadas.length === 1 && /D00002$/.test(marcadas[0]), 'só a folha pendente mantém "orientação incerta" (' + marcadas.join(',') + ')');
    chk(/6 de 7 folhas conferidas · 1 falta conferir/.test(await txt('#pj-situacao [data-sl="revisao"]')) && !!(await page.$('#pj-situacao [data-sl="revisao"] [data-pp="conferir"]')), 'revisão pendente: a linha diz quantas faltam e tem o botão "Conferir"');
    chk(!!(await page.$('#pj-situacao .sl-linha.falta[data-sl="cv"]')) && await page.isVisible('#pj-cv') && /Conferir a folha que falta na Revisão do lote/.test(await txt('#pj-cv .cv-resumo')) && !!(await page.$('#pj-cv .cv-resumo [data-pp="conferir"]')), 'com 1 folha pendente, o CAMP Vision vira "falta" e o quadro abre sozinho com o que fazer e o botão "Conferir as folhas"');
    py(`con.execute("UPDATE lista_processamento SET aprovado_em=datetime('now') WHERE projeto_codigo='${PJ}'")\ncon.execute("UPDATE item SET revisao='conferida' WHERE codigo='${PJ}-0000-S01-D00002'")`);

    // ---- (7) o aceite trava DE VERDADE: contagem de origem ----
    gravarAceite({ ...ACEITE, contagem_origem_igual_saida: { ok: false } });
    await abrir(); await page.waitForTimeout(1500);
    const r = await txt('#pj-cv .cv-resumo');
    chk(await page.isVisible('#pj-cv') && /Falta resolver 1 ponto do CAMP Vision antes de publicar/.test(r) && /Contagem de origem igual à de saída/.test(r) && /Só o CAMP Vision resolve/.test(r), 'aceite que trava de verdade: o quadro abre sozinho com "Falta resolver 1 ponto…" e quem resolve: "' + r.slice(0, 200) + '"');
    chk(/falta: Contagem de origem igual à de saída/.test(await txt('#pj-situacao [data-sl="cv"]')), 'a linha do CAMP Vision no cartão diz o que falta');
    chk(/aceite do lote no CAMP Vision/i.test(await txt('#pj-proximo')) && /Contagem de origem/.test(await txt('#pj-proximo')), 'o passo "Publicar" diz por que não dá para publicar (o mesmo aceite): "' + (await txt('#pj-proximo')).slice(0, 220) + '"');
    py(`con.execute("UPDATE projeto SET status_site='no_ar' WHERE codigo='${PJ}'")`);
    await abrir();
    const h = await page.evaluate(() => document.getElementById('pj-cv').textContent.replace(/\s+/g, ' '));
    chk(await page.isHidden('#pj-cv') && !(await page.$('#pj-cv .cv-resumo.falta')) && !/Falta resolver|não pode ser publicado|reprovado/.test(h) && /O projeto já está publicado/.test(h) && /Fica só como registro/.test(h), 'projeto JÁ publicado: nada de "reprovado"/"falta"; uma nota cinza de registro, quadro fechado: "' + h.slice(0, 200) + '"');
    py(`con.execute("UPDATE projeto SET status_site='nao_publicado' WHERE codigo='${PJ}'")`);
    gravarAceite(ACEITE);

    // ---- aviso de quase-duplicata leva à tela Duplicatas ----
    await abrir(); await page.click('#pj-situacao [data-sl-ver="cv"]'); await page.waitForTimeout(300);
    chk(/D40 é quase de D37/.test(await txt('#pj-cv .cv-avisos')) && !!(await page.$('#pj-cv .cv-avisos [data-dupv-abrir]')), 'o aviso "D40 é quase de D37" tem o botão "Conferir em Duplicatas"');
    await page.click('#pj-cv .cv-avisos [data-dupv-abrir]'); await page.waitForTimeout(1200);
    chk(page.url().endsWith('#duplicatas/' + PJ), '"Conferir em Duplicatas" abre #duplicatas/<projeto>: ' + page.url().replace(BASE, ''));

    // ---- celular ----
    await page.setViewportSize({ width: 390, height: 844 }); await abrir();
    chk(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'no celular (390px) não há rolagem lateral');
  } catch (e) { problemas.push('exceção: ' + e.message); linhas.push('FALHA exceção: ' + e.message) }
  chk(!erros.length, 'nenhum erro no console: ' + erros.slice(0, 3).join(' | '));
  chk(!falhas.length, 'nenhuma resposta 4xx/5xx inesperada: ' + falhas.slice(0, 5).join(' | '));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
