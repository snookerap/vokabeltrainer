/// <reference path="../pb_data/types.d.ts" />
// Privater Podcast-Feed der Daily News: /api/news/podcast.xml?key=…
// Die MP3s kommen über /api/news/audio/{id}.mp3?key=… – ohne Anmeldung, aber nur mit gültigem Schlüssel.
// Der Schlüssel wird in der App unter „Daily News → Als Podcast hören“ erzeugt (meta „podcast“).
routerAdd("GET", "/api/news/podcast.xml", (e) => {
  const key = String(e.request.url.query().get("key") || "");
  let want = "";
  try { want = (JSON.parse($app.findFirstRecordByData("meta", "key", "podcast").getString("data")) || {}).key || ""; } catch (err) {}
  e.response.header().set("Cache-Control", "no-store");
  if (!want || key.length < 20 || key !== want) return e.string(403, "Ungültiger Schlüssel");

  const x = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const proto = String(e.request.header.get("X-Forwarded-Proto") || (e.request.tls ? "https" : "http")).split(",")[0].trim();
  const base = proto + "://" + e.request.host;
  const k = encodeURIComponent(key);
  const img = base + "/icons/icon-uk-512.png";
  const recs = $app.findRecordsByFilter("news", "status = 'done' && audio != ''", "-date", 30, 0);
  const fsys = $app.newFilesystem();
  const items = [];
  try {
    for (const r of recs) {
      let d = {};
      try { d = JSON.parse(r.getString("data")) || {}; } catch (err) {}
      let size = 0;
      try { size = fsys.attributes(r.baseFilesPath() + "/" + r.getString("audio")).size; } catch (err) {}
      const date = r.getString("date");
      const de = date.slice(8, 10) + "." + date.slice(5, 7) + "." + date.slice(0, 4);
      let pub = new Date(String(r.getString("created")).replace(" ", "T"));
      if (isNaN(pub.getTime())) pub = new Date(date + "T06:30:00Z");
      const desc = [d.intro]
        .concat((d.headlines || []).map((h) => "• " + (h.title || "") + ": " + (h.text || "")))
        .concat([d.outro, (d.vocab || []).length ? "Words of the day: " + d.vocab.map((v) => v.en + " – " + v.de).join(", ") : ""])
        .filter((s) => s).join("\n");
      items.push(
        "<item><title>" + x(de + " · " + (r.getString("title") || "Smart Home News")) + "</title>" +
        "<guid isPermaLink=\"false\">news-" + x(r.id) + "</guid><pubDate>" + pub.toUTCString() + "</pubDate>" +
        "<enclosure url=\"" + x(base + "/api/news/audio/" + r.id + ".mp3?key=" + k) + "\" length=\"" + (size || 0) + "\" type=\"audio/mpeg\"/>" +
        (r.getInt("duration") ? "<itunes:duration>" + r.getInt("duration") + "</itunes:duration>" : "") +
        "<description>" + x(desc) + "</description></item>"
      );
    }
  } finally { fsys.close(); }

  const xml = '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>' +
    "<title>Smart Home News (Vokabeltrainer)</title><link>" + x(base + "/") + "</link><language>en</language>" +
    "<description>Daily smart home and world news in simple English – private feed.</description>" +
    "<itunes:author>Vokabeltrainer</itunes:author><itunes:block>Yes</itunes:block><itunes:explicit>false</itunes:explicit>" +
    '<itunes:image href="' + x(img) + '"/><image><url>' + x(img) + "</url><title>Smart Home News (Vokabeltrainer)</title><link>" + x(base + "/") + "</link></image>" +
    items.join("") + "</channel></rss>";
  e.response.header().set("Content-Type", "application/rss+xml; charset=utf-8");
  return e.string(200, xml);
});

routerAdd("GET", "/api/news/audio/{file}", (e) => {
  const key = String(e.request.url.query().get("key") || "");
  let want = "";
  try { want = (JSON.parse($app.findFirstRecordByData("meta", "key", "podcast").getString("data")) || {}).key || ""; } catch (err) {}
  if (!want || key.length < 20 || key !== want) return e.string(403, "Ungültiger Schlüssel");
  const id = String(e.request.pathValue("file") || "").replace(/\.mp3$/, "");
  let r = null;
  try { r = $app.findRecordById("news", id); } catch (err) {}
  if (!r || !r.getString("audio")) return e.string(404, "Nicht gefunden");
  const fsys = $app.newFilesystem();
  try {
    fsys.serve(e.response, e.request, r.baseFilesPath() + "/" + r.getString("audio"), "daily-news-" + r.getString("date") + ".mp3");
  } finally { fsys.close(); }
});
