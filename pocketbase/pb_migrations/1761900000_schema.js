/// <reference path="../pb_data/types.d.ts" />
// Datenmodell des Vokabeltrainers. Alle Daten sind nur für angemeldete Nutzer sichtbar.
const AUTH = "@request.auth.id != '' && @request.auth.collectionName = 'users'";

migrate((app) => {
  const rules = { listRule: AUTH, viewRule: AUTH, createRule: AUTH, updateRule: AUTH, deleteRule: AUTH };

  const lessons = new Collection(Object.assign({
    type: "base", name: "lessons",
    fields: [
      { type: "text", name: "key", required: true, max: 64 },
      { type: "text", name: "name", max: 200 },
      { type: "text", name: "date", max: 10 },
      { type: "bool", name: "dated" },
      { type: "number", name: "order" },
      { type: "json", name: "words", maxSize: 2000000 },
      { type: "autodate", name: "created", onCreate: true },
      { type: "autodate", name: "updated", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_lessons_key ON lessons (key)"],
  }, rules));
  app.save(lessons);

  const progress = new Collection(Object.assign({
    type: "base", name: "progress",
    fields: [
      { type: "text", name: "key", required: true, max: 64 },
      { type: "json", name: "w", maxSize: 2000000 },
      { type: "autodate", name: "updated", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_progress_key ON progress (key)"],
  }, rules));
  app.save(progress);

  const meta = new Collection(Object.assign({
    type: "base", name: "meta",
    fields: [
      { type: "text", name: "key", required: true, max: 64 },
      { type: "json", name: "data", maxSize: 2000000 },
      { type: "autodate", name: "updated", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_meta_key ON meta (key)"],
  }, rules));
  app.save(meta);

  const recordings = new Collection(Object.assign({
    type: "base", name: "recordings",
    fields: [
      { type: "text", name: "lesson_key", required: true, max: 64 },
      { type: "file", name: "file", required: true, maxSelect: 1, maxSize: 104857600, protected: true },
      { type: "text", name: "orig_name", max: 300 },
      { type: "select", name: "status", maxSelect: 1, values: ["pending", "processing", "done", "error"] },
      { type: "text", name: "error", max: 2000 },
      { type: "number", name: "duration" },
      { type: "json", name: "transcript", maxSize: 5000000 },
      { type: "number", name: "matched" },
      { type: "autodate", name: "created", onCreate: true },
      { type: "autodate", name: "updated", onCreate: true, onUpdate: true },
    ],
  }, rules));
  app.save(recordings);

  // KI-Stimme: eine MP3 pro Text + Stimme, vom Worker erzeugt (Nutzer dürfen nur lesen)
  const tts = new Collection({
    type: "base", name: "tts",
    listRule: AUTH, viewRule: AUTH, createRule: null, updateRule: null, deleteRule: null,
    fields: [
      { type: "text", name: "key", required: true, max: 64 },
      { type: "text", name: "text", max: 1000 },
      { type: "text", name: "voice", max: 100 },
      { type: "file", name: "file", maxSelect: 1, maxSize: 10485760, protected: true },
      { type: "autodate", name: "created", onCreate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_tts_key ON tts (key)"],
  });
  app.save(tts);

  // Keine Selbst-Registrierung: Konten legt nur der Admin an
  const users = app.findCollectionByNameOrId("users");
  users.createRule = null;
  app.save(users);
}, (app) => {
  for (const n of ["tts", "recordings", "meta", "progress", "lessons"]) {
    try { app.delete(app.findCollectionByNameOrId(n)); } catch (e) {}
  }
});
