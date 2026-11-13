const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/js/home-motion.js','utf8');
function setup(reduced=false) {
  const home={dataset:{}},events={};
  const media={matches:reduced,addEventListener:(k,v)=>events.media=v};
  const doc={hidden:false,querySelector:()=>home,addEventListener:(k,v)=>events[k]=v};
  vm.runInNewContext(source,{document:doc,window:{matchMedia:()=>media}});
  return {home,events,media,doc};
}
test('início anima sem depender de botão ou armazenamento',()=>{
  const h=setup();assert.equal(h.home.dataset.motion,'playing');
});
test('preferência de movimento reduzido acompanha o sistema',()=>{
  const h=setup(true);assert.equal(h.home.dataset.motion,'paused');
  h.media.matches=false;h.events.media();assert.equal(h.home.dataset.motion,'playing');
});
test('aba oculta suspende movimento e volta ao estado do sistema',()=>{
  const h=setup();h.doc.hidden=true;h.events.visibilitychange();assert.equal(h.home.dataset.motion,'paused');
  h.doc.hidden=false;h.events.visibilitychange();assert.equal(h.home.dataset.motion,'playing');
  h.media.matches=true;h.events.media();h.doc.hidden=true;h.events.visibilitychange();h.doc.hidden=false;h.events.visibilitychange();assert.equal(h.home.dataset.motion,'paused');
});
