// UX-34 · Histórico de ações (auditoria) no navegador de verdade (Playwright + Chromium).
// Prova: o filtro "quem" vem agrupado em Pessoas · Máquinas · Sistema, com nomes (pessoa pelo nome, estação pelo nome, rotinas),
// sem nenhum IP, "estacao@…", "migração 140" ou nome de script; o filtro "o quê" em português com acento (decisão, usuário, LGPD);
// escolher uma máquina filtra a lista; sem erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/hist.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/hist.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8947)
//   CAMP_DB_PATH=/tmp/hist.db CAMP_BASE=http://127.0.0.1:8947 node tests/navegador_historico.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8947', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

// atores como os de produção: e-mail, IP, estacao@IP, operador na estação, migração, script; entidades sem acento
py(`
con.execute("UPDATE configuracao SET valor='192.168.15.43' WHERE chave='estacao.contex1.ip'")
for ent, ator, tipo in (("decisao","rafael@camp.arq.br","decidida"),("usuario","192.168.15.46","login_falhou"),("item","estacao@192.168.15.43","estacao_enviou"),
                        ("projeto","Rafael (estacao@192.168.15.43)","reservado"),("sistema","migração 140","migrado"),("item","script marcar_giro_publicado","giro_marcado"),
                        ("lgpd","sistema","lgpd_retencao")):
    con.execute("INSERT INTO evento (entidade, codigo, tipo, ator, detalhe) VALUES (?,?,?,?,'{}')", (ent, 'F023-P0011', tipo, ator))
`);

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/eu$|\/favicon\.ico$/.test(u);
  const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  try {
    await page.goto(BASE + '/');
    await page.evaluate(() => { try { localStorage.clear(); } catch (_) {} });
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await page.evaluate(() => nav('auditoria'));
    await page.waitForFunction(() => document.querySelectorAll('#au-ator option').length > 1, null, { timeout: 15000 });
    const grupos = await page.$$eval('#au-ator optgroup', gs => gs.map(g => g.label));
    chk(JSON.stringify(grupos) === JSON.stringify(['Pessoas', 'Máquinas', 'Sistema']), '"quem" agrupado em Pessoas · Máquinas · Sistema: ' + JSON.stringify(grupos));
    const opcoes = await page.$$eval('#au-ator option', os => os.map(o => o.textContent));
    chk(!opcoes.some(t => /\d+\.\d+\.\d+\.\d+|estacao@|script|marcar_giro|migração \d/.test(t)), 'nenhum IP, estacao@, script ou "migração 140" nas opções: ' + JSON.stringify(opcoes));
    const porGrupo = await page.$$eval('#au-ator optgroup', gs => Object.fromEntries(gs.map(g => [g.label, [...g.querySelectorAll('option')].map(o => o.textContent.replace(/ \(\d+\)$/, ''))])));
    chk((porGrupo['Pessoas'] || []).includes('Rafael') && (porGrupo['Máquinas'] || []).includes('Estação Contex 1') && (porGrupo['Máquinas'] || []).includes('Estação Universal 2')
        && (porGrupo['Sistema'] || []).includes('Migrações do banco') && (porGrupo['Sistema'] || []).includes('Scripts de manutenção'), 'pessoa pelo nome, estações pelo nome, migrações e scripts como Sistema: ' + JSON.stringify(porGrupo));
    const ents = await page.$$eval('#au-ent option', os => os.map(o => o.textContent));
    chk(ents.includes('decisão') && ents.includes('usuário') && ents.includes('LGPD') && !ents.some(t => /^(decisao|usuario|lgpd)$/.test(t)), '"o quê" com acento (decisão, usuário, LGPD): ' + JSON.stringify(ents));
    const v = await page.$eval('#au-ator', s => [...s.options].find(o => /^Estação Contex 1/.test(o.textContent)).value);
    await page.selectOption('#au-ator', v);
    await page.waitForFunction(() => /2 de 2/.test(document.getElementById('au-cnt').textContent), null, { timeout: 8000 }).catch(() => {});
    chk(/^2 de 2$/.test((await page.textContent('#au-cnt')).trim()), 'escolher "Estação Contex 1" traz os 2 eventos dela: ' + (await page.textContent('#au-cnt')));
    chk(erros.length === 0, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  } catch (e) { chk(false, 'erro no roteiro: ' + e.message); }
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
