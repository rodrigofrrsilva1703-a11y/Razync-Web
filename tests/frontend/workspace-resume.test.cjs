const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../../assets/js/workspace-resume.js'), 'utf8');

async function fixture(identity, mobile = false, catalogAvailable = true) {
  const date = {id:'processStart', value:'', dataset: mobile ? {manualDate:'true'} : {}, validity:{valid:true}, closest:()=>null};
  const file = {id:'fileInput', value:'secret.pdf'};
  const panel = {hidden:true, dataset:{}, contains:el=>[date,file].includes(el),
    querySelectorAll:()=>[{dataset:{tool:'extrato'}, hidden:false}]};
  const view = {id:'companiesView', classList:{contains:()=>true}};
  const values = new Map([['razync:workspace-position:v1', JSON.stringify({
    owner:'same@example.test', view:'companies', wallet:'wallet', company:'42', tool:'extrato',
    values:{processStart:'2026-11-01',fileInput:'saved-private.pdf'}
  })]]);
  const company = {codigo:42};
  const events = {};
  const context = {
    panel, selected:null, activePortfolio:null, companies:catalogAvailable ? [company] : [], portfolios:[{id:'wallet'}],
    dateApiValue:input=>input.value.split("/").reverse().join("-"),
    initialCatalog:Promise.resolve(), companyBelongsToPortfolio:()=>true, hasCompanyTools:()=>true,
    document:{getElementById:id=>({companiesView:view,processStart:date,fileInput:file}[id] || null),
      querySelector:()=>panel.hidden ? view : null, addEventListener(){}},
    window:{addEventListener(name, handler){events[name] = handler;},RazyncSiteAccess:{ready:Promise.resolve(),identity:()=>identity}},
    sessionStorage:{getItem:key=>values.get(key),setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)},
  };
  context.selectPortfolio = id => {context.activePortfolio = {id};};
  context.openCompany = item => {context.selected = item; panel.hidden = false;};
  context.activateTool = name => {panel.dataset.activeTool = name;};
  vm.createContext(context);
  vm.runInContext(source, context);
  await new Promise(resolve=>setImmediate(resolve));
  return {context, panel, date, file, values, events, company};
}

test('recarregar restaura empresa, ferramenta e datas, sem recuperar nem gravar arquivo', async () => {
  const {context,panel,date,file,values} = await fixture('same@example.test');
  assert.equal(context.selected?.codigo,42);
  assert.equal(panel.dataset.activeTool,'extrato');
  assert.equal(date.value,'2026-11-01');
  assert.equal(file.value,'secret.pdf');
  context.window.RazyncWorkspaceResume.save();
  const stored = [...values.values()][0];
  assert.doesNotMatch(stored,/\.pdf|fileInput/);
  context.window.RazyncWorkspaceResume.clear();
  assert.equal(values.size,0);
});

test('outra conta não restaura a área de trabalho anterior', async () => {
  const {context,date} = await fixture('other@example.test');
  assert.equal(context.selected,null);
  assert.equal(date.value,'');
});


test('recarregar no celular mantém o formato DD/MM/AAAA', async () => {
  const {context,date,values} = await fixture('same@example.test', true);
  assert.equal(date.value,'01/11/2026');
  context.window.RazyncWorkspaceResume.save();
  assert.equal(JSON.parse([...values.values()][0]).values.processStart,'2026-11-01');
});

test('catálogo indisponível mantém a posição salva e permite retomá-la ao reconectar', async () => {
  const {context,panel,date,values,events,company} = await fixture('same@example.test', false, false);
  assert.equal(context.selected,null);
  const stored = [...values.values()][0];
  events.pagehide();
  assert.equal([...values.values()][0],stored);
  context.companies.push(company);
  await context.window.RazyncWorkspaceResume.retry();
  assert.equal(context.selected,company);
  assert.equal(panel.dataset.activeTool,'extrato');
  assert.equal(date.value,'2026-11-01');
});
