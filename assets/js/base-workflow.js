/* Guided, non-destructive steps for the Intelligent Base workspace. */
(() => {
  const steps = [...document.querySelectorAll('[data-base-step]')];
  if (!steps.length) return;
  const inputs = {
    learn: document.getElementById('learnFiles'),
    classify: document.getElementById('classifyFile')
  };
  const forms = {
    learn: document.getElementById('learnForm'),
    classify: document.getElementById('classifyForm')
  };
  const statusNodes = {
    learn: document.getElementById('baseLearnStepStatus'),
    classify: document.getElementById('baseClassifyStepStatus'),
    review: document.getElementById('baseReviewStepStatus')
  };
  const targets = {
    learn: forms.learn,
    classify: forms.classify,
    review: document.getElementById('baseAiHost') || document.getElementById('classificationCoverage')
  };
  const labels = {
    learn: ['Envie arquivos revisados', 'Arquivo(s) selecionado(s)', 'Importando padrões…', 'Base atualizada', 'Falha ao importar'],
    classify: ['Aplique padrões ao modelo', 'Modelo pronto para classificar', 'Classificando modelo…', 'Classificação concluída', 'Falha ao classificar'],
    review: ['Pendências serão preparadas automaticamente', 'Preparando revisão automática…', 'Revisão pronta', 'Sem pendências para revisar', 'Falha ao preparar revisão']
  };
  let active = 'learn';
  const countFiles = input => input?.files?.length || 0;
  const fileLabel = count => count === 1 ? '1 arquivo selecionado' : `${count} arquivos selecionados`;

  function activate(name) {
    active = name;
    for (const step of steps) {
      const selected = step.dataset.baseStep === active;
      step.classList.toggle('is-active', selected);
      if (selected) step.setAttribute('aria-current', 'step');
      else step.removeAttribute('aria-current');
    }
  }

  function setStatus(name, state, message) {
    const node = statusNodes[name];
    if (!node) return;
    const stateIndex = {empty: 0, ready: 1, processing: 2, complete: 3, error: 4};
    node.textContent = message || labels[name][stateIndex[state] ?? 0];
    const step = steps.find(item => item.dataset.baseStep === name);
    if (step) step.dataset.state = state;
    if (state === 'processing' || state === 'error' || state === 'preparing' ||
        (name === 'review' && (state === 'ready' || state === 'complete'))) activate(name);
  }

  function navigate(name) {
    activate(name);
    let target = targets[name];
    if (name === 'review') {
      const state = steps.find(item => item.dataset.baseStep === name)?.dataset.state;
      if (['preparing', 'ready', 'error'].includes(state)) {
        window.RazyncBaseInvestigation?.open?.();
      } else {
        target = document.getElementById('classificationCoverage');
      }
    } else {
      inputs[name]?.focus();
    }
    target?.scrollIntoView?.({behavior: 'smooth', block: 'center'});
  }

  for (const step of steps) {
    step.addEventListener('click', () => navigate(step.dataset.baseStep));
  }
  for (const name of ['learn', 'classify']) {
    inputs[name]?.addEventListener('change', () => {
      const count = countFiles(inputs[name]);
      setStatus(name, count ? 'ready' : 'empty', count ? fileLabel(count) : labels[name][0]);
      if (count) activate(name);
    });
  }

  window.RazyncBaseWorkflow = {
    activate,
    setLearning(state, message) { setStatus('learn', state, message); },
    setClassification(state, message) { setStatus('classify', state, message); },
    setReview(state, message) { setStatus('review', state, message); },
    reset() {
      for (const input of Object.values(inputs)) if (input) input.value = '';
      for (const name of ['learn', 'classify', 'review']) setStatus(name, 'empty');
      activate('learn');
    }
  };
  window.RazyncBaseWorkflow.reset();
})();
