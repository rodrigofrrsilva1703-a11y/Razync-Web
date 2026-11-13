const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../../assets/js/date-fields.js'),'utf8');

function setup(mobile = true) {
  const events = {}, formEvents = {};
  const input = {
    type:'date',value:'2026-10-06',dataset:{},
    addEventListener:(name,callback)=>events[name]=callback,
    setCustomValidity(message) { this.error=message; },
    dispatchEvent() { this.changed=true; },
    form:{addEventListener:(name,callback)=>formEvents[name]=callback}
  };
  const context = {window:{matchMedia:()=>({matches:mobile})},document:{querySelectorAll:()=>[input]},Event};
  vm.createContext(context); vm.runInContext(source,context);
  return {context,input,events,formEvents};
}

test('celular usa texto, teclado numérico e formato brasileiro',()=> {
  const {input}=setup();
  assert.equal(input.type,'text');
  assert.equal(input.inputMode,'numeric');
  assert.equal(input.value,'06/10/2026');
  assert.equal(input.placeholder,'DD/MM/AAAA');
});

test('desktop preserva o campo nativo de data',()=> {
  const {input}=setup(false);
  assert.equal(input.type,'date');
  assert.equal(input.value,'2026-10-06');
});

test('digitação recebe barras e gera ISO para a API',()=> {
  const {context,input,events}=setup();
  input.value='06102026'; events.input();
  assert.equal(input.value,'06/10/2026');
  assert.equal(context.dateApiValue(input),'2026-10-06');
  assert.equal(input.error,'');
  assert.equal(input.changed,true);
});

test('datas parciais e impossíveis não são enviadas',()=> {
  const {context,input,events}=setup();
  for(const value of ['31/04/2026','29/02/2026','00/10/2026','06/13/2026','06/10/0000','06/10']) {
    input.value=value; events.input();
    assert.ok(input.error,value);
    assert.throws(()=>context.dateApiValue(input),/data válida/);
  }
});

test('ano bissexto, datas vazias e comparação de períodos',()=> {
  const {context,input}=setup();
  assert.equal(context.typedDateToISO('29/02/2024'),'2024-02-29');
  assert.equal(context.typedDateToISO('29/02/2100'),null);
  assert.equal(context.typedDateToISO('29/02/2000'),'2000-02-29');
  assert.ok(context.typedDateToISO('31/01/2026') < context.typedDateToISO('01/02/2026'));
  input.value=''; assert.equal(context.dateApiValue(input),'');
});

test('reiniciar o formulário limpa o erro da data',()=> {
  const {input,events,formEvents}=setup();
  input.value='31/04/2026'; events.input();
  assert.ok(input.error);
  formEvents.reset(); assert.equal(input.error,'');
});
