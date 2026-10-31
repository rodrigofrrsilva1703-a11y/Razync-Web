const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

class Element {
  constructor(dataset={}) {
    this.dataset=dataset;this.attrs={};this.events={};this.classes=new Set();
    this.classList={toggle:(name,force)=>force?this.classes.add(name):this.classes.delete(name)};
    this.textContent='';this.files=[];this.scrolled=false;this.focused=false;
  }
  addEventListener(name,handler){this.events[name]=handler;}
  setAttribute(name,value){this.attrs[name]=value;}
  removeAttribute(name){delete this.attrs[name];}
  scrollIntoView(){this.scrolled=true;}
  focus(){this.focused=true;}
}

function setup(){
  const steps=['learn','classify','review'].map(name=>new Element({baseStep:name}));
  const ids=['learnFiles','classifyFile','learnForm','classifyForm','baseLearnStepStatus','baseClassifyStepStatus','baseReviewStepStatus','baseAiHost','classificationCoverage'];
  const nodes=Object.fromEntries(ids.map(id=>[id,new Element()]));
  let opened=0;
  const context={document:{querySelectorAll:()=>steps,getElementById:id=>nodes[id]},
    window:{RazyncBaseInvestigation:{open:()=>opened++}}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('assets/js/base-workflow.js','utf8'),context);
  return {context,nodes,steps,opened:()=>opened};
}

test('guided steps reflect selected files and focus the matching form',()=>{
  const state=setup(),learn=state.steps[0];
  state.nodes.learnFiles.files=[{name:'revisado.xlsx'},{name:'outro.xlsx'}];
  state.nodes.learnFiles.events.change();
  assert.equal(learn.dataset.state,'ready');
  assert.equal(state.nodes.baseLearnStepStatus.textContent,'2 arquivos selecionados');
  assert.equal(learn.attrs['aria-current'],'step');
  learn.events.click();
  assert.equal(state.nodes.learnFiles.focused,true);
  assert.equal(state.nodes.learnForm.scrolled,true);
});

test('workflow states progress from learning to automatic review readiness',()=>{
  const state=setup(),workflow=state.context.window.RazyncBaseWorkflow;
  workflow.setLearning('processing');
  workflow.setLearning('complete','12 padrões processados');
  workflow.activate('classify');
  workflow.setClassification('complete');
  workflow.setReview('preparing','4 pendências em preparação');
  workflow.setReview('ready','4 pendências prontas para revisão');
  assert.equal(state.steps[0].dataset.state,'complete');
  assert.equal(state.steps[1].dataset.state,'complete');
  assert.equal(state.steps[2].dataset.state,'ready');
  assert.equal(state.nodes.baseReviewStepStatus.textContent,'4 pendências prontas para revisão');
  assert.equal(state.steps[2].attrs['aria-current'],'step');
});

test('review step opens the prepared assistant and company reset clears progress',()=>{
  const state=setup(),workflow=state.context.window.RazyncBaseWorkflow;
  state.steps[2].events.click();
  assert.equal(state.opened(),0);
  workflow.setReview('ready','3 pendências prontas para revisão');
  state.steps[2].events.click();
  assert.equal(state.opened(),1);
  assert.equal(state.nodes.baseAiHost.scrolled,true);
  workflow.reset();
  assert.equal(state.steps[2].dataset.state,'empty');
  assert.equal(state.nodes.baseReviewStepStatus.textContent,'Pendências serão preparadas automaticamente');
  assert.equal(state.steps[0].attrs['aria-current'],'step');
});
