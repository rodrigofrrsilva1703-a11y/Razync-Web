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
    window:{matchMedia:()=>system,addEventListener:(key,fn)=>events[key]=fn}};
  vm.runInNewContext(source,context);
  return {root,attrs,label,meta,stored,events,system,ready:()=>listeners.DOMContentLoaded(),click:()=>buttonEvents.click()};
}
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
  assert.equal(h.meta.content,'#0e1724');h.click();assert.equal(h.root.dataset.theme,'light');
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
  for (const [fg,bg] of [[token('dark-text'),'#172333'],[token('dark-muted'),'#1d2c3e'],
    [token('dark-accent'),'#243c55'],[token('dark-success'),'#16382f'],
    [token('dark-error'),'#3b252e'],[token('dark-warning'),'#3a3023'],['#ffffff','#376eae']]) {
    const values=[luminance(fg),luminance(bg)].sort((a,b)=>b-a);
    assert.ok((values[0]+.05)/(values[1]+.05)>=4.5,`${fg} sobre ${bg}`);
  }
});
