/// <reference path="../pb_data/types.d.ts" />
// Liefert Betreiber-Name und Kontakt für die Datenschutzseite aus der .env
// (APP_OPERATOR_NAME / APP_OPERATOR_CONTACT / APP_PROXY_PROVIDER) – so stehen keine persönlichen Daten im Git-Repo.
routerAdd("GET", "/api/legal", (e) => {
  return e.json(200, {
    name: $os.getenv("APP_OPERATOR_NAME") || "",
    contact: $os.getenv("APP_OPERATOR_CONTACT") || "",
    proxy: $os.getenv("APP_PROXY_PROVIDER") || "",
  });
});
