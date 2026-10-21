const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const app = fs.readFileSync('assets/js/app.js','utf8');

function harness() {
  const handlers = {}, formHandlers = {};
  const input = {dataset:{},multiple:true,files:[],form:{addEventListener:(name,fn)=>formHandlers[name]=fn},
    parentNode:{insertBefore(){}},addEventListener:(name,fn)=>handlers[name]=fn,
    dispatchEvent:()=>handlers.change()};
  const element=()=>({classList:{add(){},remove(){}},appendChild(){},addEventListener(){},querySelector:()=>({})});
  const context={document:{createElement:element},Event:class{},queueMicrotask:fn=>fn(),
    DataTransfer:class {constructor(){this.files=[];this.items={add:file=>this.files.push(file)};}},
    updateFileSelection(){}};
  vm.createContext(context);
  for (const [start,end] of [['function enhanceFileInput(', 'function enhanceFileInputs('], ['function replaceInputFiles(', 'function updateFileSelection(']]) {
    vm.runInContext(app.slice(app.indexOf(start),app.indexOf(end)),context);
  }
  context.enhanceFileInput(input);
  return {input,handlers,formHandlers,context};
}
const file=name=>({name,size:20,lastModified:1});

test('seleções sucessivas preservam anexos e remover um arquivo não o reinclui',()=>{
  const h=harness(), a=file('julho.xlsx'),b=file('agosto.xlsx'),c=file('setembro.xlsx');
  h.input.files=[a];h.handlers.change();
  h.input.files=[b];h.handlers.change();
  assert.deepEqual(h.input.files.map(x=>x.name),['julho.xlsx','agosto.xlsx']);
  h.context.removeSelectedFile(h.input,0);
  assert.deepEqual(h.input.files.map(x=>x.name),['agosto.xlsx']);
  h.input.files=[c];h.handlers.change();
  assert.deepEqual(h.input.files.map(x=>x.name),['agosto.xlsx','setembro.xlsx']);
});

test('reset da empresa limpa também a seleção acumulada',()=>{
  const h=harness();h.input.files=[file('antigo.xlsx')];h.handlers.change();
  h.input.files=[];h.formHandlers.reset();
  h.input.files=[file('novo.xlsx')];h.handlers.change();
  assert.deepEqual(h.input.files.map(x=>x.name),['novo.xlsx']);
});

test('reselecionar o mesmo arquivo não duplica o anexo',()=>{
  const h=harness();h.input.files=[file('julho.xlsx')];h.handlers.change();
  h.input.files=[file('julho.xlsx')];h.handlers.change();
  assert.equal(h.input.files.length,1);
});

test('backend antigo não recebe múltiplos arquivos em campos que ignorariam os anteriores',async()=>{
  const sent=[];
  const context={FormData,Blob,window:{RAZYNC_CONFIG:{apiBase:'https://api.example'},fetch:async(url,options)=>{
    sent.push(url);return {ok:true,json:async()=>({ok:true})};
  }}};
  vm.createContext(context);vm.runInContext(fs.readFileSync('assets/js/attachment-support.js','utf8'),context);
  const body=new FormData();body.append('razao',new Blob(['a']),'a.csv');body.append('razao',new Blob(['b']),'b.csv');
  await assert.rejects(context.window.fetch('https://api.example/api/v1/conferencia-fiscal/preview',{body}),/aguarda a atualização/);
  assert.deepEqual(sent,['https://api.example/health']);
});
