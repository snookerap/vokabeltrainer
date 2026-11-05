/// <reference path="../pb_data/types.d.ts" />
// Die App-Seite und das Widget-Skript nie zwischenspeichern, damit Updates sofort ankommen (iPhone, Cloudflare).
routerUse((e) => {
  const p = e.request.url.path;
  if (p === "/" || p === "/index.html" || p === "/sw.js" || p === "/manifest.webmanifest" || p.startsWith("/widget/")) {
    e.response.header().set("Cache-Control", "no-cache, no-store, must-revalidate");
  }
  return e.next();
});
