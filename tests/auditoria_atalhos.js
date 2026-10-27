// Atalhos de teclado: o que o MENU anuncia tem que ser exatamente o que a tecla FAZ. Uso: bash tests/rodar_um.sh tests/auditoria_atalhos.js
const {JSDOM}=require('jsdom'); const BASE=process.env.CAMP_BASE||'http://127.0.0.1:8765'; const problems=[]; const linhas=[];
const c={}; const f=async(url,opt={})=>{ if(url.startsWith('/')) url=BASE+url; const h={...(opt.headers||{})}; if(Object.keys(c).length) h.cookie=Object.entries(c).map(([k,v])=>`${k}=${v}`).join('; ');
  if(opt.body&&!h['Content-Type']) h['Content-Type']='application/json'; const r=await fetch(url,{...opt,headers:h,redirect:'manual'}); const sc=r.headers.get('set-cookie'); if(sc){const m=sc.match(/^([^=]+)=([^;]+)/); if(m) c[m[1]]=m[2];} return r; };
const sleep=ms=>new Promise(r=>setTimeout(r,ms)); const chk=(ok,m)=>{ if(!ok) problems.push(m); };
(async()=>{
  await f('/api/auth/login',{method:'POST',body:JSON.stringify({email:'rafael@camp.arq.br',senha:'senha-bem-longa-123'})});
  const dom=new JSDOM(await (await fetch(BASE+'/')).text(),{url:BASE+'/',runScripts:'dangerously',pretendToBeVisual:true,beforeParse(w){if(!w.CSS)w.CSS={};if(!w.CSS.escape)w.CSS.escape=s=>String(s).replace(/[^a-zA-Z0-9_-]/g,c=>'\\'+c);  /* P2-18: as confirmações são uma janela do painel; a resposta vem de w.confirm(texto) */ w.addEventListener('DOMContentLoaded',()=>{new w.MutationObserver(()=>{const ov=w.document.getElementById('conf-ov');if(!ov||ov.dataset.respondido)return;ov.dataset.respondido='1';const resp=w.confirm(ov.textContent);setTimeout(()=>{if(!w.document.body.contains(ov))return;     if(resp){const dg=ov.querySelector('#conf-dig');if(dg){dg.value=ov.dataset.digitar||'';dg.dispatchEvent(new w.Event('input',{bubbles:true}))}const mt=ov.querySelector('#conf-motivo');if(mt&&!mt.value){mt.value='teste';mt.dispatchEvent(new w.Event('input',{bubbles:true}))}}     const b=ov.querySelector(resp?'[data-conf="sim"]':'[data-conf="nao"]')||ov.querySelector('[data-conf="sim"]');b&&b.click()},0)}).observe(w.document.body,{childList:true})}); w.fetch=(u,o={})=>f(u,o);w.Element.prototype.scrollTo=()=>{};w.confirm=()=>true;w.alert=()=>{};w.console.error=()=>{}}});
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
  // regra (CAMP-154/UX-28): 1–5 são Precisa de você · Projetos · Fundos · Pedidos de alta resolução · Máquinas
  const nd=Object.values(JSON.parse(w.eval('JSON.stringify(NAV_ATALHOS)'))).filter(k=>/^\d$/.test(k)).length;
  chk(nd===5,'CAMP-154: os 5 destinos deveriam ter as teclas 1–5: '+nd);
  // UX-28: menu pela ordem do trabalho SEM mudar tecla: os dígitos crescem de cima para baixo e só ficam em item sempre à vista; letras entre eles
  const dig=ordem.filter(v=>/^\d$/.test(anunciado[v]||''));
  chk(dig.map(v=>anunciado[v]).join('')==='12345','ordem do menu: os dígitos deveriam aparecer 1,2,3,4,5 de cima para baixo: '+dig.map(v=>v+'='+anunciado[v]).join(','));
  dig.forEach(v=>chk(!d.querySelector(`#nav button[data-v="${v}"]`).classList.contains('nav-sec'),`"${v}" tem dígito mas está no "Mais"`));
  ordem.filter(v=>!dig.includes(v)).forEach(v=>chk(/^[A-Z]$/.test(anunciado[v]||''),`ordem do menu: "${v}" deveria ter uma letra, tem ${anunciado[v]}`));
  { const ANTES={painel:'1',projetos:'2',fundos:'3',solicitacoes:'4',estacoes:'5',decisoes:'D',filas:'N',erros:'P',arquitetos:'I',localizacao:'W',estante:'X',etiquetas:'T',emprestimos:'O',relatorios:'L',uso:'U',auditoria:'A',qualidade:'Q',config:'C',caminho:'M',glossario:'G'};   // UX-28: as teclas de antes da reorganização
    Object.entries(ANTES).forEach(([v,k])=>chk(anunciado[v]===k,`UX-28: a tecla de "${v}" era ${k}, agora é ${anunciado[v]}`)); }
  chk(w.eval('JSON.stringify(NAV_ATALHOS)')===JSON.stringify(Object.fromEntries(ordem.map(v=>[v,anunciado[v]]))),'o menu mostra teclas diferentes da tabela NAV_ATALHOS');
  chk(!faz['0']&&!faz['z'],'teclas não anunciadas (0, z) não deveriam abrir nada: '+faz['0']+' / '+faz['z']);
  // minúscula/maiúscula e sem tecla acidental com Ctrl/⌘
  w.location.hash='#painel'; await sleep(250); tecla('P',{shiftKey:true}); await sleep(450); chk(rota()==='erros','P maiúsculo deveria abrir Problemas (item do "Mais", com o "Mais" fechado): '+rota());
  w.location.hash='#painel'; await sleep(250); tecla('3',{metaKey:true}); await sleep(450); chk(rota()==='painel','⌘3 NÃO pode abrir Fundos (é atalho do navegador): '+rota());
  // 3) o painel inicial anuncia a tecla do Painel? (botão do menu)
  
  // 4) outros atalhos prometidos pela ajuda
  const q=d.getElementById('q'); tecla('k',{metaKey:true}); await sleep(100); chk(d.activeElement===q,'⌘K deveria focar a busca');
  d.activeElement&&d.activeElement.blur(); const colapsado=()=>d.querySelector('.app').classList.contains('collapsed'); const antes=colapsado(); tecla('b',{metaKey:true}); await sleep(100); chk(colapsado()!==antes,'⌘B deveria recolher/abrir a barra lateral'); tecla('b',{metaKey:true});
  for(const v of ['filas','solicitacoes','erros','fundos','arquitetos','projetos','localizacao','auditoria']){ w.location.hash='#'+v; await sleep(1500); d.activeElement&&d.activeElement.blur&&d.activeElement.blur(); tecla('f'); await sleep(150);
    const a=d.activeElement; chk(a&&a.tagName==='INPUT'&&a.closest('.content.on'),`F deveria focar o campo de filtro da tela "${v}" (focou ${a&&a.tagName}${a&&a.id?'#'+a.id:''})`); linhas.push(`${a&&a.tagName==='INPUT'&&a.closest('.content.on')?'ok ':'ERRO'} F em "${v}" foca ${a&&a.id||a&&a.placeholder||a&&a.tagName}`) }
  d.activeElement&&d.activeElement.blur(); tecla('?'); await sleep(400); chk(!!d.querySelector('section.content.on > .ajuda-caixa')||/Atalhos|Ajuda/.test((d.getElementById('d-title')||{}).textContent||''),'? deveria abrir a ajuda (a caixa "Como funciona esta página")'); d.body.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true})); await sleep(300);
  // 5) a lista da ajuda e a dica do painel falam a mesma coisa que o menu
  const ajuda=w.eval('AJUDA_ATALHOS.map(a=>a.join(" => ")).join(" | ")'); linhas.push('ajuda: '+ajuda); chk(/1–5/.test(ajuda)&&/D · N · P/.test(ajuda)&&/Precisa de você/.test(ajuda),'a ajuda deveria listar 1–5 (os 5 destinos) e D · N · P: '+ajuda);
  // UX-28 (menu recolhido): cada tecla do menu aparece na ajuda ao lado do NOME ATUAL do item ("1–5" = 1,2,3,4,5; "D · N · P" = D, N, P, na ordem da descrição)
  { const AJ=JSON.parse(w.eval('JSON.stringify(AJUDA_ATALHOS)')), NA=JSON.parse(w.eval('JSON.stringify(NAV_ATALHOS)')), naAjuda={};
    for(const [k,desc] of AJ){ const m=k.match(/^(\d)–(\d)$/); const ks=m?Array.from({length:+m[2]-+m[1]+1},(_,i)=>String(+m[1]+i)):k.split(' · '); const ds=desc.split(' · ');
      if(ks.length===ds.length&&ks.every(x=>/^[A-Z0-9]$/.test(x))) ks.forEach((x,i)=>{naAjuda[x]=ds[i].replace(/\s*\(.*\)$/,'').trim()}) }
    for(const [v,k] of Object.entries(NA)){ const b=d.querySelector(`#nav button[data-v="${v}"]`); const nome=b?[...b.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim():'';
      const ok=naAjuda[k]===nome; linhas.push(`${ok?'ok ':'ERRO'} ajuda: ${k} = "${naAjuda[k]}" (menu: "${nome}")`); chk(ok,`ajuda: a tecla ${k} aparece como "${naAjuda[k]}", mas o item do menu se chama "${nome}"`) } }
  // UX-28: [ recolhe/expande o menu; recolhido, TODAS as teclas do menu continuam valendo
  { const col=()=>d.querySelector('.app').classList.contains('collapsed'); w.location.hash='#painel'; await sleep(300); d.activeElement&&d.activeElement.blur&&d.activeElement.blur();
    const a0=col(); tecla('['); await sleep(100); chk(col()!==a0,'[ deveria recolher/expandir o menu'); if(!col()){tecla('[');await sleep(100)} chk(col(),'menu recolhido para conferir as teclas');
    for(const [v,k] of Object.entries(JSON.parse(w.eval('JSON.stringify(NAV_ATALHOS)')))){ w.location.hash=v==='config'?'#painel':'#config'; await sleep(250); tecla(k.toLowerCase()); await sleep(400); const ok=rota()===v; linhas.push(`${ok?'ok ':'ERRO'} recolhido: ${k} -> "${rota()}"`); chk(ok,`menu recolhido: a tecla ${k} deveria abrir "${v}", abriu "${rota()}"`) }
    const q2=d.getElementById('q'); tecla('k',{ctrlKey:true}); await sleep(100); chk(d.activeElement===q2,'recolhido: Ctrl+K deveria focar a busca'); q2.blur();
    tecla('['); await sleep(100); chk(!col(),'[ de novo deveria expandir o menu') }
  console.log(linhas.join('\n')); console.log(`\n=== ATALHOS: ${problems.length} problema(s) ===`); problems.forEach(p=>console.log(' ✗ '+p)); process.exit(problems.length?1:0);
})().catch(e=>{console.log('ERRO no teste:',e.message);process.exit(2)});
