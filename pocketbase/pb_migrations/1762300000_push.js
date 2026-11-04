/// <reference path="../pb_data/types.d.ts" />
// Tägliche Erinnerungen: ein Eintrag pro Gerät mit Push-Abo, Uhrzeiten und Zeitzone.
const AUTH = "@request.auth.id != '' && @request.auth.collectionName = 'users'";

migrate((app) => {
  const c = new Collection({
    type: "base", name: "push",
    listRule: AUTH, viewRule: AUTH, createRule: AUTH, updateRule: AUTH, deleteRule: AUTH,
    fields: [
      { type: "text", name: "endpoint", required: true, max: 2000 },
      { type: "json", name: "sub", maxSize: 10000 },
      { type: "json", name: "times", maxSize: 1000 },
      { type: "text", name: "tz", max: 100 },
      { type: "json", name: "last", maxSize: 2000 },
      { type: "bool", name: "test" },
      { type: "text", name: "device", max: 200 },
      { type: "autodate", name: "created", onCreate: true },
      { type: "autodate", name: "updated", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_push_endpoint ON push (endpoint)"],
  });
  app.save(c);
}, (app) => {
  try { app.delete(app.findCollectionByNameOrId("push")); } catch (e) {}
});
