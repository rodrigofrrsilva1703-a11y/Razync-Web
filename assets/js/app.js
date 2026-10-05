const grid = document.querySelector("#companyGrid");
const search = document.querySelector("#companySearch");
const count = document.querySelector("#companyCount");
const workspace = document.querySelector(".workspace");
const panel = document.querySelector("#companyPanel");
const backButton = document.querySelector("#backButton");
const form = document.querySelector("#processForm");
const bankSelect = document.querySelector("#bankSelect");
const fileInput = document.querySelector("#fileInput");
const message = document.querySelector("#processMessage");
const apiStatus = document.querySelector("#apiStatus");

const BANKS = {
  47: { banco_brasil: "Banco do Brasil · conta 8" },
  88: { itau: "Itaú · conta 508" },
  154: { bradesco: "Bradesco · conta 9", itau: "Itaú · conta 508" },
  242: { itau: "Itaú" },
  625: { banco_brasil: "Banco do Brasil · conta 8", caixa: "Caixa · conta 508", sicredi: "Sicredi · conta 3999" },
  626: { banco_brasil: "Banco do Brasil", sicredi: "Sicredi" },
  841: { inter: "Banco Inter · conta 506" },
  912: { sicredi: "Sicredi · conta 515" },
  964: { bradesco: "Bradesco · conta 9" },
  968: { itau: "Itaú · conta 508", bradesco: "Bradesco · conta 9" },
  969: { itau: "Itaú · conta 508" },
  1096: { santander: "Santander · conta 513", sicredi: "Sicredi · conta 510" },
  1208: { itau: "Itaú · conta 508", safra: "Safra · conta 512", bradesco: "Bradesco · conta 9" },
  1402: { btg: "BTG · conta 510" },
  1408: { itau: "Itaú · conta 512" },
  1530: { itau: "Itaú · conta 508" },
  1532: { itau: "Itaú · conta 508" }
};

const API_READY = new Set([47, 88, 154, 625, 626, 841, 912, 964, 969, 1208, 1530, 1532]);
let companies = [];
let selected = null;

function normalize(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

function statusFor(code) {
  return API_READY.has(Number(code)) ? "Adaptador pronto" : "Motor preservado";
}

function render(items) {
  grid.innerHTML = "";
  count.textContent = `${items.length} empresa(s)`;
  if (!items.length) {
    grid.innerHTML = '<div class="empty-state">Nenhuma empresa encontrada.</div>';
    return;
  }

  for (const company of items) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "company-card company-card-button";
    card.innerHTML = `
      <div>
        <div class="card-topline">
          <span class="company-code">${company.codigo}</span>
          <span class="mini-status">${statusFor(company.codigo)}</span>
        </div>
        <h2>${company.nome}</h2>
        <p>${company.regime}</p>
      </div>
      <span class="arrow">→</span>
    `;
    card.addEventListener("click", () => openCompany(company));
    grid.appendChild(card);
  }
}

function openCompany(company) {
  selected = company;
  document.querySelector("#panelCode").textContent = `Empresa ${company.codigo}`;
  document.querySelector("#panelName").textContent = company.nome;
  document.querySelector("#panelRegime").textContent = company.regime;
  document.querySelector("#panelStatus").textContent = statusFor(company.codigo);

  const banks = BANKS[company.codigo] || {};
  bankSelect.innerHTML = "";
  if (Object.keys(banks).length) {
    for (const [value, label] of Object.entries(banks)) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      bankSelect.appendChild(option);
    }
  } else {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Ferramenta em adaptação para a nova API";
    bankSelect.appendChild(option);
  }

  fileInput.value = "";
  message.textContent = "";
  workspace.hidden = true;
  document.querySelector(".hero").hidden = true;
  panel.hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function closeCompany() {
  panel.hidden = true;
  workspace.hidden = false;
  document.querySelector(".hero").hidden = false;
  selected = null;
}

async function checkApi() {
  const base = String(window.RAZYNC_CONFIG?.apiBase || "").replace(/\/$/, "");
  if (!base) {
    apiStatus.textContent = "Frontend online · API em publicação";
    return;
  }
  try {
    const response = await fetch(`${base}/health`);
    if (!response.ok) throw new Error();
    apiStatus.textContent = "Sistema online";
    apiStatus.classList.add("online");
  } catch {
    apiStatus.textContent = "API temporariamente indisponível";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selected) return;
  const base = String(window.RAZYNC_CONFIG?.apiBase || "").replace(/\/$/, "");
  if (!base) {
    message.textContent = "O frontend está pronto. Falta publicar/conectar o backend Python.";
    return;
  }
  const files = [...fileInput.files];
  if (!files.length) {
    message.textContent = "Selecione pelo menos um arquivo.";
    return;
  }

  const data = new FormData();
  data.append("bank", bankSelect.value);
  files.forEach(file => data.append("files", file));

  message.textContent = "Processando…";
  document.querySelector("#processButton").disabled = true;
  try {
    const response = await fetch(`${base}/api/v1/modelo-dominio/${selected.codigo}`, {
      method: "POST",
      body: data
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || "Não foi possível processar os arquivos.");
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/i);
    const filename = match?.[1] || `RAZYNC_${selected.codigo}_MODELO_DOMINIO.xlsx`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    message.textContent = "Modelo Domínio gerado com sucesso.";
  } catch (error) {
    message.textContent = error.message;
  } finally {
    document.querySelector("#processButton").disabled = false;
  }
});

search.addEventListener("input", () => {
  const query = normalize(search.value.trim());
  const filtered = companies.filter(company =>
    normalize(company.codigo).includes(query) ||
    normalize(company.nome).includes(query) ||
    normalize(company.regime).includes(query)
  );
  render(filtered);
});

backButton.addEventListener("click", closeCompany);

fetch("./assets/data/companies.json")
  .then(response => response.json())
  .then(data => {
    companies = data;
    render(companies);
  })
  .catch(() => {
    count.textContent = "Falha ao carregar o catálogo.";
  });

checkApi();
