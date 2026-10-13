/* Janela diária: protege o acesso pelo navegador antes do carregamento do app. */
(() => {
  "use strict";
  function saoPauloHour() {
    return Number(new Intl.DateTimeFormat("en-GB", {
      timeZone: "America/Sao_Paulo", hour: "2-digit", hourCycle: "h23",
    }).format(new Date()));
  }
  function checkSchedule() {
    if (saoPauloHour() < 7) {
      window.location.replace("./indisponivel.html");
    }
  }
  checkSchedule();
  // Abas que já estavam abertas também encerram o acesso à meia-noite.
  window.setInterval(checkSchedule, 30000);
})();
