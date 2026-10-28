const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/js/theme.js','utf8');
function setup(saved=null,osDark=false,blocked=false) {
  const listeners={},events={},attrs={},buttonEvents={};
  const root={dataset:{},style:{}};
  const button={setAttribute:(key,value)=>attrs[key]=value,addEventListener:(key,fn)=>buttonEvents[key]=fn};
  const label={},meta={};
  const system={matches:osDark,addEventListener:(key,fn)=>events.media=fn};
  const stored=new Map([['razync:theme',saved]]);
  const context={document:{documentElement:root,
    querySelector:q=>q==='#themeToggle'?button:q==='#themeToggleLabel'?label:meta,
    addEventListener:(key,fn)=>listeners[key]=fn},
    localStorage:{getItem:key=>{if(blocked)throw Error('blocked');return stored.get(key);},
      setItem:(key,value)=>{if(blocked)throw Error('blocked');stored.set(key,value);}},
    window:{matchMedia:query=>query.includes('reduced-motion')?{matches:false}:system,innerWidth:1280,innerHeight:720,addEventListener:(key,fn)=>events[key]=fn}};
  vm.runInNewContext(source,context);
  return {root,attrs,label,meta,stored,events,system,document:context.document,window:context.window,button,ready:()=>listeners.DOMContentLoaded(),click:()=>buttonEvents.click()};
}

test('revelação parte do botão, preserva cliques rápidos e limpa o estado temporário',async()=>{
  const h=setup();h.ready();
  h.button.getBoundingClientRect=()=>({left:1100,top:10,width:100,height:40});
  let finish,skipped=0,animation;
  h.root.animate=(frames,options)=>{animation={frames,options};};
  h.document.startViewTransition=update=>{
    update();
    return {ready:Promise.resolve(),finished:new Promise(resolve=>finish=resolve),skipTransition(){skipped++;}};
  };
  h.click();await Promise.resolve();
  assert.equal(h.root.dataset.theme,'dark');
  assert.equal(animation.frames.clipPath[0],'circle(0px at 1150px 30px)');
  assert.equal(animation.options.pseudoElement,'::view-transition-new(root)');
  h.click();assert.equal(skipped,1);assert.equal(h.root.dataset.theme,'light');
  finish();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.root.dataset.themeTransition,undefined);
});

test('movimento reduzido e falha da API mantêm a troca de tema funcional',()=>{
  const h=setup();h.ready();
  h.document.startViewTransition=()=>{throw Error('unsupported');};
  h.window.matchMedia=()=>({matches:true});
  h.click();assert.equal(h.root.dataset.theme,'dark');
  h.window.matchMedia=()=>({matches:false});
  h.button.getBoundingClientRect=()=>({left:0,top:0,width:40,height:40});
  h.click();assert.equal(h.root.dataset.theme,'light');
  assert.equal(h.root.dataset.themeTransition,undefined);
});
test('tema salvo é aplicado antes do DOM e prevalece sobre o sistema',()=>{
  const h=setup('light',true);assert.equal(h.root.dataset.theme,'light');assert.equal(h.root.style.colorScheme,'light');
  h.ready();assert.equal(h.attrs['aria-label'],'Ativar modo escuro');
});
test('sem preferência acompanha o sistema e reage à mudança',()=>{
  const h=setup(null,true);h.ready();assert.equal(h.root.dataset.theme,'dark');
  h.system.matches=false;h.events.media();assert.equal(h.root.dataset.theme,'light');
});
test('alternância salva a escolha e atualiza acessibilidade e metadados',()=>{
  const h=setup();h.ready();h.click();assert.equal(h.root.dataset.theme,'dark');
  assert.equal(h.stored.get('razync:theme'),'dark');assert.equal(h.attrs['aria-pressed'],'true');
  assert.equal(h.attrs['aria-label'],'Ativar modo claro');assert.equal(h.label.textContent,'Escuro');
  assert.equal(h.meta.content,'#080808');h.click();assert.equal(h.root.dataset.theme,'light');
});
test('armazenamento bloqueado não impede alternância nesta visita',()=>{
  const h=setup(null,false,true);h.ready();h.click();assert.equal(h.root.dataset.theme,'dark');
});
test('preferência inválida usa o sistema e sincroniza outras abas',()=>{
  const h=setup('invalid',true);h.ready();assert.equal(h.root.dataset.theme,'dark');
  h.events.storage({key:'razync:theme',newValue:'light'});assert.equal(h.root.dataset.theme,'light');
  h.events.media();assert.equal(h.root.dataset.theme,'light');
  h.events.storage({key:null,newValue:null});assert.equal(h.root.dataset.theme,'dark');
});
test('paleta escura mantém contraste de texto normal nas superfícies e avisos',()=>{
  const css=fs.readFileSync('assets/css/themes.css','utf8');
  const token=name=>css.match(new RegExp(`--${name}:(#[a-f0-9]{6})`))[1];
  const luminance=hex=>{
    const rgb=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255)
      .map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);
    return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
  };
  for (const [fg,bg] of [[token('dark-text'),token('surface')],[token('dark-muted'),token('surface-2')],
    [token('dark-accent'),'#202020'],[token('dark-success'),'#16382f'],
    [token('dark-error'),'#3b252e'],[token('dark-warning'),'#3a3023'],['#ffffff',token('action')]]) {
    const values=[luminance(fg),luminance(bg)].sort((a,b)=>b-a);
    assert.ok((values[0]+.05)/(values[1]+.05)>=4.5,`${fg} sobre ${bg}`);
  }
});
