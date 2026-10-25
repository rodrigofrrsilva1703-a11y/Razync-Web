const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
function run(source,instant){const redirects=[];const clock={now:instant};let tick;
 class FixedDate extends Date {constructor(...args){super(...(args.length?args:[clock.now]));}}
 const interval=fn=>{tick=fn;};
 const context={Date:FixedDate,Intl,setInterval:interval,window:{location:{replace:path=>redirects.push(path)},setInterval:interval}};
 vm.createContext(context);vm.runInContext(source,context);return {redirects,clock,tick:()=>tick()};
}
const gate=fs.readFileSync('assets/js/operating-hours.js','utf8');
for(const [instant,closed] of [['2026-10-25T09:59:00Z',true],['2026-10-25T10:00:00Z',false],['2026-10-26T02:59:00Z',false],['2026-10-26T03:00:00Z',true]]){
 test(`domingo usa horário de Brasília: ${instant}`,()=>{const h=run(gate,instant);assert.equal(h.redirects.length,closed?1:0);});
}
test('aba aberta no domingo encerra somente à meia-noite',()=>{const h=run(gate,'2026-10-25T15:00:00Z');assert.equal(h.redirects.length,0);h.clock.now='2026-10-26T03:00:00Z';h.tick();assert.deepEqual(h.redirects,['./indisponivel.html']);});
test('página de pausa reabre automaticamente domingo às sete',()=>{
 const html=fs.readFileSync('indisponivel.html','utf8');const source=html.match(/<script>([\s\S]*?)<\/script>/)[1];
 const h=run(source,'2026-10-25T09:59:00Z');assert.equal(h.redirects.length,0);h.clock.now='2026-10-25T10:00:00Z';h.tick();assert.deepEqual(h.redirects,['./']);
});
