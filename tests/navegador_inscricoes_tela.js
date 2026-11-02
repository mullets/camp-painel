// 02/11 (Rafael: "inscrições no painel tinha que ter a contagem do lado" / "e está com barra horizontal lá"): o menu mostra quantas
// inscrições novas há; a tela de Inscrições não rola de lado (computador, tablet e celular).  Uso: bash tests/rodar_um.sh tests/navegador_inscricoes_tela.js
const { execFileSync } = require('child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || 'playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8765', DB = process.env.CAMP_DB_PATH;
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
execFileSync('python3', ['-c', `
import sqlite3,sys
con=sqlite3.connect(sys.argv[1])
longo='arquiteta-e-urbanista-com-um-email-bem-comprido-para-testar@universidade-federal-exemplo.edu.br'
for i in range(1,4):
    con.execute("INSERT INTO inscricao (site_id,tipo,curso_id,curso,turma,nome,email,cidade,formacao,motivacao,portfolio,situacao,criado_no_site) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
      (9800+i,'inscricao','residencia-acervos-arquitetura','Residência em Acervos de Arquitetura Moderna Paulista','turma de março de 2027','Maria Aparecida dos Santos Oliveira Ferreira '+str(i),longo,'São José dos Campos','Arquitetura e Urbanismo pela Universidade de São Paulo','x'*600,'https://www.exemplo-de-portfolio-muito-comprido.com.br/projetos/arquitetura/moderna/'+'a'*80,'nova' if i<3 else 'em_analise'))
con.execute("INSERT INTO inscricao (site_id,tipo,curso_id,curso,nome,email,situacao) VALUES (9899,'interesse','residencia-acervos-arquitetura','Residência em Acervos de Arquitetura Moderna Paulista','Bia',?, 'aguardando')",(longo,))
con.commit()`, DB]);
(async () => {
  const br = await chromium.launch(); const erros = [];
  for (const [w, h] of [[1400, 900], [1024, 768], [390, 800]]) {
    const pg = await (await br.newContext({ viewport: { width: w, height: h } })).newPage();
    pg.on('pageerror', e => erros.push('pageerror: ' + e.message));
    await pg.goto(BASE + '/');
    await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
    if (w === 1400) {
      await pg.goto(BASE + '/'); await pg.reload(); await pg.waitForTimeout(2500);
      const n0 = await pg.$eval('#n-ins', e => e.hidden ? '' : e.textContent).catch(() => '');
      chk(n0 === '2', 'já na Home, o menu mostra 2 inscrições novas ao lado de "Inscrições" (sem precisar abrir a tela)', `"${n0}"`);
    }
    await pg.goto(BASE + '/#inscricoes'); await pg.reload();
    await pg.waitForSelector('[data-ins-abrir]', { timeout: 10000 }).catch(() => {});
    await pg.waitForTimeout(800);
    if (w === 1400) {
      const n = await pg.$eval('#n-ins', e => e.hidden ? '' : e.textContent).catch(() => '');
      chk(n === '2', 'o menu mostra 2 inscrições novas ao lado de "Inscrições"', `"${n}"`);
    }
    const lado = await pg.evaluate(() => { const m = document.querySelector('.main'), v = document.getElementById('v-inscricoes');
      return { main: m.scrollWidth - m.clientWidth, pag: document.scrollingElement.scrollWidth - innerWidth, sec: v ? v.scrollWidth - v.clientWidth : 0,
               largos: [...(v ? v.querySelectorAll('*') : [])].filter(e => e.getBoundingClientRect().right > innerWidth + 1 && !e.closest('.tw')).slice(0, 4).map(e => e.tagName + '.' + e.className + ' ' + Math.round(e.getBoundingClientRect().right)) } });
    chk(lado.main <= 0 && lado.pag <= 0 && lado.sec <= 0, `${w}px: a tela de Inscrições não rola de lado`, JSON.stringify(lado));
    const tw = await pg.evaluate(() => [...document.querySelectorAll('#v-inscricoes .tw')].map(t => t.scrollWidth - t.clientWidth));
    if (w > 720) chk(tw.every(x => x <= 0), `${w}px: a tabela de Inscrições não tem barra de rolagem lateral`, JSON.stringify(tw));
    await pg.click('[data-ins-abrir]'); await pg.waitForTimeout(600);
    const dr = await pg.evaluate(() => { const d = document.getElementById('drawer'); return d ? d.scrollWidth - d.clientWidth : 0 });
    chk(dr <= 0, `${w}px: a ficha da inscrição não rola de lado`, String(dr));
  }
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n')); console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK'); process.exit(problemas.length ? 1 : 0);
})();
