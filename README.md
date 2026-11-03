# Vokabeltrainer

Ein selbst gehosteter Vokabeltrainer fürs Handy, gedacht für Englischkurse: Vokabeln pro Unterrichtsstunde, Aussprache von der Lehrkraft und einer KI-Stimme, Abfrage mit Wiederholungsplan, Sprech- und Diktatübungen. Alles läuft auf deinem eigenen Server. Spracherkennung und Sprachausgabe laufen lokal, ohne Cloud-KI.

| Dienst | Aufgabe |
|---|---|
| `pocketbase` | Datenbank, Login, MP3-Speicher und die App selbst (Port 8090) |
| `worker` | **Piper** erzeugt die KI-Stimme für jedes Wort. **Whisper** schneidet die Aufnahme der Lehrkraft Wort für Wort und prüft deine Aussprache |

Der Worker hat keinen offenen Port und spricht nur intern mit PocketBase.

## Funktionen

- Vokabeln nach Stunden, einzeln, als eingefügte Liste oder per **Excel-Import** (jeder Reiter wird eine Stunde)
- **Lehrer-MP3 hochladen:** Whisper schneidet daraus automatisch jedes Wort. Die ganze Aufnahme lässt sich mit Mitlesen anhören, auch bei gesperrtem Bildschirm
- Übungsarten: Karteikarte, Multiple Choice, Schreiben, Hören, Lückensatz, Diktat und Sprechen (mit Whisper-Prüfung)
- Wiederholung nach dem Leitner-Prinzip, „Vor dem Kurs“-Runde, Fortschrittskurve
- **Mit Claude üben:** öffnet ein Rollenspiel mit deinen Wörtern auf claude.ai (nur auf Knopfdruck)
- Grammatik-Notizen, Export und Import als JSON

## Voraussetzungen

- Ein Linux-Server oder eine VM bzw. ein LXC mit **Docker** (Docker Compose v2)
- **CPU mit AVX** (prüfen: `grep -q avx /proc/cpuinfo && echo ok`)
- ca. **3 GB RAM**, **10 GB Speicher** (Modelle ca. 1 GB plus deine Aufnahmen)
- Für den Zugriff von unterwegs: Reverse Proxy mit HTTPS, z. B. Nginx Proxy Manager, Caddy oder Traefik, eventuell zusätzlich ein Tunnel

Bei einem Proxmox-LXC unter *Options → Features* **nesting** und **keyctl** aktivieren.

## Installation

```bash
git clone https://github.com/<dein-konto>/vokabeltrainer.git
cd vokabeltrainer
cp .env.example .env
nano .env                 # E-Mail + Passwörter für dich und den Admin, Betreiber für die Datenschutzseite
docker compose up -d --build
docker compose logs -f worker
```

Beim **ersten Start** lädt der Worker die Modelle herunter: Whisper *small* ca. 500 MB, je Piper-Stimme ca. 110 MB. Danach erzeugt er die KI-Stimme für alle Wörter.

Test im lokalen Netz: `http://<server-ip>:8090`, anmelden mit `APP_USER_EMAIL` / `APP_USER_PASSWORD`.

## Reverse Proxy (Beispiel Nginx Proxy Manager)

Proxy Host auf `http://<server-ip>:8090`, **Websockets** an, SSL an. Unter *Advanced*:

```nginx
client_max_body_size 100M;
proxy_buffering off;          # Live-Aktualisierung (Server-Sent Events)
proxy_read_timeout 600s;

# Admin-Bereich von außen sperren – nur im lokalen Netz über http://<server-ip>:8090/_/
location /_/ { deny all; }
location /api/collections/_superusers/ { deny all; }
```

Bei anderen Proxys gilt dasselbe: Uploads bis 100 MB erlauben, kein Puffern, `/_/` und `/api/collections/_superusers/` von außen sperren.

**Aufs Handy:** Die Adresse in Safari oder Chrome öffnen, dann *Teilen* → **Zum Home-Bildschirm**.

## Alltag

| Was | Wie |
|---|---|
| Excel-Tabelle laden | *Stunden → 📥 Excel*: jeder Reiter wird eine Stunde, Vorhandenes wird übersprungen. Neue Wörter lassen sich in der Vorschau bearbeiten oder mit Claude prüfen |
| Lehrer-MP3 | Stunde → *MP3 hochladen*. Passt ein Clip nicht: Wort antippen → *Ausschnitt wählen* |
| Aufnahme anhören | *🎧 Anhören* auf der Startseite, beim Üben oder in der Stunde |
| Viele Wörter auf einmal | *+ Neu → 📋 Mehrere Wörter* |
| Beispielsätze | Stunde → *✍️ Sätze holen* → in Claude öffnen → Antwort einfügen |
| Stimme wechseln | *Mehr → KI-Stimme* (Britisch/Amerikanisch) |
| Claude-Projekt | *Mehr → Claude-Projekt*: eigenen Projekt-Link eintragen (optional) |
| Backup | Alle Daten liegen in `./data/`. Diesen Ordner sichern |
| Admin-Oberfläche | `http://<server-ip>:8090/_/` (nur lokal) |
| Passwort ändern | In `.env` ändern → `docker compose up -d` |
| Update | `git pull && docker compose up -d --build` (`.env` und `data/` bleiben erhalten) |
| Version | *Mehr* → ganz unten |

### Optionale Korrekturliste für eine Kurs-Excel

Enthält die Excel eurer Lehrkraft immer dieselben Tippfehler, kann der Import sie automatisch berichtigen. Lege dazu `pocketbase/pb_public/known_fix.json` an. Die Datei ist nicht Teil des Repos:

```json
[["Excel-Deutsch", "Excel-Englisch", "richtiges Deutsch", "richtiges Englisch"]]
```

## Feinabstimmung (`.env`)

- `WHISPER_MODEL`: `base` ist schneller, `medium` genauer (braucht ca. 5 GB RAM). Standard ist `small`.
- `WHISPER_LANGUAGE`: leer lassen (automatisch). Werden englische Wörter schlecht erkannt, `en` probieren.
- `PIPER_VOICE_GB` / `PIPER_VOICE_US`: Hörproben unter <https://rhasspy.github.io/piper-samples/>. Standard: `en_GB-cori-high` und `en_US-ljspeech-high`, beide gemeinfrei. **Vor einem Wechsel die MODEL_CARD der Stimme prüfen**, denn manche Stimmen sind nur für Forschung lizenziert. Stimmen auf Lessac-Basis ersetzt der Worker automatisch.
- `PIPER_LENGTH_SCALE`: `1.2` = langsamer und deutlicher.

## Datenschutz und Recht – wenn andere deine Instanz nutzen

- **Datenschutzseite:** `/legal/datenschutz.html`, verlinkt beim Login und unter *Mehr*. In der `.env` `APP_OPERATOR_NAME`, `APP_OPERATOR_CONTACT` und gegebenenfalls `APP_PROXY_PROVIDER` (z. B. `Cloudflare`) eintragen und neu starten. Prüfe, ob der Text zu deinem Betrieb passt. Er ist eine Vorlage und keine Rechtsberatung.
- **Keine Verbindungen zu Dritten:** Schriften und Skripte liegen lokal, ohne Tracking und ohne Analyse. Claude wird nur geöffnet, wenn man einen Claude-Knopf antippt.
- **Datensparsam:** Sprachaufnahmen beim Üben werden nach ca. einer Stunde gelöscht, Server-Protokolle nach 7 Tagen. Selbstregistrierung ist abgeschaltet, Konten legt der Betreiber an.
- **Gemeinsamer Datenbestand:** Alle Konten einer Instanz sehen dieselben Stunden und denselben Lernstand. Für getrennte Lernstände betreibt jede Person ihre eigene Instanz.
- **Kursinhalte gehören nicht ins Repo:** Vokabellisten und Aufnahmen der Lehrkraft sind deren Werk. Teilt sie nur mit ihrer Zustimmung. Ins Repo und in Forks gehören sie nie, `data/` ist per `.gitignore` ausgeschlossen.
- **Lizenzen:** siehe `THIRD_PARTY_NOTICES.md` und `/legal/lizenzen.html`.

## Fehlersuche

```bash
docker compose ps
docker compose logs --tail 100 worker
docker compose logs --tail 100 pocketbase
```

- **Aufnahme bleibt bei „Wartet auf Verarbeitung“:** Der Worker läuft nicht oder lädt noch Modelle → Log ansehen.
- **`Illegal instruction` im Worker-Log:** Die CPU hat kein AVX.
- **App lädt nicht über die Domain, im LAN aber schon:** Reverse Proxy bzw. Tunnel prüfen.

## Lizenz

Der Code steht unter der [MIT-Lizenz](LICENSE). Mitgelieferte Fremdsoftware, Schriften und Stimmen haben eigene Lizenzen, siehe [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
