// "Completar a ficha" em etapas e aberta SOZINHA ao terminar a conferência (Playwright, Chromium de verdade). 11/11/2026, pedidos do Rafael:
// "precisamos gamificar isso… em etapas… com as respostas mais frequentes primeiro" e "quando terminamos de aprovar as folhas, preencher elas,
// já pode cair no quiz automaticamente".
// Uso (servidor PRÓPRIO numa porta 8870-8879, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/ficha.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/ficha.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8872)
//   CAMP_BASE=http://127.0.0.1:8872 node tests/ficha_automatica_ui.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8872', CODE = process.env.CAMP_PROJETO || 'F023-P0011';
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg) => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg); if (!ok) problemas.push(msg); };
const aberta = p => p.evaluate(() => mainEl.classList.contains('with-drawer') && !!document.getElementById('ficha'));
const fimDaConferencia = p => p.evaluate(c => { const d = document.createElement('div'); d.innerHTML = fimPassoHTML(c); document.body.appendChild(d); fimConferenciaPasso(c) }, CODE);
(async () => {
  const browser = await chromium.launch({ executablePath: fs.existsSync(CHROME) ? CHROME : undefined });
  const entrar = async (email, senha) => {
    const p = await browser.newPage({ viewport: { width: 1300, height: 900 } }); const erros = []; p.on('pageerror', e => erros.push(e.message));
    await p.goto(BASE + '/'); await p.evaluate(async ([e, s]) => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: e, senha: s }) }), [email, senha]);
    await p.goto(BASE + '/#projeto/' + CODE); await p.reload(); await p.waitForTimeout(4500); return { p, erros };
  };
  const { p, erros } = await entrar('rafael@camp.arq.br', 'senha-bem-longa-123');
  chk(await p.locator('[data-ficha-abrir]').count() >= 1, 'Objetivos do projeto mostram "Completar a ficha: N perguntas rápidas"');
  await fimDaConferencia(p); await p.waitForTimeout(3500);
  chk(await aberta(p), 'ao conferir a última folha, a ficha abre sozinha');
  if (!(await aberta(p))) { await browser.close(); console.log(linhas.join('\n')); console.log(`\n=== FICHA AUTOMÁTICA: ${problemas.length} problema(s) ===`); process.exit(1) }
  chk(/Folhas conferidas/.test(await p.locator('.fc-intro').textContent().catch(() => '')), 'com a frase "Folhas conferidas. Agora a ficha do projeto…"');
  chk(await p.locator('[data-ficha-op]').count() >= 2, 'respostas em botões (as mais usadas primeiro)');
  await p.locator('[data-ficha-op]').first().click(); await p.locator('[data-ficha-salvar]').click(); await p.waitForTimeout(1200);
  const et = await p.evaluate(async c => (await (await fetch(`/api/projetos/${c}/ficha-etapas`)).json()).etapas[0], CODE);
  chk(et.feito && et.atual.length >= 1, 'a resposta grava na hora (tipo da obra preenchido): ' + JSON.stringify(et.atual));
  for (let k = 0; k < 8 && await p.locator('[data-ficha-ir="1"]').count(); k++) { await p.locator('[data-ficha-ir="1"]').click(); await p.waitForTimeout(250) }
  chk(await p.locator('[data-ficha-proximo]').count() === 1, 'no fim, "Ver o próximo passo"');
  await p.locator('[data-ficha-proximo]').click(); await p.waitForTimeout(2500);
  chk(!(await aberta(p)) && (await p.evaluate(() => location.hash)) === '#projeto/' + CODE, '"Ver o próximo passo" fecha a ficha e fica na página do projeto (Aprovar/Publicar)');
  await fimDaConferencia(p); await p.waitForTimeout(3000);
  chk(!(await aberta(p)), 'no mesmo projeto, não abre de novo sozinha');
  chk(!erros.length, 'sem erro de JavaScript (admin): ' + erros.slice(0, 3).join(' | '));
  const o = await entrar('operador@camp.arq.br', 'senha-operador-123');
  await fimDaConferencia(o.p); await o.p.waitForTimeout(3500);
  chk(!(await aberta(o.p)), 'operador não grava a ficha: ela não abre sozinha para ele');
  chk(!o.erros.length, 'sem erro de JavaScript (operador)');
  await browser.close();
  console.log(linhas.join('\n')); console.log(`\n=== FICHA AUTOMÁTICA: ${problemas.length} problema(s) ===`); process.exit(problemas.length ? 1 : 0);
})();
