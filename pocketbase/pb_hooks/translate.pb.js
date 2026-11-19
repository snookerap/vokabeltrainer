/// <reference path="../pb_data/types.d.ts" />
// Eigene Wörter aus den Daily News übersetzen: POST /api/news/translate  (nur angemeldet)
// Body: { items: [{ en: "heat pump", ctx: "Satz, in dem das Wort steht." }, …] }  (höchstens 25)
// Antwort: { items: [{ en, de }] } – ein kleiner Claude-Aufruf (Modell aus NEWS_MODEL, Standard Haiku).
// Braucht ANTHROPIC_API_KEY auch im pocketbase-Container (docker-compose.yml).
routerAdd("POST", "/api/news/translate", (e) => {
  const key = String($os.getenv("ANTHROPIC_API_KEY") || "").trim();
  if (!key) return e.json(503, { error: "Kein ANTHROPIC_API_KEY für den PocketBase-Container eingetragen (siehe README)." });
  const model = String($os.getenv("NEWS_MODEL") || "").trim() || "claude-haiku-5-5";
  const api = String($os.getenv("ANTHROPIC_API") || "").trim() || "https://api.anthropic.com/v1/messages";

  let items = [];
  try { items = (e.requestInfo().body || {}).items || []; } catch (err) {}
  if (!Array.isArray(items)) items = [];
  items = items
    .map((x) => ({ en: String((x && x.en) || "").trim().slice(0, 60), ctx: String((x && x.ctx) || "").trim().slice(0, 300) }))
    .filter((x) => x.en)
    .slice(0, 25);
  if (!items.length) return e.json(400, { error: "Keine Wörter" });

  const user = items.map((x, i) => (i + 1) + ". " + x.en + (x.ctx ? "  | Kontext: " + x.ctx : "")).join("\n");
  const system =
    "Du übersetzt englische Wörter und Wortgruppen aus einem Nachrichtentext für einen deutschen Englischlerner (Niveau A2). " +
    "Gib für jeden Eintrag die deutsche Bedeutung, die im Kontext passt – kurz wie im Wörterbuch: Nomen mit Artikel (der/die/das), " +
    "Verben im Infinitiv, höchstens zwei Bedeutungen mit Komma. Als \"en\" die englische Grundform (Singular, Infinitiv ohne \"to\"), " +
    "Eigennamen und Wortgruppen unverändert. Antworte NUR mit JSON: {\"items\":[{\"n\":1,\"en\":\"…\",\"de\":\"…\"}]}";
  const body = {
    model: model, max_tokens: 1500, system: system,
    messages: [{ role: "user", content: user }],
    output_config: { effort: "low" },
  };

  let res;
  try {
    res = $http.send({
      url: api, method: "POST", timeout: 60, body: JSON.stringify(body),
      headers: { "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01" },
    });
  } catch (err) {
    return e.json(502, { error: "Claude nicht erreichbar: " + err });
  }
  const d = res.json || {};
  if (res.statusCode >= 400) return e.json(502, { error: "Claude-API HTTP " + res.statusCode + ": " + ((d.error && d.error.message) || "") });

  const txt = (d.content || []).filter((b) => b.type === "text").map((b) => b.text || "").join("");
  const m = txt.match(/\{[\s\S]*\}/);
  let out = [];
  try { out = (JSON.parse(m ? m[0] : "{}").items || []); } catch (err) {}
  const result = items.map((x, i) => {
    const r = out.find((o) => +o.n === i + 1) || out[i] || {};
    return { src: x.en, en: String(r.en || x.en).trim(), de: String(r.de || "").trim() };
  });
  return e.json(200, { items: result, usage: d.usage || {} });
}, $apis.requireAuth());
