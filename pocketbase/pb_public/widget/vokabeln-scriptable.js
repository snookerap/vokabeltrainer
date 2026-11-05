// Vokabeltrainer – Widget für die App „Scriptable“ (iPhone/iPad)
// Zeigt: Wörter für heute, Serie, Fortschritt und das Wort des Tages.
// Größen: klein, mittel, groß sowie Sperrbildschirm (rechteckig, rund, Zeile).
const API = "__API__";   // wird von der App beim Kopieren eingesetzt
const APP = "__APP__";

const TEAL = new Color("#012169"), GOLD = new Color("#ff6b81"), WHITE = Color.white(), SOFT = new Color("#ffffff", 0.72);
const fm = FileManager.local();
const CACHE = fm.joinPath(fm.documentsDirectory(), "vokabeln-widget.json");

async function load() {
  try {
    const r = new Request(API); r.timeoutInterval = 15;
    const d = await r.loadJSON();
    if (d && typeof d.today === "number") { fm.writeString(CACHE, JSON.stringify(d)); return d; }
    if (d && d.error) return { error: d.error };
  } catch (e) {}
  if (fm.fileExists(CACHE)) { const d = JSON.parse(fm.readString(CACHE)); d.offline = true; return d; }
  return null;
}

function bar(width, height, part) {
  const dc = new DrawContext(); dc.size = new Size(width, height); dc.opaque = false; dc.respectScreenScale = true;
  const r = height / 2, bg = new Path(); bg.addRoundedRect(new Rect(0, 0, width, height), r, r);
  dc.addPath(bg); dc.setFillColor(new Color("#ffffff", 0.25)); dc.fillPath();
  const w = Math.max(height, Math.round(width * Math.min(1, Math.max(0, part))));
  if (part > 0) { const fg = new Path(); fg.addRoundedRect(new Rect(0, 0, w, height), r, r); dc.addPath(fg); dc.setFillColor(GOLD); dc.fillPath(); }
  return dc.getImage();
}

function text(stack, s, size, opts = {}) {
  const t = stack.addText(String(s)); t.font = opts.bold ? Font.boldSystemFont(size) : Font.systemFont(size);
  t.textColor = opts.color || WHITE; if (opts.lines) t.lineLimit = opts.lines; if (opts.min) t.minimumScaleFactor = opts.min; return t;
}

function headline(d) {
  if (d.practicedToday && !d.today) return "Alles erledigt ✓";
  return `${d.today === 1 ? "Wort" : "Wörter"} für heute`;
}

const fam = config.widgetFamily || "medium";
const d = await load();
const w = new ListWidget();
w.url = APP;
w.refreshAfterDate = new Date(Date.now() + 30 * 60 * 1000);

if (fam.startsWith("accessory")) {
  w.addAccessoryWidgetBackground = fam === "accessoryCircular";
  if (!d || d.error) text(w, "📚 –", 14);
  else if (fam === "accessoryInline") text(w, `📚 ${d.today} · 🔥 ${d.streak}`, 14);
  else if (fam === "accessoryCircular") { const t = text(w, d.today, 22, { bold: true }); t.centerAlignText(); const s = text(w, "Wörter", 10); s.centerAlignText(); }
  else {
    text(w, `📚 ${d.today} heute · 🔥 ${d.streak}`, 14, { bold: true, lines: 1, min: 0.7 });
    if (d.wod) text(w, `${d.wod.en} = ${d.wod.de}`, 12, { lines: 2, min: 0.7 });
  }
} else {
  w.backgroundColor = TEAL;
  w.setPadding(14, 14, 14, 14);
  if (!d) { text(w, "Vokabeln", 16, { bold: true }); w.addSpacer(6); text(w, "Keine Verbindung", 13, { color: SOFT }); }
  else if (d.error) { text(w, "Vokabeln", 16, { bold: true }); w.addSpacer(6); text(w, "Schlüssel ungültig – in der App unter Mehr → Widget neu kopieren.", 12, { color: SOFT }); }
  else {
    const row = w.addStack(); row.layoutHorizontally();
    const left = row.addStack(); left.layoutVertically();
    text(left, d.practicedToday && !d.today ? "✓" : d.today, fam === "small" ? 40 : 44, { bold: true });
    text(left, headline(d), 12, { color: SOFT, lines: 2, min: 0.8 });
    if (fam !== "small" && d.today) text(left, `🔁 ${d.due} alt · ✨ ${d.new} neu`, 11, { color: SOFT, lines: 1, min: 0.7 });
    left.addSpacer(6);
    text(left, d.streak ? `🔥 ${d.streak} ${d.streak === 1 ? "Tag" : "Tage"} in Folge` : "🔥 Starte deine Serie", 12, { lines: 1, min: 0.8 });
    left.addSpacer();
    const part = d.total ? d.sure / d.total : 0;
    left.addImage(bar(fam === "small" ? 130 : 120, 6, part)).imageSize = new Size(fam === "small" ? 130 : 120, 6);
    left.addSpacer(3);
    text(left, `${d.sure} von ${d.total} sicher`, 10, { color: SOFT, lines: 1, min: 0.8 });
    if (fam !== "small" && d.wod) {
      row.addSpacer(14);
      const right = row.addStack(); right.layoutVertically();
      text(right, "WORT DES TAGES", 10, { color: GOLD, bold: true });
      right.addSpacer(4);
      text(right, d.wod.en, fam === "large" ? 22 : 18, { bold: true, lines: 2, min: 0.6 });
      text(right, d.wod.de, 13, { color: SOFT, lines: 2, min: 0.7 });
      if (fam === "large" && d.wod.ex) { right.addSpacer(8); text(right, `„${d.wod.ex}“`, 13, { color: SOFT, lines: 5, min: 0.8 }); }
      if (fam === "large" && d.wod.lesson) { right.addSpacer(6); text(right, `aus: ${d.wod.lesson}`, 10, { color: SOFT, lines: 1, min: 0.7 }); }
      right.addSpacer();
    }
    if (d.offline) { w.addSpacer(2); text(w, "offline – letzter Stand", 9, { color: SOFT }); }
  }
}

if (config.runsInWidget) Script.setWidget(w);
else if (fam === "small") await w.presentSmall(); else if (fam === "large") await w.presentLarge(); else await w.presentMedium();
Script.complete();
