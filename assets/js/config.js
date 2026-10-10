window.RAZYNC_CONFIG = {
  apiBase: ["localhost", "127.0.0.1"].includes(window.location.hostname)
    ? window.location.origin
    : "https://razync-api-production.up.railway.app"
};
