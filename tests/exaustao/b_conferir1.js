// Exaustão da página do projeto, grupo B — CONFERIR, parte 1 (CAMP-080 a CAMP-088). Rodar: bash tests/rodar_exaustao.sh tests/exaustao/b_conferir1.js
// Lotes pelo caminho real (tests/exaustao/b_montar.py: estação reserva, CAMP Vision grava a pasta final e avisa). Tudo pelo navegador.
//   lote A: 60 folhas comuns (CAMP-080: teclado)
//   lote B: 12 folhas — D1 comum, D2 de cabeça para baixo, D3 deitada, D4 espelhada, D5 sem imagem, D6 ano lido 1927, D7 torta, D8–D12 comuns
const { execFileSync } = require('child_process');
const crypto = require('crypto'), fs = require('fs'), path = require('path');
const T = require('./_comum');
const { imgOk, chk, passo, sql, um, espera, print, txt, confirmar, entrar, abrirProjeto, abrirConferir, BASE, RAIZ, DB } = T;
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'b_montar.py'), BASE, RAIZ, ...a], { encoding: 'utf-8' }).trim().split('\n').pop();
const siteImg = c => JSON.parse(execFileSync('python3', [path.join(__dirname, 'b_montar.py'), 'site-img', DB, c], { encoding: 'utf-8' }).trim().split('\n').pop());
const hashQnap = () => { const h = crypto.createHash('sha1'); const andar = d => fs.readdirSync(d, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name)).forEach(e => { const p = path.join(d, e.name); if (e.isDirectory()) andar(p); else h.update(p + fs.readFileSync(p).length + crypto.createHash('sha1').update(fs.readFileSync(p)).digest('hex')) }); andar(RAIZ); return h.digest('hex') };
const atual = pg => pg.evaluate(() => CONF.atual);
const filtros = pg => pg.evaluate(() => Object.fromEntries([...document.querySelectorAll('#cf-filtros [data-cf-filtro]')].map(b => [b.dataset.cfFiltro, +b.querySelector('b').textContent.replace(/\D/g, '')])));
const contador = pg => txt(pg, '#cf-cont');
const imgCarregou = (pg, sel = '#rv-img') => espera(() => pg.$eval(sel, i => i.complete && i.naturalWidth > 0), 8000);
const dimsImg = (pg, sel = '#rv-img') => pg.$eval(sel, i => ({ w: i.naturalWidth, h: i.naturalHeight, src: i.getAttribute('src') }));
const linhaVisivel = (pg, cod) => pg.evaluate(c => { const l = document.querySelector(`#cf-linhas .cf-linha[data-cf-folha="${c}"]`), b = document.getElementById('cf-linhas'); if (!l || !b) return false; const r = l.getBoundingClientRect(), q = b.getBoundingClientRect(); return r.top >= q.top - 1 && r.bottom <= q.bottom + 1 }, cod);
const corpoFoco = pg => pg.evaluate(() => { const a = document.activeElement; return a ? a.tagName + (a.id ? '#' + a.id : '') : '' });

T.rodar(async () => {
  // ======================= CAMP-080: 60 folhas só pelo teclado =======================
  passo('CAMP-080: conferir 60 folhas só pelo teclado (↑ ↓ Enter R K)');
  const PA = montar('CASA SESSENTA FOLHAS', '60');
  const DA = n => `${PA}-1972-S01-D${String(n).padStart(5, '0')}`;
  chk(um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', PA) === 60, `CAMP-080: o lote de 60 folhas entrou pelo aviso do CAMP Vision (${PA})`);
  const op = await entrar('operador');
  await abrirConferir(op, PA); await imgCarregou(op);
  chk(await atual(op) === DA(1), 'CAMP-080: a tela de conferir abre na primeira folha', await atual(op));
  chk(/0 de 60 conferidas/.test(await contador(op)), 'CAMP-080: contador "0 de 60 conferidas"', await contador(op));
  await op.mouse.click(5, 300);   // clique fora de campos, como quem começa a usar o teclado
  // ↓ ↓ ↑ andam na lista
  await op.keyboard.press('ArrowDown'); await espera(async () => await atual(op) === DA(2), 4000);
  await op.keyboard.press('ArrowDown'); await espera(async () => await atual(op) === DA(3), 4000);
  await op.keyboard.press('ArrowUp'); await espera(async () => await atual(op) === DA(2), 4000);
  chk(await atual(op) === DA(2), 'CAMP-080: ↓ ↓ ↑ andam na lista (D1 → D3 → D2)', await atual(op));
  // R gira (e grava), R de novo ×3 volta ao começo
  await op.keyboard.press('r');
  chk(await espera(() => um('SELECT giro_manual FROM item WHERE codigo=?', DA(2)) === 90, 6000), 'CAMP-080: R gira a folha 90° (gravado)', um('SELECT giro_manual FROM item WHERE codigo=?', DA(2)));
  for (let k = 0; k < 3; k++) { await op.waitForTimeout(500); await op.keyboard.press('r') }
  chk(await espera(() => (um('SELECT giro_manual FROM item WHERE codigo=?', DA(2)) || 0) % 360 === 0, 6000), 'CAMP-080: R ×4 volta a 0°', um('SELECT giro_manual FROM item WHERE codigo=?', DA(2)));
  // K abre recortar; Esc cancela sem trocar de folha
  await op.keyboard.press('k');
  chk(await op.waitForSelector('#aj-ed', { timeout: 6000 }).then(() => true, () => false), 'CAMP-080: K abre "Recortar e alinhar"');
  await op.keyboard.press('Escape');
  chk(await espera(async () => !(await op.$('#aj-ed')), 4000) && await atual(op) === DA(2), 'CAMP-080: Esc fecha o recorte e continua na mesma folha');
  // Enter confere e abre a próxima; medir o tempo de cada folha
  const tempos = []; let foiAte = 2, fala = '';
  for (let n = 2; n <= 31; n++) {
    const antes = await atual(op), t0 = Date.now();
    await op.keyboard.press('Enter');
    const ok = await espera(async () => { const a = await atual(op); return a && a !== antes && await op.$eval('#rv-img', i => i.complete && i.naturalWidth > 0).catch(() => false) }, 6000);
    if (!ok) { fala = `parou em ${antes}: foco em ${await corpoFoco(op)}`; break }
    tempos.push(Date.now() - t0); foiAte = n;
  }
  chk(foiAte === 31, `CAMP-080: Enter confere e abre a próxima, 30 vezes seguidas sem tocar no mouse (foi até D${foiAte})`, fala);
  const maxT = Math.max(...tempos), medT = Math.round(tempos.reduce((a, b) => a + b, 0) / (tempos.length || 1));
  chk(maxT < 1000, `CAMP-080: cada folha abre em menos de 1 s (média ${medT} ms, pior ${maxT} ms)`);
  chk(new RegExp(`^30 de 60 conferidas`).test(await contador(op)), 'CAMP-080: contador anda junto ("30 de 60 conferidas")', await contador(op));
  chk(um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND revisao!='pendente'", PA) === 30, 'CAMP-080: 30 folhas conferidas no banco', um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND revisao!='pendente'", PA));
  chk(await linhaVisivel(op, await atual(op)), 'CAMP-080: a lista rolou até a folha aberta (a linha selecionada está à vista)');
  const f80 = await corpoFoco(op); chk(!/^(INPUT|TEXTAREA|SELECT|BUTTON|A)/.test(f80), 'CAMP-080: o foco não fica preso num botão/campo (o teclado continua valendo)', f80);
  await print(op, 'a_teclado_30');
  // ↓ no fim da lista não quebra; ↑ volta
  await op.evaluate(c => nav('conferir/' + c), PA + '/' + DA(60)); await espera(async () => await atual(op) === DA(60), 6000); await op.mouse.click(5, 300);
  await op.keyboard.press('ArrowDown'); await op.waitForTimeout(600);
  chk(await atual(op) === DA(60), 'CAMP-080: ↓ na última folha fica nela (sem erro)');
  chk(await linhaVisivel(op, DA(60)), 'CAMP-080: link direto para a D60 rola a lista até ela');

  // ======================= lote B =======================
  const PB = montar('CASA DOZE CASOS', '12', '--incerta', '2', '--deitada', '3', '--espelhada', '4', '--sem-imagem', '5', '--metadado', '6', '--torta', '7');
  const D = n => `${PB}-1972-S01-D${String(n).padStart(5, '0')}`;
  const qnap0 = hashQnap();
  // ======================= CAMP-081: filtros e contagens =======================
  passo('CAMP-081: filtros e contagens a cada ação');
  const esperado = async (rot, exp) => {
    const f = await filtros(op), banco = { todas: um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', PB), a_conferir: um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND revisao='pendente'", PB) };
    const ok = f.todas === banco.todas && f.a_conferir === banco.a_conferir && (exp.problema == null || f.problema === exp.problema) && (exp.sem_imagem == null || f.sem_imagem === exp.sem_imagem);
    chk(ok, `CAMP-081: ${rot}: filtros batem (todas ${f.todas}, a conferir ${f.a_conferir}, com problema ${f.problema}, sem imagem ${f.sem_imagem})`, JSON.stringify({ tela: f, banco, esperado: exp }));
  };
  await abrirConferir(op, PB); await imgCarregou(op);
  await esperado('no começo', { problema: 4, sem_imagem: 1 });   // D2, D3 (giro), D4 (espelhada), D6 (ano lido)
  // a página do projeto conta igual
  const contaProjeto = async () => { await abrirProjeto(op, PB); const b = await txt(op, '.folhas-bar'); return { problema: +(b.match(/Com problema \((\d+)\)/) || [])[1], sem_imagem: +(b.match(/Sem imagem \((\d+)\)/) || [])[1], a_conferir: +(b.match(/A conferir \((\d+)\)/) || [])[1] } };
  const cp0 = await contaProjeto();
  chk(cp0.problema === 4 && cp0.sem_imagem === 1 && cp0.a_conferir === 12, 'CAMP-081: a barra da página do projeto tem os mesmos números (4 com problema, 1 sem imagem, 12 a conferir)', JSON.stringify(cp0));
  await abrirConferir(op, PB);
  await op.click('#cf-filtros [data-cf-filtro="sem_imagem"]'); await op.waitForTimeout(400);
  const linhasSem = await op.$$eval('#cf-linhas .cf-linha:not(.sel)', l => l.map(x => x.dataset.cfFolha.slice(-2)));   // a folha aberta (D1) fica na lista mesmo fora do filtro
  chk(linhasSem.join(',') === '05', 'CAMP-081: filtro "Sem imagem" mostra só a D5 (além da folha aberta)', linhasSem.join(','));
  await op.click('#cf-filtros [data-cf-filtro="problema"]'); await op.waitForTimeout(400);
  const linhasProb = await op.$$eval('#cf-linhas .cf-linha:not(.sel)', l => l.map(x => x.dataset.cfFolha.slice(-2)));
  chk(linhasProb.join(',') === '02,03,04,06', 'CAMP-081: filtro "Com problema" mostra D2, D3, D4, D6', linhasProb.join(','));
  await op.click('#cf-filtros [data-cf-filtro="todas"]'); await op.waitForTimeout(300);

  // ======================= CAMP-082: folha sem imagem =======================
  passo('CAMP-082: folha sem imagem');
  await abrirConferir(op, PB, D(5));
  const p5 = await txt(op, '#cf-pane');
  chk(/Sem (prévia|imagem)/.test(p5), 'CAMP-082: a folha mostra o aviso de que está sem imagem', p5.slice(0, 200));
  const temRel = await op.$('#cf-pane [data-releitura-item]');
  chk(!!temRel, 'CAMP-082: oferece "Pedir releitura"');
  if (temRel) { await op.click('#cf-pane [data-releitura-item]'); await confirmar(op) }
  chk(await espera(() => um("SELECT COUNT(*) FROM pedido_releitura WHERE item_codigo=?", D(5)) >= 1, 6000), 'CAMP-082: "Pedir releitura" grava o pedido ao CAMP Vision', um("SELECT COUNT(*) FROM pedido_releitura WHERE item_codigo=?", D(5)));
  await print(op, 'b_sem_imagem');
  await abrirConferir(op, PB, D(5));
  await op.click('#cf-pane [data-rev-item="conferida"]');
  const pergunta = await op.waitForSelector('#conf-ov', { timeout: 4000 }).then(() => true, () => false);
  chk(pergunta && /sem ver a imagem/i.test(await txt(op, '#conf-ov')), '"CAMP-082: "Está certo" pede confirmação ("Confirmar sem ver a imagem?")', await txt(op, '#conf-ov'));
  if (pergunta) { await op.click('#conf-ov [data-conf="nao"], #conf-ov .btn:not([data-conf="sim"])'); await op.waitForTimeout(500) }
  chk(um('SELECT revisao FROM item WHERE codigo=?', D(5)) === 'pendente', 'CAMP-082: cancelar deixa a folha a conferir');
  await op.click('#cf-pane [data-rev-item="conferida"]'); await confirmar(op);
  chk(await espera(() => um('SELECT revisao FROM item WHERE codigo=?', D(5)) === 'conferida', 6000), 'CAMP-082: confirmar mesmo assim confere a folha');
  // sair do conferir logo depois de "Está certo": a próxima folha ainda carregando não pode abrir a gaveta na outra tela (rede lenta simulada)
  await abrirConferir(op, PB, D(1)); await imgCarregou(op);
  await op.route('**/api/itens/*/edicao', async r => { await new Promise(x => setTimeout(x, 1500)); await r.continue().catch(() => {}) });
  await op.click('#cf-pane [data-rev-item="conferida"]'); await op.waitForTimeout(200);
  await op.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, PB);
  await op.waitForTimeout(3000); await op.unroute('**/api/itens/*/edicao');
  const gavSozinha = await op.evaluate(() => mainEl.classList.contains('with-drawer') && document.getElementById('d-title').textContent);
  chk(!gavSozinha, 'CAMP-082: sair do conferir logo depois de "Está certo" não abre a gaveta "Revisar folha" por cima da página do projeto', gavSozinha);
  // na página do projeto, o botão de dentro do cartão sem imagem não abre a revisão por baixo
  await abrirProjeto(op, PB);
  const btnCard = await op.$(`.thumb[data-rev-abrir="${D(5)}"] [data-releitura-item]`);
  chk(!!btnCard, 'CAMP-082: o cartão da folha sem imagem na página do projeto tem "Pedir releitura"');
  if (btnCard) { const antesGav = await op.evaluate(() => mainEl.classList.contains('with-drawer') && document.getElementById('d-title').textContent);
    await btnCard.click(); await op.waitForTimeout(800); const ov = await txt(op, '#conf-ov'); await confirmar(op); await op.waitForTimeout(500);
    const depoisGav = await op.evaluate(() => mainEl.classList.contains('with-drawer') && document.getElementById('d-title').textContent);
    chk(!depoisGav, 'CAMP-082: o botão de dentro do cartão não abre a revisão por baixo', JSON.stringify({ antesGav, ov, depoisGav })) }

  // ======================= CAMP-083: girar =======================
  passo('CAMP-083: girar 90/180/270 e desfazer');
  await abrirConferir(op, PB, D(3)); await imgCarregou(op);
  const d0 = await dimsImg(op);
  chk(d0.h > d0.w, 'CAMP-083: a D3 chega deitada (em pé no papel = retrato na tela)', JSON.stringify(d0));
  chk(/Orientação incerta/.test(await txt(op, '#cf-pane')), 'CAMP-083: aviso "Orientação incerta" na D3');
  const girar = async g => { const antes = um('SELECT giro_manual FROM item WHERE codigo=?', D(3)) || 0; await op.click(`#cf-pane .rev-giro [data-rev-girar="${g}"], #cf-pane [data-rev-girar="${g}"] >> nth=-1`); await espera(() => (um('SELECT giro_manual FROM item WHERE codigo=?', D(3)) || 0) !== antes, 6000); await op.waitForTimeout(400); await imgCarregou(op) };
  await girar(90);
  const d1 = await dimsImg(op), mini1 = await op.$eval(`#cf-linhas .cf-linha[data-cf-folha="${D(3)}"] img`, i => i.getAttribute('src')).catch(() => '');
  chk(d1.w > d1.h && /g=90/.test(d1.src), 'CAMP-083: "Virar à direita" deixa a imagem grande em pé', JSON.stringify(d1));
  chk(/g=90/.test(mini1), 'CAMP-083: a miniatura da lista gira junto', mini1);
  await op.reload(); await op.waitForSelector('#cf-pane #rv-img', { timeout: 15000 }); await imgCarregou(op);
  chk(um('SELECT giro_manual FROM item WHERE codigo=?', D(3)) === 90 && /g=90/.test((await dimsImg(op)).src), 'CAMP-083: ao recarregar o giro continua (90°)');
  await girar(90); await girar(90);
  chk(um('SELECT giro_manual FROM item WHERE codigo=?', D(3)) === 270, 'CAMP-083: 270° gravado');
  await girar(90);
  chk((um('SELECT giro_manual FROM item WHERE codigo=?', D(3)) || 0) === 0 && (await dimsImg(op)).h > (await dimsImg(op)).w, 'CAMP-083: mais um giro volta a 0° (deitada de novo)');
  await girar(90); await print(op, 'b_girada');
  await op.click('#cf-pane [data-rev-item="conferida"]'); await confirmar(op);
  await espera(() => um('SELECT revisao FROM item WHERE codigo=?', D(3)) === 'conferida', 6000);
  const tags3 = await op.$eval(`#cf-linhas .cf-linha[data-cf-folha="${D(3)}"]`, l => l.textContent).catch(() => '');
  chk(!/orientação incerta/.test(tags3), 'CAMP-083: "orientação incerta" sai da lista ao conferir', tags3);
  const s3 = siteImg(D(3)); chk(s3.em_pe, 'CAMP-083: a imagem que vai ao site sai em pé', JSON.stringify(s3));
  // D2 (de cabeça para baixo): R R
  await abrirConferir(op, PB, D(2)); await imgCarregou(op); await op.mouse.click(5, 300);
  await op.keyboard.press('r'); await espera(() => um('SELECT giro_manual FROM item WHERE codigo=?', D(2)) === 90, 5000); await op.waitForTimeout(400); await op.keyboard.press('r');
  chk(await espera(() => um('SELECT giro_manual FROM item WHERE codigo=?', D(2)) === 180, 5000), 'CAMP-083: D2 girada 180°');
  const s2 = siteImg(D(2)); chk(s2.em_pe, 'CAMP-083: a D2 vai ao site em pé', JSON.stringify(s2));
  await op.click('#cf-pane [data-rev-item="conferida"]'); await confirmar(op); await espera(() => um('SELECT revisao FROM item WHERE codigo=?', D(2)) === 'conferida', 6000);
  await esperado('depois de girar e conferir D2 e D3', { problema: 2, sem_imagem: 1 });

  // ======================= CAMP-084: espelhar =======================
  passo('CAMP-084: espelhar e "espelhada?"');
  await abrirProjeto(op, PB);
  const flag4 = await txt(op, `.thumb[data-rev-abrir="${D(4)}"]`);
  chk(/espelhada\?/.test(flag4), 'CAMP-084: a página do projeto marca a D4 "espelhada?"', flag4);
  await abrirConferir(op, PB, D(4)); await imgCarregou(op);
  chk(/Espelhada\?/.test(await txt(op, '#cf-pane')), 'CAMP-084: o conferir mostra o aviso "Espelhada?"');
  const s4a = siteImg(D(4)); chk(s4a.em_pe, 'CAMP-084: o painel já desfaz o espelho que o CAMP Vision apontou (a imagem do site sai certa)', JSON.stringify(s4a));
  const src4a = (await dimsImg(op)).src;
  await op.click('#cf-pane .rev-giro [data-rev-espelhar], #cf-pane [data-rev-espelhar] >> nth=-1'); await op.waitForTimeout(1200);
  const e1 = um('SELECT espelho_manual FROM item WHERE codigo=?', D(4)), s4b = siteImg(D(4));
  chk(e1 != null && !s4b.em_pe, 'CAMP-084: "Espelhar" inverte (gravado; a imagem do site ficaria ao contrário)', JSON.stringify({ e1, s4b }));
  await op.click('#cf-pane .rev-giro [data-rev-espelhar], #cf-pane [data-rev-espelhar] >> nth=-1'); await op.waitForTimeout(1200);
  const s4c = siteImg(D(4)), src4c = (await dimsImg(op)).src;
  chk(s4c.em_pe && src4c.replace(/&t=\d+/, '') === src4a.replace(/&t=\d+/, ''), 'CAMP-084: espelhar 2× volta ao original (tela e site)', JSON.stringify({ src4a, src4c, s4c }));
  await op.click('#cf-pane [data-rev-item="conferida"]'); await confirmar(op); await espera(() => um('SELECT revisao FROM item WHERE codigo=?', D(4)) === 'conferida', 6000);
  await abrirProjeto(op, PB);
  chk(!/espelhada\?/.test(await txt(op, `.thumb[data-rev-abrir="${D(4)}"]`)), 'CAMP-084: a marca "espelhada?" some depois de conferir');
  await abrirConferir(op, PB);
  await esperado('depois de conferir a D4', { problema: 1, sem_imagem: 1 });

  // ======================= CAMP-085: recortar e alinhar =======================
  passo('CAMP-085: recortar e alinhar + desfazer');
  await abrirConferir(op, PB, D(7)); await imgCarregou(op);
  const w7 = (await dimsImg(op)).w, s7orig = siteImg(D(7));
  await op.click('#cf-pane [data-rev-ajustar]');
  chk(await op.waitForSelector('#aj-ed #aj-img', { timeout: 8000 }).then(() => true, () => false), 'CAMP-085: abre a tela de recortar');
  await op.click('[data-aj-auto]'); await op.waitForTimeout(1500);
  const ang = await op.evaluate(() => AJ && AJ.ang);
  chk(ang != null && Math.abs(Math.abs(ang) - 4) <= 1.5, `CAMP-085: "Endireitar automaticamente" sugere ~4° (a folha está 4° torta): ${ang}°`);
  // arrasta o canto de cima à esquerda e o de baixo à direita para dentro (tira a borda da mesa)
  const palco = await op.$eval('#aj-palco', p => { const r = p.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height } });
  for (const [k, fx, fy] of [['nw', 0.09, 0.09], ['se', -0.09, -0.09]]) {
    const h = await op.$eval(`.aj-${k}`, e => { const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 } });
    await op.mouse.move(h.x, h.y); await op.mouse.down(); await op.mouse.move(h.x + fx * palco.w, h.y + fy * palco.h, { steps: 6 }); await op.mouse.up();
  }
  const caixa = await op.evaluate(() => AJ && AJ.box);
  chk(caixa && caixa.x > 0.05 && caixa.w < 0.9, 'CAMP-085: arrastar os cantos muda a caixa de recorte', JSON.stringify(caixa));
  await op.click('[data-aj-aplicar]');
  chk(await espera(() => !!um('SELECT imagem_corrigida FROM item WHERE codigo=?', D(7)), 8000), 'CAMP-085: "Aplicar" grava o recorte e gera o JPG corrigido');
  const corr = um('SELECT imagem_corrigida FROM item WHERE codigo=?', D(7)) || '';
  const dirPainel = path.dirname(DB);
  const achado = corr && (fs.existsSync(corr) || fs.existsSync(path.join(dirPainel, 'imagens_corrigidas', corr)) || fs.existsSync(path.join(dirPainel, corr)));
  chk(achado && !String(corr).startsWith(RAIZ), 'CAMP-085: o JPG corrigido fica no diretório do painel, fora do QNAP', corr);
  chk(hashQnap() === qnap0, 'CAMP-085: nenhum arquivo da pasta do CAMP Vision mudou (TIF, JPG, prévia, JSON)');
  await imgCarregou(op);
  const d7 = await dimsImg(op);
  chk(/[&?]a=/.test(d7.src) && d7.w < w7, 'CAMP-085: a imagem grande passa a ser a recortada', JSON.stringify({ antes: w7, depois: d7 }));
  const mini7 = await op.$eval(`#cf-linhas .cf-linha[data-cf-folha="${D(7)}"] img`, i => i.getAttribute('src')).catch(() => '');
  chk(/[&?]a=/.test(mini7), 'CAMP-085: a miniatura da lista usa a recortada', mini7);
  const s7 = siteImg(D(7)); chk(s7.caminho && s7.w > s7.h && s7.w < s7orig.w, 'CAMP-085: o site receberia a recortada (menor que a original, sem a borda)', JSON.stringify({ s7, s7orig }));
  await print(op, 'b_recortada');
  await abrirProjeto(op, PB);
  const th7 = await op.$eval(`.thumb[data-rev-abrir="${D(7)}"] img`, i => i.getAttribute('src')).catch(() => '');
  chk(/[&?]a=/.test(th7), 'CAMP-085: a miniatura da página do projeto também', th7);
  await abrirConferir(op, PB, D(7)); await imgCarregou(op);
  const bDesf = await op.$('#cf-pane [data-rev-ajuste-desfazer]:not([hidden])');
  chk(!!bDesf, 'CAMP-085: aparece "Desfazer recorte/alinhamento"');
  if (bDesf) { await bDesf.click(); await confirmar(op) }
  chk(await espera(() => !um('SELECT recorte FROM item WHERE codigo=?', D(7)) && !+um('SELECT alinhamento FROM item WHERE codigo=?', D(7)), 6000), 'CAMP-085: desfazer volta à imagem do CAMP Vision (sem recorte e sem ângulo)');
  await op.waitForTimeout(500);
  chk(!/[&?]a=/.test((await dimsImg(op)).src) && await op.$eval('#cf-pane [data-rev-ajuste-desfazer]', b => b.hidden).catch(() => true), 'CAMP-085: a tela mostra a original e esconde "Desfazer"');
  chk(hashQnap() === qnap0, 'CAMP-085: a pasta do CAMP Vision continua igual depois de desfazer');

  // ======================= CAMP-086: salvar correção com todos os campos =======================
  passo('CAMP-086: "Salvar correção" com todos os campos');
  await abrirConferir(op, PB, D(6)); await imgCarregou(op);
  chk(/1927/.test(await txt(op, '#cf-pane .cf-avisos')), 'CAMP-086: o problema "ano lido 1927" aparece na folha');
  await op.fill('#rv-titulo', 'Fachada principal — estudo "B"');
  for (const t of ['Planta', 'Corte', 'Detalhe']) { const cb = op.locator(`#cf-pane input[type=checkbox][value="${t}"]`); if (!(await cb.isChecked())) await cb.check() }
  await op.fill('#rv-folha', '06A'); await op.fill('#rv-escala', '1:20'); await op.fill('#rv-ano', '1972');
  await op.fill('#rv-endereco', 'Rua Dr. Alberto Faria, 120'); await op.fill('#rv-cliente', 'Família Sales');
  for (const [esc, dis] of [['Escritório Estrutura Ltda', 1], ['Paisagismo Burle', 2]]) {
    await op.click('#cf-pane [data-parc-add]'); const ln = op.locator('#cf-pane .parc-linha').last();
    await ln.locator('.parc-esc').fill(esc); const opcs = await ln.locator('.parc-dis option').allTextContents(); await ln.locator('.parc-dis').selectOption({ index: Math.min(dis, opcs.length - 1) });
  }
  await print(op, 'b_correcao_preenchida');
  await op.click('#cf-pane [data-rev-item="corrigida"]'); await confirmar(op);
  const i6 = async () => sql('SELECT titulo, tipo_documento, tipos_documento, folha, escala, ano_folha, endereco_folha, cliente_folha, parceiros, revisao FROM item WHERE codigo=?', D(6))[0] || [];
  chk(await espera(async () => (await i6())[9] === 'corrigida', 8000), 'CAMP-086: revisão "corrigida"', JSON.stringify(await i6()));
  const v6 = await i6();
  const tiposOk = /Planta/.test(v6[2] || v6[1]) && /Corte/.test(v6[2] || '') && /Detalhe/.test(v6[2] || '');
  chk(v6[0] === 'Fachada principal — estudo "B"' && tiposOk && v6[3] === '06A' && v6[4] === '1:20' && +v6[5] === 1972 && v6[6] === 'Rua Dr. Alberto Faria, 120' && v6[7] === 'Família Sales',
    'CAMP-086: título, 3 tipos, folha, escala, ano, endereço e cliente gravados', JSON.stringify(v6));
  const parc6 = JSON.parse(v6[8] || '[]');
  chk(parc6.length === 2 && parc6.some(p => /Estrutura/.test(p.escritorio)) && parc6.some(p => /Burle/.test(p.escritorio)), 'CAMP-086: os 2 escritórios parceiros gravados', v6[8]);
  chk(!um("SELECT COUNT(*) FROM erro WHERE codigo=? AND categoria='metadado' AND situacao IN ('aberto','em_correcao')", D(6)), 'CAMP-086: o problema do ano lido fecha com a correção');
  await op.reload(); await op.evaluate(c => nav(c), 'conferir/' + PB + '/' + D(6)); await op.waitForSelector('#cf-pane #rv-titulo', { timeout: 15000 }); await op.waitForTimeout(800);
  const tela6 = await op.evaluate(() => ({ t: document.getElementById('rv-titulo').value, f: document.getElementById('rv-folha').value, e: document.getElementById('rv-escala').value, a: document.getElementById('rv-ano').value, en: document.getElementById('rv-endereco').value, c: document.getElementById('rv-cliente').value, tipos: [...document.querySelectorAll('#cf-pane input[type=checkbox]:checked')].map(x => x.value), parc: [...document.querySelectorAll('#cf-pane .parc-esc')].map(x => x.value) }
    ), null).catch(async () => ({ erro: await txt(op, '#cf-pane') }));
  chk(tela6.t === 'Fachada principal — estudo "B"' && tela6.f === '06A' && tela6.a === '1972' && tela6.tipos && tela6.tipos.length >= 3 && tela6.parc && tela6.parc.length === 2, 'CAMP-086: ao recarregar, a tela mostra tudo o que foi salvo', JSON.stringify(tela6));
  await op.evaluate(c => nav('item/' + c), D(6)); await op.waitForSelector('#idet .dethdr', { timeout: 15000 }); await op.waitForTimeout(800);
  const pag6 = await txt(op, '#idet');
  const faltam6 = ['Fachada principal', '1:20', 'Alberto Faria', 'Família Sales', 'Estrutura', 'Burle'].filter(x => !pag6.includes(x));
  chk(await imgOk(op, '#idet img.img-grande'), 'CAMP-086: a página da folha mostra a imagem (a prévia do CAMP Vision)', pag6.slice(0, 200));
  chk(!faltam6.length, 'CAMP-086: a página da folha mostra os dados corrigidos (título, escala, endereço, cliente, parceiros)', 'faltam: ' + faltam6.join(', ') + ' | ' + pag6.slice(0, 1500));
  if (0) chk(/Fachada principal/.test(pag6) && /1:20/.test(pag6) && /Alberto Faria/.test(pag6) && /Família Sales/.test(pag6) && /Estrutura/.test(pag6), 'CAMP-086: a página da folha mostra os dados corrigidos', pag6.slice(0, 400));
  await print(op, 'b_pagina_folha');

  // ======================= CAMP-087: copiar parceiros =======================
  passo('CAMP-087: "Copiar para outras folhas"');
  // a D8 já tem um parceiro próprio (salvo antes, pela tela)
  await abrirConferir(op, PB, D(8)); await imgCarregou(op);
  await op.click('#cf-pane [data-parc-add]'); { const ln = op.locator('#cf-pane .parc-linha').last(); await ln.locator('.parc-esc').fill('Instalações Prediais SA'); await ln.locator('.parc-dis').selectOption({ index: 3 }) }
  await op.click('#cf-pane [data-rev-item="corrigida"]'); await confirmar(op);
  await espera(() => /Instalações/.test(um('SELECT parceiros FROM item WHERE codigo=?', D(8)) || ''), 6000);
  await abrirConferir(op, PB, D(6)); await op.waitForSelector('#cf-pane [data-parc-copiar]', { timeout: 10000 });
  await op.click('#cf-pane [data-parc-copiar]');
  await op.waitForSelector('#cf-pane .parc-copia', { timeout: 8000 });
  const caixaTxt = await txt(op, '#cf-pane .parc-copia');
  chk(/Estrutura/.test(caixaTxt) && /Burle/.test(caixaTxt), 'CAMP-087: a caixa diz o que vai ser copiado', caixaTxt.slice(0, 300));
  await op.check('#cf-pane [name="parc-alvo"][value="itens"]');
  for (const n of [8, 9, 10]) await op.check(`#cf-pane .parc-escolher input[value="${D(n)}"]`);
  chk(/já tem/.test(await txt(op, `#cf-pane .parc-escolher label:has(input[value="${D(8)}"])`)), 'CAMP-087: avisa que a D8 já tem parceiro');
  await op.click('#cf-pane [data-parc-copiar-ok]');
  chk(await op.waitForSelector('#cf-pane .parc-copiado', { timeout: 8000 }).then(() => true, () => false) && /3 folha/.test(await txt(op, '#cf-pane .parc-copiado')), 'CAMP-087: confirma "Copiado para 3 folha(s)"', await txt(op, '#cf-pane .parc-copia, #cf-pane .parc-copiado'));
  const p8 = JSON.parse(um('SELECT parceiros FROM item WHERE codigo=?', D(8)) || '[]'), p9 = JSON.parse(um('SELECT parceiros FROM item WHERE codigo=?', D(9)) || '[]'), p11 = JSON.parse(um('SELECT parceiros FROM item WHERE codigo=?', D(11)) || '[]');
  chk(p8.length === 3 && p8.some(p => /Instalações/.test(p.escritorio)), 'CAMP-087: a D8 manteve o parceiro dela e ganhou os 2 (nada apagado sem avisar)', JSON.stringify(p8));
  chk(p9.length === 2 && !p11.length, 'CAMP-087: a D9 ganhou os 2; a D11 (não escolhida) ficou igual', JSON.stringify({ p9, p11 }));
  const desf = await op.$('#cf-pane .parc-copiado [data-parc-copia-desfazer]');
  chk(!!desf, 'CAMP-087: dá para desfazer a cópia');
  if (desf) { await desf.click(); await confirmar(op);
    chk(await espera(() => JSON.parse(um('SELECT parceiros FROM item WHERE codigo=?', D(9)) || '[]').length === 0 && JSON.parse(um('SELECT parceiros FROM item WHERE codigo=?', D(8)) || '[]').length === 1, 6000),
      'CAMP-087: desfazer volta cada folha ao que tinha (D8 com 1, D9 e D10 sem nenhum)', JSON.stringify(sql('SELECT substr(codigo,-3), parceiros FROM item WHERE codigo IN (?,?,?)', D(8), D(9), D(10)))) }
  await print(op, 'b_copia_parceiros');

  // ======================= CAMP-088: sair com alteração não salva =======================
  passo('CAMP-088: sair com alteração não salva');
  await abrirConferir(op, PB, D(9)); await op.waitForSelector('#cf-pane #rv-titulo', { timeout: 10000 });
  const tit9 = um('SELECT titulo FROM item WHERE codigo=?', D(9));
  await op.fill('#rv-titulo', 'Título que não foi salvo');
  await op.click(`#cf-linhas .cf-linha[data-cf-folha="${D(10)}"]`);
  const perg1 = await op.waitForSelector('#conf-ov', { timeout: 4000 }).then(() => true, () => false);
  chk(perg1 && /sem salvar/i.test(await txt(op, '#conf-ov')), 'CAMP-088: trocar de folha pergunta "Sair sem salvar?"', await txt(op, '#conf-ov'));
  if (perg1) { await op.click('#conf-ov [data-conf="nao"], #conf-ov .btn:not([data-conf="sim"])'); await op.waitForTimeout(400) }
  chk(await atual(op) === D(9) && await op.inputValue('#rv-titulo') === 'Título que não foi salvo', 'CAMP-088: "Continuar editando" fica na folha com o texto digitado');
  await op.mouse.click(5, 300); await op.keyboard.press('ArrowDown');
  const perg2 = await op.waitForSelector('#conf-ov', { timeout: 4000 }).then(() => true, () => false);
  chk(perg2, 'CAMP-088: a seta ↓ também pergunta antes de trocar');
  if (perg2) { await op.click('#conf-ov [data-conf="nao"], #conf-ov .btn:not([data-conf="sim"])'); await op.waitForTimeout(400) }
  await op.click('#cfv [data-cf-projeto], [data-cf-projeto] >> nth=0');
  const perg3 = await op.waitForSelector('#conf-ov', { timeout: 4000 }).then(() => true, () => false);
  chk(perg3, 'CAMP-088: "← Projeto" pergunta antes de sair');
  if (perg3) { await op.click('#conf-ov [data-conf="sim"]'); await op.waitForTimeout(1200) }
  chk(/^projeto\//.test(await op.evaluate(() => rotaAtual())), 'CAMP-088: "Sair sem salvar" sai da tela', await op.evaluate(() => rotaAtual()));
  chk(um('SELECT titulo FROM item WHERE codigo=?', D(9)) === tit9, 'CAMP-088: nada foi gravado');
  // salvar de verdade depois de "continuar editando"
  await abrirConferir(op, PB, D(9)); await op.waitForSelector('#cf-pane #rv-titulo', { timeout: 10000 });
  await op.fill('#rv-titulo', 'Planta de locação'); await op.click('#cf-pane [data-rev-item="corrigida"]'); await confirmar(op);
  chk(await espera(() => um('SELECT titulo FROM item WHERE codigo=?', D(9)) === 'Planta de locação', 6000), 'CAMP-088: "Salvar correção" grava e libera a troca de folha');
  chk(!(await op.evaluate(() => temAlteracoes())), 'CAMP-088: depois de salvar, não há mais alteração pendente');
  // fechar a aba com alteração
  await op.fill('#rv-titulo', 'Outro texto não salvo');
  let pediu = false; op.on('dialog', d => { if (d.type() === 'beforeunload') pediu = true; d.dismiss().catch(() => {}) });
  await op.close({ runBeforeUnload: true }); await new Promise(r => setTimeout(r, 1200));
  chk(pediu, 'CAMP-088: fechar a aba com alteração pede confirmação do navegador');
});
