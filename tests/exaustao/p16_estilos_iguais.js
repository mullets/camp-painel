// CAMP-155 (Trello, 22/10): limpeza visual = só tokens, SEM mudança de layout visível. Este teste grava o estilo calculado
// (fonte, raio, espaços, cores) de cada elemento de 6 telas num arquivo; rodado no main e na versão nova, os arquivos têm de ser iguais.
// Rodar: EXAUSTAO_PORTA=8970 ESTILOS_SAIDA=/tmp/estilos_novo.json bash tests/rodar_exaustao.sh tests/exaustao/p16_estilos_iguais.js
const fs = require('fs');
const T = require('./_comum');

T.rodar(async () => {
  const P = T.cv2('reservar', T.BASE, 'F026', 'CASA ESTILOS', '1972');
  const ad = await T.entrar('admin');
  const telas = { painel: 'painel', projetos: 'projetos', projeto: 'projeto/' + P, fila: 'filas/todas', fundos: 'fundos', config: 'config' };
  const out = {};
  for (const [nome, rota] of Object.entries(telas)) {
    await ad.evaluate(r => nav(r), rota); await ad.waitForTimeout(2500);
    out[nome] = await ad.evaluate(() => {
      const props = ['fontSize', 'borderTopLeftRadius', 'borderBottomRightRadius', 'paddingTop', 'paddingLeft', 'marginTop', 'gap', 'color', 'backgroundColor', 'borderTopColor', 'fontWeight', 'lineHeight'];
      const raiz = document.querySelector('.content.on') || document.body, r = [];
      for (const el of [document.querySelector('#nav'), ...document.querySelectorAll('#nav *'), raiz, ...raiz.querySelectorAll('*')]) {
        if (!el || el.closest('svg')) continue;
        const cs = getComputedStyle(el), cls = (el.className && el.className.baseVal === undefined ? String(el.className) : '').split(/\s+/).filter(Boolean).sort().join('.');
        r.push(el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (cls ? '.' + cls : '') + ' ' + props.map(p => cs[p]).join('|'));
      }
      return r;
    });
  }
  fs.writeFileSync(process.env.ESTILOS_SAIDA || '/tmp/estilos.json', JSON.stringify(out));
  T.chk(Object.values(out).every(x => x.length > 20), 'gravou o estilo calculado de 6 telas', Object.entries(out).map(([k, v]) => k + ':' + v.length).join(' '));
});
