/// <reference path="../pb_data/types.d.ts" />
// Die App-Seite nie zwischenspeichern, damit Updates sofort ankommen (iPhone, Cloudflare).
routerUse((e) => {
  const p = e.request.url.path;
  if (p === "/" || p === "/index.html") {
    e.response.header().set("Cache-Control", "no-cache, no-store, must-revalidate");
  }
  return e.next();
});
