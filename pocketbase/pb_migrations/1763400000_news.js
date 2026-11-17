/// <reference path="../pb_data/types.d.ts" />
// Daily News: eine Folge pro Tag – Smart-Home-Nachrichten vom Vortag in einfachem Englisch (Text + MP3).
// Der Worker legt die Einträge an; die App liest sie nur.
const AUTH = "@request.auth.id != '' && @request.auth.collectionName = 'users'";

migrate((app) => {
  const c = new Collection({
    type: "base", name: "news",
    listRule: AUTH, viewRule: AUTH, createRule: null, updateRule: AUTH, deleteRule: AUTH,
    fields: [
      { type: "text", name: "date", required: true, max: 10 },        // Tag der Folge (JJJJ-MM-TT)
      { type: "text", name: "title", max: 300 },
      { type: "json", name: "data", maxSize: 200000 },                // intro, headlines, outro, vocab, sources, usage
      { type: "text", name: "status", max: 20 },                      // done | error | empty
      { type: "text", name: "error", max: 2000 },
      { type: "number", name: "tries" },
      { type: "file", name: "audio", maxSelect: 1, maxSize: 20971520, protected: true },
      { type: "number", name: "duration" },
      { type: "bool", name: "pushed" },
      { type: "bool", name: "listened" },
      { type: "autodate", name: "created", onCreate: true },
      { type: "autodate", name: "updated", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_news_date ON news (date)"],
  });
  app.save(c);
}, (app) => {
  try { app.delete(app.findCollectionByNameOrId("news")); } catch (e) {}
});
