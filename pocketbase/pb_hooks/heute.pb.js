/// <reference path="../pb_data/types.d.ts" />
// Tagesübersicht für das iPhone-Widget (Scriptable): /api/heute?key=…
// Der Schlüssel wird in der App unter „Mehr → Widget“ erzeugt; ohne gültigen Schlüssel gibt es nichts.
routerAdd("GET", "/api/heute", (e) => {
  const key = String(e.request.url.query().get("key") || "");
  let want = "";
  try { want = (JSON.parse($app.findFirstRecordByData("meta", "key", "widget").getString("data")) || {}).key || ""; } catch (err) {}
  e.response.header().set("Cache-Control", "no-store");
  if (!want || key.length < 20 || key !== want) return e.json(403, { error: "Ungültiger Schlüssel" });
  let s = {};
  try { s = JSON.parse($app.findFirstRecordByData("meta", "key", "summary").getString("data")) || {}; } catch (err) {}
  return e.json(200, s);
});
