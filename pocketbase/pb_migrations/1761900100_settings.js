/// <reference path="../pb_data/types.d.ts" />
// Grundeinstellungen: App-Name, Schutz gegen Passwort-Raten, echte Client-IP hinter Cloudflare.
migrate((app) => {
  const s = app.settings();
  s.meta.appName = "Vokabeltrainer";
  s.rateLimits.enabled = true;
  s.trustedProxy.headers = ["CF-Connecting-IP", "X-Forwarded-For"];
  s.trustedProxy.useLeftmostIP = true;
  app.save(s);
}, (app) => {});
