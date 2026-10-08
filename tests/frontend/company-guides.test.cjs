const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const app = fs.readFileSync(path.join(__dirname,'../../assets/js/app.js'),'utf8');
const html = fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8');
const css = fs.readFileSync(path.join(__dirname,'../../assets/css/workspace.css'),'utf8');

test('empresa 266 possui instruções para as três ferramentas',()=> {
  assert.match(app,/266:\s*\{/);
  assert.match(app,/organizar:\s*\{/);
  assert.match(app,/base:\s*\{/);
  assert.match(app,/extrato:\s*\{/);
  for(const banco of ['Itaú 508','Bradesco 9','Fibra 506']) assert.ok(app.includes(banco));
  assert.match(app,/Só fica “Batendo” quando os dois saldos forem zero/);
});

test('guia é flutuante e abre somente dentro da empresa com instruções',()=> {
  assert.match(html,/id="companyToolHelp"/);
  assert.match(html,/id="companyToolHelpButton"/);
  assert.match(html,/aria-expanded="false"/);
  assert.match(html,/id="companyToolGuideClose"/);
  assert.match(css,/\.company-tool-help\s*\{[^}]*position:fixed/s);
  assert.match(css,/\.company-tool-guide/);
  assert.match(app,/renderCompanyToolGuide\(name\)/);
  assert.match(app,/wrapper\.hidden = !content/);
  assert.match(app,/closeCompanyToolHelp\(true\)/);
});

test('ajuda da 266 abre, arrasta, fecha, lembra a posição e não aparece em outras empresas',()=> {
  const listeners={}, timers=[], stored={};
  const nodes={};
  const viewport={innerWidth:400,innerHeight:700};
  function node(id) {
    if (!nodes[id]) {
      nodes[id]={
        hidden:true,textContent:'',attrs:{},children:[],style:{},offsetWidth:46,offsetHeight:46,
        classList:{add(){},remove(){}},
        addEventListener(type,cb){this.handlers ||= {};this.handlers[type]=cb;},
        setAttribute(name,val){this.attrs[name]=val;},
        replaceChildren(){this.children=[];},
        appendChild(child){this.children.push(child);},
        append(...children){this.children.push(...children);},
        focus(){this.focused=true;},
        contains(target){return target===this || (id==='#companyToolHelp' && (target===node('#companyToolHelpButton') || target===node('#companyToolGuide')));},
        setPointerCapture(){},hasPointerCapture(){return true;},releasePointerCapture(){},
        getBoundingClientRect(){
          if(id==='#companyToolGuide')return {left:0,top:0,right:310,bottom:190,width:310,height:190};
          const wrapper=node('#companyToolHelp');
          const left=parseFloat(wrapper.style.left) || viewport.innerWidth-70;
          const top=parseFloat(wrapper.style.top) || viewport.innerHeight-70;
          return {left,top,right:left+46,bottom:top+46,width:46,height:46};
        }
      };
    }
    return nodes[id];
  }
  const document={
    createElement:()=>node('generated-'+Object.keys(nodes).length),
    addEventListener:(event,cb)=>{listeners[event]=cb;}
  };
  const context={
    document,selected:{codigo:266},$:node,
    window:{get innerWidth(){return viewport.innerWidth;},get innerHeight(){return viewport.innerHeight;},addEventListener:(event,cb)=>{listeners[event]=cb;}},
    localStorage:{getItem:key=>stored[key] || null,setItem:(key,value)=>{stored[key]=value;}},
    setTimeout:cb=>{timers.push(cb);}
  };
  vm.createContext(context);
  const start=app.indexOf('const COMPANY_TOOL_GUIDES =');
  const end=app.indexOf('function activateTool(name)',start);
  assert.ok(start>=0 && end>start);
  vm.runInContext(app.slice(start,end),context);

  context.renderCompanyToolGuide('organizar');
  assert.equal(node('#companyToolHelp').hidden,false);
  assert.equal(node('#companyToolGuide').hidden,true);
  assert.equal(node('#companyToolGuideSteps').children.length,4);

  const trigger=node('#companyToolHelpButton');
  trigger.handlers.click();
  assert.equal(node('#companyToolGuide').hidden,false);
  assert.equal(trigger.attrs['aria-expanded'],'true');
  assert.equal(node('#companyToolGuide').style.left.endsWith('px'),true);
  context.renderCompanyToolGuide('base');
  assert.equal(node('#companyToolGuide').hidden,true);
  assert.equal(node('#companyToolGuideSteps').children.length,3);

  trigger.handlers.click();
  listeners.keydown({key:'Escape'});
  assert.equal(node('#companyToolGuide').hidden,true);
  trigger.handlers.click();
  listeners.pointerdown({target:node('#outside')});
  assert.equal(node('#companyToolGuide').hidden,true);

  trigger.handlers.pointerdown({pointerId:7,pointerType:'touch',button:0,clientX:330,clientY:630});
  trigger.handlers.pointermove({pointerId:7,clientX:150,clientY:460,cancelable:true,preventDefault(){}});
  assert.equal(node('#companyToolHelp').style.left,'150px');
  assert.equal(node('#companyToolHelp').style.top,'460px');
  trigger.handlers.pointerup({pointerId:7});
  assert.match(stored['razync-company-help-position-v1'],/"x":150/);
  trigger.handlers.click();
  assert.equal(node('#companyToolGuide').hidden,true,'arrastar não deve abrir ajuda');
  timers.forEach(fn=>fn());
  trigger.handlers.click();
  assert.equal(node('#companyToolGuide').hidden,false,'clicar ainda abre ajuda');

  viewport.innerWidth=250;
  viewport.innerHeight=340;
  listeners.resize();
  assert.ok(parseFloat(node('#companyToolHelp').style.left)<=192);
  assert.ok(parseFloat(node('#companyToolHelp').style.top)<=282);

  context.selected={codigo:1402};
  context.renderCompanyToolGuide('organizar');
  assert.equal(node('#companyToolHelp').hidden,true);
});
