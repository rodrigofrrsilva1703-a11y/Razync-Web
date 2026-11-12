/* Orientações contextuais de uso. Derivadas das capacidades reais da empresa.
 * Empresa 266 mantém o roteiro específico já existente em app.js. */
(function () {
  "use strict";
  const DETAILS = {
    1131: {
      intro:"Envie o extrato Itaú da empresa 1131 (PDF) e o documento auxiliar de agosto em PDF, para identificar históricos sem alterar os valores bancários.",
      note:"O extrato é a única fonte de lançamentos. Históricos só são substituídos por data e valor únicos; diferenças de um dia exigem valor único no mês. Divergências e duplicidades são listadas para revisão.",
      extrato:"Compare o Modelo Domínio da conta 508 com o extrato Itaú original da mesma competência. O documento auxiliar não substitui o extrato bancário.",
      base:"Classifique os lançamentos da conta Itaú 508 usando o Modelo Domínio revisado, sem alterar a competência."
    },
    1024: {
      intro:"Envie o extrato Banco do Brasil em PDF e a planilha de entradas e saídas para complementar os históricos da conta 8.",
      note:"O cruzamento só substitui históricos quando o lançamento é identificado com segurança; valores repetidos ou ambíguos permanecem para conferência.",
      extrato:"Use o PDF original do Banco do Brasil e o Modelo Domínio revisado da conta 8, na mesma competência.",
      base:"Ensine as classificações utilizando os lançamentos revisados do Banco do Brasil 8."
    },
    1033: {
      intro:"Envie o extrato mensal Bradesco em PDF da empresa 1033, conta contábil 9.",
      note:"O leitor identifica tarifas e históricos em várias linhas, verifica os saldos e ignora posições do Invest Fácil.",
      extrato:"Compare o Modelo Domínio com o extrato Bradesco mensal em PDF da mesma competência.",
      base:"Ensine as classificações dos lançamentos revisados da conta Bradesco 9."
    },
    1058: {
      intro:"Envie o extrato mensal Itaú 514 em PDF e a planilha de favorecidos em XLSX para identificar históricos. A Caixa 504 usa o extrato PDF.",
      note:"O extrato Itaú é a fonte de todas as movimentações e valores; a planilha auxiliar só complementa históricos com correspondência segura. Valores repetidos ambíguos permanecem com o histórico bancário para revisão.",
      extrato:"Na Conferência, use o extrato bancário do Itaú (PDF ou OFX, também XLS/XLSX/CSV compatíveis), não a planilha de favorecidos. Para a Caixa 504, envie o PDF. Selecione o banco correto e o Modelo Domínio correspondente à competência.",
      base:"Ensine e revise os lançamentos por banco e conta contábil, sem misturar Itaú 514 e Caixa 504."
    },
    977: {
      intro:"Envie os extratos do Bradesco (510) e do Banco do Brasil (8) em PDF. Anexe o ZIP de francesinhas do Bradesco para detalhar os créditos de cobrança.",
      note:"O sistema substitui o crédito consolidado pelos títulos liquidados quando agência, conta, data de crédito e total conferem. O Excel separa os bancos em abas.",
      extrato:"No campo Bradesco, selecione o PDF e o mesmo ZIP usado no Organizador. Para o Banco do Brasil, envie o PDF da competência.",
      base:"Use o Modelo Domínio revisado para ensinar as contrapartidas de cada conta."
    },
    818: {
      intro:"Envie o extrato Santander e o relatório de boletos liquidados em PDF para gerar o Modelo Domínio da conta 509.",
      note:"A identificação usa o valor cobrado e o dia útil seguinte à liquidação, considerando segunda a sexta. O histórico original é preservado se o cruzamento não for único.",
      extrato:"Compare o Modelo Domínio com o extrato Santander. Nos créditos agrupados, os nomes dos pagadores aparecem juntos, com a data e o valor do banco.",
      base:"Use o Modelo Domínio revisado para ensinar as contrapartidas dos movimentos do Santander 509."
    },
    803: {
      intro:"Envie o Extrato Mensal Bradesco em PDF para gerar o Modelo Domínio da conta contábil 9.",
      note:"O sistema usa a conta 9 no crédito dos pagamentos e no débito dos recebimentos.",
      extrato:"Compare o Modelo Domínio com o extrato Bradesco em PDF da mesma competência.",
      base:"Use o Modelo Domínio revisado para ensinar as contrapartidas dos movimentos do Bradesco."
    },
    745: {
      intro:"Envie o Extrato Mensal Itaú Empresas em PDF para gerar o Modelo Domínio da conta contábil 508.",
      note:"O sistema verifica os totais do PDF e separa as aplicações e os resgates automáticos dos lançamentos da conta corrente.",
      extrato:"Compare o Modelo Domínio com o Extrato Mensal Itaú em PDF. Os saldos, as aplicações e os resgates automáticos ficam fora da comparação.",
      base:"Use o Modelo Domínio revisado, com a conta Itaú 508, para ensinar as contrapartidas dos pagamentos e recebimentos."
    },
    521: {
      intro:"Envie o Movimento Mensal por Categoria em XLSX. O organizador lê os pagamentos da aba Caixa.",
      note:"O Modelo Domínio usa a data de pagamento, valor negativo e conta contábil 5 no crédito.",
      extrato:"Compare o Modelo Domínio com o extrato Caixa ou com o relatório de origem. A conferência abrange somente pagamentos.",
      base:"Use um Modelo Domínio revisado com a conta Caixa 5 para ensinar a classificação dos pagamentos."
    },
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
    734: {
      intro:"A empresa 734 utiliza o extrato PDF do BTG Pactual para montar o Modelo Domínio.",
      note:"Conta contábil BTG 510. Rendimentos e movimentos internos são excluídos; aplicações e resgates recebem a inversão contábil configurada.",
      extrato:"Use o PDF original do BTG e confira se a conta e o período pertencem à empresa."
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
      intro:"A Accede Automação aceita SIG do Itaú e SIG ou PDF do Sicredi.",
      note:"Contas: Itaú 508 e Sicredi 505."
    },
    1001: {
      intro:"A Accede Equipamentos utiliza planilha SIG do Itaú, Sicredi em SIG ou PDF e extratos PDF do Aplicativo Santander Empresas para montar o Modelo Domínio.",
      note:"Envie o Santander em PDF (conta 513). Itaú 508 em SIG. Sicredi 505 em SIG ou PDF. O PDF pode abranger mais de um mês; selecione o período desejado."
    },
    1064: {
      intro:"A Tech Control aceita SIG ou extrato PDF do Sicredi para produzir os lançamentos contábeis.",
      note:"Envie o Sicredi da conta 505 em SIG ou PDF."
    },
    1096: {
      intro:"A Up Pack aceita SIG do Santander e SIG ou PDF do Sicredi.",
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
      intro:"A Dias e Pereira aceita relatórios Nibo em PDF e o extrato original do Banco do Brasil no formato Consultas.",
      note:"Envie cada PDF no banco correspondente: Itaú 508 ou Banco do Brasil 8. No BB Consultas, os movimentos de Rende Fácil são separados do saldo."
    },
    1522: {
      intro:"A empresa 1522 utiliza o extrato consolidado mensal do Santander para gerar o Modelo Domínio.",
      note:"Conta contábil Santander 513. Envie um PDF por mês; os complementos dos históricos são preservados e os saldos são conferidos.",
      extrato:"Use o extrato consolidado original do Santander. A movimentação da conta corrente já inclui aplicações e resgates; a seção de investimentos não é duplicada."
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
        step(4,"Confira o resultado", "Clique em Gerar prévia e verifique os movimentos separados por banco antes de baixar.")
      ];
    } else if (type === "advanced") {
      const required = docs.filter(role=>!role.optional);
      const optional = docs.filter(role=>role.optional);
      const hasPicker = PICKER_BANK_CODES.has(code) || docs.some(role=>Object.hasOwn(cap.banks||{},role.name));
      const requiredLabel = required.map(role=>role.label).join(" + ");
      const optionalLabel = optional.map(role=>role.label).join(", ");
      const hasManualPeriod = code !== 1408;
      steps = [
        step(1,hasPicker ? "Escolha os bancos" : "Confira os documentos",
          hasPicker ? "Marque os bancos que serão processados: "+names+"." :
          (requiredLabel ? "Prepare: "+requiredLabel+"." : "Separe os relatórios e extratos disponíveis para esta empresa.")),
        step(2,"Envie os arquivos",requiredLabel ?
          "Preencha os campos obrigatórios: "+requiredLabel+"." :
          "Anexe os arquivos nos campos indicados, conforme os documentos disponíveis."),
        step(3,
          optional.length ? (hasManualPeriod ? "Complementos e período" : "Complementos") : "Período dos lançamentos",
          (optionalLabel ? "Quando disponíveis, inclua: "+optionalLabel+"." : "")+
          (hasManualPeriod ? (optionalLabel ? " " : "")+"Se quiser limitar os lançamentos, informe as datas De e Até." : "")
        ),
        step(4,"Revise a prévia", "Clique em Gerar prévia e confira datas, valores e históricos antes de baixar o Modelo Domínio.")
      ];
    } else {
      steps = [
        step(1,"Selecione o banco", "Escolha o banco indicado para a empresa"+(names ? ": "+names+"." : ".")),
        step(2,"Envie os extratos", "Anexe um ou vários arquivos de extrato no campo Arquivos."),
        step(3,"Período (opcional)", "Preencha De e Até para filtrar o período, ou deixe as datas em branco."),
        step(4,"Confira os lançamentos", "Clique em Gerar prévia e revise as datas, os valores e os históricos do Modelo Domínio.")
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
        step(3,"Compare no assistente", "Abra o assistente para revisar as pendências. Use os filtros no topo e compare o lançamento com a referência da base, lado a lado. A análise com IA é opcional e deve ser acionada para o lançamento desejado."),
        step(4,"Escolha e aprove a conta", "Confira os históricos completos, selecione ou informe uma conta compatível e clique em Aprovar e próximo. Use Adiar se ainda precisar conferir documentos."),
        step(5,"Baixe o Excel revisado", "Depois de aprovar, use o download na área do resultado, fora do assistente, para baixar o Excel com as revisões. Se quiser ensinar esses ajustes à base, marque Aprender na Base Inteligente somente as revisões aprovadas.")
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
        step(4,"Confira as diferenças", "Clique em Atualizar conferência e revise entradas, saídas e lançamentos sem correspondência. Totais diários iguais não dispensam a conferência individual."),
        step(5,"Aplicações e resgates (opcional)", "No resultado, abra Aplicações e resgates · prévia e TXT. Escolha um banco com todas as entradas e saídas diárias batendo; outro banco divergente não bloqueia esse banco. Informe a conta de aplicação e resgate e o saldo anterior, gere a prévia, confira os débitos e créditos e use Salvar TXT ou Baixar TXT.")
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
    const requiredTool = {organizar:"modelo_dominio",base:"base_inteligente",extrato:"conferencia_extrato"}[toolName];
    if (!requiredTool || !cap.tools.includes(requiredTool)) return null;
    if (toolName==="organizar") return organizer(company,cap,extra);
    if (toolName==="base") return base(company,cap,extra);
    if (toolName==="extrato") return extrato(company,cap,extra);
    return null;
  }
  window.RAZYNC_COMPANY_HELP = {resolve,knownCodes:Object.keys(DETAILS).map(Number)};
})();
