const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function setup(){
  class Element {
    constructor(tag){this.tag=tag;this.children=[];this.events={};this.attributes={};this.value='';}
    append(...items){this.children.push(...items);} appendChild(item){this.children.push(item);return item;}
    setAttribute(k,v){this.attributes[k]=v;} addEventListener(k,fn){this.events[k]=fn;}
    reportValidity(){return true;}
  }
  class FormData {
    constructor(){this.values=[];}append(k,v){this.values.push([k,v]);}entries(){return this.values[Symbol.iterator]();}
    get(k){return this.values.find(([name])=>name===k)?.[1];}
  }
  const calls=[],downloads=[];
  const context={document:{createElement:tag=>new Element(tag)},FormData,AbortController,
    fetch:async(url,options)=>{calls.push({url,...options});return {ok:true};}};
  vm.createContext(context);vm.runInContext(fs.readFileSync('assets/js/bank-investments.js','utf8'),context);
  const target=new Element('div'),snapshot=new FormData();snapshot.append('model_file','MODELO_A');snapshot.append('files','EXTRATO_A');snapshot.append('options_json','{"data_inicial":"2026-08-01"}');
  const state={target,company:3,banks:[{code:'itau',label:'Itaú',account:'508'}],snapshot,summary:{ok:true},rows:[{DATA:'01/08/2026'}],balances:()=>({ok:true}),isCurrent:()=>true,signal:new AbortController().signal,api:'/api',download:async(r,name)=>downloads.push(name),responseError:async()=> 'Falha'};
  const all=root=>[root,...root.children.flatMap(all)];
  return {context,state,calls,downloads,all,find:(cls)=>all(target).find(el=>el.className===cls)};
}

test('opção só aparece com dias conferidos, saldo batendo e sem erros parciais',()=>{
  for(const modify of [s=>s.rows=[],s=>s.summary={ok:false},s=>s.summary.errors=[{}],s=>s.balances=()=>({ok:false})]){
    const {context,state}=setup();modify(state);context.RazyncInvestments.mount(state);assert.equal(state.target.children.length,0);
  }
});

test('TXT usa mesma conta para aplicação e resgate e preserva arquivos e período da prévia',async()=>{
  const {context,state,calls,downloads,all,find}=setup();context.RazyncInvestments.mount(state);
  const inputs=all(state.target).filter(el=>el.tag==='input');assert.equal(inputs[0].readOnly,true);inputs[1].value='900';
  await find('bank-investments-form').events.submit({preventDefault(){}});
  assert.equal(calls[0].url,'/api/api/v1/conferencia-extrato/3/aplicacoes-resgates');
  assert.equal(calls[0].body.get('model_file'),'MODELO_A');assert.equal(calls[0].body.get('files'),'EXTRATO_A');
  assert.equal(calls[0].body.get('options_json'),'{"data_inicial":"2026-08-01"}');
  assert.deepEqual(JSON.parse(calls[0].body.get('settings_json')),{itau:{conta_banco:'508',conta_aplicacao:'900',saldo_anterior:'0,00'}});
  assert.equal(downloads.length,1);
});

test('trocar conta durante a geração cancela e não baixa arquivo com configuração anterior',async()=>{
  const {context,state,downloads,all,find}=setup();let finish;
  context.fetch=()=>new Promise(resolve=>{finish=resolve;});context.RazyncInvestments.mount(state);
  const inputs=all(state.target).filter(el=>el.tag==='input');inputs[1].value='900';
  const form=find('bank-investments-form'),pending=form.events.submit({preventDefault(){}});
  inputs[1].value='901';form.events.input();finish({ok:true});await pending;
  assert.equal(downloads.length,0);assert.equal(find('bank-investments-download').disabled,false);
});

test('conta igual ao banco não gera arquivo',async()=>{
  const {context,state,calls,all,find}=setup();context.RazyncInvestments.mount(state);
  all(state.target).filter(el=>el.tag==='input')[1].value='508';
  await find('bank-investments-form').events.submit({preventDefault(){}});
  assert.equal(calls.length,0);assert.match(find('bank-investments-message').textContent,/diferente/);
});
