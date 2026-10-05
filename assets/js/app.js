const search = document.querySelector("#companySearch");

search?.addEventListener("input", (event) => {
  const value = event.target.value.trim();
  document.documentElement.dataset.searching = value ? "true" : "false";
});
