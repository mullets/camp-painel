// Auditoria do painel no navegador simulado (jsdom). Uso: suba a API em 127.0.0.1:8765 com um banco de teste e rode: NODE_PATH=$(npm root -g) node tests/auditoria_painel.js
const {JSDOM}=require('jsdom');
const BASE='http://127.0.0.1:8765';
const problems=[]; const okl=[];
const cookies={};
async function nodeFetch(url,opt={}){ if(url.startsWith('/')) url=BASE+url;
  const h={...(opt.headers||{})}; if(Object.keys(cookies).length) h['cookie']=Object.entries(cookies).map(([k,v])=>`${k}=${v}`).join('; ');
  const r=await fetch(url,{...opt,headers:h,redirect:'manual'});
  const sc=r.headers.get('set-cookie'); if(sc){const m=sc.match(/^([^=]+)=([^;]+)/); if(m) cookies[m[1]]=m[2];}
  return r; }
(async()=>{
const html=await (await fetch(BASE+'/')).text();
const dom=new JSDOM(html,{url:BASE+'/',runScripts:'dangerously',pretendToBeVisual:true,beforeParse(w){
  w.fetch=nodeFetch; w.Element.prototype.scrollTo=()=>{}; w.confirm=()=>true; w.alert=m=>okl.push('alert:'+m); w.prompt=()=>null;
  w.console.error=(...a)=>problems.push('console.error: '+a.join(' '));
  w.addEventListener('error',e=>problems.push('window.error: '+(e.error&&e.error.stack||e.message)));
  w.addEventListener('unhandledrejection',e=>problems.push('unhandled: '+(e.reason&&e.reason.stack||e.reason)));
}});
const w=dom.window, d=w.document;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const txt=sel=>{const el=d.querySelector(sel);return el?el.textContent.replace(/\s+/g,' ').trim():null};
function checkDom(label){ // procura sinais de template quebrado / dados falsos
  const vis=[...d.querySelectorAll('.content.on, .modal.on, .drawer, .top, .side, #gcrumb')].map(e=>e.textContent).join(' ');const body=vis;
  for(const bad of ['undefined','NaN','${','[object Object]','null ·',' null','Carregando']){ if(body.includes(bad)) problems.push(`${label}: texto "${bad}" na tela`);}
  d.querySelectorAll('[onclick]').forEach(el=>{const fn=(el.getAttribute('onclick').match(/^\s*([A-Za-z_$][\w$]*)\s*\(/)||[])[1]; if(fn&&typeof w[fn]!=='function') problems.push(`${label}: onclick chama função inexistente ${fn}()`)});
}
await sleep(1500);
if(!d.getElementById('login').classList.contains('on')) problems.push('tela de login não apareceu sem sessão');
d.getElementById('lg-email').value='rafael@camp.arq.br'; d.getElementById('lg-senha').value='senha-bem-longa-123';
try{await w.fazerLogin({preventDefault(){}});}catch(e){problems.push('fazerLogin lançou: '+e.stack)} await sleep(800);
if(!w.eval('EU')) problems.push('login não definiu EU: err='+txt('#lg-err')+' cookie='+JSON.stringify(cookies)); else okl.push('login ok como '+w.eval('EU').papel);
if(d.getElementById('login').classList.contains('on')) problems.push('tela de login continua aberta após login');
// rodapé versão
okl.push('rodapé: '+txt('#foot'));
// FUNDOS
w.route_to('fundos'); await sleep(1200);
const fr=d.querySelectorAll('#fundos-body tr').length; okl.push(`fundos: ${fr} linhas`); if(fr<30) problems.push('fundos: menos de 30 linhas ('+fr+')');
if(d.querySelector('#fundos-body').textContent.includes('Arnaldo') && d.querySelector('#fundos-body tr[data-nav="fundo/F001"]').textContent.includes('no ar')) problems.push('fundos: F001 aparece "no ar" indevidamente');
const siglas=[...d.querySelectorAll('#fundos-body .sig')].filter(e=>!e.classList.contains('na')).length; okl.push('fundos: siglas visíveis '+siglas); if(siglas<28) problems.push('fundos: siglas não aparecem ('+siglas+')');
checkDom('fundos');
// FUNDO detalhe
w.route_to('fundo/F026'); await sleep(1200); okl.push('fundo F026: '+txt('#fd h1')+' | '+(txt('#fd .meta')||'').slice(0,80));
if(!txt('#fd h1')) problems.push('fundo/F026: sem título'); if(d.querySelectorAll('#fd tbody tr[data-nav]').length<1) problems.push('fundo/F026: lista de projetos vazia');
if(!txt('#gcrumb').includes('F026')) problems.push('breadcrumb não mostra F026'); checkDom('fundo/F026');
// editar fundo (drawer)
await w.editarFundo('F026'); await sleep(400); if(!d.querySelector('#ef-titulo')) problems.push('editar fundo: formulário não abriu'); else okl.push('editar fundo: drawer ok');
w.closeDrawer();
// PROJETOS lista
w.route_to('projetos'); await sleep(1200); const pr=d.querySelectorAll('#projetos-body tr[data-nav]').length; okl.push('projetos: '+pr+' linhas'); if(pr<6) problems.push('projetos: lista incompleta '+pr); checkDom('projetos');
// busca servidor
d.getElementById('proj-q').value='Taru'; d.getElementById('proj-q').dispatchEvent(new w.Event('input')); await sleep(900); okl.push('busca projetos "Taru": '+d.querySelectorAll('#projetos-body tr[data-nav]').length+' linha(s)');
// PROJETO detalhe
w.route_to('projeto/F026-P0001'); await sleep(1200); okl.push('projeto: '+txt('#pd h1')+' | folhas '+d.querySelectorAll('#pd .thumb').length);
if(d.querySelectorAll('#pd .thumb').length!==6) problems.push('projeto F026-P0001: esperava 6 folhas, veio '+d.querySelectorAll('#pd .thumb').length);
if(!d.querySelector('#pd .thumb img')) problems.push('projeto: miniaturas do site não usadas'); checkDom('projeto');
for(const t of ['erros','pedidos','historico']){ await w.showProjeto('F026-P0001',t); await sleep(300); checkDom('projeto aba '+t); }
await w.editarProjeto('F026-P0001'); await sleep(300); if(!d.querySelector('#ep-titulo')) problems.push('editar projeto: formulário não abriu'); else okl.push('editar projeto: drawer ok'); w.closeDrawer();
// ITEM
const first=d.querySelector('#pd .thumb[data-nav]'); await w.showProjeto('F026-P0001','itens'); await sleep(300);
const code=d.querySelector('#pd .thumb[data-nav]').dataset.nav.split('/')[1]; w.route_to('item/'+code); await sleep(1000);
okl.push('folha: '+txt('#idet h1')+' | '+(txt('#idet .pager')||'')); if(!d.querySelector('#idet img')) problems.push('folha: imagem do site não aparece'); checkDom('item');
if(!txt('#gcrumb').includes('folha')) problems.push('breadcrumb da folha errado: '+txt('#gcrumb'));
// ARQUITETOS
w.route_to('arquitetos'); await sleep(1000); const ar=d.querySelectorAll('#v-arquitetos tbody tr').length; okl.push('arquitetos: '+ar+' linhas'); if(ar<30) problems.push('arquitetos: lista incompleta '+ar); checkDom('arquitetos');
// CONFIG
w.route_to('config'); await sleep(1000); okl.push('config: usuários '+d.querySelectorAll('#usr-body tr').length+' | campos config '+d.querySelectorAll('#cfg-body input').length);
if(d.querySelectorAll('#usr-body tr').length<2) problems.push('config: usuários não carregaram'); if(d.querySelectorAll('#cfg-body input').length<10) problems.push('config: configurações não carregaram'); checkDom('config');
// ETIQUETAS
w.route_to('etiquetas'); await sleep(300); if(!d.querySelector('#lab-preview .label')) problems.push('etiquetas: preview vazio'); else okl.push('etiquetas: preview ok'); 
for(const t of ['documento','caixa','tubo','fundo']){ d.querySelector(`#lab-tabs [data-t="${t}"]`).click(); await sleep(100); if(!d.querySelector('#lab-preview .label')) problems.push('etiqueta '+t+' sem preview'); }
checkDom('etiquetas');
// PERFIL
await w.abrirPerfil(); await sleep(600); if(!d.querySelector('#pf-nova')) problems.push('perfil: não abriu'); else okl.push('perfil: ok'); w.closeModal();
// PAINEL / FILAS / SOLICITACOES / ERROS (módulos de exemplo)
for(const v of ['painel','filas','solicitacoes','erros']){ w.route_to(v); await sleep(200); const av=d.querySelectorAll(`#v-${v} .aviso-exemplo`).length; okl.push(`${v}: ${av} aviso(s) de exemplo`); }
// modais: botões referenciam funções?
checkDom('global');
// novo fundo via modal
w.openModal('m-fundo'); d.getElementById('nf-nome').value='Teste Auditoria'; d.getElementById('nf-sigla').value='TAU'; await w.addFundo(); await sleep(1200);
okl.push('novo fundo: hash='+w.location.hash+' h1='+txt('#fd h1'));
console.log('\n=== OK ==='); okl.forEach(x=>console.log(' ✓',x));
console.log('\n=== PROBLEMAS ('+problems.length+') ==='); [...new Set(problems)].forEach(x=>console.log(' ✗',x));
process.exit(0);
})().catch(e=>{console.log('FALHA DO TESTE',e);process.exit(1)});
