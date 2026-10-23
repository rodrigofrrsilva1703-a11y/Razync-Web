// Carteiras: enquanto somente a primeira estiver cadastrada, ela reúne todas
// as empresas existentes. Para os próximos colaboradores, usar códigos
// explícitos em companyCodes, sem modificar ferramentas nem dados contábeis.
const portfolios = [
  {id: "rodrigo", name: "Rodrigo", companyCodes: null},
];
let activePortfolio = null;
const portfolioPicker = document.querySelector("#portfolioPicker");
const portfolioList = document.querySelector("#portfolioList");

function companyBelongsToPortfolio(company) {
  if (!activePortfolio) return false;
  return activePortfolio.companyCodes === null ||
    activePortfolio.companyCodes.includes(Number(company.codigo));
}

function renderPortfolios() {
  const today = new Date();
  const hour = Number(new Intl.DateTimeFormat("pt-BR", {hour:"numeric", hourCycle:"h23", timeZone:"America/Sao_Paulo"}).format(today));
  $("#portfolioGreeting").textContent = hour < 12 ? "Bom dia. Vamos começar?" : hour < 18 ? "Boa tarde. Vamos começar?" : "Boa noite. Vamos começar?";
  $("#portfolioDate").textContent = new Intl.DateTimeFormat("pt-BR", {weekday:"long", day:"numeric", month:"long", timeZone:"America/Sao_Paulo"}).format(today);
  $("#portfolioCompanyTotal").textContent = companies.length.toLocaleString("pt-BR");
  $("#portfolioWalletTotal").textContent = portfolios.length.toLocaleString("pt-BR");
  $("#portfolioWalletLabel").textContent = portfolios.length === 1 ? "carteira disponível" : "carteiras disponíveis";
  portfolioList.replaceChildren();
  for (const portfolio of portfolios) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "portfolio-entry";
    const avatar = document.createElement("span");
    avatar.className = "portfolio-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = portfolio.name.trim().slice(0, 1).toUpperCase();
    const info = document.createElement("span");
    info.className = "portfolio-entry-info";
    const name = document.createElement("strong");
    name.textContent = portfolio.name;
    const details = document.createElement("span");
    const quantity = companies.filter(company =>
      portfolio.companyCodes === null || portfolio.companyCodes.includes(Number(company.codigo))).length;
    details.textContent = quantity.toLocaleString("pt-BR") + (quantity === 1 ? " empresa na carteira" : " empresas na carteira");
    details.className = "portfolio-entry-quantity";
    info.append(name, details);
    const arrow = document.createElement("span");
    arrow.className = "portfolio-entry-arrow";
    arrow.setAttribute("aria-hidden", "true");
    arrow.textContent = "→";
    btn.setAttribute("aria-label", "Abrir carteira de " + portfolio.name);
    const action = document.createElement("span");
    action.className = "portfolio-entry-action";
    const actionLabel = document.createElement("span");
    actionLabel.textContent = "Entrar na carteira";
    action.append(actionLabel, arrow);
    const label = document.createElement("span");
    label.className = "portfolio-entry-label";
    label.textContent = "CARTEIRA DE EMPRESAS";
    btn.append(label, avatar, info, action);
    btn.addEventListener("click", () => selectPortfolio(portfolio.id));
    portfolioList.appendChild(btn);
  }
  portfolioList.setAttribute("aria-busy", "false");
}

function selectPortfolio(id) {
  const portfolio = portfolios.find(item => item.id === id);
  if (!portfolio) return;
  activePortfolio = portfolio;
  portfolioPicker.hidden = true;
  workspace.hidden = false;
  $(".hero").hidden = false;
  $("#portfolioActiveName").textContent = "Carteira de " + portfolio.name;
  $(".hero h1").textContent = "Empresas de " + portfolio.name;
  $(".hero p").textContent = "Pesquise uma empresa e acesse suas ferramentas.";
  search.value = "";
  $('#regimeFilter').value = "";
  filterCompanies();
  window.scrollTo({top:0,behavior:"smooth"});
}

function showPortfolioPicker() {
  activePortfolio = null;
  selected = null;
  panel.hidden = true;
  portfolioPicker.hidden = false;
  workspace.hidden = true;
  $(".hero").hidden = true;
  renderPortfolios();
  window.scrollTo({top:0,behavior:"smooth"});
}
document.querySelector("#backToPortfolios").addEventListener("click", showPortfolioPicker);

