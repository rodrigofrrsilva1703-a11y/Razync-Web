const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../../assets/js/workspace-ui.js'),'utf8');
const dates = fs.readFileSync(path.join(__dirname,'../../assets/js/date-fields.js'),'utf8');

function setup() {
  const context={
    window:{matchMedia:()=>({matches:false})}, document:{}, selected:null,
    bankLabel:(bank,account)=>`${bank} ${account}`,bankSelect:{value:'itau'}
  };
  vm.createContext(context);vm.runInContext(dates+'\n'+source,context);
  return {context};
}

test('prévia sinaliza data impossível sem marcar contas vazias ou zero',()=> {
  const h=setup(),headers=['DATA','DÉBITO','CRÉDITO','VALOR'];
  assert.deepEqual([...h.context.previewRowIssues(headers,['31/04/2026','',1155,-100])],['Data inválida']);
  assert.deepEqual([...h.context.previewRowIssues(headers,['06/10/2026',8,9,100])],[]);
  assert.deepEqual([...h.context.previewRowIssues(headers,['2024-02-29T00:00:00',0,9,100])],[]);
  assert.deepEqual([...h.context.previewRowIssues(headers,['06/10/2026','',0,100])],[]);
});

test('resumo de arquivos identifica a conta configurada sem inferir bancos desconhecidos',()=> {
  const h=setup();h.context.selected={capabilities:{banks:{sicredi:'1155'}}};
  assert.equal(h.context.selectedFileBankLabel({dataset:{reconcileBank:'sicredi'}}),'sicredi 1155');
  assert.equal(h.context.selectedFileBankLabel({dataset:{},id:'classifyFile'}),'Abas do modelo');
  assert.equal(h.context.selectedFileBankLabel({dataset:{},id:'auxiliar'}),'Identificado no processamento');
});
