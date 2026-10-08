const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const root=path.resolve(__dirname,'../..');
const script=fs.readFileSync(path.join(root,'assets/js/company-guides.js'),'utf8');
const registry=fs.readFileSync(path.join(root,'backend/app/registry.py'),'utf8');
const catalog=JSON.parse(fs.readFileSync(path.join(root,'assets/data/companies.json'),'utf8'));
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const context={window:{}};
vm.createContext(context);
vm.runInContext(script,context,{filename:'company-guides.js'});
const {resolve,knownCodes}=context.window.RAZYNC_COMPANY_HELP;
const apiCodes=[...registry.matchAll(/^    (\d+): \{/gm)].map(match=>Number(match[1]));
apiCodes.push(1248);
apiCodes.sort((a,b)=>a-b);
const demo=(code,extra={})=>({
  codigo:code,
  nome:catalog.find(c=>c.codigo===code)?.nome || 'Empresa '+code,
  capabilities:{
    status:'api_ready',tools:['modelo_dominio','base_inteligente','conferencia_extrato'],
    banks:{itau:'508'},workflow:'standard',...extra
  }
});

test('cobre exatamente todas as empresas com ferramenta, além da 266 existente',()=>{
  const expected=apiCodes.filter(code=>code!==266);
  assert.deepEqual([...knownCodes].sort((a,b)=>a-b),expected);
  assert.equal(apiCodes.length,29);
  assert.equal(expected.length,28);
  for(const code of expected){
    assert.ok(catalog.some(company=>company.codigo===code),String(code));
    for(const tool of ['organizar','base','extrato']){
      const guide=resolve(demo(code),tool);
      assert.ok(guide,code+' / '+tool);
      assert.equal(guide.caption.includes(String(code)),true,code+' / '+tool);
      assert.ok(guide.intro.length>=25,code+' / '+tool);
      assert.ok(guide.note.length>10,code+' / '+tool);
      assert.ok(guide.steps.length>=3,code+' / '+tool);
      guide.steps.forEach((item,index)=>{
        assert.equal(item.length,3,code+' / '+tool+' / '+index);
        assert.ok(item[1].length>=6,code+' / '+tool+' / '+index);
        assert.ok(item[2].length>=20,code+' / '+tool+' / '+index);
      });
    }
  }
});

test('não ensina ferramentas inexistentes nem empresas sem capacidade',()=>{
  assert.equal(resolve(demo(266),'organizar'),null,'266 mantém roteiro próprio');
  assert.equal(resolve(demo(257),'organizar'),null,'empresa sem integração');
  assert.equal(resolve({...demo(242),capabilities:{status:'catalog_only',tools:[]}},'organizar'),null);
  assert.equal(resolve({...demo(242),capabilities:{status:'api_ready',tools:[]}},'base'),null);
  assert.equal(resolve(demo(1408),'francesinhas'),null);
  assert.equal(resolve(null,'organizar'),null);
});

test('orientações seguem os campos realmente exibidos para fluxos diferentes',()=>{
  const g1408=resolve(demo(1408,{workflow:'advanced',banks:{itau:'512'},roles:[
    {name:'extrato',label:'Extrato Itaú',accept:'.pdf',multiple:true},
    {name:'recebidos',label:'Planilha de recebidos',accept:'.xls,.xlsx'},
    {name:'francesinhas',label:'Francesinhas ZIP',accept:'.zip',optional:true}
  ]}),'organizar');
  assert.match(g1408.steps[1][2],/Extrato Itaú.*Planilha de recebidos/);
  assert.match(g1408.steps[2][2],/Francesinhas ZIP/);
  assert.doesNotMatch(g1408.steps[2][2],/De e Até|limitar os lançamentos/);
  assert.match(g1408.note,/512/);

  const g242=resolve(demo(242,{workflow:'advanced',banks:{itau_508:'508',itau_509:'509',banco_brasil:'8'},roles:[
    {name:'despesas',label:'Relatório Despesa',optional:true},
    {name:'fornecedores',label:'Relatório Fornecedor',optional:true},
    {name:'recebidos',label:'Relatório Recebido',optional:true},
    {name:'francesinhas',label:'Francesinhas ZIP',optional:true}
  ]}),'organizar');
  assert.match(g242.note,/pelo menos um/);
  assert.match(resolve(demo(242),'base').note,/Consolidada, Despesa, Fornecedor, Recebido ou Francesinhas/);

  const g1211=resolve(demo(1211,{workflow:'advanced',banks:{itau:'508'},roles:[
    {name:'extrato',label:'Extrato Itaú',accept:'.pdf'},
    {name:'boletos',label:'Boletos liquidados',accept:'.pdf'}
  ]}),'organizar');
  assert.match(g1211.steps[1][2],/Extrato Itaú.*Boletos liquidados/);
  assert.match(g1211.note,/PDF, não planilha Excel/);

  const g625=resolve(demo(625,{workflow:'standard_multi_bank',banks:{banco_brasil:'8',caixa:'504',sicredi:'3999'}}),'organizar');
  assert.match(g625.steps[0][2],/Banco do Brasil 8.*Caixa 504.*Sicredi 3999/);
  assert.match(g625.steps[1][2],/campo específico de cada banco/);

  const g1396=resolve(demo(1396,{workflow:'advanced',banks:{itau:'515',bradesco:'514'},roles:[
    {name:'consolidada',label:'Planilha consolidada'}
  ]}),'organizar');
  assert.match(g1396.steps[0][2],/Itaú 515.*Bradesco 514/);
  assert.match(g1396.note,/Não utilize a planilha da matriz 266/);

  const g626=resolve(demo(626,{workflow:'standard_multi_bank',banks:{banco_brasil:'8',sicredi:'1155'}}),'extrato');
  assert.match(g626.steps[0][2],/Sicredi 1155/);
});

test('frontend carrega as instruções antes do JS principal',()=>{
  const guideIndex=html.indexOf('src="./assets/js/company-guides.js');
  const appIndex=html.indexOf('src="./assets/js/app.js');
  assert.ok(guideIndex>0 && appIndex>guideIndex);
});

test('não resolve instrução para ferramenta ausente na capacidade da empresa',()=> {
  const company=demo(1402,{tools:['modelo_dominio'],workflow:'advanced',banks:{btg:'510'},roles:[{name:'planilha',label:'Planilha de caixa'}]});
  assert.ok(resolve(company,'organizar'));
  assert.equal(resolve(company,'base'),null);
  assert.equal(resolve(company,'extrato'),null);
});
