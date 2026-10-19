// Tela "Duplicatas" do projeto no navegador de verdade (Playwright + Chromium), depois de "teria como checar melhor quem é duplicata?
// tá complexo quando tem 50 folhas lá e 25 são duplicatas" (19/10).
// Prova: o botão "Duplicatas (n)" da página do projeto abre #duplicatas/<projeto>; cada grupo mostra a folha que vai ao site e as
// cópias lado a lado, com imagem que abre grande em outra aba e o porquê do CAMP Vision; "12 de 25 conferidas" anda a cada decisão;
// Confirmar, atalhos (J/K, C, N; o C não abre Configurações), "Publicar esta em vez da outra" (com confirmação), "Não é duplicata",
// "Confirmar todos os grupos que eu não mexi" (com confirmação, sem tocar nos que a pessoa mexeu), filtros, sugestões
// ("Talvez sejam duplicatas"), leitura só vê; no celular não há rolagem lateral; nenhum erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/dupv.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/dupv.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8951)
//   CAMP_DB_PATH=/tmp/dupv.db CAMP_BASE=http://127.0.0.1:8951 node tests/navegador_duplicatas.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8951', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const D = n => 'F023-P0011-1959-S01-D' + String(n).padStart(5, '0');
const col = (n, k) => py(`print(con.execute("SELECT ${k} FROM item WHERE codigo=?", ("${D(n)}",)).fetchone()[0])`);

// Residência Riviera (35 folhas): 6 grupos com 7 cópias (D11 com o problema do CAMP Vision "quase de D00010"); D20 e D21 parecem iguais
// (mesmo tipo, folha e título) e ninguém marcou: vão para "Talvez sejam duplicatas".
py(`
D = lambda n: 'F023-P0011-1959-S01-D%05d' % n
for cp, og, tp in ((11, 10, 'exata'), (12, 10, 'perceptual'), (14, 13, 'mesma_folha'), (16, 15, 'exata'), (18, 17, 'exata'), (23, 22, 'exata'), (25, 24, 'perceptual')):
    con.execute("UPDATE item SET duplicata_de=?, tipo_duplicata=? WHERE codigo=?", (D(og), tp, D(cp)))
con.execute("INSERT INTO erro (gravidade,categoria,origem,codigo,descricao) VALUES ('corrigir','duplicata','campvision',?,'quase de D00010 — só a única publica')", (D(11),))
for n in (20, 21):
    con.execute("UPDATE item SET tipo_documento='Corte', folha='20/35', titulo='Corte A' WHERE codigo=?", (D(n),))
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [], falhas = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() >= 400 && !ESPERADO(r.url())) falhas.push(r.status() + ' ' + r.url().replace(BASE, '')); });
  const grupo = c => `#dupv-grupos .dupv-grupo[data-dupv-grupo="${D(c)}"]`;
  const cont = async txt => { await page.waitForFunction(t => ((document.getElementById('dupv-cont') || {}).textContent || '') === t, txt, { timeout: 10000 }); return true; };
  const login = async (pg, em, s) => { await pg.goto(BASE + '/'); await pg.fill('#lg-email', em); await pg.fill('#lg-senha', s); await pg.press('#lg-senha', 'Enter'); await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }); };
  try {
    await login(page, 'rafael@camp.arq.br', 'senha-bem-longa-123');
    // ---- da página do projeto para a tela ----
    await page.evaluate(() => nav('projeto/F023-P0011'));
    await page.waitForSelector('#pd [data-dupv-abrir="F023-P0011"]', { timeout: 15000 });
    chk(/Duplicatas \(7\)/.test(await page.textContent('#pd .dethdr [data-dupv-abrir]')), 'página do projeto: botão "Duplicatas (7)" no topo');
    await page.click('#pd .dethdr [data-dupv-abrir]');
    await page.waitForFunction(() => location.hash === '#duplicatas/F023-P0011', null, { timeout: 8000 });
    await page.waitForSelector(grupo(10), { timeout: 10000 });
    chk(await cont('0 de 7 conferidas') && (await page.locator('#dupv-grupos .dupv-grupo').count()) === 6, 'abre #duplicatas/F023-P0011 com "0 de 7 conferidas" e os 6 grupos a conferir');
    chk(/Duplicatas/.test(await page.textContent('#gcrumb')) && /F023-P0011/.test(await page.textContent('#gcrumb')), 'o caminho no topo mostra o projeto e "Duplicatas"');
    const g1 = page.locator(grupo(10));
    chk((await g1.locator('figure.dupv-folha').count()) === 3 && /vai ao site/.test(await g1.locator('figure.publica').textContent()) && /D00010/.test(await g1.locator('figure.publica').textContent()),
      'grupo lado a lado: a folha que vai ao site (D00010) e as 2 cópias');
    const a11 = g1.locator(`figure[data-dupv-copia="${D(11)}"] a.dupv-img`);
    chk((await a11.getAttribute('target')) === '_blank' && /exemplo\.test\/img\/F023-P0011-1959-S01-D00011\.jpg/.test(await a11.getAttribute('href')) && (await a11.locator('img').count()) === 1, 'a imagem da cópia abre grande em outra aba (o arquivo do documento)');
    const t11 = await g1.locator(`figure[data-dupv-copia="${D(11)}"]`).textContent();
    chk(/Por quê: o CAMP Vision achou a imagem idêntica/.test(t11) && /quase de D00010/.test(t11), 'o porquê do CAMP Vision aparece na cópia (tipo e problema registrado)');

    // ---- Confirmar ----
    await g1.locator('[data-dupv-confirmar]').click();
    chk(await cont('2 de 7 conferidas'), '"Confirmar" o grupo: o progresso vai para "2 de 7 conferidas"');
    chk(!(await page.$(grupo(10))) && (await page.locator('#dupv-grupos .dupv-grupo').count()) === 5, '... e o grupo sai de "A conferir"');
    chk(col(11, 'duplicata_conferida_de') === D(10) && col(12, 'duplicata_conferida_por') === 'rafael@camp.arq.br', 'no servidor: as 2 cópias conferidas, com quem conferiu');

    // ---- atalhos: J / C / N ----
    await page.locator(grupo(13) + ' .ph').click();
    await page.keyboard.press('j');
    chk(await page.evaluate(id => document.querySelector(`.dupv-grupo[data-dupv-grupo="${id}"]`).classList.contains('foco'), D(15)), 'J leva ao grupo seguinte');
    await page.keyboard.press('c');
    chk(await cont('3 de 7 conferidas') && (await page.evaluate(() => location.hash)) === '#duplicatas/F023-P0011', 'C confirma o grupo em foco (e não abre Configurações)');
    chk(col(16, 'duplicata_conferida_de') === D(15), 'no servidor: D16 conferida pelo atalho');
    await page.keyboard.press('k'); await page.keyboard.press('j');
    chk(await page.evaluate(id => document.querySelector(`.dupv-grupo[data-dupv-grupo="${id}"]`).classList.contains('foco'), D(17)), 'K volta e J avança (foco no grupo de D00017)');
    await page.keyboard.press('n');
    chk(await cont('3 de 6 conferidas') && col(18, 'duplicata_de') === 'None', 'N: "Não é duplicata" na única cópia do grupo (D00018 volta a poder ir ao site)');

    // ---- Publicar esta em vez da outra ----
    await page.click(`${grupo(13)} [data-dupv-trocar="${D(14)}"]`);
    await page.waitForSelector('#conf-ov', { timeout: 5000 });
    chk(/Publicar esta folha em vez da outra/.test(await page.textContent('#conf-ov')), '"Publicar esta em vez da outra" pede confirmação');
    await page.click('#conf-ov [data-conf="sim"]');
    chk(await cont('4 de 6 conferidas') && col(13, 'duplicata_de') === D(14) && col(14, 'duplicata_de') === 'None', 'trocou: D00014 vai ao site e D00013 virou cópia conferida');

    // ---- Confirmar todos os que eu não mexi ----
    const bt = page.locator('[data-dupv-todos]');
    chk(/Confirmar todos os grupos que eu não mexi \(2\)/.test(await bt.textContent()), 'botão "Confirmar todos os grupos que eu não mexi (2)" (o grupo trocado não entra)');
    await bt.click(); await page.waitForSelector('#conf-ov', { timeout: 5000 });
    chk(/Confirmar 2 grupos/.test(await page.textContent('#conf-ov')), '... com confirmação antes');
    await page.click('#conf-ov [data-conf="sim"]');
    chk(await cont('6 de 6 conferidas') && /Todas as duplicatas foram conferidas/.test(await page.textContent('#dupv-grupos')), 'confirmados: "6 de 6 conferidas" e a lista "A conferir" fica vazia');
    await page.click('[data-dupv-filtro="conferidos"]');
    chk((await page.locator('#dupv-grupos .dupv-grupo').count()) === 5 && (await page.locator('#dupv-grupos .tag.g', { hasText: 'conferido' }).count()) === 5, 'filtro "Conferidos": os 5 grupos, cada um com "conferido"');

    // ---- sugestões ----
    const sug = page.locator('.dupv-sugs');
    chk(/Talvez sejam duplicatas/.test(await sug.textContent()) && /D00020/.test(await sug.textContent()) && /D00021/.test(await sug.textContent()), '"Talvez sejam duplicatas" sugere D00020 e D00021 (mesmo tipo, folha e título)');
    await sug.locator(`[data-dupv-sug-marcar="${D(20)}"]`).click();
    chk(await cont('7 de 7 conferidas') && col(21, 'duplicata_de') === D(20) && !(await page.$('.dupv-sugs')), 'aceitar a sugestão: D00021 vira cópia conferida de D00020 e a sugestão some');

    // ---- voltar ao projeto ----
    await page.click('[data-dupv-voltar]');
    await page.waitForFunction(() => location.hash === '#projeto/F023-P0011', null, { timeout: 8000 });
    chk(true, '"Voltar ao projeto" leva à página do projeto');

    // ---- leitura: só vê ----
    const ctxLe = await browser.newContext({ viewport: { width: 1366, height: 900 } }); const le = await ctxLe.newPage();
    le.on('pageerror', e => erros.push('pageerror (leitura): ' + e.message));
    await login(le, 'leitor@camp.arq.br', 'senha-leitor-1234');
    await le.evaluate(() => nav('duplicatas/F023-P0011')); await le.waitForSelector('#dupv-cont', { timeout: 10000 });
    await le.click('[data-dupv-filtro="todos"]');
    chk(!(await le.$('[data-dupv-confirmar],[data-dupv-trocar],[data-dupv-nao],[data-dupv-todos]')) && /Só operador, admin e master decidem/.test(await le.textContent('#dupv')), 'leitura vê os grupos, sem botões de decidir');
    await ctxLe.close();

    // ---- celular ----
    await page.evaluate(() => nav('duplicatas/F023-P0011')); await page.waitForSelector('#dupv-cont', { timeout: 10000 });
    await page.click('[data-dupv-filtro="todos"]');
    await page.setViewportSize({ width: 390, height: 844 }); await page.waitForTimeout(600);
    const lateral = await page.evaluate(() => mainEl.scrollWidth - mainEl.clientWidth);
    chk(lateral <= 1, 'no celular os grupos cabem na largura (sem rolagem lateral: ' + lateral + 'px)');
  } catch (e) { chk(false, 'exceção: ' + e.message.split('\n')[0]); }
  chk(!erros.length, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 5).join(' | ') : ''));
  chk(!falhas.length, 'nenhuma resposta de erro do painel' + (falhas.length ? ': ' + falhas.slice(0, 5).join(' | ') : ''));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
