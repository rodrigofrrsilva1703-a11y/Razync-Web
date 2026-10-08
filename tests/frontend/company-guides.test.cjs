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

test('ajuda da 266 abre, fecha ao trocar de ferramenta e some em outras empresas',()=> {
  const listeners = {};
  const nodes = {};
  function node(id) {
    if (!nodes[id]) {
      nodes[id] = {
        hidden:true, textContent:'', attrs:{}, children:[],
        addEventListener(type,cb) { this.handlers ||= {}; this.handlers[type]=cb; },
        setAttribute(name,val) { this.attrs[name]=val; },
        replaceChildren() { this.children=[]; },
        appendChild(child) { this.children.push(child); },
        append(...children) { this.children.push(...children); },
        focus() { this.focused=true; },
        contains(target) { return target===this; }
      };
    }
    return nodes[id];
  }
  const document = {
    createElement:()=>node('generated-'+Object.keys(nodes).length),
    addEventListener:(event,callback)=> { listeners[event]=callback; }
  };
  const context={document,selected:{codigo:266}, $:node};
  vm.createContext(context);
  const start=app.indexOf('const COMPANY_TOOL_GUIDES =');
  const end=app.indexOf('function activateTool(name)',start);
  assert.ok(start>=0 && end>start);
  vm.runInContext(app.slice(start,end),context);

  context.renderCompanyToolGuide('organizar');
  assert.equal(node('#companyToolHelp').hidden,false);
  assert.equal(node('#companyToolGuide').hidden,true);
  assert.equal(node('#companyToolGuideSteps').children.length,4);

  node('#companyToolHelpButton').handlers.click();
  assert.equal(node('#companyToolGuide').hidden,false);
  assert.equal(node('#companyToolHelpButton').attrs['aria-expanded'],'true');

  context.renderCompanyToolGuide('base');
  assert.equal(node('#companyToolGuide').hidden,true);
  assert.equal(node('#companyToolGuideSteps').children.length,3);

  node('#companyToolHelpButton').handlers.click();
  listeners.keydown({key:'Escape'});
  assert.equal(node('#companyToolGuide').hidden,true);

  node('#companyToolHelpButton').handlers.click();
  listeners.pointerdown({target:node('#outside')});
  assert.equal(node('#companyToolGuide').hidden,true);

  context.selected={codigo:1402};
  context.renderCompanyToolGuide('organizar');
  assert.equal(node('#companyToolHelp').hidden,true);
});
