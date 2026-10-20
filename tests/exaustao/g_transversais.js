// Exaustão da página do projeto, grupo G (transversais): CAMP-115 a CAMP-121. Tudo pelo navegador, lotes pelo caminho real
// (estação + CAMP Vision; 500 folhas e XSS em g_montar.py). Rodar: bash tests/rodar_exaustao.sh tests/exaustao/g_transversais.js
const { execFileSync } = require('child_process');
const path = require('path');
const T = require('./_comum');
const { chk, passo, sql, um, espera, print, txt, confirmar, imgOk, loteReal, entrar, abrirProjeto, abrirConferir } = T;
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'g_montar.py'), ...a], { encoding: 'utf-8' }).trim();
const api = (pg, rota, metodo = 'POST', corpo) => pg.evaluate(async ([r, m, c]) => { const x = await fetch(r, { method: m, headers: { 'Content-Type': 'application/json' }, body: c ? JSON.stringify(c) : undefined }); return { st: x.status, j: await x.json().catch(() => ({})) } }, [rota, metodo, corpo]);
// CAMP-094: "Aprovar todas" deixa as folhas com aviso para conferir uma a uma; a montagem confere essas pela rota de cada folha
const conferirTodas = async (pg, l) => { const r = await api(pg, `/api/lotes/${l}/conferir-todas`); for (const f of (r.j && r.j.ficaram) || []) await api(pg, `/api/itens/${encodeURIComponent(f.codigo)}/revisao`, 'POST', { estado: 'conferida' }); return r };
const loteDe = P => um('SELECT id FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC LIMIT 1', P);
// botões/links de AÇÃO visíveis na página (o que a pessoa pode clicar)
const acoesVisiveis = pg => pg.evaluate(() => [...document.querySelectorAll('#pd button, #pd a.btn, #cfv button, #d-body button')].filter(b => b.offsetParent && !b.closest('[hidden]'))
  .map(b => ({ t: b.textContent.replace(/\s+/g, ' ').trim().slice(0, 40), d: [...b.attributes].filter(a => a.name.startsWith('data-')).map(a => a.name + (a.value ? '=' + a.value.slice(0, 20) : '')).join(' '), dis: b.disabled || b.getAttribute('aria-disabled') === 'true' })));
const semRolagemLateral = pg => pg.evaluate(() => { const d = document.scrollingElement; return { ok: d.scrollWidth <= window.innerWidth + 1, sw: d.scrollWidth, w: window.innerWidth,
  largos: [...document.querySelectorAll('body *')].filter(e => e.offsetParent && e.getBoundingClientRect().right > window.innerWidth + 2 && !e.closest('.cf-linhas,.tbl-wrap,pre,code,[data-rolagem]')).slice(0, 5).map(e => e.tagName + '.' + String(e.className).slice(0, 30) + ' ' + Math.round(e.getBoundingClientRect().right)) } });

T.rodar(async () => {
  // ---------------- montagem: três estados do mesmo tipo de lote (a conferir, aprovado, publicado) ----------------
  const A = loteReal('CASA PAPEIS A'), B = loteReal('CASA PAPEIS B'), C = loteReal('CASA PAPEIS C');
  const adm = await entrar('admin');
  for (const X of [B, C]) {
    sql("UPDATE erro SET situacao='ignorado', resolucao='montagem do teste' WHERE codigo LIKE ? AND gravidade='bloqueia'", X.P + '%');
    const l = loteDe(X.P); await conferirTodas(adm, l); const ap = await api(adm, `/api/lotes/${l}/aprovar`);
    chk(ap.st === 200, `montagem: lote de ${X.P} aprovado`, JSON.stringify(ap));
  }
  const pub = await api(adm, `/api/projetos/${C.P}/publicar-tudo`);
  chk(um('SELECT status_site FROM projeto WHERE codigo=?', C.P) === 'no_ar', 'montagem: projeto C publicado no site falso', JSON.stringify(pub).slice(0, 300));

  // ================= CAMP-115 · cada papel, cada botão =================
  passo('CAMP-115: cada papel, cada botão (leitura, operador, admin × a conferir, aprovado, publicado)');
  const REGRAS = {
    leitura: /data-pp=|data-rev-item|data-pjc-conferir|data-pjc-publicar|data-deste-projeto|data-rev-girar|data-rev-espelhar|data-fp-outro|data-rev-lote|data-cf-autoria-ok|data-cf-bloqueio-ok|data-dup-marcar|data-releitura|data-pp-cond/,
    operador: /data-pp=(aprovar|publicar)|data-pjc-publicar|data-pp-cond|data-pub-/,
  };
  for (const papel of ['leitura', 'operador', 'admin']) {
    const pg = papel === 'admin' ? adm : await entrar(papel);
    const r403 = []; pg.on('response', r => { if (r.status() === 403) r403.push(r.request().method() + ' ' + r.url().replace(T.BASE, '')) });
    for (const [rot, X] of [['a conferir', A], ['aprovado', B], ['publicado', C]]) {
      await abrirProjeto(pg, X.P);
      // todas as abas, as gavetas e a tela de conferir: nenhuma leitura (GET) pode dar 403
      for (const aba of await pg.$$eval('#pd [role="tab"]', l => l.map(t => t.textContent.trim()))) { await pg.click(`#pd [role="tab"]:has-text("${aba.split(' ')[0]}")`).catch(() => {}); await pg.waitForTimeout(700) }
      await abrirProjeto(pg, X.P);
      for (const g of await pg.$$eval('#pj-cards [data-pjc-gav]', l => [...new Set(l.map(b => b.dataset.pjcGav))])) { await pg.click(`#pj-cards [data-pjc-gav="${g}"]`).catch(() => {}); await pg.waitForTimeout(500) }
      const acoes = await acoesVisiveis(pg);
      await abrirConferir(pg, X.P); await pg.waitForTimeout(800);
      const acoesCf = await acoesVisiveis(pg);
      const ativos = [...acoes, ...acoesCf].filter(a => !a.dis);
      if (REGRAS[papel]) { const proibidos = ativos.filter(a => REGRAS[papel].test(a.d));
        chk(!proibidos.length, `CAMP-115: ${papel} (${rot}): nenhum botão de ação que não é dele`, JSON.stringify(proibidos)) }
      if (papel === 'operador' && rot === 'aprovado') chk(/um administrador publica|peça a um admin|falta um admin/i.test(await txt(pg, '#cfv') + ' ' + (await abrirProjeto(pg, X.P), await txt(pg, '#pj-cards'))), 'CAMP-115: operador (aprovado): a tela diz que quem publica é um admin', await txt(pg, '#pj-cards'));
      if (papel === 'admin' && rot === 'aprovado') { await abrirProjeto(pg, X.P); chk(!!(await pg.$('[data-pjc-publicar]:not([aria-disabled]):visible, [data-pp="publicar"]:visible')), 'CAMP-115: admin (aprovado): "Publicar" disponível', await txt(pg, '#pj-cards')) }
      if (papel === 'operador' && rot === 'a conferir') { await abrirProjeto(pg, X.P); chk(!!(await pg.$('[data-pjc-conferir]:visible')), 'CAMP-115: operador (a conferir): "Conferir" disponível') }
      await print(pg, `115_${papel}_${rot.replace(' ', '_')}`);
    }
    const lidas = r403.filter(x => x.startsWith('GET'));
    chk(!lidas.length, `CAMP-115: ${papel}: nenhuma tela do projeto pede dado que dá 403`, [...new Set(lidas)].join(' | '));
    // e o que aparece habilitado funciona: para o operador, clicar "Conferir"/"Está certo" não dá 403
    if (papel === 'operador') { r403.length = 0; await abrirConferir(pg, A.P);
      if (await pg.$('#cf-pane [data-rev-item="conferida"]')) { await pg.click('#cf-pane [data-rev-item="conferida"]'); await confirmar(pg); await pg.waitForTimeout(1200) }
      chk(!r403.length, 'CAMP-115: operador: "Está certo" não dá 403', r403.join(' | ')) }
    if (papel === 'leitura') { r403.length = 0; await abrirConferir(pg, A.P);
      chk(!(await pg.$('#cf-pane [data-rev-item]:visible')), 'CAMP-115: leitura na tela de conferir: vê a folha, sem "Está certo"/"Salvar correção"', JSON.stringify(await acoesVisiveis(pg)));
      chk(await imgOk(pg, '#cf-pane img'), 'CAMP-115: leitura vê a imagem da folha no conferir') }
  }

  // ================= CAMP-116 · celular e tablet =================
  passo('CAMP-116: celular (390 px) e tablet (768 px)');
  for (const [nome, vp] of [['celular', { width: 390, height: 844 }], ['tablet', { width: 768, height: 1024 }]]) {
    const pg = await entrar('operador', { viewport: vp });
    await abrirProjeto(pg, A.P);
    let s = await semRolagemLateral(pg); chk(s.ok, `CAMP-116: ${nome}: página do projeto sem rolagem lateral`, JSON.stringify(s));
    const cards = await pg.$$eval('#pj-cards .pjc', l => l.map(c => { const r = c.getBoundingClientRect(); return { x: Math.round(r.left), w: Math.round(r.width) } }));
    chk(cards.length === 4 && cards.every(c => c.x >= 0 && c.x + c.w <= vp.width + 1), `CAMP-116: ${nome}: os 4 cartões cabem na tela`, JSON.stringify(cards));
    if (nome === 'celular') chk(cards.every(c => c.w > vp.width * 0.7), 'CAMP-116: celular: cartões empilhados (um por linha)', JSON.stringify(cards));
    await print(pg, `116_${nome}_projeto`);
    const gv = await pg.$('#pj-gaveta:not([hidden])'); if (gv) { s = await semRolagemLateral(pg); chk(s.ok, `CAMP-116: ${nome}: gaveta aberta sem rolagem lateral`, JSON.stringify(s)) }
    await pg.evaluate(() => window.scrollTo(0, 0));
    await abrirConferir(pg, A.P);
    s = await semRolagemLateral(pg); chk(s.ok, `CAMP-116: ${nome}: tela de conferir sem rolagem lateral`, JSON.stringify(s));
    const img = await pg.$eval('#cf-pane img', i => { const r = i.getBoundingClientRect(); return { l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width) } }).catch(() => null);
    chk(img && img.l >= 0 && img.r <= vp.width + 1 && img.w > vp.width * 0.5, `CAMP-116: ${nome}: a imagem da folha cabe e é grande`, JSON.stringify(img));
    const bt = await pg.$('#cf-pane [data-rev-item="conferida"]');
    if (bt) { await bt.scrollIntoViewIfNeeded(); const r = await bt.boundingBox(); chk(r && r.x >= 0 && r.x + r.width <= vp.width + 1 && r.height >= 30, `CAMP-116: ${nome}: "Está certo" alcançável e com altura de toque (≥ 30 px)`, JSON.stringify(r));
      const antes = um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND revisao!='pendente'", A.P); await bt.click(); await confirmar(pg);
      chk(await espera(() => um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND revisao!='pendente'", A.P) === antes + 1), `CAMP-116: ${nome}: o toque em "Está certo" confere a folha`) }
    await print(pg, `116_${nome}_conferir`);
  }

  // ================= CAMP-117 · teclado e acessibilidade =================
  passo('CAMP-117: teclado e acessibilidade');
  {
    const K = loteReal('CASA TECLADO');
    const pg = await entrar('operador'); await abrirProjeto(pg, K.P);
    const semFoco = [], focados = new Set();
    await pg.evaluate(() => { document.activeElement && document.activeElement.blur(); document.querySelector('#pd').setAttribute('tabindex', '-1'); document.querySelector('#pd').focus() });
    for (let i = 0; i < 70; i++) {
      await pg.keyboard.press('Tab');
      const f = await pg.evaluate(() => { const e = document.activeElement; if (!e || !e.closest('#pd')) return null; const s = getComputedStyle(e);
        const visivel = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || (s.boxShadow && s.boxShadow !== 'none');
        return { id: e.tagName + ' ' + e.textContent.replace(/\s+/g, ' ').trim().slice(0, 25) + ' ' + [...e.attributes].filter(a => a.name.startsWith('data-')).map(a => a.name).join(','), visivel } });
      if (f) { focados.add(f.id); if (!f.visivel) semFoco.push(f.id) }
    }
    chk([...focados].some(x => /data-pjc-conferir|data-pjc-gav/.test(x)), 'CAMP-117: os botões dos cartões recebem foco pelo Tab', [...focados].slice(0, 15).join(' | '));
    chk(!semFoco.length, 'CAMP-117: todo elemento focado mostra o foco (contorno visível)', [...new Set(semFoco)].slice(0, 10).join(' | '));
    // aria-expanded acompanha a gaveta
    const g = await pg.$('#pj-cards [data-pjc-gav]');
    if (g) { const k = await g.getAttribute('data-pjc-gav'); const a0 = await g.getAttribute('aria-expanded'); await g.focus(); await pg.keyboard.press('Enter'); await pg.waitForTimeout(500);
      const a1 = await pg.getAttribute(`#pj-cards [data-pjc-gav="${k}"]`, 'aria-expanded'); chk(a0 !== a1, 'CAMP-117: Enter abre/fecha a gaveta e aria-expanded muda', `${a0} → ${a1}`) }
    // Esc cancela a confirmação (nada acontece)
    await abrirProjeto(pg, K.P);
    if (!(await pg.isVisible('#pj-probs'))) await pg.click('#pj-cards [data-pjc-gav="problemas"]').catch(() => {});
    const bd = await pg.$(`#pj-probs [data-deste-projeto]`);
    if (bd) { await bd.click(); const abriu = await pg.waitForSelector('#conf-ov', { timeout: 3000 }).then(() => true, () => false);
      chk(abriu && await pg.evaluate(() => document.activeElement && !!document.activeElement.closest('#conf-ov')), 'CAMP-117: a confirmação abre com o foco dentro dela');
      await pg.keyboard.press('Escape'); await pg.waitForTimeout(500);
      chk(!(await pg.$('#conf-ov')) && !um('SELECT COUNT(*) FROM item WHERE codigo=?', K.D(7)), 'CAMP-117: Esc fecha a confirmação sem fazer nada') }
    else chk(false, 'CAMP-117: botão "É deste projeto" na lista para testar a confirmação', await txt(pg, '#pj-gaveta'));
    // Esc fecha a gaveta lateral da revisão
    await pg.click(`.thumb[data-rev-abrir="${K.D(1)}"] .cap`).catch(() => {});
    if (await pg.waitForSelector('#d-body [data-rev-item="conferida"]', { timeout: 6000 }).then(() => true, () => false)) {
      await pg.keyboard.press('Escape'); await pg.waitForTimeout(600);
      chk(!(await pg.isVisible('#d-body [data-rev-item="conferida"]')), 'CAMP-117: Esc fecha a gaveta da folha') } else chk(false, 'CAMP-117: clicar na miniatura abre a gaveta da folha');
    // atalhos não disparam dentro de campos
    await abrirConferir(pg, K.P, K.D(2)); const giro0 = um('SELECT giro_manual FROM item WHERE codigo=?', K.D(2));
    await pg.click('#rv-titulo'); await pg.keyboard.type(' rk'); await pg.waitForTimeout(800);
    chk(um('SELECT giro_manual FROM item WHERE codigo=?', K.D(2)) === giro0 && !(await pg.isVisible('.aj-ov, #aj-ov, [data-aj-painel]').catch(() => false)) && /rk$/.test(await pg.inputValue('#rv-titulo')),
      'CAMP-117: "r" e "k" digitados no título não giram nem abrem o recorte', `giro ${giro0}→${um('SELECT giro_manual FROM item WHERE codigo=?', K.D(2))} título "${await pg.inputValue('#rv-titulo')}"`);
    // fora dos campos, o atalho R gira
    await pg.click('#cf-pane .cf-avisos, #cf-pane h2, #cf-prog').catch(() => {}); await pg.evaluate(() => document.activeElement && document.activeElement.blur());
    // (o título mudou: descarta para trocar de folha)
    await pg.keyboard.press('ArrowDown'); if (await pg.$('#conf-ov')) { await pg.click('#conf-ov [data-conf="nao"], #conf-ov [data-conf="descartar"]').catch(() => pg.keyboard.press('Escape')) }
    // anúncios: lista com aria-current, toast com role=status, contador ao vivo
    chk(await pg.$eval('#cf-linhas [aria-current="true"]', () => true).catch(() => false), 'CAMP-117: a folha aberta na lista tem aria-current');
    chk(await pg.evaluate(() => { const t = document.getElementById('toast'); return !!t && /status|alert/.test(t.getAttribute('role') || '') || (t && t.getAttribute('aria-live')) }), 'CAMP-117: avisos (toast) anunciados ao leitor de tela (role=status/aria-live)');
    chk(await pg.$eval('#cf-prog [role="status"], #cf-prog progress[aria-labelledby], #cf-cont', () => true).catch(() => false), 'CAMP-117: o progresso da conferência tem rótulo acessível');
    await print(pg, '117_teclado');
  }

  // ================= CAMP-118 · projeto grande =================
  passo('CAMP-118: projeto grande (500 folhas em S01–S08 e S99)');
  {
    const P = T.cv2('reservar', T.BASE, 'F026', 'CONJUNTO GRANDE', '1972'); T.cv2('processando', T.BASE, T.RAIZ, P, 'CONJUNTO GRANDE');
    const t0 = Date.now(); montar('grande', T.BASE, T.RAIZ, P, '500'); const tImp = Date.now() - t0;
    const n = um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', P);
    chk(n === 500, `CAMP-118: o aviso do CAMP Vision importou as 500 folhas (${(tImp / 1000).toFixed(1)} s, contando gravar as imagens)`, n);
    const pg = await entrar('operador');
    const tempos = {};
    let t = Date.now(); await pg.evaluate(c => { window.SL = null; window.PJ_GAV = null; nav('projeto/' + c) }, P);
    await pg.waitForSelector('#pj-cards .pjc[data-pjc="folhas"]', { timeout: 30000 }); tempos.cartoes = Date.now() - t;
    await pg.waitForFunction(() => document.querySelectorAll('#pd .thumb').length >= 50, null, { timeout: 30000 }).catch(() => {}); tempos.miniaturas = Date.now() - t;
    chk(tempos.miniaturas < 3000, `CAMP-118: a página do projeto abre em menos de 3 s (cartões ${tempos.cartoes} ms, folhas na tela ${tempos.miniaturas} ms)`);
    const nThumb = await pg.$$eval('#pd .thumb', l => l.length), carregadas = await pg.$$eval('#pd .thumb img', l => l.filter(i => i.complete && i.naturalWidth > 0).length);
    const lazy = await pg.$$eval('#pd .thumb img', l => l.filter(i => i.loading === 'lazy').length);
    chk(lazy >= nThumb * 0.9, `CAMP-118: miniaturas carregam aos poucos (loading=lazy em ${lazy} de ${nThumb}; ${carregadas} já carregadas na abertura)`);
    // contagens por série
    const series = await pg.$$eval('#pd h3', l => l.filter(h => h.nextElementSibling && /^\d+$/.test(h.nextElementSibling.textContent.trim())).map(h => h.textContent.trim() + ' ' + h.nextElementSibling.textContent.trim()));
    const soma = series.reduce((s, x) => s + Number(x.match(/(\d+)$/)[1]), 0);
    chk(series.length >= 9 && soma === 500, `CAMP-118: 9 séries com a contagem certa (soma ${soma})`, series.join(' | '));
    chk(/0 de 500|Conferidas 0 de 500/.test(await txt(pg, '.folhas-bar')), 'CAMP-118: a barra diz "Conferidas 0 de 500"', await txt(pg, '.folhas-bar'));
    for (const [f, nome] of [['conferir', 'A conferir'], ['', 'Todas']]) { t = Date.now(); await pg.click(`.folhas-bar [data-fl-f="${f}"]`); await pg.waitForTimeout(50); tempos['filtro ' + nome] = Date.now() - t }
    for (const k of ['p', 'g', 'm']) { t = Date.now(); await pg.click(`.folhas-bar [data-tam="${k}"]`); await pg.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))); tempos['tamanho ' + k.toUpperCase()] = Date.now() - t }
    const lentos = Object.entries(tempos).filter(([k, v]) => !/cartoes|miniaturas/.test(k) && v > 1000);
    chk(!lentos.length, `CAMP-118: filtros e P/M/G respondem em menos de 1 s (${Object.entries(tempos).filter(([k]) => !/cartoes|miniaturas/.test(k)).map(([k, v]) => `${k} ${v} ms`).join(', ')})`, JSON.stringify(lentos));
    await print(pg, '118_grande_projeto');
    t = Date.now(); await abrirConferir(pg, P); await pg.waitForSelector('#cf-pane [data-rev-item="conferida"]', { timeout: 30000 }); tempos.conferir = Date.now() - t;
    chk(tempos.conferir < 3000, `CAMP-118: a tela de conferir abre em menos de 3 s (${tempos.conferir} ms)`);
    const passos = []; for (let i = 0; i < 5; i++) { const a = await pg.evaluate(() => CONF.atual); t = Date.now(); await pg.keyboard.press('ArrowDown'); await espera(async () => (await pg.evaluate(() => CONF.atual)) !== a, 5000); passos.push(Date.now() - t) }
    chk(Math.max(...passos) < 1000, `CAMP-118: trocar de folha no conferir leva menos de 1 s (${passos.join(', ')} ms)`);
    const a1 = await pg.evaluate(() => CONF.atual); t = Date.now(); await pg.click('#cf-pane [data-rev-item="conferida"]'); await pg.waitForFunction(a => CONF.atual !== a && /1 de 500/.test(document.getElementById('cf-prog').textContent), a1, { timeout: 8000 }).catch(() => {}); tempos.conferirUma = Date.now() - t;
    chk(tempos.conferirUma < 2000, `CAMP-118: "Está certo" numa folha de 500 grava em menos de 2 s (${tempos.conferirUma} ms)`);
    chk(/1 de 500/.test(await txt(pg, '#cf-prog')), 'CAMP-118: contador do conferir "1 de 500"', await txt(pg, '#cf-prog'));
    await print(pg, '118_grande_conferir');
    T.linhas.push('      medido (CAMP-118): ' + Object.entries(tempos).map(([k, v]) => `${k}=${v}ms`).join(' · ') + ` · importar 500 folhas=${tImp}ms`);
  }

  // ================= CAMP-119 · dados estranhos =================
  passo('CAMP-119: dados estranhos (XSS, aspas, emoji, 300 caracteres)');
  {
    const P = T.cv2('reservar', T.BASE, 'F026', 'CASA ESTRANHA', '1972'); T.cv2('processando', T.BASE, T.RAIZ, P, 'CASA ESTRANHA');
    montar('xss', T.BASE, T.RAIZ, P);
    chk(um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', P) === 3, 'CAMP-119: as 3 folhas com dados estranhos foram importadas');
    // o nome do projeto também estranho (editar pelo cadastro, como alguém faria)
    sql('UPDATE projeto SET titulo=?, endereco_obra=? WHERE codigo=?', '<img src=x onerror="window.__xss=3"> Residência “Ação” 🏛️ ' + 'Muito Longo '.repeat(25), '<script>window.__xss=4</script> Rua', P);
    const xss = async (pg, onde) => { const v = await pg.evaluate(() => window.__xss); chk(v === undefined, `CAMP-119: nada executa (${onde})`, 'window.__xss=' + v) };
    const largura = async (pg, onde) => { const r = await pg.evaluate(() => [...document.querySelectorAll('#pd .pjc, #pd .dethdr, #pd .panel, #cfv .panel, #cf-pane, .cf-linha, #d-body, #toast, #pj-gaveta')].filter(e => e.offsetParent && e.scrollWidth > e.clientWidth + 4 && getComputedStyle(e).overflowX !== 'auto' && getComputedStyle(e).overflowX !== 'scroll').map(e => (e.id || e.className).toString().slice(0, 30) + ` ${e.scrollWidth}>${e.clientWidth}`));
      const s = await semRolagemLateral(pg); chk(!r.length && s.ok, `CAMP-119: layout não estoura (${onde})`, JSON.stringify(r) + ' ' + JSON.stringify(s)) };
    for (const papel of ['operador', 'admin']) {
      const pg = await entrar(papel);
      await abrirProjeto(pg, P); await xss(pg, `${papel}: página do projeto`); await largura(pg, `${papel}: página do projeto`); await print(pg, `119_${papel}_projeto`);
      for (const aba of ['Problemas', 'Dados', 'Histórico', 'Publicação']) { await pg.click(`#pd [role="tab"]:has-text("${aba}")`).catch(() => {}); await pg.waitForTimeout(900); await xss(pg, `${papel}: aba ${aba}`); await largura(pg, `${papel}: aba ${aba}`) }
      await abrirProjeto(pg, P);
      for (const g of ['problemas', 'dados', 'folhas']) { await pg.click(`#pj-cards [data-pjc-gav="${g}"]`).catch(() => {}); await pg.waitForTimeout(600); await xss(pg, `${papel}: gaveta ${g}`) }
      for (const n of [1, 2, 3]) { await abrirConferir(pg, P, `${P}-1972-S01-D0000${n}`); await xss(pg, `${papel}: conferir D${n}`); await largura(pg, `${papel}: conferir D${n}`) }
      await print(pg, `119_${papel}_conferir`);
      if (papel === 'operador') { await pg.click('#cf-pane [data-rev-item="conferida"]').catch(() => {}); await confirmar(pg); await pg.waitForTimeout(800); await xss(pg, 'toast depois de conferir'); await largura(pg, 'toast') }
      await pg.evaluate(c => nav('item/' + c), `${P}-1972-S01-D00001`); await pg.waitForTimeout(2000); await xss(pg, `${papel}: página da folha`);
      await pg.evaluate(() => nav('painel')); await pg.waitForTimeout(2500); await xss(pg, `${papel}: Painel inicial`);
      await pg.evaluate(c => nav('erros/' + c), P); await pg.waitForTimeout(2000); await xss(pg, `${papel}: tela Problemas`);
      const onclicks = await pg.evaluate(() => [...document.querySelectorAll('[onclick]')].map(e => e.getAttribute('onclick')).filter(o => /__xss|onerror|<script|Ação|Muito Longo/.test(o)));
      chk(!onclicks.length, `CAMP-119: ${papel}: nenhum dado do lote dentro de onclick`, onclicks.slice(0, 3).join(' | '));
    }
  }

  // ================= CAMP-120 · mudança com a página aberta =================
  passo('CAMP-120: mudança enquanto a página está aberta');
  {
    const M = loteReal('CASA AO VIVO');
    sql("UPDATE erro SET situacao='ignorado', resolucao='montagem do teste' WHERE codigo LIKE ? AND gravidade='bloqueia'", M.P + '%');
    const op = await entrar('operador'); await abrirProjeto(op, M.P);
    // (a) o CAMP Vision relê o lote (novo aviso) com a página aberta
    T.cv2('pronto', T.BASE, T.RAIZ, M.P);
    const viuA = await espera(() => op.$('[data-pj-mudou]:visible').then(Boolean), 45000);
    chk(viuA, 'CAMP-120: o CAMP Vision releu o lote: a página avisa que mudou (com "Atualizar")', await txt(op, '#pd'));
    await print(op, '120_aviso_mudou');
    if (viuA) { await op.click('[data-pj-mudou] button'); await op.waitForTimeout(1500); chk(!(await op.$('[data-pj-mudou]:visible')), 'CAMP-120: "Atualizar" recarrega a página do projeto e o aviso some') }
    // (b) a operadora está editando o título no conferir quando outra pessoa aprova o lote
    await abrirConferir(op, M.P, M.D(2)); await op.fill('#rv-titulo', 'Título que eu estava digitando');
    const ad2 = await entrar('admin'); const l = loteDe(M.P); await conferirTodas(ad2, l); await api(ad2, `/api/lotes/${l}/aprovar`);
    const viuB = await espera(() => op.$('[data-pj-mudou]:visible').then(Boolean), 45000);
    chk(viuB, 'CAMP-120: outra pessoa aprovou: a tela de conferir avisa que mudou', await txt(op, '#cfv'));
    chk(await op.inputValue('#rv-titulo').catch(() => '') === 'Título que eu estava digitando', 'CAMP-120: o aviso não apaga o que a pessoa estava digitando');
    // o botão velho não dá erro sem explicação
    const resp = []; op.on('response', r => { if (/\/revisao|\/itens\//.test(r.url()) && r.request().method() === 'POST') resp.push(r.status()) });
    await op.click('#cf-pane [data-rev-item="corrigida"]').catch(() => {}); await confirmar(op); await op.waitForTimeout(1500);
    const t1 = await txt(op, '#toast');
    chk(!resp.some(s => s >= 500) && (resp.every(s => s < 400) || /aprovad|reabr|admin|mudou/i.test(t1)), 'CAMP-120: salvar depois da aprovação do outro: grava ou explica em português (sem 500)', `${resp.join(',')} · ${t1}`);
    await print(op, '120_depois_aprovar');
    // (c) "Ler dados agora" termina com a página aberta
    const R = loteReal('CASA RELEITURA'); await abrirProjeto(op, R.P);
    const pr = await api(op, `/api/projetos/${R.P}/releitura`, 'POST', { motivo: 'teste de exaustão' });
    const pid = (pr.j && (pr.j.id || (pr.j.pedido || {}).id)) || um('SELECT id FROM pedido_releitura WHERE projeto_codigo=? ORDER BY id DESC LIMIT 1', R.P);
    await abrirProjeto(op, R.P);
    const fim = await op.evaluate(async id => (await fetch(`/api/estacoes/pedidos-releitura/${id}/concluido`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ok: true, mensagem: 'relido' }) })).status, pid);
    const viuC = await espera(() => op.$('[data-pj-mudou]:visible').then(Boolean), 45000);
    chk(fim === 200 && viuC, 'CAMP-120: "Ler dados agora" terminou com a página aberta: a página avisa', `concluido=${fim}`);
  }

  // ================= CAMP-121 · navegação, link direto, sessão expirada =================
  passo('CAMP-121: navegação, link direto, recarregar e sessão expirada');
  {
    const N = loteReal('CASA NAVEGA');
    const pg = await entrar('operador'); await abrirProjeto(pg, N.P);
    await pg.click(`#pj-cards [data-pjc-conferir="${N.P}"]`); await pg.waitForSelector('#cf-pane [data-rev-item="conferida"]', { timeout: 15000 });
    await pg.evaluate(() => document.activeElement && document.activeElement.blur()); await pg.keyboard.press('ArrowDown'); await pg.waitForTimeout(800);
    const rotaCf = await pg.evaluate(() => rotaAtual());
    await pg.goBack(); await pg.waitForTimeout(1500);
    chk((await pg.evaluate(() => rotaAtual())) === 'projeto/' + N.P && !!(await pg.$('#pj-cards')), 'CAMP-121: Voltar do conferir volta à página do projeto', await pg.evaluate(() => rotaAtual()));
    await pg.goForward(); await pg.waitForTimeout(1500);
    chk((await pg.evaluate(() => rotaAtual())).startsWith('conferir/' + N.P), 'CAMP-121: Avançar volta ao conferir', `${rotaCf} → ${await pg.evaluate(() => rotaAtual())}`);
    // link direto numa aba nova
    const nova = await pg.context().newPage(); await nova.goto(`${T.BASE}/#conferir/${N.P}/${N.D(4)}`);
    await nova.waitForFunction(() => typeof CONF !== 'undefined' && CONF.atual, null, { timeout: 15000 }).catch(() => {});
    chk((await nova.evaluate(() => typeof CONF !== 'undefined' && CONF.atual)) === N.D(4), 'CAMP-121: link direto #conferir/<projeto>/<folha> abre a folha certa', await nova.evaluate(() => typeof CONF !== 'undefined' && CONF.atual));
    const nova2 = await pg.context().newPage(); await nova2.goto(`${T.BASE}/#projeto/${N.P}`); await nova2.waitForSelector('#pj-cards .pjc', { timeout: 15000 }).catch(() => {});
    chk(!!(await nova2.$('#pj-cards .pjc')), 'CAMP-121: link direto #projeto/<projeto> abre o projeto');
    await nova.close(); await nova2.close();
    // recarregar no meio da conferência: o que foi salvo continua, e volta à mesma folha
    await abrirConferir(pg, N.P, N.D(1)); await pg.click('#cf-pane [data-rev-item="conferida"]'); await confirmar(pg); await pg.waitForTimeout(1200);
    const atual = await pg.evaluate(() => CONF.atual); await pg.reload(); await pg.waitForFunction(() => typeof CONF !== 'undefined' && CONF.atual, null, { timeout: 15000 }).catch(() => {});
    chk(um('SELECT revisao FROM item WHERE codigo=?', N.D(1)) === 'conferida' && /1 de/.test(await txt(pg, '#cf-prog')), 'CAMP-121: recarregar: a folha conferida continua conferida', await txt(pg, '#cf-prog'));
    chk((await pg.evaluate(() => CONF.atual)) === atual, 'CAMP-121: recarregar volta à mesma folha', `${atual} → ${await pg.evaluate(() => CONF.atual)}`);
    // sessão expirada com alteração aberta
    await abrirConferir(pg, N.P, N.D(3)); await pg.fill('#rv-titulo', 'Título digitado antes de cair a sessão');
    sql('DELETE FROM sessao');
    await pg.click('#cf-pane [data-rev-item="corrigida"]'); await confirmar(pg);
    const pediu = await pg.waitForSelector('#login.on', { timeout: 8000 }).then(() => true, () => false);
    chk(pediu, 'CAMP-121: sessão expirada: o painel pede login (sem perder a tela)', await txt(pg, '#toast'));
    await print(pg, '121_sessao_expirada');
    if (pediu) {
      await pg.fill('#lg-email', 'operador@camp.arq.br'); await pg.fill('#lg-senha', 'senha-operador-123'); await pg.press('#lg-senha', 'Enter');
      await pg.waitForSelector('#login.on', { state: 'detached', timeout: 10000 }).catch(() => {}); await pg.waitForFunction(() => !document.querySelector('#login.on'), null, { timeout: 10000 }).catch(() => {}); await pg.waitForTimeout(1500);
      chk((await pg.evaluate(() => rotaAtual())) === `conferir/${N.P}/${N.D(3)}`, 'CAMP-121: depois do login volta à mesma tela (a mesma folha)', await pg.evaluate(() => rotaAtual()));
      chk((await pg.inputValue('#rv-titulo').catch(() => '')) === 'Título digitado antes de cair a sessão', 'CAMP-121: o que estava digitado continua no campo', await pg.inputValue('#rv-titulo').catch(() => '(sem campo)'));
      await pg.click('#cf-pane [data-rev-item="corrigida"]'); await confirmar(pg);
      chk(await espera(() => um('SELECT titulo FROM item WHERE codigo=?', N.D(3)) === 'Título digitado antes de cair a sessão'), 'CAMP-121: e "Salvar correção" grava depois de entrar de novo', um('SELECT titulo FROM item WHERE codigo=?', N.D(3)));
    }
  }
});
