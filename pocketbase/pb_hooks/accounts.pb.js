/// <reference path="../pb_data/types.d.ts" />
// Legt beim Start die Konten aus der .env an (bzw. aktualisiert die Passwörter):
//  - APP_USER_EMAIL / APP_USER_PASSWORD   -> dein Login für die App
//  - PB_SUPERUSER_EMAIL / PB_SUPERUSER_PASSWORD -> Admin-Konto (auch vom Worker genutzt)
onBootstrap((e) => {
  e.next();
  const upsert = (collection, email, password) => {
    if (!email || !password) return;
    let rec;
    try {
      rec = e.app.findAuthRecordByEmail(collection, email);
    } catch (err) {
      rec = new Record(e.app.findCollectionByNameOrId(collection));
      rec.setEmail(email);
    }
    // Nur bei Änderung neu setzen – sonst werden alle Anmeldungen (auch die des Workers) ungültig
    let changed = false;
    if (!rec.id || !rec.validatePassword(password)) { rec.setPassword(password); changed = true; }
    if (collection === "users" && !rec.verified()) { rec.setVerified(true); changed = true; }
    if (changed) e.app.save(rec);
    console.log("[vokabeltrainer] Konto bereit:", collection, email, changed ? "(Passwort gesetzt)" : "(unverändert)");
  };
  try {
    upsert("_superusers", $os.getenv("PB_SUPERUSER_EMAIL"), $os.getenv("PB_SUPERUSER_PASSWORD"));
    upsert("users", $os.getenv("APP_USER_EMAIL"), $os.getenv("APP_USER_PASSWORD"));
  } catch (err) {
    console.error("[vokabeltrainer] Konten konnten nicht angelegt werden:", err);
  }
});
