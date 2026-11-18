// 18/11: "F018-S00060" (código antigo de catálogo vindo do site) não é nº de folha; "306", "Folha 12", "12/30" são.
const fs=require('fs'),path=require('path');
const html=fs.readFileSync(path.join(__dirname,'..','frontend','index.html'),'utf8');
const re=html.match(/(?:const RE_FOLHA_CODIGO=[^\n]*\n)?function numFolha\(it\)\{[^\n]*\}/);
if(!re){console.log('FALHA: numFolha não encontrada');process.exit(1)}
const numFolha=new Function(re[0]+';return numFolha')();
let f=0;const ok=(c,m)=>{if(c)console.log('  ok   '+m);else{f++;console.log('  FALHA '+m)}};
ok(numFolha({folha:'F018-S00060'})===null,'F018-S00060 → sem nº');
ok(numFolha({folha:'Folha F018-S00061'})===null,'"Folha F018-S00061" → sem nº');
ok(numFolha({folha:'306'})===306,'306 → 306');
ok(numFolha({folha:'Folha 12'})===12,'"Folha 12" → 12');
ok(numFolha({folha:'12/30'})===12,'12/30 → 12');
ok(numFolha({folha:''})===null,'vazio → sem nº');
console.log(f?f+' FALHA(S)':'TUDO OK');process.exit(f?1:0);
