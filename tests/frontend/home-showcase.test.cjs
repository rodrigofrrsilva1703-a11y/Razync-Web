const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/js/home-showcase.js','utf8');
function setup(reduced=false) {
 const timers=new Map(),events={},observers=[];let id=0,now=0;
 const node=()=>({dataset:{},attributes:{},hidden:false,events:{},setAttribute(k,v){this.attributes[k]=v},addEventListener(k,fn){this.events[k]=fn}});
 const buttons=[node(),node(),node()],panels=[node(),node(),node()],pause=node(),scene=node(),home=node();
 scene.querySelectorAll=s=>s==='.showcase-step'?buttons:panels;
 scene.querySelector=()=>pause;scene.contains=x=>buttons.includes(x)||x===pause;
 home.querySelector=()=>scene;home.dataset.motion='playing';
 const media={matches:reduced,addEventListener:(k,fn)=>events.media=fn};
 const classes=new Set(),doc={hidden:false,body:{classList:{contains:k=>classes.has(k)}},querySelector:()=>home,addEventListener:(k,fn)=>events[k]=fn};
 vm.runInNewContext(source,{document:doc,window:{matchMedia:()=>media,setTimeout:(fn,delay)=>{const n=++id;timers.set(n,{fn,delay});return n},clearTimeout:n=>timers.delete(n)},Date:{now:()=>now},MutationObserver:class{constructor(fn){observers.push(fn)}observe(){}}});
 const advance=()=>{const jobs=[...timers.values()];timers.clear();jobs.forEach(job=>{now+=job.delay;job.fn()})};
 return {timers,events,observers,buttons,panels,pause,scene,home,media,doc,classes,advance,elapse:ms=>{now+=ms},delay:()=>[...timers.values()][0]?.delay};
}
test('uma etapa visível por vez e avanço automático',()=>{
 const h=setup();assert.deepEqual(h.panels.map(p=>p.hidden),[false,true,true]);assert.equal(h.timers.size,1);
 h.advance();assert.equal(h.scene.dataset.stage,'1');assert.deepEqual(h.panels.map(p=>p.hidden),[true,false,true]);assert.equal(h.buttons[1].attributes['aria-pressed'],'true');assert.equal(h.timers.size,1);
 h.buttons[2].events.click();assert.equal(h.scene.dataset.stage,'2');assert.equal(h.timers.size,1);
});
test('movimento reduzido e aba oculta suspendem a demonstração',()=>{
 const h=setup(true);assert.equal(h.timers.size,0);h.buttons[2].events.click();assert.equal(h.scene.dataset.stage,'2');
 h.media.matches=false;h.events.media();assert.equal(h.timers.size,1);
 h.doc.hidden=true;h.events.visibilitychange();assert.equal(h.timers.size,0);
 h.doc.hidden=false;h.events.visibilitychange();assert.equal(h.timers.size,1);
});
test('mouse, foco, menu e entrada na carteira suspendem a demonstração',()=>{
 const h=setup();h.scene.events.pointerenter({pointerType:'mouse'});assert.equal(h.timers.size,0);
 h.scene.events.pointerleave();assert.equal(h.timers.size,1);
 h.scene.events.focusin();assert.equal(h.timers.size,0);
 h.scene.events.focusout({relatedTarget:null});assert.equal(h.timers.size,1);
 h.classes.add('nav-drawer-open');h.observers[0]();assert.equal(h.timers.size,0);
 h.classes.clear();h.observers[0]();assert.equal(h.timers.size,1);
 h.home.hidden=true;h.observers[0]();assert.equal(h.timers.size,0);
 h.home.hidden=false;h.observers[0]();assert.equal(h.timers.size,1);
});
test('pausa manual persiste e retoma sem duplicar temporizadores',()=>{
 const h=setup();h.pause.events.click();assert.equal(h.timers.size,0);assert.equal(h.pause.attributes['aria-pressed'],'true');
 h.events.visibilitychange();h.observers[0]();assert.equal(h.timers.size,0);
 h.pause.events.click();assert.equal(h.timers.size,1);assert.equal(h.pause.attributes['aria-label'],'Pausar demonstração');
});

test('pausar preserva o tempo restante em vez de reiniciar a etapa',()=>{
 const h=setup();h.elapse(1700);h.scene.events.pointerenter({pointerType:'mouse'});assert.equal(h.timers.size,0);
 h.elapse(8000);h.scene.events.pointerleave();assert.equal(h.delay(),3900);
 h.buttons[0].events.click();assert.equal(h.delay(),3900);
 h.advance();assert.equal(h.scene.dataset.stage,'1');assert.equal(h.delay(),5600);
});

test('mouse pausa apenas a troca da etapa; pausa explícita também para a arte',()=>{
 const h=setup();h.scene.events.pointerenter({pointerType:'mouse'});
 assert.equal(h.scene.dataset.playing,'false');assert.equal(h.scene.dataset.artMotion,'playing');
 h.pause.events.click();assert.equal(h.scene.dataset.artMotion,'paused');
 h.pause.events.click();assert.equal(h.scene.dataset.artMotion,'playing');
 h.media.matches=true;h.events.media();assert.equal(h.scene.dataset.artMotion,'paused');
});
