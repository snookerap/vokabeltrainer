/// <reference path="../pb_data/types.d.ts" />
// Datensparsamkeit: Server-Protokolle (inkl. IP-Adresse) nur 7 Tage aufbewahren.
// Die IP bleibt im Protokoll, damit sich Angriffe (Passwort-Raten) erkennen lassen.
migrate((app) => {
  const s = app.settings();
  s.logs.maxDays = 7;
  s.logs.logIP = true;
  app.save(s);
}, (app) => {});
