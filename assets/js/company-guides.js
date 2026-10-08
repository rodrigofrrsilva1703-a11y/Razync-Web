/* Orientações contextuais de uso. Derivadas das capacidades reais da empresa.
 * Empresa 266 mantém o roteiro específico já existente em app.js. */
(function () {
  "use strict";
  const DETAILS = {
    3: {
      intro:"A Autokraft Industrial usa o mapa bancário em Excel para montar os lançamentos do Itaú e Daycoval.",
      note:"Confira se os movimentos do mapa pertencem à empresa 3 antes de gerar o Modelo Domínio."
    },
    47: {
      intro:"A CRJ utiliza os movimentos do Banco do Brasil para gerar o Modelo Domínio.",
      note:"Selecione Banco do Brasil, conta 8, e confira as datas e os valores extraídos."
    },
    88: {
      intro:"A empresa 88 converte os movimentos do extrato Itaú para o Modelo Domínio.",
      note:"Use o extrato da conta Itaú 508 e verifique a descrição dos lançamentos na prévia."
    },
    154: {
      intro:"A RM Postais possui movimentos no Bradesco e no Itaú; cada banco deve ser anexado no campo correspondente.",
      note:"Confira as abas separadas por banco e as contas Bradesco 9 e Itaú 508."
    },
    178: {
      intro:"A Autokraft Projetos utiliza a planilha de mapa bancário, com os movimentos separados por Itaú e Daycoval.",
      note:"Esta é a empresa 178; confira os movimentos do mapa e as contas Itaú 508 e Daycoval 505."
    },
    242: {
      intro:"A Eletro Forte matriz utiliza relatórios de despesas, fornecedores e recebidos. A planilha consolidada é montada com os documentos enviados.",
      note:"Os relatórios são opcionais individualmente, mas é preciso enviar pelo menos um. Francesinhas em ZIP podem complementar os recebidos.",
      base:"Na empresa 242, selecione antes o tipo correto: Consolidada, Despesa, Fornecedor, Recebido ou Francesinhas.",
      extrato:"Para conferir, use o Modelo Domínio consolidado e os extratos das contas Itaú 508, Itaú 509 e/ou Banco do Brasil 8."
    },
    285: {
      intro:"A empresa 285 combina a Planilha Jaguar com a planilha de Entradas detalhadas para compor os lançamentos.",
      note:"Os dois arquivos são necessários. Confira os recebimentos na prévia antes de baixar o modelo.",
      extrato:"O extrato utilizado na conferência deve ser do Santander, conta 513."
    },
    343: {
      intro:"A ISA utiliza o mapa bancário em Excel, com separação dos lançamentos entre Itaú e Daycoval.",
      note:"Confira as datas identificadas no mapa e as contas Itaú 508 e Daycoval 506."
    },
    625: {
      intro:"A Valean 625 processa extratos de três bancos e organiza os lançamentos em abas separadas.",
      note:"Use as contas Banco do Brasil 8, Caixa 504 e Sicredi 3999. Confira cada banco antes de baixar.",
      extrato:"Anexe os extratos das mesmas contas selecionadas no Modelo Domínio, sem misturar documentos de outro banco."
    },
    626: {
      intro:"A Valean 626 processa Banco do Brasil e Sicredi, com a conferência de cada conta separadamente.",
      note:"Contas configuradas: Banco do Brasil 8 e Sicredi 1155. Confira cuidadosamente as entradas, saídas e diferenças de saldo.",
      extrato:"Observe divergências por dia e por banco; um saldo correto de um banco não substitui a conferência do outro."
    },
    841: {
      intro:"A empresa 841 utiliza o extrato do Banco Inter para montar o Modelo Domínio.",
      note:"Conta configurada do Banco Inter: 506."
    },
    912: {
      intro:"A Vital Safety utiliza os movimentos do extrato Sicredi para gerar o Modelo Domínio.",
      note:"Confira se o extrato pertence à conta Sicredi 515."
    },
    964: {
      intro:"A empresa 964 converte os movimentos do Bradesco para o Modelo Domínio.",
      note:"Conta Bradesco configurada: 9. Confira lançamentos repetidos e seus valores na prévia."
    },
    968: {
      intro:"A Radani recebe extratos Itaú e Bradesco em PDF, além de comprovantes SISPAG quando disponíveis.",
      note:"Os comprovantes SISPAG podem complementar o detalhamento dos pagamentos. Confira Itaú 508 e Bradesco 9."
    },
    969: {
      intro:"A Engekraft utiliza extrato Itaú para converter os movimentos bancários em Modelo Domínio.",
      note:"Conta Itaú configurada: 508. Confira históricos e datas convertidos."
    },
    1000: {
      intro:"A Accede Automação utiliza planilhas SIG do Itaú e/ou do Sicredi, separadas por banco.",
      note:"Envie as planilhas SIG originais. Contas: Itaú 508 e Sicredi 505."
    },
    1001: {
      intro:"A Accede Equipamentos utiliza planilhas SIG do Itaú e/ou do Sicredi para montar o Modelo Domínio.",
      note:"Selecione a empresa 1001 e use os arquivos próprios dela; contas Itaú 508 e Sicredi 505."
    },
    1064: {
      intro:"A Tech Control utiliza a planilha SIG do Sicredi para produzir os lançamentos contábeis.",
      note:"Envie a planilha SIG Sicredi da conta 505; esse é o arquivo necessário para o processamento."
    },
    1096: {
      intro:"A Up Pack utiliza planilhas SIG do Santander e/ou Sicredi, em campos separados.",
      note:"Contas configuradas: Santander 513 e Sicredi 510. Envie arquivos do banco correspondente."
    },
    1208: {
      intro:"A Kairos possui movimentos nos bancos Itaú, Safra e Bradesco. Os extratos devem ser enviados por banco.",
      note:"Contas: Itaú 508, Safra 512 e Bradesco 9. Revise cada aba do Modelo Domínio."
    },
    1211: {
      intro:"A GZ precisa de dois PDFs: o extrato Itaú e o relatório de boletos liquidados.",
      note:"Os dois documentos são necessários. O campo Boletos liquidados aceita PDF, não planilha Excel."
    },
    1248: {
      intro:"A RGR combina o extrato Itaú em PDF com a planilha de Entradas e Saídas RGR.",
      note:"Os dois arquivos são obrigatórios. Confira se as movimentações da planilha pertencem ao mesmo período do extrato."
    },
    1396: {
      intro:"A Nova Geração filial utiliza uma planilha consolidada para separar os movimentos Itaú e Bradesco.",
      note:"A filial usa Itaú 515 e Bradesco 514. Não utilize a planilha da matriz 266.",
      base:"Os padrões da filial 1396 devem ser ensinados com modelos próprios dela, sem misturar com a matriz."
    },
    1402: {
      intro:"A VGV utiliza a Planilha de caixa como origem do Modelo Domínio; o extrato BTG é complementar.",
      note:"A Planilha de caixa é obrigatória. O Extrato BTG em PDF é opcional no organizador; conta BTG 510."
    },
    1408: {
      intro:"A Eletro Forte filial precisa do extrato Itaú e da Planilha de recebidos. Francesinhas podem ser incluídas em ZIP.",
      note:"Os dois primeiros arquivos são obrigatórios. Conta Itaú da filial: 512. Francesinhas são opcionais.",
      base:"A classificação consolidada da 1408 considera a conta Itaú 512 e preserva classificações já preenchidas.",
      extrato:"Confira o Modelo Domínio da filial contra o extrato Itaú 512. Não confunda com as contas da matriz 242."
    },
    1529: {
      intro:"A Dias e Pereira utiliza extratos gerados pelo Nibo em PDF, de Itaú e/ou Banco do Brasil.",
      note:"Envie o PDF Nibo no campo do banco correspondente: Itaú 508 ou Banco do Brasil 8."
    },
    1530: {
      intro:"A empresa 1530 utiliza o extrato Itaú para gerar o Modelo Domínio.",
      note:"Conta Itaú configurada: 508. Confirme o período e confira os históricos."
    },
    1532: {
      intro:"A empresa 1532 utiliza extrato Itaú para converter os lançamentos ao Modelo Domínio.",
      note:"Selecione Itaú conta 508 e confira o Modelo Domínio gerado antes de classificar."
    }
  };
  const BANK_NAMES = {
    itau:"Itaú",itau_508:"Itaú",itau_509:"Itaú",bradesco:"Bradesco",
    fibra:"Banco Fibra",daycoval:"Daycoval",sicredi:"Sicredi",
    banco_brasil:"Banco do Brasil",caixa:"Caixa",inter:"Banco Inter",
    santander:"Santander",safra:"Safra",btg:"BTG"
  };
  const PICKER_BANK_CODES = new Set([3,178,343,266,1396]);
  const shortBank = (id,account) => {
    const name = BANK_NAMES[id] || id;
    return account ? name+" "+account : name;
  };
  const bankNames = cap => Object.entries(cap.banks || {}).map(([id,account]) => shortBank(id,account)).join(", ");
  const step = (n,title,text) => [String(n),title,text];
  function organizer(company, cap, extra) {
    const code = Number(company.codigo);
    const names = bankNames(cap);
    const type = cap.workflow || "standard";
    const docs = Array.isArray(cap.roles) ? cap.roles : [];
    let steps;
    if (type === "standard_multi_bank") {
      steps = [
        step(1,"Escolha os bancos", "Marque no seletor os bancos que serão processados: "+names+"."),
        step(2,"Envie os extratos", "Anexe um ou vários extratos no campo específico de cada banco selecionado."),
        step(3,"Defina o período (opcional)", "Preencha as duas datas, De e Até, ou deixe em branco para usar todos os lançamentos."),
        step(4,"Confira o resultado", "Atualize a prévia e verifique os movimentos separados por banco antes de baixar.")
      ];
    } else if (type === "advanced") {
      const required = docs.filter(role=>!role.optional);
      const optional = docs.filter(role=>role.optional);
      const hasPicker = PICKER_BANK_CODES.has(code) || docs.some(role=>Object.hasOwn(cap.banks||{},role.name));
      const requiredLabel = required.map(role=>role.label).join(" + ");
      const optionalLabel = optional.map(role=>role.label).join(", ");
      steps = [
        step(1,hasPicker ? "Escolha os bancos" : "Confira os documentos",
          hasPicker ? "Marque os bancos que serão processados: "+names+"." :
          (requiredLabel ? "Prepare: "+requiredLabel+"." : "Separe os relatórios e extratos disponíveis para esta empresa.")),
        step(2,"Envie os arquivos",requiredLabel ?
          "Preencha os campos obrigatórios: "+requiredLabel+"." :
          "Anexe os arquivos nos campos indicados, conforme os documentos disponíveis."),
        step(3,optional.length ? "Complementos e período" : "Período dos lançamentos",
          (optionalLabel ? "Quando disponíveis, inclua: "+optionalLabel+". " : "")+
          "Se quiser limitar os lançamentos, informe as datas De e Até."),
        step(4,"Revise a prévia", "Clique em Atualizar prévia e confira datas, valores e históricos antes de baixar o Modelo Domínio.")
      ];
    } else {
      steps = [
        step(1,"Selecione o banco", "Escolha o banco indicado para a empresa"+(names ? ": "+names+"." : ".")),
        step(2,"Envie os extratos", "Anexe um ou vários arquivos de extrato no campo Arquivos."),
        step(3,"Período (opcional)", "Preencha De e Até para filtrar o período, ou deixe as datas em branco."),
        step(4,"Confira os lançamentos", "Atualize a prévia e revise as datas, os valores e os históricos do Modelo Domínio.")
      ];
    }
    return {
      caption:"Empresa "+code+" · Organizar arquivos",
      intro:extra?.intro || "Utilize os documentos bancários configurados para esta empresa.",
      steps,
      note:extra?.note || ("Bancos configurados: "+names+".")
    };
  }
  function base(company,cap,extra) {
    const code=Number(company.codigo);
    const names=bankNames(cap);
    return {
      caption:"Empresa "+code+" · Base Inteligente",
      intro:"Ensine e aplique classificações contábeis usando arquivos revisados desta empresa"+(names?" ("+names+")":"")+".",
      steps:[
        step(1,"Ensinar à base", "Na seção Ensinar à base, envie planilhas já conferidas, com as contas contábeis preenchidas corretamente."),
        step(2,"Classificar Modelo Domínio", "Anexe um Modelo Domínio da empresa "+code+" para aplicar os padrões aprendidos."),
        step(3,"Revisar classificações", "Confira a prévia e as contas preenchidas antes de baixar. Use Revisão Inteligente para tratar pendências.")
      ],
      note:extra?.base || "Não misture modelos de outras empresas: os padrões são organizados por empresa e banco."
    };
  }
  function extrato(company,cap,extra) {
    const code=Number(company.codigo), names=bankNames(cap);
    const multiple=Object.keys(cap.banks||{}).length>1;
    return {
      caption:"Empresa "+code+" · Conferência com Extrato",
      intro:"Compare o Modelo Domínio final da empresa "+code+" com os extratos bancários correspondentes.",
      steps:[
        step(1,multiple?"Selecione os bancos":"Confirme o banco", 
          multiple ? "Marque apenas os bancos que deseja conferir: "+names+"." : 
          "Confira o banco configurado: "+names+"."),
        step(2,"Envie o Modelo Domínio", "Anexe o arquivo final, com os lançamentos da empresa "+code+"."),
        step(3,"Anexe os extratos", "Envie os extratos correspondentes nos campos de cada banco selecionado."),
        step(4,"Confira as diferenças", "Atualize a conferência, analise as entradas e saídas por dia e confira os lançamentos divergentes.")
      ],
      note:extra?.extrato || "O status “Batendo” exige que tanto a diferença de entradas quanto a diferença de saídas seja zero."
    };
  }
  function resolve(company,toolName) {
    const code=Number(company?.codigo);
    const cap=company?.capabilities;
    if (!cap || cap.status!=="api_ready" || !Array.isArray(cap.tools) || cap.tools.length===0) return null;
    const extra=DETAILS[code];
    if (!extra) return null; // Não apresentar instruções inventadas para novos cadastros.
    if (toolName==="organizar") return organizer(company,cap,extra);
    if (toolName==="base") return base(company,cap,extra);
    if (toolName==="extrato") return extrato(company,cap,extra);
    return null;
  }
  window.RAZYNC_COMPANY_HELP = {resolve,knownCodes:Object.keys(DETAILS).map(Number)};
})();
