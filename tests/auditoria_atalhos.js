// Atalhos de teclado: o que o MENU anuncia tem que ser exatamente o que a tecla FAZ. Uso: bash tests/rodar_um.sh tests/auditoria_atalhos.js
const {JSDOM}=require('jsdom'); const BASE='http://127.0.0.1:8765'; const problems=[]; const linhas=[];
const c={}; const f=async(url,opt={})=>{ if(url.startsWith('/')) url=BASE+url; const h={...(opt.headers||{})}; if(Object.keys(c).length) h.cookie=Object.entries(c).map(([k,v])=>`${k}=${v}`).join('; ');
  if(opt.body&&!h['Content-Type']) h['Content-Type']='application/json'; const r=await fetch(url,{...opt,headers:h,redirect:'manual'}); const sc=r.headers.get('set-cookie'); if(sc){const m=sc.match(/^([^=]+)=([^;]+)/); if(m) c[m[1]]=m[2];} return r; };
const sleep=ms=>new Promise(r=>setTimeout(r,ms)); const chk=(ok,m)=>{ if(!ok) problems.push(m); };
(async()=>{
  await f('/api/auth/login',{method:'POST',body:JSON.stringify({email:'rafael@camp.arq.br',senha:'senha-bem-longa-123'})});
  const dom=new JSDOM(await (await fetch(BASE+'/')).text(),{url:BASE+'/',runScripts:'dangerously',pretendToBeVisual:true,beforeParse(w){w.fetch=(u,o={})=>f(u,o);w.Element.prototype.scrollTo=()=>{};w.confirm=()=>true;w.alert=()=>{};w.console.error=()=>{}}});
  const w=dom.window, d=w.document; await sleep(2800);
  const tecla=(k,extra={})=>d.dispatchEvent(new w.KeyboardEvent('keydown',{key:k,bubbles:true,...extra}));
  const rota=()=>w.eval('rotaAtual()').split('/')[0];
  // 1) o que o menu ANUNCIA
  const anunciado={}; d.querySelectorAll('#nav button[data-v]').forEach(b=>{const k=b.querySelector('kbd'); anunciado[b.dataset.v]=k?k.textContent.trim():null});
  // 2) o que cada tecla FAZ (dígitos e letras, maiúscula ou minúscula)
  const faz={};
  const TECLAS=['0','z',...Object.values(JSON.parse(w.eval('JSON.stringify(NAV_ATALHOS)'))).map(x=>x.toLowerCase())];   // as teclas vêm da TABELA (um atalho novo nunca escapa da auditoria); '0' e 'z' são controles que não fazem nada
  for(const k of TECLAS){ w.location.hash='#config'; await sleep(250); tecla(k); await sleep(450); const r=rota(); faz[k]=(r==='config'&&!(k==='c'||k==='9'))?null:r; if(k==='c')faz[k]=r; }
  const ordem=[...d.querySelectorAll('#nav button[data-v]')].map(b=>b.dataset.v);
  for(const [view,k] of Object.entries(anunciado)){
    if(!k){ linhas.push(`ERRO menu "${view}" ficou SEM tecla`); chk(false,`menu: "${view}" não anuncia tecla`); continue }
    const ok=faz[k.toLowerCase()]===view; linhas.push(`${ok?'ok ':'ERRO'} menu "${view}" anuncia ${k} -> a tecla ${k} vai para "${faz[k.toLowerCase()]}"`); chk(ok,`menu: "${view}" anuncia a tecla ${k}, mas a tecla ${k} abre "${faz[k.toLowerCase()]}"`) }
  // regra: dígitos 1..9 nas nove primeiras entradas, NA ORDEM do menu; letras depois
  ordem.slice(0,9).forEach((v,i)=>chk(anunciado[v]===String(i+1),`ordem do menu: a ${i+1}ª entrada ("${v}") deveria anunciar ${i+1}, anuncia ${anunciado[v]}`));
  ordem.slice(9).forEach(v=>chk(/^[A-Z]$/.test(anunciado[v]||''),`ordem do menu: "${v}" (depois da 9ª) deveria ter uma letra, tem ${anunciado[v]}`));
  chk(w.eval('JSON.stringify(NAV_ATALHOS)')===JSON.stringify(Object.fromEntries(ordem.map(v=>[v,anunciado[v]]))),'o menu mostra teclas diferentes da tabela NAV_ATALHOS');
  chk(!faz['0']&&!faz['z'],'teclas não anunciadas (0, z) não deveriam abrir nada: '+faz['0']+' / '+faz['z']);
  // minúscula/maiúscula e sem tecla acidental com Ctrl/⌘
  w.location.hash='#painel'; await sleep(250); tecla('E',{shiftKey:true}); await sleep(450); chk(rota()==='estacoes','E maiúsculo deveria abrir Estações: '+rota());
  w.location.hash='#painel'; await sleep(250); tecla('5',{metaKey:true}); await sleep(450); chk(rota()==='painel','⌘5 NÃO pode abrir Fundos (é atalho do navegador): '+rota());
  // 3) o painel inicial anuncia a tecla do Painel? (botão do menu)
  
  // 4) outros atalhos prometidos pela ajuda
  const q=d.getElementById('q'); tecla('k',{metaKey:true}); await sleep(100); chk(d.activeElement===q,'⌘K deveria focar a busca');
  d.activeElement&&d.activeElement.blur(); const colapsado=()=>d.querySelector('.app').classList.contains('collapsed'); const antes=colapsado(); tecla('b',{metaKey:true}); await sleep(100); chk(colapsado()!==antes,'⌘B deveria recolher/abrir a barra lateral'); tecla('b',{metaKey:true});
  for(const v of ['filas','solicitacoes','erros','fundos','arquitetos','projetos','localizacao','auditoria']){ w.location.hash='#'+v; await sleep(1500); d.activeElement&&d.activeElement.blur&&d.activeElement.blur(); tecla('f'); await sleep(150);
    const a=d.activeElement; chk(a&&a.tagName==='INPUT'&&a.closest('.content.on'),`F deveria focar o campo de filtro da tela "${v}" (focou ${a&&a.tagName}${a&&a.id?'#'+a.id:''})`); linhas.push(`${a&&a.tagName==='INPUT'&&a.closest('.content.on')?'ok ':'ERRO'} F em "${v}" foca ${a&&a.id||a&&a.placeholder||a&&a.tagName}`) }
  d.activeElement&&d.activeElement.blur(); tecla('?'); await sleep(400); chk(!!d.querySelector('section.content.on > .ajuda-caixa')||/Atalhos|Ajuda/.test((d.getElementById('d-title')||{}).textContent||''),'? deveria abrir a ajuda (a caixa "Como funciona esta página")'); d.body.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true})); await sleep(300);
  // 5) a lista da ajuda e a dica do painel falam a mesma coisa que o menu
  const ajuda=w.eval('AJUDA_ATALHOS.map(a=>a.join(" => ")).join(" | ")'); linhas.push('ajuda: '+ajuda); chk(/1–9/.test(ajuda)&&/E · A · C/.test(ajuda),'a ajuda deveria listar 1–9 e E · A · C: '+ajuda);
  console.log(linhas.join('\n')); console.log(`\n=== ATALHOS: ${problems.length} problema(s) ===`); problems.forEach(p=>console.log(' ✗ '+p)); process.exit(problems.length?1:0);
})().catch(e=>{console.log('ERRO no teste:',e.message);process.exit(2)});
