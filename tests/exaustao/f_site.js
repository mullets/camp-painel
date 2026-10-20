// Exaustão da página do projeto — grupo F: site e publicação (CAMP-109 a CAMP-114). Tudo por clique no navegador; o lote nasce pelo
// caminho real (estação reserva, CAMP Vision grava a pasta e avisa). Site FALSO com falhas armáveis (tests/exaustao/f_servidor_falho.py).
// Rodar: bash tests/rodar_exaustao.sh tests/exaustao/f_site.js   (o executor sobe o site falso com a queda armável do CAMP-111)
const { execFileSync } = require('child_process');
const fs = require('fs'), path = require('path');
const T = require('./_comum');
const { chk, passo, sql, um, espera, print, txt, confirmar, imgOk } = T;
const FALHA = process.env.F_FALHA_ARQ;   // arma a falha do site falso (a 4ª folha cai) — e FALHA+'_imagem' faz a troca de imagem falhar

// lote LIMPO de n folhas (sem retirados nem problemas), pelo caminho real; teste=true → lote de teste
const montar = (...a) => execFileSync('python3', [path.join(__dirname, 'f_montar.py'), ...a], { encoding: 'utf-8' }).trim();
const loteLimpo = (nome, n, teste = false) => {
  const P = T.cv2('reservar', T.BASE, 'F026', nome, '1972');
  const t = teste ? ['--teste'] : [], avisos = [montar('processando', T.BASE, T.RAIZ, P, nome, ...t), montar('pronto', T.BASE, T.RAIZ, P, String(n), ...t)];
  return { P, D: i => `${P}-1972-S01-D${String(i).padStart(5, '0')}`, avisos };
};
// confere todas as folhas pela tela de conferir ("Está certo e próxima" até o fim)
const conferirTudo = async (pg, P) => {
  await T.abrirConferir(pg, P);
  for (let i = 0; i < 40; i++) {
    if (await pg.$('#cf-pane [data-fim-passo]')) break;
    const b = await pg.$('#cf-pane [data-rev-item="conferida"]'); if (!b) break;
    const atual = await pg.evaluate(() => CONF.atual);
    await b.click(); await confirmar(pg);
    await espera(async () => (await pg.evaluate(() => CONF.atual)) !== atual || !!(await pg.$('#cf-pane [data-fim-passo]')), 8000);
  }
  return !!(await pg.$('#cf-pane [data-fim-passo]'));
};
const aprovarNoProjeto = async (ad, P) => {
  await T.abrirProjeto(ad, P);
  if (!(await ad.waitForSelector('[data-pp="aprovar"]:visible', { timeout: 10000 }).then(() => true, () => false))) return false;
  await ad.click('[data-pp="aprovar"]:visible'); await confirmar(ad);
  return espera(() => um('SELECT aprovado_em IS NOT NULL FROM lista_processamento WHERE projeto_codigo=? ORDER BY id DESC LIMIT 1', P) === 1);
};
const cartaoSite = (pg) => txt(pg, '#pj-cards .pjc[data-pjc="site"]');
const btPublicar = (pg) => pg.$('#pj-cards [data-pjc-publicar]');
// abre a publicação guiada pelo cartão Site e clica "Publicar agora"; devolve o texto da janela ao terminar
const publicarPeloCartao = async (ad, P) => {
  await T.abrirProjeto(ad, P);
  const b = await ad.waitForSelector('#pj-cards [data-pjc-publicar]:not([aria-disabled="true"])', { timeout: 10000 }).catch(() => null);
  if (!b) return { ok: false, texto: 'sem botão Publicar' };
  await b.click();
  if (!(await ad.waitForSelector('#pub-go:not([disabled])', { timeout: 15000 }).then(() => true, () => false))) return { ok: false, texto: await txt(ad, '#d-body') };
  await ad.click('#pub-go');
  await espera(async () => !!(await ad.$('#d-body .pub-resultado')) || /não subiram|Não consegui|nada foi publicado|Tentar de novo/i.test(await txt(ad, '#d-body')), 60000);
  return { ok: !!(await ad.$('#d-body .pub-resultado')), texto: await txt(ad, '#d-body') };
};

T.rodar(async () => {
  const ad = await T.entrar('admin'), op = await T.entrar('operador');

  // ---------------- CAMP-109 ----------------
  passo('CAMP-109: direitos do fundo não autorizados');
  sql("UPDATE direitos_fundo SET situacao='nao_definida', documento_autorizacao=NULL WHERE fundo_codigo='F026'");
  const a = loteLimpo('CASA DIREITOS', 3);
  chk(await conferirTudo(ad, a.P), 'CAMP-109: as 3 folhas conferidas pela tela de conferir');
  chk(await aprovarNoProjeto(ad, a.P), 'CAMP-109: lote aprovado');
  await T.abrirProjeto(ad, a.P); await espera(async () => !/verificando/.test(await cartaoSite(ad)));
  const s1 = await cartaoSite(ad);
  chk(/direitos/i.test(s1), 'CAMP-109: cartão Site diz o que falta (direitos do fundo)', s1);
  const bDir = await ad.$('#pj-cards .pjc[data-pjc="site"] [data-pp-cond="direitos"]');
  chk(!!bDir && /direitos/i.test(await bDir.innerText()), 'CAMP-109: botão que leva a resolver ("Definir direitos do fundo")', s1);
  const bp1 = await btPublicar(ad);
  chk(!bp1 || (await bp1.getAttribute('aria-disabled')) === 'true', 'CAMP-109: Publicar não fica liberado enquanto faltam os direitos');
  await print(ad, '109_direitos_faltam');
  if (bDir) {
    await bDir.click();
    const form = await ad.waitForSelector('#d-body input[name="dr-sit-op"][value="autorizado"]', { state: 'attached', timeout: 10000 }).then(() => true, () => false);
    chk(form, 'CAMP-109: abre o formulário de direitos do fundo com a opção "Autorizado"', await txt(ad, '#d-body'));
    await print(ad, '109_form_direitos');
    if (form) {
      await ad.check('#d-body input[name="dr-sit-op"][value="autorizado"]');
      if (!(await ad.inputValue('#dr-tit'))) await ad.fill('#dr-tit', 'Família Bussab');
      if (!(await ad.inputValue('#dr-doc'))) await ad.fill('#dr-doc', 'Termo de doação assinado pela família');
      const salvar = ad.locator('#d-body button', { hasText: /Salvar/ }).first();
      if (await salvar.count()) { await salvar.click(); await confirmar(ad) }
    }
    chk(await espera(() => um("SELECT situacao FROM direitos_fundo WHERE fundo_codigo='F026'") === 'autorizado'), 'CAMP-109: direitos gravados como autorizados', JSON.stringify(sql("SELECT * FROM direitos_fundo WHERE fundo_codigo='F026'")));
    const liberou = await espera(async () => { const b = await ad.$('#pj-cards [data-pjc-publicar]'); return !!b && (await b.getAttribute('aria-disabled')) !== 'true' && await b.isVisible() }, 10000);
    chk(liberou, 'CAMP-109: ao autorizar, "Publicar" libera na página do projeto sem recarregar', `rota=${await ad.evaluate(() => rotaAtual())} site=${await cartaoSite(ad)}`);
    await print(ad, '109_direitos_ok');
  }
  sql("INSERT OR REPLACE INTO direitos_fundo (fundo_codigo, situacao, titular, documento_autorizacao) VALUES ('F026','autorizado','Família','Termo assinado')");

  // ---------------- CAMP-110 ----------------
  passo('CAMP-110: publicar com problema que impede publicar');
  const b = T.loteReal('CASA BLOQUEADA');   // D00007 e D00008: "com identificação para outra pasta — fora da publicação até resolver" (bloqueia)
  chk(um("SELECT COUNT(*) FROM erro WHERE codigo LIKE ? AND gravidade='bloqueia' AND situacao='aberto'", b.P + '%') >= 2, 'CAMP-110: o lote chega com 2 problemas que impedem publicar');
  await T.abrirConferir(ad, b.P);
  chk(await conferirTudo(ad, b.P), 'CAMP-110: admin confere todas as folhas');
  const aprF = await ad.$('#cf-pane [data-fim-passo] [data-pp="aprovar"]');
  if (aprF) { await aprF.click(); await confirmar(ad) }
  await espera(async () => !(await ad.$('#cf-pane [data-fim-passo] [data-pp="aprovar"]')), 10000);
  await ad.waitForTimeout(1500);
  const fimTxt = await txt(ad, '#cf-pane [data-fim-passo]');
  chk(/impede|bloque|problema/i.test(fimTxt) && !(await ad.$('#cf-pane [data-fim-passo] [data-pp="publicar"]')), 'CAMP-110: o fim da conferência diz o que impede publicar (sem "Publicar")', fimTxt);
  chk(!!(await ad.$('#cf-pane [data-fim-passo] a[href*="erros"], #cf-pane [data-fim-passo] [data-pp-cond], #cf-pane [data-fim-passo] [data-pjc-resolver]')), 'CAMP-110: o fim da conferência tem o link para os problemas', fimTxt);
  await print(ad, '110_fim_conferir');
  await T.abrirProjeto(ad, b.P); await espera(async () => !/verificando/.test(await cartaoSite(ad)));
  const bp2 = await btPublicar(ad), s2 = await cartaoSite(ad);
  chk(!!bp2 && (await bp2.getAttribute('aria-disabled')) === 'true' && /Resolva os problemas/.test(await bp2.getAttribute('title') || ''), 'CAMP-110: Publicar desligado com "Resolva os problemas que impedem publicar"', s2);
  chk(/libera quando os problemas/i.test(s2), 'CAMP-110: cartão Site diz que libera quando os problemas forem resolvidos', s2);
  if (bp2 && await bp2.isEnabled()) { await bp2.click(); await ad.waitForTimeout(800) }
  chk(!(await ad.$('#pub-go:not([disabled])')), 'CAMP-110: clicar no Publicar desligado não publica');
  chk(!!(await ad.$('#pj-cards .pjc[data-pjc="problemas"] [data-pjc-resolver], #pj-cards .pjc[data-pjc="problemas"] [data-pjc-gav="problemas"]')), 'CAMP-110: o cartão Problemas tem o caminho para resolver');
  await print(ad, '110_publicar_desligado');
  // resolve: as duas são mesmo de outra obra
  await ad.evaluate(c => nav('erros/' + c), b.P);
  for (const n of [7, 8]) {
    const ok = await ad.waitForSelector(`#err-body [data-fp-outro="${b.D(n)}"]`, { timeout: 10000 }).then(() => true, () => false);
    if (ok) { await ad.click(`#err-body [data-fp-outro="${b.D(n)}"]`); await confirmar(ad); await espera(() => um("SELECT COUNT(*) FROM erro WHERE codigo=? AND situacao IN ('aberto','em_correcao')", b.D(n)) === 0) }
  }
  chk(um("SELECT COUNT(*) FROM erro WHERE codigo LIKE ? AND gravidade='bloqueia' AND situacao IN ('aberto','em_correcao')", b.P + '%') === 0, 'CAMP-110: resolvidos pela tela Problemas ("É de outro projeto…")');
  await T.abrirProjeto(ad, b.P);
  const liberou2 = await espera(async () => { const x = await btPublicar(ad); return !!x && (await x.getAttribute('aria-disabled')) !== 'true' }, 10000);
  chk(liberou2, 'CAMP-110: resolveu → "Publicar" liga', await cartaoSite(ad));
  await print(ad, '110_publicar_ligado');

  // ---------------- CAMP-111 ----------------
  passo('CAMP-111: a publicação cai no meio (folha 4 de 10)');
  const c = loteLimpo('CASA QUEDA', 10);
  chk(um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', c.P) === 10, 'CAMP-111: 10 folhas importadas');
  chk(await conferirTudo(ad, c.P), 'CAMP-111: 10 folhas conferidas');
  chk(await aprovarNoProjeto(ad, c.P), 'CAMP-111: lote aprovado');
  fs.writeFileSync(FALHA, '1');   // a 4ª folha enviada ao site vai cair
  const r1 = await publicarPeloCartao(ad, c.P);
  await print(ad, '111_caiu');
  chk(!r1.ok && /não subiram|nada foi publicado|502/i.test(r1.texto), 'CAMP-111: a queda aparece em português e diz que nada foi publicado', r1.texto.slice(0, 400));
  chk(um('SELECT status_site FROM projeto WHERE codigo=?', c.P) !== 'no_ar' && um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND status_site='no_ar'", c.P) === 0, 'CAMP-111: nada ficou público pela metade');
  const subiram = um('SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND tainacan_item_id IS NOT NULL', c.P);
  chk(subiram === 9, `CAMP-111: as outras 9 folhas subiram como rascunho, só a 4ª ficou: ${subiram}`);
  chk(/1 folha não subiu ao site/.test(r1.texto), 'CAMP-111: a frase concorda ("1 folha não subiu ao site")', r1.texto.slice(0, 300));
  const deNovo = ad.locator('#d-body #pub-go', { hasText: /Tentar de novo/ }).first();
  const temDeNovo = await deNovo.count() > 0 && await deNovo.isEnabled();
  chk(temDeNovo, 'CAMP-111: a janela oferece tentar de novo', r1.texto.slice(0, 300));
  if (temDeNovo) { await deNovo.click(); await espera(async () => !!(await ad.$('#d-body .pub-resultado')), 60000) }
  else { await ad.evaluate(() => closeDrawer(true)); await publicarPeloCartao(ad, c.P) }
  await print(ad, '111_retomou');
  chk(um('SELECT status_site FROM projeto WHERE codigo=?', c.P) === 'no_ar' && um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND status_site='no_ar'", c.P) === 10, 'CAMP-111: tentar de novo continua de onde parou e publica as 10');
  const noSite = sql("SELECT codigo_detectado, COUNT(*) FROM wp_item WHERE projeto_detectado=? AND colecao_id=8013 GROUP BY codigo_detectado HAVING COUNT(*)>1", c.P);
  chk(um("SELECT COUNT(*) FROM wp_item WHERE projeto_detectado=? AND colecao_id=8013", c.P) === 10 && !noSite.length, 'CAMP-111: nenhuma folha duplicada no site (10 registros, um por folha)', JSON.stringify(noSite));
  chk(um("SELECT COUNT(*) FROM wp_item WHERE codigo_detectado=? AND colecao_id=8007", c.P) === 1, 'CAMP-111: a página do projeto foi criada uma vez só');
  await ad.evaluate(() => closeDrawer(true));

  // ---------------- CAMP-112 ----------------
  passo('CAMP-112: folha publicada girada → "Atualizar imagem no site"');
  const F = c.D(2);
  await T.abrirProjeto(op, c.P);
  await op.click(`.thumb[data-rev-abrir="${F}"] .cap`);
  const girou = await op.waitForSelector(`#d-body [data-rev-girar="90"]`, { timeout: 10000 }).then(() => true, () => false);
  chk(girou, 'CAMP-112: a operadora abre a folha publicada e tem o botão de girar');
  if (girou) { await op.click(`#d-body [data-rev-girar="90"]`); await confirmar(op) }
  chk(await espera(() => um('SELECT giro_manual FROM item WHERE codigo=?', F) === 90), 'CAMP-112: giro gravado no painel (90°)', um('SELECT giro_manual FROM item WHERE codigo=?', F));
  chk(await op.waitForSelector(`#d-body [data-img-site-pend="${F}"]`, { timeout: 10000 }).then(() => true, () => false), 'CAMP-112: a faixa "A imagem no site ainda é a antiga" aparece na hora', await txt(op, '#d-body'));
  chk(!(await op.$(`#d-body [data-img-site="${F}"]`)), 'CAMP-112: a operadora não tem o botão de atualizar o site (é de admin)');
  await print(op, '112_faixa_operadora');
  await op.evaluate(() => closeDrawer(true));
  // admin, site fora: "Tentar de novo". Num navegador à parte: o 502 é a resposta CERTA do painel quando o site recusa (não é erro do painel)
  fs.writeFileSync(FALHA + '_imagem', '1');
  {
    const { chromium } = require(process.env.PLAYWRIGHT_MOD || '/opt/node22/lib/node_modules/playwright');
    const br2 = await chromium.launch({ executablePath: process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
    const p2 = await (await br2.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
    const errJs = []; p2.on('pageerror', e => errJs.push(e.message));
    await p2.goto(T.BASE + '/'); await p2.fill('#lg-email', 'rafael@camp.arq.br'); await p2.fill('#lg-senha', 'senha-bem-longa-123'); await p2.press('#lg-senha', 'Enter');
    await p2.waitForFunction(() => typeof EU !== 'undefined' && !!EU, null, { timeout: 15000 });
    await p2.evaluate(c2 => nav('item/' + c2), F); await p2.waitForTimeout(1500);
    const temBt = await p2.waitForSelector(`#idet [data-img-site="${F}"]`, { timeout: 10000 }).then(() => true, () => false);
    chk(temBt, 'CAMP-112: admin vê "Atualizar imagem no site" na página da folha');
    if (temBt) await p2.click(`#idet [data-img-site="${F}"]`);
    chk(await espera(async () => (await txt(p2, `#idet [data-img-site="${F}"]`)) === 'Tentar de novo'), 'CAMP-112: site fora do ar → "Tentar de novo" e a faixa continua', await txt(p2, '#idet [data-img-site-pend]'));
    const t112 = await txt(p2, '#toast'); chk(/continua a antiga|não aceitou/.test(t112), 'CAMP-112: mensagem em português (a imagem do site continua a antiga)', t112);
    chk(um("SELECT COUNT(*) FROM divergencia_site WHERE codigo=? AND campo='pendente_imagem_ajustada' AND COALESCE(resolvida,0)=0", F) === 1, 'CAMP-112: com o site fora, a pendência continua aberta');
    await p2.screenshot({ path: path.join(T.SAIDA, '112b_tentar_de_novo.png') });
    chk(!errJs.length, 'CAMP-112: nenhum erro de JavaScript na falha do site', errJs.join(' | '));
    await br2.close();
  }
  await ad.evaluate(c2 => nav('item/' + c2), F); await ad.waitForTimeout(1500);
  await ad.waitForSelector(`#idet [data-img-site="${F}"]`, { timeout: 10000 }).catch(() => {});
  fs.unlinkSync(FALHA + '_imagem');
  await ad.click(`#idet [data-img-site="${F}"]`);
  chk(await espera(async () => !(await ad.$(`#idet [data-img-site-pend="${F}"]`))), 'CAMP-112: site respondeu → a faixa some');
  chk(um("SELECT COUNT(*) FROM divergencia_site WHERE codigo=? AND campo='pendente_imagem_ajustada' AND COALESCE(resolvida,0)=0", F) === 0, 'CAMP-112: a pendência fica resolvida no banco');
  await ad.reload(); await ad.waitForTimeout(1500);
  chk(!(await ad.$(`[data-img-site-pend="${F}"]`)), 'CAMP-112: recarregando, a faixa continua sumida');
  await print(ad, '112_atualizada');

  // ---------------- CAMP-113 ----------------
  passo('CAMP-113: despublicar, republicar e trocar a capa');
  await T.abrirProjeto(ad, c.P);
  const nova = c.D(5);
  await ad.evaluate(c2 => nav('item/' + c2), nova); await ad.waitForTimeout(1500);
  const bCapa = await ad.$(`[data-capa-usar]:visible`);
  chk(!!bCapa, 'CAMP-113: a página da folha tem "Usar como capa"');
  if (bCapa) { await bCapa.click(); await confirmar(ad) }
  chk(await espera(() => um('SELECT capa_item FROM projeto WHERE codigo=?', c.P) === nova), 'CAMP-113: a capa do projeto passa a ser a D00005');
  chk(await espera(() => um("SELECT COUNT(*) FROM evento WHERE codigo=? AND tipo='site_capa'", c.P) >= 1), 'CAMP-113: a capa foi enviada ao site');
  const tc = await txt(ad, '#toast'); chk(/site já mostra|capa/i.test(tc), 'CAMP-113: aviso diz que o site já mostra a nova capa', tc);
  await T.abrirProjeto(ad, c.P);
  chk(await ad.$eval(`.thumb[data-rev-abrir="${nova}"], .thumb[data-nav="item/${nova}"]`, t => /capa/.test(t.textContent)).catch(() => false), 'CAMP-113: a miniatura da D00005 mostra o selo "capa"');
  await print(ad, '113_capa');
  // despublicar pelo "Mais ⋯": o item do menu tem de dizer "despublicar" (a pessoa precisa achar)
  await ad.click('#pd .pj-mais-menu > summary');
  const itemDesp = ad.locator('#pd .pj-mais-menu [role="menuitem"]', { hasText: /despublicar/i }).first();
  const achou = await itemDesp.count() > 0 && await itemDesp.isVisible();
  chk(achou, 'CAMP-113: o menu "Mais ⋯" mostra "despublicar" num projeto no ar', await txt(ad, '#pd .pj-mais-menu'));
  await print(ad, '113_menu_mais');
  if (achou) await itemDesp.click(); else await ad.click('#pd .pj-mais-menu [data-pj-mais]').catch(() => {});
  const bDesp = await ad.waitForSelector('[data-mais="despublicar"]:not([disabled])', { timeout: 8000 }).then(() => true, () => false);
  chk(bDesp, 'CAMP-113: a lista de ações oferece "Despublicar"');
  if (bDesp) {
    await ad.click('[data-mais="despublicar"]');
    await ad.waitForTimeout(800); await print(ad, '113_despublicar_form');
    const go = ad.locator('#d-body button', { hasText: /^Despublicar$/ }).first();
    chk(await go.count() > 0 && !(await go.isEnabled()), 'CAMP-113: "Despublicar" só libera depois de marcar "Entendi"');
    const ent = await ad.$('#d-body input[type="checkbox"]'); if (ent) await ent.check();
    if (await go.count()) { await go.click(); await confirmar(ad) }
  }
  chk(await espera(() => um('SELECT status_site FROM projeto WHERE codigo=?', c.P) === 'fora_do_ar'), 'CAMP-113: projeto despublicado (fora do ar)', um('SELECT status_site FROM projeto WHERE codigo=?', c.P));
  chk(um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND status_site='no_ar'", c.P) === 0, 'CAMP-113: nenhuma folha fica pública', JSON.stringify(sql("SELECT status_site, COUNT(*) FROM item WHERE projeto_codigo=? GROUP BY 1", c.P)));
  await T.abrirProjeto(ad, c.P); await espera(async () => !/verificando/.test(await cartaoSite(ad)));
  const s3 = await cartaoSite(ad);
  chk(/Despublicado/i.test(s3), 'CAMP-113: cartão Site mostra "Despublicado"', s3);
  await print(ad, '113_despublicado');
  const r3 = await publicarPeloCartao(ad, c.P);
  chk(r3.ok && um('SELECT status_site FROM projeto WHERE codigo=?', c.P) === 'no_ar' && um("SELECT COUNT(*) FROM item WHERE projeto_codigo=? AND status_site='no_ar'", c.P) === 10, 'CAMP-113: republicar volta tudo ao ar', r3.texto.slice(0, 300));
  chk(um("SELECT COUNT(*) FROM wp_item WHERE projeto_detectado=? AND colecao_id=8013", c.P) === 10, 'CAMP-113: republicar não duplica folhas no site');
  chk(um('SELECT capa_item FROM projeto WHERE codigo=?', c.P) === nova, 'CAMP-113: a capa escolhida continua depois de republicar');
  await print(ad, '113_republicado');
  await ad.evaluate(() => closeDrawer(true));

  // ---------------- CAMP-114 ----------------
  passo('CAMP-114: lote de teste ("teste": true)');
  // o CAMP Vision grava "teste": true desde o "processando"; por contrato o painel NÃO importa lote de teste (nada vira fila nem vai ao site)
  const d = loteLimpo('CASA LOTE DE TESTE', 3, true);
  chk(d.avisos.every(x => /lote de teste/.test(x)), 'CAMP-114: os avisos do CAMP Vision respondem "ignorada: lote de teste"', d.avisos.join(' | '));
  chk(um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', d.P) === 0 && !um('SELECT COUNT(*) FROM lista_processamento WHERE projeto_codigo=?', d.P), 'CAMP-114: nenhuma folha nem lote do teste entra no painel');
  await T.abrirProjeto(ad, d.P); await espera(async () => !/verificando/.test(await cartaoSite(ad)));
  const s4 = await cartaoSite(ad);
  chk(/lote de teste/i.test(s4), 'CAMP-114: a página do projeto diz claramente que só chegou lote de teste', s4);
  const bp4 = await btPublicar(ad);
  chk(!bp4 || (await bp4.getAttribute('aria-disabled')) === 'true', 'CAMP-114: sem "Publicar" liberado', s4);
  chk(!(await ad.$('[data-pp="publicar"]:visible')), 'CAMP-114: nenhum botão "Publicar" visível');
  await print(ad, '114_projeto');
  const rTeste = await ad.evaluate(async c2 => { const r = await fetch('/api/projetos/' + c2 + '/publicar-tudo', { method: 'POST' }); return r.status }, d.P);
  chk(rTeste === 400 && um('SELECT status_site FROM projeto WHERE codigo=?', d.P) !== 'no_ar' && !um('SELECT tainacan_item_id FROM projeto WHERE codigo=?', d.P), 'CAMP-114: o painel recusa publicar mesmo chamado direto (nada é criado no site)', rTeste);
  await ad.evaluate(() => nav('painel')); await ad.waitForSelector('.ini-task', { timeout: 15000 }).catch(() => {}); await ad.waitForTimeout(1000);
  const tarefas = await ad.$$eval('.ini-task', l => l.filter(x => x.offsetParent).map(x => x.innerText.replace(/\s+/g, ' ')));
  chk(tarefas.length > 0 && !tarefas.some(t => t.includes('CASA LOTE DE TESTE') || t.includes(d.P)), 'CAMP-114: o lote de teste não entra no "O que fazer agora" como trabalho real', tarefas.join(' | ').slice(0, 600));
  await print(ad, '114_painel');
  // um lote REAL depois, no mesmo projeto, volta ao normal (o aviso de teste não trava o projeto para sempre)
  montar('processando', T.BASE, T.RAIZ, d.P, 'CASA LOTE DE TESTE'); montar('pronto', T.BASE, T.RAIZ, d.P, '2');
  chk(um('SELECT COUNT(*) FROM item WHERE projeto_codigo=?', d.P) === 2, 'CAMP-114: chegando um lote de verdade, as folhas entram normalmente');
  await conferirTudo(ad, d.P); await aprovarNoProjeto(ad, d.P); await T.abrirProjeto(ad, d.P); await espera(async () => !/verificando/.test(await cartaoSite(ad)));
  const bp6 = await btPublicar(ad);
  chk(!!bp6 && (await bp6.getAttribute('aria-disabled')) !== 'true', 'CAMP-114: com folhas de verdade conferidas e aprovadas, "Publicar" libera', await cartaoSite(ad));
  await print(ad, '114_lote_real');
});
