/// <reference path="../pb_data/types.d.ts" />
// Bremse gegen Passwort-Raten und Fremde bleibt streng – angemeldete Nutzer dürfen viel speichern (z. B. beim Import).
migrate((app) => {
  const s = app.settings();
  s.rateLimits.enabled = true;
  s.rateLimits.rules = [
    { label: "*:auth", audience: "", duration: 3, maxRequests: 2 },
    { label: "*:create", audience: "@guest", duration: 5, maxRequests: 20 },
    { label: "*:create", audience: "@auth", duration: 10, maxRequests: 500 },
    { label: "/api/batch", audience: "", duration: 1, maxRequests: 3 },
    { label: "/api/", audience: "@guest", duration: 10, maxRequests: 300 },
    { label: "/api/", audience: "@auth", duration: 10, maxRequests: 2000 },
  ];
  app.save(s);
}, (app) => {});
