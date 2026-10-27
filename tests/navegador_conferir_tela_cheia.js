// UX-10 no navegador de verdade (Playwright + Chromium): conferência em tela cheia, SÓ PELO TECLADO.
// Antes: a gaveta "Revisar folha" ocupava meia tela (imagem 459×296 de um original 2000×1290), Ano/Endereço/Cliente vinham vazios mesmo
// com o projeto tendo ano e cidade, "Tipo" eram 15 caixas e não havia lista de atalhos.
// Prova, a 1440 px, num lote de 5 folhas (D1 normal, D2 orientação incerta, D3 normal, D4 "outro projeto?", D5 normal):
//  - "Começar a conferir" (Enter no botão) abre a PRIMEIRA folha pendente em tela cheia; a imagem tem ≥ 70% da largura e o formulário fica à direita;
//  - ano/cidade/cliente do projeto aparecem como SUGERIDOS (cinza, vazios, marcados "sugerido do projeto"), diferentes do valor lido;
//  - "Tipo": só os 4 mais usados à vista + "Mais tipos";  "?" lista todos os atalhos (Enter, J/K, R, L, M, D, P, F, Tab, ?);
//  - R/L giram, M espelha (gravado no servidor); Enter confere e vai para a próxima SEM gravar o sugerido (ano continua vazio);
//  - J/K andam sem conferir; folha com orientação incerta mostra o aviso; folha "outro projeto?" mostra "É deste projeto";
//  - Tab aceita o sugerido e Enter grava (ano 1973, "corrigida"); D abre "Marcar duplicata"; P abre "Relatar problema" e Esc fecha só ela;
//  - perda de conexão ao salvar: a folha continua aberta, com o erro, e nada muda; F sai e volta da tela cheia; zoom por duplo clique, roda e + 0;
//  - 390 px: sem rolagem para o lado; nenhum erro de JavaScript.
// Uso (servidor PRÓPRIO numa porta 89xx, nunca a 8765 compartilhada):
//   CAMP_DB_PATH=/tmp/tc.db python3 tests/semear_banco_teste.py
//   (cd backend && CAMP_DB_PATH=/tmp/tc.db CAMP_COOKIE_SECURE=false WP_BASE_URL=http://127.0.0.1:9 python3 -m uvicorn app.main:app --port 8944)
//   CAMP_DB_PATH=/tmp/tc.db CAMP_BASE=http://127.0.0.1:8944 node tests/navegador_conferir_tela_cheia.js
const { execFileSync } = require('child_process');
const path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
const BASE = process.env.CAMP_BASE || 'http://127.0.0.1:8944', DB = process.env.CAMP_DB_PATH;
const CHROME = process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const problemas = [], linhas = [];
const chk = (ok, msg, det = '') => { linhas.push((ok ? 'ok    ' : 'FALHA ') + msg + (ok || !det ? '' : ' -> ' + det)); if (!ok) problemas.push(msg); };
if (!DB) { console.error('informe CAMP_DB_PATH (o mesmo banco do servidor)'); process.exit(2); }
const PRONTOS = path.join(path.dirname(DB), 'prontos_tela_cheia'); fs.mkdirSync(PRONTOS, { recursive: true });
const py = (codigo) => execFileSync('python3', ['-c', 'import sqlite3,sys,json\ncon=sqlite3.connect(sys.argv[1])\n' + codigo + '\ncon.commit()', DB, PRONTOS], { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'inherit'] }).trim();
const P = 'F026-P0098', D = n => `${P}-1973-S01-D0000${n}`;
py(`
from pathlib import Path
from PIL import Image, ImageDraw
raiz = Path(sys.argv[2])
con.execute("UPDATE configuracao SET valor=? WHERE chave='qnap.prontos_raiz'", (str(raiz),))
con.execute("INSERT OR IGNORE INTO numero_p (fundo_codigo, numero) VALUES ('F026', 98)")
con.execute("INSERT OR REPLACE INTO projeto (codigo,fundo_codigo,numero,titulo,ano,cidade,uf,cliente) VALUES ('${P}','F026',98,'Clube Tela Cheia',1973,'Santos','SP','Clube Atlético X')")
con.execute("DELETE FROM item WHERE projeto_codigo='${P}'")
lid = con.execute("INSERT INTO lista_processamento (nome, projeto_codigo, pasta_qnap, etapa) VALUES ('Lote tela cheia','${P}','/x/tc','revisao')").lastrowid
tipos = {1: 'Corte', 2: 'Corte', 3: 'Detalhe', 4: 'Implantação', 5: 'Planta'}
for s in range(1, 6):
    cod = "${P}-1973-S01-D%05d" % s
    rel = "_campvision/preview/${P}/%s.jpg" % cod
    (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (2000, 1290), "white"); dr = ImageDraw.Draw(im); dr.rectangle((100, 100, 1900, 1190), outline="black", width=12); dr.text((960, 620), "D%d" % s, fill="black")
    im.save(raiz / rel, "JPEG", quality=80)
    sinais = ["orientação incerta"] if s == 2 else (["projeto divergente: o carimbo diz outra obra"] if s == 4 else [])
    pend = {"bloqueios": [], "sinais": sinais, "ressalvas": [], "previa": rel, "titulo_lido": "Prancha %d" % s}
    con.execute("INSERT INTO item (codigo,projeto_codigo,serie_codigo,sequencial,titulo,tipo_documento,folha,origem,lote_id,status_site,pendencias,revisao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      (cod, '${P}', 'S01', s, "Prancha %d" % s, tipos[s], "%02d/05" % s, 'campvision', lid, 'nao_publicado', json.dumps(pend, ensure_ascii=False), 'pendente'))
con.execute("DELETE FROM erro WHERE codigo LIKE '${P}%'")
`);
const item = n => JSON.parse(py(`r = con.execute("SELECT revisao, ano_folha, giro_manual, espelho_manual FROM item WHERE codigo=?", ("${D(n)}",)).fetchone(); print(json.dumps(list(r)))`));
const espera = async (f, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await f()) return true; } catch (_) {} await new Promise(r => setTimeout(r, 150)); } return false; };

(async () => {
  const br = await chromium.launch({ executablePath: CHROME });
  const erros = [];
  const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } }); const pg = await ctx.newPage();
  pg.on('pageerror', e => erros.push(`pageerror: ${e.message}`));
  pg.on('console', m => { if (m.type() === 'error' && !/401|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ERR_FAILED|Failed to load resource|Failed to fetch/.test(m.text())) erros.push(`console.error: ${m.text()}`); });
  await pg.addInitScript(() => { try { localStorage.setItem('camp.dicaRev', '9') } catch (_) {} });
  await pg.goto(BASE + '/');
  await pg.evaluate(() => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'rafael@camp.arq.br', senha: 'senha-bem-longa-123' }) }));
  await pg.goto(BASE + '/#projeto/' + P); await pg.reload();
  await pg.waitForSelector('#pj-proximo [data-pp="conferir"]', { timeout: 15000 });
  const sub = () => pg.evaluate(() => (document.getElementById('d-sub') || {}).textContent || '');
  const cheia = () => pg.evaluate(() => document.querySelector('.main').classList.contains('rev-cheia'));
  const abriu = c => espera(async () => (await sub()) === c && !!(await pg.$('#d-body [data-rev-item="conferida"]')));
  const tecla = async k => { await pg.keyboard.press(k); await pg.waitForTimeout(120); };

  // ---------- "Começar a conferir" pelo teclado: a primeira pendente, em tela cheia ----------
  await pg.focus('#pj-proximo [data-pp="conferir"]'); await tecla('Enter');
  chk(await abriu(D(1)), '"Começar a conferir" (Enter) abre a primeira folha pendente (D1)', await sub());
  chk(await cheia(), 'abre em tela cheia');
  await espera(() => pg.evaluate(() => { const i = document.getElementById('rv-img'); return i && i.complete && i.naturalWidth > 0; }));
  const geo = await pg.evaluate(() => { const i = document.getElementById('rv-img').getBoundingClientRect(), f = document.querySelector('#d-body .rev-col-dados').getBoundingClientRect(), d = document.getElementById('drawer').getBoundingClientRect();
    return { iw: i.width, il: i.left, ir: i.right, fl: f.left, fw: f.width, dw: d.width }; });
  chk(geo.iw >= 0.7 * 1440, 'a imagem ocupa ≥ 70% da largura em 1440 px', JSON.stringify(geo));
  chk(geo.fl >= geo.ir && geo.fw <= 380, 'o formulário fica à direita da imagem, compacto', JSON.stringify(geo));
  chk(geo.dw >= 1430, 'a gaveta ocupa a tela toda', JSON.stringify(geo));

  // ---------- sugeridos do projeto ----------
  const sug = await pg.evaluate(() => ['rv-ano', 'rv-endereco', 'rv-cliente', 'rv-titulo'].map(id => { const el = document.getElementById(id); return el ? { id, v: el.value, ph: el.placeholder, cls: el.className, nota: ((el.closest('.rev-campo') || {}).querySelector && (el.closest('.rev-campo').querySelector('.rev-sug') || {}).textContent) || '', cor: getComputedStyle(el, '::placeholder').color, corTexto: getComputedStyle(el).color } : null; }));
  const [ano, end, cli, tit] = sug;
  chk(ano && ano.v === '' && ano.ph === '1973' && /sugerido/.test(ano.cls), 'Ano da folha: 1973 do projeto como sugerido (campo vazio, em cinza)', JSON.stringify(ano));
  chk(end && end.v === '' && end.ph === 'Santos, SP' && cli && cli.v === '' && cli.ph === 'Clube Atlético X', 'Endereço e Cliente: cidade e cliente do projeto como sugeridos', JSON.stringify([end, cli]));
  chk(ano && /sugerido do projeto/.test(ano.nota) && ano.cor !== ano.corTexto, 'o sugerido é distinguível: marca "sugerido do projeto" e cor diferente do texto', JSON.stringify(ano));
  chk(tit && tit.v === 'Prancha 1' && !/sugerido/.test(tit.cls) && !tit.nota, 'o valor lido/confirmado (Título) não tem a marca de sugerido', JSON.stringify(tit));

  // ---------- Tipo: 4 mais usados + "Mais tipos" ----------
  const tp = await pg.evaluate(() => { const g = document.querySelector('#d-body [data-tipos-para="rv-tipo"]'); const fora = [...g.querySelectorAll(':scope > .tm-op input')].map(x => x.value), mais = g.querySelector('.tm-mais'); return { fora, mais: mais ? mais.querySelector('summary').textContent : '', dentro: mais ? mais.querySelectorAll('.tm-op').length : 0 }; });
  chk(tp.fora.length === 4 && tp.fora[0] === 'Corte' && tp.fora.includes('Planta'), '"Tipo": 4 à vista, os mais usados no projeto primeiro (Corte)', JSON.stringify(tp));
  chk(/Mais tipos/.test(tp.mais) && tp.dentro > 0, 'os outros tipos ficam em "Mais tipos"', JSON.stringify(tp));

  // ---------- ? : todos os atalhos ----------
  await tecla('Shift+Slash');
  const aj = await pg.evaluate(() => { const o = document.getElementById('conf-ov'); return o ? o.textContent : ''; });
  chk(/Atalhos da conferência/.test(aj) && ['Enter', 'J · K', 'R', 'L', 'M', 'D', 'P', 'F', 'Tab', '?'].every(k => aj.includes(k)), '"?" lista todos os atalhos (Enter, J/K, R, L, M, D, P, F, Tab, ?)', aj.slice(0, 300));
  await tecla('Escape');
  chk(!(await pg.$('#conf-ov')) && (await sub()) === D(1) && await cheia(), 'Esc fecha a lista de atalhos e a conferência continua');

  // ---------- girar e espelhar pelo teclado ----------
  await tecla('r'); await espera(() => item(1)[2] === 90);
  chk(item(1)[2] === 90, 'R vira à direita (giro gravado: 90)', JSON.stringify(item(1)));
  await tecla('l'); await espera(() => item(1)[2] === 0);
  chk(item(1)[2] === 0, 'L vira à esquerda (giro volta a 0)', JSON.stringify(item(1)));
  await tecla('m'); await espera(() => item(1)[3] === 1);
  chk(item(1)[3] === 1, 'M espelha (gravado)', JSON.stringify(item(1)));
  await tecla('m'); await espera(() => item(1)[3] === 0);

  // ---------- zoom ----------
  await pg.dblclick('#rv-img');
  const z1 = await pg.evaluate(() => document.getElementById('rv-img').style.transform);
  chk(/scale\(2\.5\)/.test(z1), 'duplo clique na imagem dá zoom', z1);
  await pg.mouse.move(geo.il + 200, 300); await pg.mouse.wheel(0, -300); await pg.waitForTimeout(150);
  const z2 = await pg.evaluate(() => document.getElementById('rv-img').style.transform);
  chk(/scale\(3\.1/.test(z2), 'a roda do mouse aumenta o zoom', z2);
  await tecla('0'); chk(!(await pg.evaluate(() => document.getElementById('rv-img').style.transform)), '0 volta o zoom');
  await tecla('Equal'); chk(/scale\(1\.25\)/.test(await pg.evaluate(() => document.getElementById('rv-img').style.transform)), '+ (=) aumenta o zoom pelo teclado');
  chk(pg.context().pages().length === 1, 'clicar na imagem em tela cheia não abriu outra aba');

  // ---------- Enter: confere sem gravar o sugerido ----------
  await pg.evaluate(() => document.activeElement && document.activeElement.blur && document.activeElement.blur());
  await tecla('Enter');
  chk(await abriu(D(2)), 'Enter: "Está certo e próxima" (abre D2)', await sub());
  chk(item(1)[0] === 'conferida' && (item(1)[1] == null || item(1)[1] === 0), 'D1 conferida e o ano sugerido NÃO foi gravado (nada salvo sem ação explícita)', JSON.stringify(item(1)));
  chk(await cheia(), 'a próxima folha continua em tela cheia');
  chk(/orientação incerta/i.test(await pg.evaluate(() => document.getElementById('d-body').textContent)), 'folha com orientação incerta mostra o aviso na tela cheia');

  // ---------- J/K andam sem conferir ----------
  await tecla('k'); chk(await abriu(D(3)), 'K vai para a próxima (D3)', await sub());
  chk(item(2)[0] === 'pendente', 'andar com K não confere a folha (D2 continua a conferir)');
  await tecla('j'); chk(await abriu(D(2)), 'J volta para a anterior (D2)', await sub());
  await tecla('k'); await abriu(D(3)); await tecla('k');
  chk(await abriu(D(4)), 'K de novo: D4', await sub());
  chk(!!(await pg.$('#d-body [data-deste-projeto]')), 'folha marcada "outro projeto?" mostra "É deste projeto" na tela cheia');
  await tecla('j'); await abriu(D(3));

  // ---------- Tab aceita o sugerido; Enter grava ----------
  await pg.focus('#rv-ano'); await tecla('Tab');
  const ac = await pg.evaluate(() => { const el = document.getElementById('rv-ano'); return { v: el.value, aceito: el.closest('.rev-campo').classList.contains('aceito'), alterado: el.closest('.rev-campo').classList.contains('alterado'), foco: document.activeElement && document.activeElement.id }; });
  chk(ac.v === '1973' && ac.aceito && ac.alterado, 'Tab aceita o ano sugerido (o campo passa a "alterado")', JSON.stringify(ac));
  chk(item(3)[1] == null || item(3)[1] === 0, 'aceitar com Tab ainda não grava nada', JSON.stringify(item(3)));
  await tecla('Enter');
  await espera(() => item(3)[0] !== 'pendente');
  chk(item(3)[0] === 'corrigida' && item(3)[1] === 1973, 'Enter grava o ano aceito (1973) e marca "corrigida"', JSON.stringify(item(3)));
  chk(await abriu(D(4)), 'e segue para a próxima (D4)', await sub());

  // ---------- D duplicata, P relatar problema ----------
  await tecla('d');
  const dup = await espera(async () => /duplicat|igual a esta/i.test(await pg.evaluate(() => (document.getElementById('conf-ov') || {}).textContent || '')), 4000);
  chk(dup, 'D abre "Marcar duplicata"');
  await tecla('Escape'); await espera(async () => !(await pg.$('#conf-ov')));
  await tecla('p');
  const rel = await espera(() => pg.evaluate(() => { const m = document.getElementById('m-erro'); return !!(m && m.classList.contains('on')); }), 4000);
  chk(rel, 'P abre "Relatar problema"');
  await tecla('Escape');
  chk(!(await pg.evaluate(() => document.getElementById('m-erro').classList.contains('on'))) && (await sub()) === D(4) && await cheia(), 'Esc fecha só "Relatar problema"; a conferência continua');

  // ---------- perda de conexão ao salvar ----------
  await pg.route('**/api/itens/*/revisao', r => r.abort('internetdisconnected'));
  await pg.evaluate(() => document.activeElement && document.activeElement.blur && document.activeElement.blur());
  await tecla('Enter');
  await espera(() => pg.evaluate(() => /Não salvou/.test(document.getElementById('d-body').textContent)), 6000);
  chk(await pg.evaluate(() => /Não salvou/.test(document.getElementById('d-body').textContent)) && (await sub()) === D(4) && item(4)[0] === 'pendente', 'sem conexão: "Não salvou", a folha continua aberta e a conferir', JSON.stringify(item(4)));
  await pg.unroute('**/api/itens/*/revisao');
  await espera(async () => !(await pg.$('#d-body [data-rev-item="conferida"][disabled]')), 3000);
  await pg.evaluate(() => document.activeElement && document.activeElement.blur && document.activeElement.blur());
  await tecla('Enter'); await espera(() => item(4)[0] === 'conferida');
  chk(item(4)[0] === 'conferida', 'conexão de volta: Enter confere');

  // ---------- F sai e volta da tela cheia ----------
  await abriu(D(5)); await pg.evaluate(() => document.activeElement && document.activeElement.blur && document.activeElement.blur());
  await tecla('f'); chk(!(await cheia()) && /Tela cheia/.test(await pg.evaluate(() => document.querySelector('[data-rev-cheia]').textContent)), 'F sai da tela cheia (a gaveta volta ao tamanho de antes)');
  await tecla('f'); chk(await cheia(), 'F volta para a tela cheia');

  // ---------- 390 px ----------
  await pg.setViewportSize({ width: 390, height: 800 }); await pg.waitForTimeout(300);
  const lado = await pg.evaluate(() => { const d = document.getElementById('drawer'); return { s: d.scrollWidth, c: d.clientWidth, doc: document.documentElement.scrollWidth }; });
  chk(lado.s <= lado.c + 1 && lado.doc <= 391, '390 px: tela cheia sem rolagem para o lado', JSON.stringify(lado));
  chk(!erros.length, 'nenhum erro de JavaScript', erros.join(' | '));
  await br.close();
  console.log(linhas.join('\n'));
  console.log(problemas.length ? `\n${problemas.length} FALHA(S)` : '\nTUDO OK');
  process.exit(problemas.length ? 1 : 0);
})().catch(e => { console.log(linhas.join("\n")); console.error(e); process.exit(1); });
