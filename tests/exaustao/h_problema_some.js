// 20/10 (print da F026-P0009: "se eu resolvo um problema ele tem que sair da lista, pelo amor de deus isso é básico!").
// O CAMP Vision manda "série incerta na triagem … conferir na folha de contatos" em cada folha. Na aba Problemas do projeto (agrupada por
// tipo desde o CAMP-127) a pessoa abre a folha, confere ("Está certo") e ela tem de SAIR na hora — do grupo, da lista completa e do número
// da aba — e continuar fora ao recarregar. Dois caminhos: o botão da folha no grupo e a linha da lista completa (gaveta → "Abrir a folha").
// Vale para as categorias que o CAMP Vision pode usar para isso ("série", "metadado", sem categoria).
const T = require('./_comum');
const { execFileSync } = require('child_process'), path = require('path');
T.rodar(async () => {
  for (const cat of ['série', 'metadado', '']) {
    const tag = `[${cat || 'vazia'}]`;
    T.passo(`aviso "série incerta" com categoria "${cat || '(vazia)'}"`);
    const { P, D } = T.loteReal('CASA SERIE ' + (cat || 'VAZIA').toUpperCase(), 'F026', { semAviso: true });
    execFileSync('python3', [path.join(__dirname, 'h_montar.py'), T.BASE, T.RAIZ, P, cat], { encoding: 'utf-8' });
    const abertos = () => T.um("SELECT COUNT(*) FROM erro WHERE codigo LIKE ? AND situacao IN ('aberto','em_correcao') AND descricao LIKE '%série incerta%'", P + '%');
    T.chk(abertos() === 6, `${tag} cenário: 6 avisos "série incerta" abertos`, abertos());
    const op = await T.entrar('operador'); await T.abrirProjeto(op, P);
    await op.evaluate(c => showProjeto(c, 'erros'), P); await op.waitForTimeout(1500);
    const grupoSel = '#pj-prob-tipos .pt-grupo[data-pt-tipo="erro-' + (cat === 'metadado' ? 'metadado' : 'outro') + '"]';
    const noGrupo = () => op.$$eval(`${grupoSel} [data-rev-abrir]`, l => l.map(b => b.textContent.trim())).catch(() => []);
    const nGrupo = () => op.$eval(`${grupoSel} .pt-n`, b => Number(b.textContent)).catch(() => -1);
    const naLista = () => op.$$eval('#pd tr[data-abrir^="erro:"]', l => l.filter(x => /série incerta/.test(x.textContent)).map(x => (x.textContent.match(/D\d{5}/) || [''])[0]));
    const nAba = async () => Number(((await T.txt(op, '#pd [role="tab"][aria-selected="true"]')).match(/Problemas \((\d+)\)/) || [])[1]);
    const g0 = await nGrupo(); T.chk((await noGrupo()).length === 6 && g0 >= 6, `${tag} a aba agrupa as 6 folhas do aviso`, JSON.stringify(await noGrupo()));
    const aba0 = await nAba();
    // caminho 1: o botão da folha no grupo abre a revisão; "Está certo"
    await op.click(`${grupoSel} [data-rev-abrir="${D(1)}"]`);
    T.chk(await op.waitForSelector('#d-body [data-rev-item="conferida"]', { timeout: 10000 }).then(() => true, () => false), `${tag} o botão da D00001 no grupo abre a revisão`);
    await op.click('#d-body [data-rev-item="conferida"]'); await T.confirmar(op); await op.waitForTimeout(1500);
    T.chk(abertos() === 5, `${tag} conferir a D00001 fecha o aviso dela no banco`, abertos());
    T.chk(!(await noGrupo()).includes('D00001') && await nGrupo() === g0 - 1, `${tag} a D00001 sai do grupo NA HORA e o número do grupo desce 1`, JSON.stringify(await noGrupo()));
    T.chk(!(await naLista()).includes('D00001'), `${tag} …e sai da lista completa`);
    T.chk(await nAba() === aba0 - 1, `${tag} o número da aba Problemas desce 1`, `${aba0} → ${await nAba()}`);
    await T.print(op, `serie_${cat || 'vazia'}_grupo`);
    await op.evaluate(() => closeDrawer && closeDrawer(true)).catch(() => {});
    // caminho 2: a lista completa → gaveta do problema → "Abrir a folha" → "Está certo"
    await op.click('#pd details.pj-prob-lista summary');
    await op.locator('#pd tr[data-abrir^="erro:"]', { hasText: 'D00002' }).filter({ hasText: 'série incerta' }).first().click();
    await op.waitForSelector('#d-body', { timeout: 10000 }); await op.waitForTimeout(800);
    const titulo = await T.txt(op, '#d-title'); T.chk(!/^outro$/i.test(titulo), `${tag} a gaveta do problema não se chama "outro"`, titulo);
    T.chk(!/Problema relatado/.test(await T.txt(op, '#d-body')), `${tag} não diz "Problema relatado" (quem apontou foi o CAMP Vision)`);
    if (!(await op.$('#d-body [data-rev-item="conferida"]'))) await op.click('#d-body [data-err-acao]');
    T.chk(await op.waitForSelector('#d-body [data-rev-item="conferida"]', { timeout: 10000 }).then(() => true, () => false), `${tag} "Abrir a folha" abre a revisão ali mesmo`);
    await op.click('#d-body [data-rev-item="conferida"]'); await T.confirmar(op); await op.waitForTimeout(1500);
    T.chk(abertos() === 4 && !(await naLista()).includes('D00002') && !(await noGrupo()).includes('D00002'), `${tag} a D00002 sai da lista e do grupo na hora`, `${abertos()} ${JSON.stringify(await naLista())}`);
    await op.evaluate(() => closeDrawer && closeDrawer(true)).catch(() => {});
    await T.abrirProjeto(op, P); await op.evaluate(c => showProjeto(c, 'erros'), P); await op.waitForTimeout(1500);
    const rec = await noGrupo(); T.chk(!rec.includes('D00001') && !rec.includes('D00002') && rec.length === 4, `${tag} ao recarregar, as duas continuam fora`, JSON.stringify(rec));
    await op.context().close();
  }
});
