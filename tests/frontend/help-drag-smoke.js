// Browser-only smoke test; injected into _smoke, never deployed.
(async () => {
  const state = (value, detail = "") => {
    document.documentElement.dataset.companyHelpSmoke = value;
    document.documentElement.dataset.companyHelpSmokeDetail = detail;
  };
  try {
    const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
    const company = {
      codigo:266, nome:"NOVA GERACAO COMERCIAL ELETRICA LTDA",
      regime:"LUCRO PRESUMIDO",
      capabilities:{
        status:"api_ready", tools:["modelo_dominio","base_inteligente","conferencia_extrato"],
        workflow:"advanced",
        roles:[{name:"consolidada",label:"Planilha consolidada",accept:".xls,.xlsx",multiple:false}],
        banks:{itau:"508",bradesco:"9",fibra:"506"}
      }
    };
    openCompany(company);
    await pause(300); // aguarda a animação inicial da área da empresa
    const wrapper=document.getElementById("companyToolHelp");
    const button=document.getElementById("companyToolHelpButton");
    const guide=document.getElementById("companyToolGuide");
    if(wrapper.hidden) throw Error("Botão oculto na empresa 266");
    const before=button.getBoundingClientRect();
    if(before.width<30||before.height<30)throw Error("Botão sem dimensões visíveis");
    if(document.elementFromPoint(before.left+before.width/2,before.top+before.height/2)!==button){
      throw Error("Botão coberto por outro elemento");
    }

    // Drag com coordenadas reais e layout calculado pelo Chromium.
    // Não é necessário capturar um ponteiro sintético para testar o movimento.
    button.setPointerCapture=()=>{};
    button.hasPointerCapture=()=>false;
    const startX=before.left+before.width/2;
    const startY=before.top+before.height/2;
    const dx=-Math.min(150,Math.max(40,startX-30));
    const dy=-Math.min(150,Math.max(40,startY-30));
    button.dispatchEvent(new PointerEvent("pointerdown",{
      bubbles:true,pointerId:42,pointerType:"mouse",button:0,buttons:1,
      clientX:startX,clientY:startY
    }));
    window.dispatchEvent(new PointerEvent("pointermove",{
      bubbles:true,cancelable:true,pointerId:42,pointerType:"mouse",button:-1,buttons:1,
      clientX:startX+dx,clientY:startY+dy
    }));
    window.dispatchEvent(new PointerEvent("pointerup",{
      bubbles:true,pointerId:42,pointerType:"mouse",button:0,buttons:0,
      clientX:startX+dx,clientY:startY+dy
    }));
    const after=button.getBoundingClientRect();
    if(Math.abs(after.left-(before.left+dx))>3 || Math.abs(after.top-(before.top+dy))>3){
      throw Error("Botão não deslocou no layout: "+JSON.stringify({before:[before.left,before.top],after:[after.left,after.top],dx,dy}));
    }
    if(document.elementFromPoint(after.left+after.width/2,after.top+after.height/2)!==button){
      throw Error("Botão movido não pode receber clique");
    }
    await pause(300);
    button.click();
    if(guide.hidden || button.getAttribute("aria-expanded")!=="true")throw Error("Instruções não abriram após arraste");
    if(!guide.textContent.includes("Selecione os bancos"))throw Error("Guia não mostrou os passos");

    const filial = {
      codigo:1408, nome:"Eletro Forte Filial", regime:"LUCRO REAL",
      capabilities:{
        status:"api_ready",tools:["modelo_dominio","base_inteligente","conferencia_extrato"],
        workflow:"advanced",banks:{itau:"512"},
        roles:[
          {name:"extrato",label:"Extrato Itaú",accept:".pdf",multiple:true},
          {name:"recebidos",label:"Planilha de recebidos",accept:".xls,.xlsx"},
          {name:"francesinhas",label:"Francesinhas ZIP",accept:".zip",optional:true}
        ]
      }
    };
    openCompany(filial);
    await pause(250);
    if(wrapper.hidden)throw Error("Botão não aparece na 1408");
    button.click();
    if(guide.hidden || !guide.textContent.includes("Planilha de recebidos"))throw Error("Guia de organizar da 1408 incorreto");
    activateTool("base");
    if(!guide.hidden)throw Error("Guia deve fechar ao mudar ferramenta");
    button.click();
    if(guide.hidden || !guide.textContent.includes("conta Itaú 512"))throw Error("Guia da Base Inteligente da 1408 incorreto");

    // Valida no navegador real a nova aba exclusiva da Eletro Forte 242.
    const matriz = {
      codigo:242, nome:"Eletro Forte Matriz", regime:"LUCRO REAL",
      capabilities:{
        status:"api_ready",
        tools:["modelo_dominio","base_inteligente","conferencia_extrato"],
        workflow:"advanced",
        banks:{itau_508:"508",itau_509:"509",banco_brasil:"8"},
        roles:[{name:"despesas",label:"Despesas",accept:".xls,.xlsx",optional:true}]
      }
    };
    openCompany(matriz);
    await pause(100);
    const fiscalTab=document.querySelector('#companyPanel .tool-tab[data-tool="fiscal"]');
    const fiscalPane=document.querySelector('#companyPanel .tool-pane[data-pane="fiscal"]');
    if (!fiscalTab || fiscalTab.hidden || getComputedStyle(fiscalTab).display==="none") {
      throw Error("A aba Fiscal × Contábil não apareceu na empresa 242.");
    }
    fiscalTab.click();
    if (!fiscalPane || fiscalPane.hidden || getComputedStyle(fiscalPane).display==="none") {
      throw Error("O painel da conferência fiscal não abriu na empresa 242.");
    }
    if (!document.querySelector("#fiscal242Form") || !document.querySelector("#fiscal242Results")) {
      throw Error("Os controles de upload e resultados da 242 estão ausentes.");
    }
    openCompany(filial);
    await pause(80);
    if (!fiscalTab.hidden || getComputedStyle(fiscalTab).display!=="none") {
      throw Error("A aba exclusiva da 242 apareceu na filial 1408.");
    }

    const withoutTools = {
      codigo:257,nome:"Empresa sem ferramenta",regime:"LUCRO PRESUMIDO",
      capabilities:{status:"catalog_only",tools:[],banks:{}}
    };
    openCompany(withoutTools);
    if(!wrapper.hidden)throw Error("Botão apareceu em empresa sem ferramentas");
    state("ok");
  } catch(error) {
    state("failed",String(error.message||error).slice(0,400));
  }
})();
