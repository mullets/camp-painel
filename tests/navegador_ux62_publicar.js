// UX-62 (P1): o cartão "Site" do projeto dizia "Não publicado — pronto: o painel autoriza e envia ao site" e mostrava "Publicar"
// com 0 de 49 folhas conferidas (F001-P0033 Teatro Piracicaba). Playwright + Chromium de verdade, servidor PRÓPRIO (porta 8971).
//  A) projeto não publicado, lote "processando" com 6 folhas a conferir + 2 antigas sem lote: o cartão diz "falta conferir 6 folhas",
//     não diz "pronto", não tem Publicar ativo; o botão é "Conferir as folhas".
//  B) tudo conferido, lote ainda sem aprovar: continua "pronto" com Publicar (o Publicar aprova junto, CAMP-148).
// Uso:
//   CAMP_DB_PATH=/tmp/ux62.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux62.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8971)
//   CAMP_DB_PATH=/tmp/ux62.db CAMP_BASE=http://127.0.0.1:8971 node tests/navegador_ux62_publicar.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8971', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const A = 'F003-P9621', B = 'F003-P9622';
py(`
con.execute("UPDATE configuracao SET valor='0' WHERE chave='publicacao.exige_direitos'")
for cod, n, etapa, pend, conf, leg in (('${A}', 9621, 'processando', 6, 0, 2), ('${B}', 9622, 'revisao', 0, 3, 0)):
    con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F003', ?)", (n,))
    con.execute("INSERT INTO projeto (codigo, fundo_codigo, numero, titulo, ano, cidade, autorizado_site) VALUES (?, 'F003', ?, 'Teatro Municipal', 1975, 'Piracicaba', 1)", (cod, n))
    lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES (?, ?, '/nao/existe/ux62', ?)", (cod + ' - Teatro', cod, etapa)).lastrowid
    k = 0
    for rev, q, lote in (('pendente', pend, lid), ('conferida', conf, lid), ('conferida', leg, None)):
        for _ in range(q):
            k += 1
            con.execute("INSERT INTO item (codigo, projeto_codigo, serie_codigo, sequencial, titulo, tipo_documento, origem, lote_id, revisao) VALUES (?,?,?,?,?,?,'campvision',?,?)",
                        ('%s-1975-S01-D%05d' % (cod, k), cod, 'S01', k, 'Planta %d' % k, 'Planta', lote, rev))
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|\/previa|\/miniatura|folhas-qnap\/arquivo|exemplo\.test/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO((m.location() || {}).url || '')) erros.push(m.text() + ' @' + ((m.location() || {}).url || '')); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  const abrir = async c => { await page.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, c);
    await page.waitForFunction(c => window.PUB_G && PUB_G[c] && document.querySelector('#pj-cards .pjc[data-pjc="site"]') && !/…/.test(document.querySelector('#pj-cards .pjc[data-pjc="site"] .pjc-v').textContent), c, { timeout: 15000 }); await page.waitForTimeout(1200) };
  const cartao = () => page.$eval('#pj-cards .pjc[data-pjc="site"]', c => c.innerText.replace(/\s+/g, ' ').trim());
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    for (const sel of ['.ajuda-caixa [data-ajuda-fechar]', '[data-faixa-fechar]']) { const b = await page.$(sel); if (b && await b.isVisible()) { await b.click(); await page.waitForTimeout(300) } }

    await abrir(A);
    const sa = await cartao();
    chk(/Não publicado/.test(sa) && /falta conferir 6 folhas/.test(sa) && !/pronto/.test(sa), '(A) cartão Site: "falta conferir 6 folhas", sem "pronto": "' + sa + '"');
    const pubAtivo = await page.$('#pj-cards .pjc[data-pjc="site"] [data-pjc-publicar]:not([aria-disabled="true"])');
    chk(!pubAtivo, '(A) sem botão Publicar ativo no cartão Site');
    const conf = await page.$('#pj-cards .pjc[data-pjc="site"] [data-pp-cond="revisao"]');
    chk(!!conf && /Conferir as folhas/.test(await conf.textContent()), '(A) o botão do cartão leva a conferir as folhas');
    const st = await page.evaluate(c => fetch('/api/projetos/' + c + '/publicar-tudo', { method: 'POST', headers: { 'Content-Type': 'application/json' } }).then(r => r.status), A);
    chk(st === 409, '(A) o servidor recusa publicar com 409 (' + st + ')');

    await abrir(B);
    const sb = await cartao();
    chk(/pronto/.test(sb) && !!(await page.$('#pj-cards .pjc[data-pjc="site"] [data-pjc-publicar]:not([aria-disabled="true"])')), '(B) tudo conferido e o lote sem aprovar: continua "pronto" com Publicar (aprova junto): "' + sb + '"');
  } catch (e) { problemas.push('exceção: ' + e.message); linhas.push('FALHA exceção: ' + e.message) }
  chk(!erros.filter(x => !/409/.test(x)).length, 'nenhum erro no console: ' + erros.slice(0, 3).join(' | '));
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
