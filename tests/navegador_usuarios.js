// UX-13 · Configurações › Usuários no navegador de verdade (Playwright + Chromium).
// Prova: na linha só "Editar" e o menu "⋯"; dentro do menu Foto/Nova senha/Papel e, separado por uma linha, "Desativar" em vermelho;
// Desativar pede confirmação (Cancelar não desativa); "Editar" troca o nome; o aviso de contas genéricas lista as contas sem pessoa e
// destaca a que é admin; a senha temporária vencida aparece na lista e o login com ela é recusado com mensagem clara; sem erro no console.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/usr.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/usr.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8947)
//   CAMP_DB_PATH=/tmp/usr.db CAMP_BASE=http://127.0.0.1:8947 node tests/navegador_usuarios.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8947', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ESPERADO = u => /\/api\/auth\/(eu|login)$|\/favicon\.ico$|\/foto/.test(u);
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error' && !ESPERADO(((m.location() || {}).url || ''))) erros.push(m.text()); });
  page.on('pageerror', e => erros.push('pageerror: ' + e.message));
  const api = (url, opt = {}) => page.evaluate(async ([u, o]) => { const r = await fetch(u, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...o }); return { status: r.status, json: await r.json().catch(() => null) }; }, [url, opt]);
  const linha = nome => page.locator('#usr-body tr').filter({ hasText: nome });
  try {
    await page.goto(BASE + '/');
    await page.fill('#lg-email', 'rafael@camp.arq.br'); await page.fill('#lg-senha', 'senha-bem-longa-123'); await page.press('#lg-senha', 'Enter');
    await page.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    // conta genérica admin (como a "Administração CAMP" de produção) e um convidado com senha temporária gerada há 4 dias
    const g = await api('/api/usuarios', { method: 'POST', body: JSON.stringify({ nome: 'Administração CAMP', email: 'administracao@camp.arq.br', papel: 'admin' }) });
    const cv = await api('/api/usuarios', { method: 'POST', body: JSON.stringify({ nome: 'Pesquisador convidado', email: 'convidado@camp.arq.br', papel: 'leitura' }) });
    chk(g.status === 200 && cv.status === 200, 'cria as contas de teste pela API');
    py(`con.execute("UPDATE usuario SET senha_temporaria_em=datetime('now','-96 hours') WHERE email='convidado@camp.arq.br'")`);
    await page.evaluate(() => { nav('config'); return carregarUsuarios(); });
    await page.waitForFunction(() => /administracao@camp/.test(document.getElementById('usr-body').textContent), null, { timeout: 15000 }); await page.waitForTimeout(400);

    // ---- aviso de contas genéricas, admin em destaque ----
    const av = page.locator('#usr-genericas');
    chk(await av.isVisible(), 'aviso de contas genéricas aparece na tela de Usuários');
    const avt = (await av.textContent()).replace(/\s+/g, ' ');
    chk(/Administração CAMP/.test(avt) && /Pesquisador convidado/.test(avt) && !/Rafael\b/.test(avt.replace(/rafael@/g, '')), 'lista as contas sem pessoa (Administração CAMP, Pesquisador convidado) e não a conta do Rafael: "' + avt.slice(0, 160) + '"');
    chk(/1 é admin/.test(avt) && (await av.locator('li.usr-gen-adm', { hasText: 'Administração CAMP' }).count()) === 1, 'a genérica com papel admin vem destacada ("1 é admin")');

    // ---- ações da linha: Editar + ⋯; Desativar só dentro do menu, separado e em vermelho ----
    const L = linha('administracao@camp.arq.br');
    const visiveis = await L.locator('.usr-acoes > button.btn:visible').allTextContents();
    chk(JSON.stringify(visiveis) === '["Editar"]', 'na linha, fora do menu, só "Editar" (antes: Foto · Nova senha · Papel · Desativar lado a lado): ' + JSON.stringify(visiveis));
    chk(!(await L.locator('button:has-text("Desativar")').isVisible()), 'Desativar não aparece com o menu fechado');
    await L.locator('details.usr-menu > summary').click();
    const itens = await L.locator('.mais-lista > *').evaluateAll(els => els.map(e => e.tagName === 'HR' ? '—' : e.textContent.trim()));
    chk(JSON.stringify(itens) === JSON.stringify(['Foto', 'Nova senha', 'Papel', '—', 'Desativar']), 'menu ⋯: Foto, Nova senha, Papel e, depois de uma linha, Desativar: ' + JSON.stringify(itens));
    const des = L.locator('.mais-lista button:has-text("Desativar")');
    chk(await des.evaluate(b => b.classList.contains('perigo-txt') && getComputedStyle(b).color !== getComputedStyle(b.previousElementSibling.previousElementSibling).color), 'Desativar em vermelho (perigo-txt)');
    await des.click();
    await page.waitForSelector('#conf-ov .conf-box.perigo', { timeout: 5000 });
    chk(/Desativar este usuário\?/.test(await page.textContent('#conf-ov')) && /Administração CAMP/.test(await page.textContent('#conf-ov')), 'Desativar pede confirmação dizendo quem');
    await page.click('#conf-ov [data-conf="nao"]'); await page.waitForTimeout(300);
    let us = (await api('/api/usuarios')).json;
    chk(us.find(x => x.email === 'administracao@camp.arq.br').ativo === 1, 'Cancelar não desativa');

    // ---- Editar troca o nome ----
    await linha('convidado@camp.arq.br').locator('button[data-usr-editar]').click();
    await page.waitForSelector('#conf-ov #conf-campo', { timeout: 5000 });
    await page.fill('#conf-campo', 'Joana Pesquisadora Silva'); await page.click('#conf-ov [data-conf="sim"]');
    await page.waitForFunction(() => /Joana Pesquisadora Silva/.test(document.getElementById('usr-body').textContent), null, { timeout: 5000 });
    us = (await api('/api/usuarios')).json;
    chk(us.find(x => x.email === 'convidado@camp.arq.br').nome === 'Joana Pesquisadora Silva', 'Editar salva o novo nome');

    // ---- senha temporária vencida: na lista e no login ----
    chk(/senha temporária vencida/.test(await linha('convidado@camp.arq.br').textContent()), 'a lista mostra "senha temporária vencida"');
    const p2 = await (await browser.newContext()).newPage();
    await p2.goto(BASE + '/');
    await p2.fill('#lg-email', 'convidado@camp.arq.br'); await p2.fill('#lg-senha', cv.json.senha_temporaria); await p2.press('#lg-senha', 'Enter');
    await p2.waitForFunction(() => (document.getElementById('lg-err').textContent || '').length > 0, null, { timeout: 8000 });
    const msg = await p2.textContent('#lg-err');
    chk(/venceu/.test(msg) && /nova senha/i.test(msg), 'login com a senha temporária vencida é recusado com mensagem clara: "' + msg + '"');
    chk(erros.length === 0, 'nenhum erro no console' + (erros.length ? ': ' + erros.slice(0, 3).join(' | ') : ''));
  } catch (e) { chk(false, 'erro no roteiro: ' + e.message); }
  await browser.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})();
