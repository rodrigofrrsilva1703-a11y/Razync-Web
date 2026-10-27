const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/js/home-motion.js','utf8');
function setup(saved=null,reduced=false,blocked=false) {
  const home={dataset:{}},attrs={},events={},stored=new Map([['razync:home-motion',saved]]);
  const button={setAttribute:(k,v)=>attrs[k]=v,addEventListener:(k,v)=>events.click=v};
  const media={matches:reduced,addEventListener:(k,v)=>events.media=v};
  const doc={hidden:false,querySelector:q=>q==='#portfolioPicker'?home:button,addEventListener:(k,v)=>events[k]=v};
  vm.runInNewContext(source,{document:doc,window:{matchMedia:()=>media},localStorage:{
    getItem:k=>{if(blocked)throw Error('blocked');return stored.get(k);},
    setItem:(k,v)=>{if(blocked)throw Error('blocked');stored.set(k,v);}}});
  return {home,button,attrs,events,stored,media,doc};
}
test('controle pausa e retoma sem afetar acesso ou conteúdo',()=>{
  const h=setup();assert.equal(h.home.dataset.motion,'playing');
  h.events.click();assert.equal(h.home.dataset.motion,'paused');assert.equal(h.attrs['aria-pressed'],'true');
  assert.equal(h.attrs['aria-label'],'Retomar animações do início');
  assert.equal(h.stored.get('razync:home-motion'),'paused');h.events.click();assert.equal(h.home.dataset.motion,'playing');
});
test('escolha de pausar é recuperada no próximo carregamento',()=>{
  const h=setup('paused');assert.equal(h.home.dataset.motion,'paused');assert.equal(h.attrs['aria-pressed'],'true');
});
test('movimento reduzido prevalece e mudança do sistema é respeitada',()=>{
  const h=setup(null,true);assert.equal(h.home.dataset.motion,'paused');assert.equal(h.button.disabled,true);
  h.media.matches=false;h.events.media();assert.equal(h.home.dataset.motion,'playing');assert.equal(h.button.disabled,false);
});
test('aba oculta pausa e retorno respeita a escolha manual',()=>{
  const h=setup();h.doc.hidden=true;h.events.visibilitychange();assert.equal(h.home.dataset.motion,'paused');
  h.doc.hidden=false;h.events.visibilitychange();assert.equal(h.home.dataset.motion,'playing');
  h.events.click();h.doc.hidden=true;h.events.visibilitychange();h.doc.hidden=false;h.events.visibilitychange();assert.equal(h.home.dataset.motion,'paused');
});
test('armazenamento indisponível não impede pausar',()=>{
  const h=setup(null,false,true);h.events.click();assert.equal(h.home.dataset.motion,'paused');
});
