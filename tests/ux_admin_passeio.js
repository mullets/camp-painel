// Passeio de auditoria (não é teste de CI): visita as telas da Administração e o "casco" em 3 larguras e 3 papéis,
// grava prints e um JSON com erros de JS, rolagem lateral, elementos que vazam, botões desalinhados.
// Uso: CAMP_BASE=http://127.0.0.1:9171 OUT=/caminho node tests/ux_admin_passeio.js
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9171';
const OUT = process.env.OUT || '/dev/shm/uxadm_out';
fs.mkdirSync(OUT, { recursive: true });
const USERS = { master: ['rafael@camp.arq.br', 'senha-bem-longa-123'], operador: ['operador@camp.arq.br', 'senha-operador-123'], leitura: ['leitor@camp.arq.br', 'senha-leitor-1234'] };
const ROTAS = (process.env.ROTAS || 'painel,estacoes,financeiro/geral,financeiro/receitas,financeiro/despesas,financeiro/fixas,financeiro/dre,financeiro/conferencia,financeiro/projeto,projetos_camp,emails,config,auditoria,qualidade,caminho,glossario').split(',');
const LARG = (process.env.LARG || '1440x900,2000x1100,390x844').split(',').map(s => s.split('x').map(Number));
const PAPEIS = (process.env.PAPEIS || 'master,operador').split(',');
const res = [];
(async () => {
  const br = await chromium.launch();
  for (const papel of PAPEIS) for (const [w, h] of LARG) {
    const ctx = await br.newContext({ viewport: { width: w, height: h } });
    const pg = await ctx.newPage();
    let erros = [];
    pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
    pg.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|status of 4\d\d|status of 5\d\d/.test(m.text())) erros.push('console: ' + m.text().slice(0, 200)); });
    pg.on('dialog', d => d.dismiss().catch(() => {}));
    await pg.route(/mercadopago|camp\.arq\.br|sender\.net/, r => r.abort());
    await pg.goto(BASE + '/');
    await pg.fill('#lg-email', USERS[papel][0]); await pg.fill('#lg-senha', USERS[papel][1]); await pg.press('#lg-senha', 'Enter');
    await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 }).catch(() => {});
    for (const r of ROTAS) {
      erros = [];
      await pg.goto(BASE + '/#' + r).catch(() => {});
      await pg.waitForTimeout(r.startsWith('financeiro') ? 2500 : 1800);
      await pg.evaluate(() => document.querySelectorAll('.toast,#toast').forEach(t => t.style.visibility = 'hidden')).catch(() => {});
      const info = await pg.evaluate(() => {
        const vw = document.documentElement.clientWidth;
        const sc = document.scrollingElement;
        const main = document.querySelector('.main');
        const vis = [...document.querySelectorAll('section.content')].find(s => s.offsetParent || getComputedStyle(s).display !== 'none' && s.classList.contains('on'));
        const vaza = [];
        document.querySelectorAll('.main *').forEach(el => {
          if (!el.offsetParent || vaza.length > 12) return;
          const r = el.getBoundingClientRect();
          if (r.width > 0 && r.right > vw + 2 && !el.closest('[style*="overflow"],.tbl-wrap,.scroll-x,pre,table')) vaza.push((el.id ? '#' + el.id : el.tagName.toLowerCase() + '.' + [...el.classList].slice(0, 2).join('.')) + ' right=' + Math.round(r.right));
        });
        const sem = [...document.querySelectorAll('.main button:not([disabled])')].filter(b => b.offsetParent && !b.textContent.trim() && !b.getAttribute('aria-label') && !b.title).length;
        const emoji = (document.querySelector('.main')?.innerText.match(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu) || []).length;
        return { hscroll: sc.scrollWidth > vw + 1 || (main && main.scrollWidth > main.clientWidth + 1), vw, sw: sc.scrollWidth, mainsw: main && main.scrollWidth, vaza, semRotulo: sem, emoji, titulo: (vis && vis.querySelector('h1')?.textContent) || document.querySelector('.content.on h1, h1')?.textContent || '', hash: location.hash };
      }).catch(e => ({ erro: e.message }));
      const nome = `${papel}-${w}-${r.replace(/\//g, '_')}`;
      await pg.screenshot({ path: `${OUT}/${nome}.png`, fullPage: w !== 2000 }).catch(() => {});
      res.push({ papel, w, rota: r, ...info, erros: erros.slice(0, 6) });
      console.log(nome, info.hscroll ? 'HSCROLL' : '', (info.vaza || []).length ? 'VAZA ' + info.vaza.slice(0, 3).join(' | ') : '', erros.length ? 'ERROS ' + erros.slice(0, 2).join(' | ') : '', info.semRotulo ? 'botoes-sem-rotulo=' + info.semRotulo : '', info.emoji ? 'emoji=' + info.emoji : '', '«' + (info.titulo || '').trim().slice(0, 40) + '»', info.hash);
    }
    await ctx.close();
  }
  fs.writeFileSync(`${OUT}/passeio.json`, JSON.stringify(res, null, 1));
  await br.close();
})().catch(e => { console.error(e); process.exit(2); });
