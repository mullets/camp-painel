// UX-33 no navegador: números em pt-BR em toda a interface (vírgula decimal, ponto de milhar).
// Prova: os helpers únicos (fmtNum, fmtUSD, fmtTamanho, fmtBytes, fmtPct) dão "US$ 4,27", "US$ 0,0179", "30,7 GB", "1.548,1 MB";
// a Qualidade do CAMP Vision mostra o custo do lote como "US$ 4,27" (antes "US$ 4.269") e o custo por folha com vírgula; o painel do
// Backup e a quarentena usam vírgula; e nenhuma das telas principais (Precisa de você, Material novo, Projetos, Máquinas, Qualidade)
// mostra número com ponto decimal junto de unidade, porcentagem ou moeda, nem "1548,1 MB" sem o ponto de milhar.
// Uso (servidor PRÓPRIO numa porta exclusiva):
//   CAMP_DB_PATH=/tmp/ux33/x.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ux33/x.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8949)
//   CAMP_DB_PATH=/tmp/ux33/x.db CAMP_BASE=http://127.0.0.1:8949 node tests/navegador_ux33_numeros.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8949', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// o lote com mais folhas ganha o bloco "execucao" do CAMP Vision com custo US$ 4.269 (o caso do card)
const nFolhas = +py(`
lid, n = con.execute("SELECT lote_id, COUNT(*) FROM item WHERE lote_id IS NOT NULL GROUP BY lote_id ORDER BY 2 DESC LIMIT 1").fetchone()
con.execute("UPDATE lista_processamento SET execucao_json=? WHERE id=?", (json.dumps({"versao_cv2": "2.4.1", "modelo": "x", "custo_usd": 4.269, "tempo_s": 812.4, "chamadas": 12}), lid))
print(n)`);

// número com PONTO decimal junto de moeda, unidade ou porcentagem; e milhar sem ponto antes de MB/GB
// (US$ sempre tem vírgula: fmtUSD dá no mínimo 2 casas; "11.880 GB" é milhar e vale; "30.73 GB", "4.269" sem vírgula, "1548,1 MB" não)
const RUIM = /US\$\s*\d[\d.]*(?![\d.]*,)|\b\d+\.(?:\d{1,2}|\d{4,})(?!\d)\s*(?:%|GB|MB|KB|TB|s\b)|\b\d{4,}(?:,\d+)?\s*(?:GB|MB)\b/;
const achar = t => { const m = t.match(new RegExp('.{0,40}(?:' + RUIM.source + ').{0,20}')); return m ? m[0] : null; };

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$|exemplo\.test|\/previa\?t=/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });

    // ---- helpers únicos ----
    const h = await page.evaluate(() => ({ t: fmtUSD(4.269), f: fmtUSD(0.0179, 4), gb: fmtTamanho(30.73, 'GB'), mb: fmtTamanho(1548.1, 'MB'), b: fmtBytes(1623302553),
      n: fmtN(1234567), p: fmtPct(87.5), z: fmtTamanho(0, 'GB'), nada: fmtUSD(null), au: tamanhoAu(1623302553) })).catch(e => ({ erro: e.message }));
    chk(h.t === 'US$ 4,27' && h.f === 'US$ 0,0179', 'moeda: "US$ 4,27" e "US$ 0,0179": ' + JSON.stringify([h.t, h.f]));
    chk(h.gb === '30,7 GB' && h.mb === '1.548,1 MB' && h.b === '1,5 GB' && h.au === '1.548,1 MB' && h.z === '0 GB', 'tamanhos: "30,7 GB", "1.548,1 MB": ' + JSON.stringify([h.gb, h.mb, h.b, h.au, h.z]));
    chk(h.n === '1.234.567' && h.p === '87,5%' && h.nada === '—', 'número, porcentagem e vazio: ' + JSON.stringify([h.n, h.p, h.nada]));

    // ---- Qualidade do CAMP Vision: o custo do card ----
    await page.evaluate(() => nav('qualidade'));
    await page.waitForFunction(() => { const c = document.getElementById('qc-corpo'); return c && /US\$/.test(c.innerText); }, null, { timeout: 15000 });
    const q = await page.innerText('#qc-corpo');
    chk(/US\$ 4,27\b/.test(q) && !/US\$ 4\.269/.test(q), 'Qualidade: custo do lote "US$ 4,27" (não "US$ 4.269")');
    const porFolha = 'US$ ' + (4.269 / nFolhas).toFixed(4).replace('.', ',').replace(/0+$/, '');
    chk(q.includes(porFolha), `Qualidade: custo por folha com vírgula (${porFolha}, ${nFolhas} folhas)`);
    chk(!achar(q), 'Qualidade: nenhum número com ponto decimal: ' + achar(q));

    // ---- Backup e quarentena (os "30.73 GB" e "1548.1 MB" do card) ----
    const bk = await page.evaluate(() => { const d = document.createElement('div'); d.innerHTML = painelBackup({ existe: true, ok: true, em: '2026-10-27T03:30:00', idade_horas: 2, quantidade: 3, ocupa_mb: 1548.1, livre_gb: 30.73 }) + quarentenaHTML({ arquivos: 2, gb: 12.25 }); return d.innerText; });
    chk(/3 \(1\.548,1 MB\)/.test(bk) && /30,7 GB/.test(bk) && /12,3 GB/.test(bk) && !achar(bk), 'Backup e quarentena em pt-BR: ' + bk.replace(/\s+/g, ' ').slice(0, 200));

    // ---- as telas principais: nada de ponto decimal ----
    for (const [rota, sel] of [['painel', '#v-painel'], ['filas', '#v-filas'], ['projetos', '#v-projetos'], ['estacoes', '#v-estacoes']]) {
      await page.evaluate(r => nav(r), rota); await page.waitForTimeout(2500);
      const t = await page.evaluate(s => (document.querySelector(s) || document.body).innerText, sel);
      chk(t.length > 50 && !achar(t), `${rota}: nenhum número com ponto decimal` + (achar(t) ? ': "' + achar(t) + '"' : ''));
    }
    chk(!erros.length, 'nenhum erro no console: ' + erros.join(' | '));
  } catch (e) { chk(false, 'exceção: ' + (e.stack || e.message)); }
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
