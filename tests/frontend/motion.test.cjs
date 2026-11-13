const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('loading acompanha processamento, conclusão, erro e limpeza da mensagem', () => {
  let callback;
  const classes = new Set(), attrs = {};
  const message = {nodeType:1, textContent:'', closest:()=>message,
    classList:{toggle:(name,on)=>on ? classes.add(name) : classes.delete(name)},
    setAttribute:(name,value)=>attrs[name]=value, hasAttribute:name=>name in attrs};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../assets/js/motion.js'),'utf8'), {
    document:{body:{}, querySelectorAll:()=>[message]},
    MutationObserver:class {constructor(fn){callback=fn;} observe(){}}
  });
  for (const [text,busy] of [['Classificando…',true],['Conferindo saldos por dia…',true],
    ['Arquivos prontos. Montando conciliação diária…',true],['Todos os dias analisados estão batendo.',false],
    ['Não foi possível processar o arquivo.',false],['',false]]) {
    message.textContent=text;
    callback([{target:message,addedNodes:[]}]);
    assert.equal(classes.has('preview-loading'),busy,text);
    assert.equal(attrs['aria-busy'],String(busy));
  }
});
