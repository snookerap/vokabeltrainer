/// <reference path="../pb_data/types.d.ts" />
// Aussprache-Training: kurze Sprachaufnahmen, die der Worker mit Whisper auswertet.
const AUTH = "@request.auth.id != '' && @request.auth.collectionName = 'users'";

migrate((app) => {
  const c = new Collection({
    type: "base", name: "attempts",
    listRule: AUTH, viewRule: AUTH, createRule: AUTH, updateRule: AUTH, deleteRule: AUTH,
    fields: [
      { type: "file", name: "file", required: true, maxSelect: 1, maxSize: 5242880, protected: true },
      { type: "text", name: "expected", max: 500 },
      { type: "select", name: "status", maxSelect: 1, values: ["pending", "done", "error"] },
      { type: "text", name: "heard", max: 1000 },
      { type: "text", name: "error", max: 1000 },
      { type: "autodate", name: "created", onCreate: true },
      { type: "autodate", name: "updated", onCreate: true, onUpdate: true },
    ],
  });
  app.save(c);
}, (app) => {
  try { app.delete(app.findCollectionByNameOrId("attempts")); } catch (e) {}
});
