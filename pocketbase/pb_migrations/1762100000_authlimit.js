/// <reference path="../pb_data/types.d.ts" />
// Anmelde-Bremse etwas lockerer: 5 Versuche je 10 s (vorher 2 je 3 s) – ein Vertipper sperrt nicht mehr sofort,
// gegen Passwort-Raten bleibt es wirksam (max. 30 Versuche pro Minute).
migrate((app) => {
  const s = app.settings();
  s.rateLimits.rules = (s.rateLimits.rules || []).map((r) =>
    r.label === "*:auth" ? Object.assign({}, r, { duration: 10, maxRequests: 5 }) : r);
  app.save(s);
}, (app) => {});
