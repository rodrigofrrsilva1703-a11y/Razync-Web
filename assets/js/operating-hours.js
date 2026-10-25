/* Janela diária: protege o acesso pelo navegador antes do carregamento do app. */
(() => {
  "use strict";
  function isClosed() {
    const now = new Date();
    const hour = Number(new Intl.DateTimeFormat("en-GB", {
      timeZone: "America/Sao_Paulo", hour: "2-digit", hourCycle: "h23",
    }).format(now));
    return hour < 7;
  }
  function checkSchedule() {
    if (isClosed()) {
      window.location.replace("./indisponivel.html");
    }
  }
  checkSchedule();
  // Abas que já estavam abertas também encerram o acesso à meia-noite.
  window.setInterval(checkSchedule, 30000);
})();
