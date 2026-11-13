/* Mobile dates use the numeric keyboard; services continue receiving ISO dates. */
function typedDateToISO(value) {
  if (!value) return "";
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value);
  if (!match) return null;
  const [, day, month, year] = match;
  const d = Number(day), m = Number(month), y = Number(year);
  const leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (y < 1 || m < 1 || m > 12 || d < 1 || d > days[m - 1]) return null;
  return `${year}-${month}-${day}`;
}

function dateApiValue(input) {
  if (!input.dataset.manualDate) return input.value;
  const value = typedDateToISO(input.value);
  if (value === null) throw new Error("Informe uma data válida no formato DD/MM/AAAA.");
  return value;
}

function enableMobileDateFields(root = document) {
  if (!window.matchMedia("(max-width: 760px), (pointer: coarse)").matches) return;
  root.querySelectorAll('input[type="date"]').forEach(input => {
    const initial = input.value;
    input.type = "text";
    input.dataset.manualDate = "true";
    input.inputMode = "numeric";
    input.placeholder = "DD/MM/AAAA";
    input.maxLength = 10;
    input.autocomplete = "off";
    if (initial) input.value = initial.split("-").reverse().join("/");
    input.addEventListener("input", () => {
      const raw = /^\d{4}-\d{2}-\d{2}$/.test(input.value)
        ? input.value.split("-").reverse().join("") : input.value;
      const digits = raw.replace(/\D/g, "").slice(0, 8);
      input.value = digits.slice(0, 2) + (digits.length > 2 ? "/" + digits.slice(2, 4) : "")
        + (digits.length > 4 ? "/" + digits.slice(4) : "");
      input.setCustomValidity(typedDateToISO(input.value) === null
        ? "Informe uma data válida no formato DD/MM/AAAA." : "");
      // Invalidate the previous result immediately, including partial dates.
      input.dispatchEvent(new Event("change", {bubbles:true}));
    });
    input.form?.addEventListener("reset", () => input.setCustomValidity(""));
  });
}

enableMobileDateFields();
