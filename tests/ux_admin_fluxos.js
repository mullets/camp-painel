// Passeio de fluxos (auditoria): abre modais/menus do casco e da Administração e grava prints + medidas.
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:9171';
const OUT = process.env.OUT || '/dev/shm/uxadm_fluxos'; fs.mkdirSync(OUT, { recursive: true });
const W = +(process.env.W || 1440), H = +(process.env.H || 900);
(async () => {
  const br = await chromium.launch(); const pg = await br.newPage({ viewport: { width: W, height: H } });
  const erros = []; pg.on('pageerror', e => erros.push(e.message));
  pg.on('dialog', d => { console.log('DIALOG', d.type(), d.message().slice(0, 120)); d.dismiss().catch(() => {}); });
  await pg.route(/mercadopago|camp\.arq\.br|sender\.net/, r => r.abort());
  const shot = async n => { await pg.evaluate(() => document.querySelectorAll('.toast,#toast').forEach(t => t.style.visibility = 'hidden')).catch(() => {}); await pg.screenshot({ path: `${OUT}/${W}-${n}.png` }); };
  const medir = async n => console.log(n, JSON.stringify(await pg.evaluate(() => { const m = document.querySelector('.main'); const vw = document.documentElement.clientWidth;
    const mods = [...document.querySelectorAll('.drawer.on,dialog[open],.modal.on,[role=dialog]:not([hidden])')].filter(x => x.offsetParent || getComputedStyle(x).position === 'fixed').map(x => { const r = x.getBoundingClientRect(); return (x.id || x.className).toString().slice(0, 30) + ' ' + Math.round(r.left) + '-' + Math.round(r.right) + (r.right > vw + 1 || r.left < -1 ? ' VAZA' : '') });
    return { hs: m.scrollWidth > m.clientWidth + 1 || document.scrollingElement.scrollWidth > vw + 1, mods, hash: location.hash }; })));
  // login errado
  await pg.goto(BASE + '/'); await pg.fill('#lg-email', 'rafael@camp.arq.br'); await pg.fill('#lg-senha', 'errada-123456'); await pg.press('#lg-senha', 'Enter');
  await pg.waitForTimeout(1200); console.log('login errado:', await pg.evaluate(() => (document.querySelector('#login .err,#lg-erro,#login [role=alert]')?.textContent || document.querySelector('#login')?.innerText.slice(0, 300) || '').replace(/\s+/g, ' ')));
  await shot('login-errado');
  await pg.fill('#lg-senha', 'senha-bem-longa-123'); await pg.press('#lg-senha', 'Enter');
  await pg.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
  await pg.waitForTimeout(1000);
  // atalhos
  await pg.keyboard.press('?'); await pg.waitForTimeout(600); await medir('atalhos'); await shot('atalhos'); await pg.keyboard.press('Escape'); await pg.waitForTimeout(300);
  // menu do usuário
  const um = pg.locator('.user, #user-btn, .top .who, button[aria-haspopup]').last();
  await pg.locator('#usr-menu-btn, .top-user, .user-btn, .who').first().click().catch(async () => { await um.click().catch(() => {}) });
  await pg.waitForTimeout(500); await medir('menu-usuario'); await shot('menu-usuario'); await pg.keyboard.press('Escape');
  // busca
  await pg.click('.search input').catch(() => {}); await pg.keyboard.type('financ'); await pg.waitForTimeout(900); await medir('busca'); await shot('busca-financ');
  await pg.keyboard.press('Escape');
  // status pill
  await pg.locator('.top .sis, #sis-pill, .estado-sis, .top [data-sis]').first().click().catch(() => {}); await pg.waitForTimeout(600); await medir('status'); await shot('status'); await pg.keyboard.press('Escape');
  // Financeiro: receita, despesa, fila, voltar
  await pg.goto(BASE + '/#financeiro/receitas'); await pg.waitForTimeout(2500);
  await pg.locator('#fin-p-receitas [data-fin-rec]').first().click().catch(e => console.log('sem receita', e.message)); await pg.waitForTimeout(800); await medir('fin-receita'); await shot('fin-receita');
  await pg.goBack(); await pg.waitForTimeout(800); await medir('fin-voltar'); await shot('fin-voltar');
  await pg.goto(BASE + '/#financeiro/despesas'); await pg.waitForTimeout(2500);
  await pg.locator('#fin-p-despesas [data-fin-desp]').first().click().catch(e => console.log('sem despesa', e.message)); await pg.waitForTimeout(800); await medir('fin-despesa'); await shot('fin-despesa');
  await pg.keyboard.press('Escape'); await pg.waitForTimeout(400); await medir('fin-despesa-esc');
  await pg.locator('[data-fin-acao="fila"]').first().click().catch(e => console.log('sem fila', e.message)); await pg.waitForTimeout(900); await medir('fin-fila'); await shot('fin-fila');
  await pg.keyboard.press('Escape'); await pg.waitForTimeout(400); await medir('fin-fila-esc'); await shot('fin-fila-esc');
  // Projetos da CAMP: novo projeto, nova tarefa
  await pg.goto(BASE + '/#projetos_camp'); await pg.waitForTimeout(1500);
  await pg.locator('button:has-text("Novo projeto")').first().click().catch(e => console.log('sem novo projeto', e.message)); await pg.waitForTimeout(700); await medir('pc-novo'); await shot('pc-novo'); await pg.keyboard.press('Escape'); await pg.waitForTimeout(300);
  await pg.goto(BASE + '/#projetos_camp/1/cronograma'); await pg.waitForTimeout(1500);
  await pg.locator('button:has-text("Nova tarefa")').first().click().catch(e => console.log('sem nova tarefa', e.message)); await pg.waitForTimeout(700); await medir('pc-tarefa'); await shot('pc-tarefa'); await pg.keyboard.press('Escape');
  // Configurações: novo usuário
  await pg.goto(BASE + '/#config'); await pg.waitForTimeout(1500);
  await pg.locator('button:has-text("Novo usuário")').first().click().catch(e => console.log('sem novo usuario', e.message)); await pg.waitForTimeout(700); await medir('cfg-novo-usuario'); await shot('cfg-novo-usuario'); await pg.keyboard.press('Escape');
  // Máquinas: abas
  await pg.goto(BASE + '/#estacoes'); await pg.waitForTimeout(1500);
  for (const a of ['Alertas', 'Logs']) { await pg.locator(`#v-estacoes [role=tab]:has-text("${a}"), #v-estacoes button:has-text("${a}")`).first().click().catch(e => console.log('sem aba', a)); await pg.waitForTimeout(800); await medir('maq-' + a); await shot('maq-' + a); }
  console.log('ERROS', erros.slice(0, 8));
  await br.close();
})().catch(e => { console.error(e); process.exit(2); });
