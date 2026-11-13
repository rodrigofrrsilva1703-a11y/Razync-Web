const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function setup(accept='.pdf,.xls,.xlsx') {
  let changed;
  class Element {
    constructor(type='div'){this.type=type;this.nodeType=1;this.children=[];this.attrs={};this.textContent='';}
    matches(){return this.type==='file';}
    querySelectorAll(){return this.children.flatMap(child=>[...(child.type==='file'?[child]:[]),...child.querySelectorAll()]);}
    closest(){return this.shell || null;}
    appendChild(child){if(child.parentElement)child.parentElement.children=child.parentElement.children.filter(n=>n!==child);this.children.push(child);child.parentElement=this;}
    getAttribute(key){return this.attrs[key] || null;}
    setAttribute(key,value){this.attrs[key]=value;}
  }
  const parent=new Element(),input=new Element('file');input.accept=accept;
  input.setAttribute('aria-describedby','existing-help');parent.appendChild(input);
  const context={document:{documentElement:parent,querySelectorAll:()=>[input],createElement:()=>new Element('small')},
    MutationObserver:class{constructor(fn){changed=fn;}observe(){}}};
  vm.runInNewContext(fs.readFileSync('assets/js/file-formats.js','utf8'),context);
  return {input,parent,Element,notify:records=>changed(records),label:()=>parent.children.find(n=>n.className==='file-accepted-formats')};
}
test('mostra os formatos reais sem remover descrições acessíveis existentes',()=>{
  const h=setup();assert.equal(h.label().textContent,'Formatos aceitos: PDF, XLS, XLSX');
  assert.equal(h.input.getAttribute('aria-describedby'),'existing-help '+h.label().id);
});
test('trocar de empresa atualiza accept sem duplicar a indicação',()=>{
  const h=setup();h.input.accept='.zip';
  for(let i=0;i<3;i++)h.notify([{type:'attributes',target:h.input}]);
  assert.equal(h.label().textContent,'Formatos aceitos: ZIP');
  assert.equal(h.parent.children.filter(n=>n.className==='file-accepted-formats').length,1);
});
test('campos dinâmicos e mudança para o contêiner de upload mantêm o texto junto do campo',()=>{
  const h=setup(),field=new h.Element(),input=new h.Element('file');input.accept='.ofx,.csv';field.appendChild(input);
  h.notify([{type:'childList',addedNodes:[field]}]);
  const label=field.children.find(n=>n.className==='file-accepted-formats');
  assert.equal(label.textContent,'Formatos aceitos: OFX, CSV');
  const shell=new h.Element();input.shell=shell;shell.appendChild(input);
  h.notify([{type:'childList',addedNodes:[input]}]);
  assert.equal(label.parentElement,shell);
  assert.ok(!field.children.includes(label));
});
test('MIME não repete formatos e accept vazio não anuncia suporte genérico',()=>{
  const h=setup('application/pdf, .PDF, application/vnd.ms-excel,.xlsx,');
  assert.equal(h.label().textContent,'Formatos aceitos: PDF, XLS, XLSX');
  h.input.accept='';h.notify([{type:'attributes',target:h.input}]);
  assert.equal(h.label().textContent,'Consulte os formatos nas instruções da ferramenta.');
});
