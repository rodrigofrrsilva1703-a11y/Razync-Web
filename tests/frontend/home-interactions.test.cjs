const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/js/home-interactions.js','utf8');
function setup() {
  const events={},styles=new Map(),frames=new Map();let next=0,measurements=0;
  const card={isConnected:true,style:{setProperty:(k,v)=>styles.set(k,v),removeProperty:k=>styles.delete(k)},
    getBoundingClientRect:()=>{measurements++;return {left:10,top:20,width:200,height:100};}};
  const home={hidden:false,contains:node=>node===card,addEventListener:(k,v)=>events[k]=v};
  const media={matches:true,addEventListener:(k,v)=>events.media=v};
  const doc={hidden:false,querySelector:()=>home,addEventListener:(k,v)=>events[k]=v};
  vm.runInNewContext(source,{document:doc,window:{matchMedia:()=>media,
    requestAnimationFrame:fn=>{const id=++next;frames.set(id,fn);return id;},cancelAnimationFrame:id=>frames.delete(id),
    addEventListener:(k,v)=>events[k]=v}});
  const move=(x,y,type='mouse')=>events.pointermove({target:{closest:()=>card},clientX:x,clientY:y,pointerType:type});
  const flush=()=>{const queued=[...frames.values()];frames.clear();queued.forEach(fn=>fn());};
  return {events,styles,frames,card,home,doc,media,move,flush,measurements:()=>measurements};
}
test('movimentos são agrupados em um frame e medem o cartão uma única vez',()=>{
  const h=setup();for(let i=0;i<100;i++)h.move(10+i,40);
  assert.equal(h.frames.size,1);assert.equal(h.measurements(),1);h.flush();
  assert.equal(h.styles.get('--pointer-x'),'49.5%');assert.equal(h.styles.get('--pointer-y'),'20.0%');
});
test('sair, clicar ou mudar tamanho limpa efeito e frame pendente',()=>{
  for(const event of ['pointerleave','click','resize','blur','scroll']) {
    const h=setup();h.move(110,70);h.flush();h.move(210,120);h.events[event]();
    assert.equal(h.frames.size,0);assert.equal(h.styles.size,0);
  }
});
test('toque e preferência reduzida não iniciam efeitos',()=>{
  const h=setup();h.move(110,70,'touch');assert.equal(h.frames.size,0);
  h.media.matches=false;h.move(110,70);assert.equal(h.frames.size,0);
});
test('aba oculta e cartão removido suspendem os cálculos com segurança',()=>{
  const h=setup();h.move(110,70);h.doc.hidden=true;h.events.visibilitychange();assert.equal(h.frames.size,0);
  h.doc.hidden=false;h.move(110,70);h.card.isConnected=false;h.flush();assert.equal(h.styles.size,0);
});
test('valores ficam limitados à área do cartão',()=>{
  const h=setup();h.move(500,-100);h.flush();assert.equal(h.styles.get('--pointer-x'),'100.0%');
  assert.equal(h.styles.get('--tilt-x'),'1.50deg');assert.equal(h.styles.get('--tilt-y'),'1.50deg');
});
