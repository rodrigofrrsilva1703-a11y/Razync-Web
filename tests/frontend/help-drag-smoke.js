// Browser-only smoke test; injected into _smoke, never deployed.
(async () => {
  const state = (value, detail = "") => {
    document.documentElement.dataset.companyHelpSmoke = value;
    document.documentElement.dataset.companyHelpSmokeDetail = detail;
  };
  try {
    const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
    // A página inicia na seleção de colaborador; o teste deve abrir a
    // carteira antes de conferir linhas e ferramentas das empresas.
    for (let i = 0; i < 30 && !document.querySelector(".portfolio-entry"); i++) {
      await pause(70);
    }
    const portfolio = document.querySelector(".portfolio-entry");
    if (!portfolio) throw Error("Carteira inicial não foi renderizada.");
    portfolio.click();
    await pause(100);
    if (!document.querySelector(".company-row")) {
      throw Error("Pesquisa de empresas não abriu após selecionar a carteira.");
    }
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

    // Ferramenta geral: acessível pelo menu lateral independente da empresa.
    const fiscalNav=document.querySelector('.main-nav-btn[data-view="fiscal"]');
    const fiscalPane=document.querySelector('#fiscalView');
    if(!fiscalNav || !fiscalPane)throw Error("Conferência universal ausente do menu lateral.");
    fiscalNav.click();
    await pause(120);
    if(!fiscalPane.classList.contains("active") || getComputedStyle(fiscalPane).display==="none") {
      throw Error("A conferência universal não abriu pelo menu lateral.");
    }
    if(!document.querySelector("#fiscal242Form") || !document.querySelector("#fiscal242Results") ||
       !document.querySelector("#fiscalFilialCodigo") ||
       !document.querySelector("#fiscal242CompanyName")) {
      throw Error("Formulário ou identificação automática da empresa não encontrado.");
    }
    if (document.querySelector("#fiscalEmpresaCodigo")) {
      throw Error("O código manual da empresa não deveria aparecer na conferência.");
    }
    if(document.querySelector('.main-nav-btn[data-view="converter"]') ||
       document.querySelector("#converterView")) {
      throw Error("O Conversor de Extratos ainda aparece no site.");
    }
    const fiscalSetup = document.querySelector("#fiscalView .fiscal-setup");
    const fiscalForm = document.querySelector("#fiscal242Form");
    const fiscalFile = document.querySelector("#fiscal242Razao");
    const context = document.querySelector("#fiscalView .fiscal-context-grid");
    if(!fiscalSetup || !fiscalFile || !context || !document.querySelector("#fiscal242AcumuladoresName")) {
      throw Error("A conferência não possui todos os componentes do novo layout.");
    }
    const setupWidth = fiscalSetup.getBoundingClientRect().width;
    const formWidth = fiscalForm.getBoundingClientRect().width;
    if(setupWidth < 400 || formWidth < setupWidth * .85) {
      throw Error("O formulário continua estreito e deixa uma coluna vazia: " +
        JSON.stringify({setupWidth,formWidth}));
    }
    if(getComputedStyle(context).display !== "grid" || getComputedStyle(fiscalForm).display === "none") {
      throw Error("O layout central da conferência fiscal não foi aplicado.");
    }
    openCompany(filial);
    await pause(80);
    fiscalNav.click();
    if(!fiscalPane.classList.contains("active")) {
      throw Error("A conferência não ficou disponível após entrar em outra empresa.");
    }
    document.querySelector('.main-nav-btn[data-view="companies"]').click();

    const withoutTools = {
      codigo:257,nome:"Empresa sem ferramenta",regime:"LUCRO PRESUMIDO",
      capabilities:{status:"catalog_only",tools:[],banks:{}}
    };
    openCompany(withoutTools);
    if(!wrapper.hidden)throw Error("Botão apareceu em empresa sem ferramentas");
    // Real browser cascade: dark theme must survive the lazy fiscal styles.
    const themeButton=document.querySelector('#themeToggle');
    const initialTheme=document.documentElement.dataset.theme;
    const transparentWrappers=['#companyPanel .tool-card','#companyPanel .tool-tabs','#companiesView .directory-controls','#companiesView .grid'];
    if(initialTheme==='dark')themeButton.click();
    const lightBorders=new Map(transparentWrappers.map(selector=>[selector,getComputedStyle(document.querySelector(selector)).borderTopWidth]));
    themeButton.click();
    for(const selector of ['#companyPanel .tool-card','#companyPanel .tool-tabs','#companiesView .directory-controls','#companiesView .grid']) {
      const wrapper=document.querySelector(selector);
      if(!wrapper)throw Error('Contêiner de teste ausente: '+selector);
      const style=getComputedStyle(wrapper);
      if(style.backgroundColor!=='rgba(0, 0, 0, 0)' || style.borderTopWidth!==lightBorders.get(selector)) {
        throw Error('O modo escuro pintou um contêiner transparente: '+selector);
      }
    }
    document.querySelectorAll('#companyPanel .file-drop-shell,#companyPanel .reconcile-bank-file,#fiscalView .fiscal-upload-item').forEach(upload=>{
      const style=getComputedStyle(upload);
      if(style.borderTopWidth!=='1px' || style.borderTopStyle==='none')throw Error('O campo de anexo perdeu sua borda.');
    });
    document.querySelectorAll('#companyPanel .tool-intro,#companyPanel .modern-form').forEach(panel=>{
      if(getComputedStyle(panel).borderTopWidth!=='1px')throw Error('Um painel da ferramenta perdeu seu contorno.');
    });
    const selectedBank=document.querySelector('#companyPanel .bank-choice.selected');
    if(selectedBank && getComputedStyle(selectedBank).backgroundColor!=='rgb(23, 36, 58)')throw Error('O banco selecionado perdeu o destaque.');
    document.querySelectorAll('#companyPanel .panel-quick-info > span,#companyPanel .tool-feature-list b,#companyPanel .tool-flow span b').forEach(marker=>{
      const channels=(getComputedStyle(marker).backgroundColor.match(/\d+/g)||[]).slice(0,3).map(Number);
      if(channels.length===3 && Math.min(...channels)>150)throw Error('Etiqueta ou etapa ainda usa fundo claro.');
    });
    document.querySelectorAll('#companyPanel .tool-flow').forEach(flow=>{
      if(getComputedStyle(flow).backgroundColor!=='rgba(0, 0, 0, 0)')throw Error('A faixa de etapas ganhou fundo no modo escuro.');
    });
    await pause(250); // allow the sidebar's 180ms theme color transition to settle
    document.querySelectorAll('#mainSidebar .main-nav-btn,#mainSidebar .sidebar-close').forEach(control=>{
      const style=getComputedStyle(control);
      if(style.borderTopColor!=='rgba(0, 0, 0, 0)')throw Error('O menu escuro ganhou uma borda extra: '+control.className+' '+style.borderTopColor);
      if(!control.classList.contains('active') && style.backgroundColor!=='rgba(0, 0, 0, 0)')throw Error('O item inativo do menu ganhou fundo de botão.');
    });
    const formStyle=getComputedStyle(fiscalForm);
    const darkChannels=(formStyle.backgroundColor.match(/\d+/g)||[]).slice(0,3).map(Number);
    if(darkChannels.length!==3 || Math.max(...darkChannels)>45 || Math.max(...darkChannels)-Math.min(...darkChannels)>8) {
      throw Error("O formulário fiscal não manteve a superfície escura neutra: "+formStyle.backgroundColor);
    }
    const previewProbe=document.createElement('div');
    previewProbe.appendChild(tableFor(['DATA','HISTÓRICO','VALOR'],[['27/10/2026','Amostra visual',100]]));
    document.querySelector('#companyPanel').appendChild(previewProbe);
    const cellStyle=getComputedStyle(previewProbe.querySelector('td'));
    const luminance=color=>{
      const c=color.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>v/255)
        .map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
      return c[0]*.2126+c[1]*.7152+c[2]*.0722;
    };
    const light=[luminance(cellStyle.color),luminance(cellStyle.backgroundColor)].sort((a,b)=>b-a);
    if((light[0]+.05)/(light[1]+.05)<4.5)throw Error("Contraste insuficiente na prévia escura.");
    // Exercise dynamically mounted daily cards, then the same result in a dialog.
    renderDailyReconciliation(previewProbe,{rows:[{DATA:'2026-10-27','ENTRADAS PLANILHA':100,'ENTRADAS EXTRATO':100}]});
    const assertDarkSurface=element=>{
      const style=getComputedStyle(element);
      if(luminance(style.backgroundColor)>.05)throw Error('Resultado ficou claro no tema escuro: '+element.className);
      const levels=[luminance(style.color),luminance(style.backgroundColor)].sort((a,b)=>b-a);
      if((levels[0]+.05)/(levels[1]+.05)<4.5)throw Error('Contraste insuficiente no card da conferência.');
    };
    previewProbe.querySelectorAll('.daily-summary > div,.daily-rule').forEach(assertDarkSurface);
    const expandedProbe=document.createElement('dialog');expandedProbe.className='preview-dialog';
    const expandedHeader=document.createElement('div');expandedHeader.className='preview-dialog-header';
    expandedHeader.textContent='Prévia de teste';expandedProbe.append(expandedHeader,previewProbe);document.body.append(expandedProbe);
    assertDarkSurface(expandedHeader);
    previewProbe.querySelectorAll('.daily-summary > div,.daily-rule').forEach(assertDarkSurface);
    expandedProbe.remove();
    const fiscalThemeProbe=document.createElement('div');
    fiscalThemeProbe.innerHTML='<div class="fiscal-summary"><div class="fiscal-summary-card">Totais fiscais</div></div><section class="fiscal-account-dialog"><header class="fiscal-account-dialog-header">Detalhe da conta</header><div class="fiscal-account-dialog-body"><div class="fiscal-account-opinion-conclusion">Conclusão</div><div class="fiscal-ai-case">Explicação da análise</div></div></section>';
    fiscalPane.append(fiscalThemeProbe);
    fiscalThemeProbe.querySelectorAll('.fiscal-summary-card,.fiscal-account-dialog-header,.fiscal-account-opinion-conclusion,.fiscal-ai-case').forEach(assertDarkSurface);
    // Inline account controls must not paint rectangles over alternating rows.
    const fiscalRows=document.querySelector('#fiscal242Rows');
    const inlineRows=[0,1].map(()=>{
      const row=document.createElement('tr');row.className='fiscal-result-row';
      row.innerHTML='<td><button type="button" class="fiscal-account-link">2221</button><span class="fiscal-account-type">ENTRADAS</span></td><td><span class="fiscal-accum-tag">1153</span></td><td><span class="fiscal-difference-number">-100,00</span></td><td><span class="fiscal-status fiscal-status-review">Divergência</span></td>';
      fiscalRows.append(row);return row;
    });
    for(const row of inlineRows){
      for(const selected of [false,true]){
        row.classList.toggle('selected',selected);
        row.querySelectorAll('.fiscal-account-link,.fiscal-account-type,.fiscal-accum-tag,.fiscal-difference-number').forEach(inline=>{
          if(getComputedStyle(inline).backgroundColor!=='rgba(0, 0, 0, 0)')throw Error('Resultado fiscal com fundo sobreposto: '+inline.className);
        });
        if(getComputedStyle(row.querySelector('.fiscal-status')).backgroundColor==='rgba(0, 0, 0, 0)')throw Error('O aviso fiscal perdeu seu destaque.');
      }
      row.remove();
    }
    fiscalThemeProbe.remove();
    previewProbe.remove();
    if(initialTheme!=="dark")themeButton.click();
    state("ok");
  } catch(error) {
    state("failed",String(error.message||error).slice(0,400));
  }
})();
