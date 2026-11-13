/* Pure catalog operations; processor capabilities and company records are preserved. */
(() => {
  const collator = new Intl.Collator('pt-BR', {numeric:true,sensitivity:'base'});
  const text = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  const hasTools = company => Array.isArray(company.capabilities?.tools) && company.capabilities.tools.length > 0;
  const byCode = (a,b) => collator.compare(String(a.codigo),String(b.codigo)) || collator.compare(a.nome,b.nome);
  const accountingStatuses = {
    digital: {
      label: 'Contabilidade digital',
      description: 'Os lançamentos desta empresa já estão disponíveis no Domínio.',
    },
    noBankMovement: {
      label: 'Sem movimento bancário',
      description: 'Esta empresa não possui movimento bancário.',
    },
  };
  const statusByCode = new Map([
    ...[163, 594, 1128, 1159, 1382, 1448, 1481, 1491].map(code => [code, 'digital']),
    ...[167, 307, 414, 604, 627, 733, 1007, 1059, 1134, 1220, 1243, 1295, 1370, 1414, 1510]
      .map(code => [code, 'noBankMovement']),
  ]);
  const accountingStatus = company => accountingStatuses[statusByCode.get(Number(company.codigo))];
  function select(items,{query='',regime='',filter='all',sort='code'}={}) {
    const words=text(query).split(/\s+/).filter(Boolean);
    const exactCode = words.length===1 && /^\d+$/.test(words[0]) ? Number(words[0]) : null;
    return items.filter(company => {
      if(regime && company.regime!==regime)return false;
      if(filter==='organizer' && !hasTools(company))return false;
      if(filter==='catalog' && hasTools(company))return false;
      if(filter==='multibank' && Object.keys(company.capabilities?.banks || {}).length<2)return false;
      if(Object.hasOwn(accountingStatuses,filter) && statusByCode.get(Number(company.codigo))!==filter)return false;
      const searchable=text(`${company.codigo} ${company.nome} ${company.regime || ''} ${accountingStatus(company)?.label || ''}`);
      return words.every(word=>searchable.includes(word) || (/^\d+$/.test(word) && Number(company.codigo)===Number(word)));
    }).sort((a,b)=>{
      if(exactCode!==null) {
        const exact=Number(Number(b.codigo)===exactCode)-Number(Number(a.codigo)===exactCode);
        if(exact)return exact;
      }
      if(sort==='name')return collator.compare(a.nome,b.nome) || byCode(a,b);
      if(sort==='tools')return Number(hasTools(b))-Number(hasTools(a)) || byCode(a,b);
      return byCode(a,b);
    });
  }
  globalThis.RazyncDirectory={select,accountingStatus};
})();
