// Auditoria de XSS armazenado: depois de envenenar o banco (tests/envenenar_banco.py), visita todas as telas e abre
// os detalhes; qualquer elemento [data-xss] na página significa que o HTML digitado virou ELEMENTO REAL.
// Uso: bash tests/rodar_auditoria.sh
const {JSDOM}=require('jsdom'); const BASE='http://127.0.0.1:8765'; const cookies={};
async function f(u,o={}){ if(u.startsWith('/')) u=BASE+u; const h={...(o.headers||{})}; if(Object.keys(cookies).length) h.cookie=Object.entries(cookies).map(([k,v])=>`${k}=${v}`).join('; ');
  if(o.body&&!h['Content-Type']) h['Content-Type']='application/json'; const r=await fetch(u,{...o,headers:h,redirect:'manual'}); const sc=r.headers.get('set-cookie'); if(sc){const m=sc.match(/^([^=]+)=([^;]+)/); if(m) cookies[m[1]]=m[2];} return r; }
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 await f('/api/auth/login',{method:'POST',body:JSON.stringify({email:'rafael@camp.arq.br',senha:'senha-bem-longa-123'})});
 const dom=new JSDOM(await (await fetch(BASE+'/')).text(),{url:BASE+'/',runScripts:'dangerously',pretendToBeVisual:true,beforeParse(w){
   w.fetch=(u,o={})=>f(u,o); w.Element.prototype.scrollTo=()=>{}; w.confirm=()=>true; w.alert=()=>{}; w.prompt=()=>null; w.console.error=()=>{}; w.URL.createObjectURL=()=>'blob:x'; }});
 const w=dom.window,d=w.document; await sleep(1500);
 d.getElementById('lg-email').value='rafael@camp.arq.br'; d.getElementById('lg-senha').value='senha-bem-longa-123'; await w.fazerLogin({preventDefault(){}}); await sleep(900);
 const vazou={}, visto=new Set();   // "tela/passo" -> ["contêiner ← campo"]; cada par só conta na PRIMEIRA vez
 const ondeEstou=e=>{ const c=e.closest('[id]'); return c?c.id:'(sem id)'; };
 const vocab={};   // frase antiga ou valor interno cru VISÍVEL na tela (ver docs/vocabulario.md)
 const PROIB=/\bnao\b|\bno ar\b|fora do ar|tirar do ar|colocar no ar|retirar da publica|\b(?:no_ar|fora_do_ar|nao_publicado|tirar_do_ar)\b/i;
 const sobre={};   // fragmento de HTML mostrado como TEXTO = escapou demais
 const RX_FRAG=/<(span|div|tr|td|b|small|button|li|ul|dl|dt|dd|table|a)\b[^>]*>/i;
 const checa=(onde)=>{ const cl=d.body.cloneNode(true); cl.querySelectorAll('script,style').forEach(e=>e.remove()); const tx=cl.textContent||''; const pv=tx.match(PROIB); if(pv&&!Object.values(vocab).includes(pv[0])) vocab[onde]=pv[0]; const mm=tx.match(RX_FRAG); if(mm&&!Object.values(sobre).includes(mm[0])) sobre[onde]=mm[0]; for(const e of d.querySelectorAll('[data-xss]')){ const par=ondeEstou(e)+' ← '+e.getAttribute('data-xss'); if(visto.has(par)) continue; visto.add(par); (vazou[onde]=vazou[onde]||[]).push(par); } };
 const passos=[['painel'],['fundos'],['fundo/F026'],['fundo/F023'],['arquitetos'],['projetos'],['projeto/F026-P0001'],['projeto/F023-P0011'],['item/F023-P0011-1959-S01-D00001'],['item/F023-P0011-1959-S01-D00003'],['item/F023-P0011-1959-S01-D00004'],['fundo/F029'],['fundo/F003'],['projeto/F002-P0001'],['projeto/F001-P0001'],['filas'],['solicitacoes'],['erros'],['etiquetas'],['config'],['localizacao'],['estacoes'],['auditoria']];
 for(const [rota] of passos){ try{ w.route_to(rota); await sleep(1500); checa(rota);
     // abre o detalhe de até 5 linhas (drawer)
     const trs=[...d.querySelectorAll('.content.on tbody tr, #v-'+rota.split('/')[0]+' tbody tr')].slice(0,5);
     for(const [i,tr] of trs.entries()){ tr.click(); await sleep(500); checa(rota+' › detalhe da linha '+(i+1)); try{w.closeDrawer(true)}catch(_){ } } }catch(e){ vazou[rota+' (exceção)']=[e.message.slice(0,80)] } }

 // detalhes e formulários abertos por função, com IDs reais da API
 const J=async u=>{ try{ return await (await f(u)).json() }catch(_){ return null } };
 const erros=await J('/api/erros'), sols=await J('/api/solicitacoes'), ags=await J('/api/agentes'), evs=await J('/api/eventos?limite=60');
 const lista=x=>Array.isArray(x)?x:(x&&(x.itens||x.items||x.eventos||x.dados))||[];
 const ev2=lista(evs).filter(e=>/xss|data-xss/.test(JSON.stringify(e)));
 const funcoes=[['editarDireitos F026',()=>w.editarDireitos('F026')],['editarDireitos F023',()=>w.editarDireitos('F023')],['abrirPerfil',()=>w.abrirPerfil&&w.abrirPerfil()],
   ...lista(erros).slice(0,2).map(e=>['abrirErro '+e.id,()=>w.abrirErro(e.id)]), ...lista(sols).slice(0,2).map(e=>['abrirSolicitacao '+e.id,()=>w.abrirSolicitacao(e.id)]),
   ...lista(ags).slice(0,3).map(e=>['editarAgente '+e.id,()=>w.editarAgente(e.id)]), ...ev2.slice(0,3).map(e=>['abrirEventoAuditoria '+e.id,()=>w.abrirEventoAuditoria(e.id)])];
 for(const [nome,fn] of funcoes){ try{ await fn(); await sleep(600); checa('abre: '+nome); try{w.closeDrawer(true)}catch(_){ } }catch(e){ vazou['abre: '+nome+' (exceção)']=[e.message.slice(0,80)] } }
 // modais de criação (selects com fundos/projetos envenenados)
 for(const m of ['m-arq','m-entrada','m-erro','m-fundo','m-lista','m-loc','m-proj','m-sol','m-usr']){ try{ w.openModal(m); await sleep(400); checa('modal '+m); w.closeModal() }catch(e){ } }
 try{ w.route_to('estacoes'); await sleep(2500); await w.previaImportacao(); await sleep(1500); checa('prévia do importador'); if(!(d.getElementById('imp-corpo').textContent||'').includes('wp_item.sem_codigo')) vazou['prévia do importador: TESTE VAZIO']=['o dado envenenado nem apareceu nas listas']; }catch(e){ vazou['prévia do importador (exceção)']=[e.message.slice(0,80)] }
 // formulários de edição e criação
 for(const [nome,fn] of [['editarFundo F026',()=>w.editarFundo('F026')],['editarProjeto F026-P0001',()=>w.editarProjeto('F026-P0001')],['editarItem',()=>w.editarItem('F023-P0011-1959-S01-D00001')],['abrirAjuda',()=>w.abrirAjuda()]]){
   try{ await fn(); await sleep(700); checa('formulário: '+nome); try{w.closeDrawer(true)}catch(_){ } }catch(e){ vazou['formulário: '+nome+' (exceção)']=[e.message.slice(0,80)] } }
 // busca global
 try{ const Q=w.eval('q'); Q.value='F026'; Q.dispatchEvent(new w.Event('input')); await sleep(900); checa('busca global'); }catch(e){}
 const campos=new Set(); Object.values(vazou).forEach(a=>a.forEach(x=>campos.add(x.split(' ← ')[1])));
 console.log('\n(passos executados: '+(passos.length)+' telas, '+funcoes.length+' detalhes/formulários, 9 modais)');
 console.log('\n=== VAZAMENTOS: '+visto.size+' ponto(s) de injeção (contêiner ← campo), '+campos.size+' campo(s) distintos ===');
 for(const [k,v] of Object.entries(vazou)) { console.log(' ✗ '+k); v.forEach(x=>console.log('      '+x)); }
 console.log('\n=== SOBRE-ESCAPE (HTML do próprio painel aparecendo como texto): '+Object.keys(sobre).length+' ===');
 for(const [k,v] of Object.entries(sobre)) console.log(' ✗ '+k+'  →  '+v.slice(0,90));
 console.log('\n=== VOCABULÁRIO (frase antiga/valor interno visível): '+Object.keys(vocab).length+' ===');
 for(const [k,v] of Object.entries(vocab)) console.log(' ✗ '+k+'  →  "'+v+'"');
 console.log('\nCAMPOS_QUE_VAZAM='+JSON.stringify([...campos].sort()));
 process.exit(visto.size||Object.keys(sobre).length||Object.keys(vocab).length?1:0);
})().catch(e=>{console.log('FALHA DO TESTE',e);process.exit(1)});
