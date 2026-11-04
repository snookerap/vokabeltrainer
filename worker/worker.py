"""Vokabeltrainer-Worker.

Läuft neben PocketBase und erledigt zwei Aufgaben im Hintergrund:
  1. KI-Stimme: erzeugt mit Piper für jedes englische Wort eine MP3 (Collection "tts").
  2. Lehrer-Aufnahmen: transkribiert neue MP3s mit Whisper (Wort-Zeitstempel),
     findet jede Vokabel der Stunde darin und speichert den Ausschnitt als Clip.

  3. Tagesübersicht (für Widget und Erinnerungen) berechnen und tägliche
     Push-Erinnerungen verschicken.

Er spricht nur über die PocketBase-API mit dem Admin-Konto (aus der .env) und ist
von außen nicht erreichbar.
"""
import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
import unicodedata
import urllib.request
import wave
from difflib import SequenceMatcher

import requests

socket_timeout = 120
import socket
socket.setdefaulttimeout(socket_timeout)  # Downloads dürfen nie ewig hängen

PB_URL = os.environ.get("PB_URL", "http://pocketbase:8090").rstrip("/")
PB_EMAIL = os.environ["PB_SUPERUSER_EMAIL"]
PB_PASSWORD = os.environ["PB_SUPERUSER_PASSWORD"]
MODELS = os.environ.get("MODELS_DIR", "/models")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
WHISPER_LANG = os.environ.get("WHISPER_LANGUAGE", "") or None
WHISPER_THREADS = int(os.environ.get("WHISPER_THREADS", "0") or 0)
# Nur Stimmen mit freier Datensatz-Lizenz (Public Domain / CC0 / CC-BY).
# Stimmen auf Basis des Blizzard-Lessac-Datensatzes (u. a. en_US-lessac-*) sind nur
# für Forschung/nicht-kommerziell lizenziert und werden deshalb ersetzt,
# außer PIPER_ALLOW_RESTRICTED=1 ist gesetzt.
RESTRICTED_VOICES = ("lessac",)
SAFE_DEFAULT = {"en-GB": "en_GB-cori-high", "en-US": "en_US-ljspeech-high"}


def _voice(lang, env):
    name = os.environ.get(env, "") or SAFE_DEFAULT[lang]
    if os.environ.get("PIPER_ALLOW_RESTRICTED") != "1" and any(r in name for r in RESTRICTED_VOICES):
        logging.getLogger("worker").warning(
            "Stimme %s hat eine eingeschränkte Datensatz-Lizenz – nutze stattdessen %s", name, SAFE_DEFAULT[lang])
        name = SAFE_DEFAULT[lang]
    return name


VOICES = {"en-GB": _voice("en-GB", "PIPER_VOICE_GB"), "en-US": _voice("en-US", "PIPER_VOICE_US")}
# In der App wählbare Stimmen – nur frei lizenzierte (Public Domain / CC0 / CC BY-SA), siehe THIRD_PARTY_NOTICES.md
VOICE_CHOICES = {
    "en_GB-cori-high": "en-GB", "en_GB-southern_english_female-low": "en-GB",
    "en_US-ljspeech-high": "en-US", "en_US-kristin-medium": "en-US", "en_US-bryce-medium": "en-US",
    "en_US-john-medium": "en-US", "en_US-norman-medium": "en-US",
}


def voice_model(st):
    """Gewählte Stimme aus den App-Einstellungen (nur aus der freien Liste), sonst Standard aus der .env."""
    voice = st.get("voice") or "en-GB"
    m = st.get("voiceModel")
    if m in VOICE_CHOICES and VOICE_CHOICES[m] == voice:
        return voice, m
    return voice, VOICES.get(voice, VOICES["en-GB"])
PIPER_SPEED = float(os.environ.get("PIPER_LENGTH_SCALE", "1.05"))
FAKE = os.environ.get("FAKE_AI") == "1"  # nur für Tests ohne Modelle

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")
for noisy in ("httpx", "huggingface_hub", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------- PocketBase
_AUTH_LOCK = threading.Lock()
_SHARED = {"token": None}


class PB:
    """Ein Admin-Token für alle Threads (PocketBase bremst zu viele Anmeldungen)."""

    def __init__(self):
        self.s = requests.Session()
        self.token = None

    def auth(self):
        old = self.token
        with _AUTH_LOCK:
            if _SHARED["token"] and _SHARED["token"] != old:  # ein anderer Thread hat schon neu angemeldet
                self.token = _SHARED["token"]
                self.s.headers["Authorization"] = self.token
                return
            while True:
                try:
                    r = self.s.post(f"{PB_URL}/api/collections/_superusers/auth-with-password",
                                    json={"identity": PB_EMAIL, "password": PB_PASSWORD}, timeout=20)
                    r.raise_for_status()
                    self.token = _SHARED["token"] = r.json()["token"]
                    self.s.headers["Authorization"] = self.token
                    return
                except Exception as e:  # PocketBase startet evtl. noch
                    log.warning("Anmeldung an PocketBase fehlgeschlagen (%s) – neuer Versuch in 10 s", e)
                    time.sleep(10)

    def check_auth(self):
        """Ungültige Anmeldung erkennen: PocketBase liefert dann still leere Listen statt eines Fehlers."""
        try:
            r = self.s.post(f"{PB_URL}/api/collections/_superusers/auth-refresh", timeout=20)
            if r.status_code in (401, 403, 404):
                log.warning("Admin-Anmeldung ungültig geworden – melde neu an")
                self.auth()
            elif r.ok:
                self.token = _SHARED["token"] = r.json()["token"]
                self.s.headers["Authorization"] = self.token
        except Exception as e:
            log.warning("Anmeldung konnte nicht geprüft werden: %s", e)
        self.checked = time.time()

    def req(self, method, path, **kw):
        if not self.token:
            self.auth()
        elif time.time() - getattr(self, "checked", 0) > 120:
            self.check_auth()
        kw.setdefault("timeout", 60)
        r = self.s.request(method, PB_URL + path, **kw)
        if r.status_code == 401:
            self.auth()
            r = self.s.request(method, PB_URL + path, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path}: {r.status_code} {r.text[:300]}")
        return r.json() if r.content and "json" in r.headers.get("content-type", "") else r

    def full_list(self, col, flt=None):
        out, page = [], 1
        while True:
            params = {"page": page, "perPage": 500}
            if flt:
                params["filter"] = flt
            d = self.req("GET", f"/api/collections/{col}/records", params=params)
            out += d["items"]
            if page >= d["totalPages"]:
                return out
            page += 1

    def download(self, col, rec, field, dest):
        tok = self.req("POST", "/api/files/token")["token"]
        r = self.s.get(f"{PB_URL}/api/files/{col}/{rec['id']}/{rec[field]}", params={"token": tok}, stream=True, timeout=300)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)


# ---------------------------------------------------------------- Text-Helfer
def tts_text(en):
    """Muss zur Funktion ttsText() in der App passen."""
    return re.sub(r"\s+", " ", re.sub(r"\(.*?\)", " ", en or "")).strip()


def norm_token(t):
    t = unicodedata.normalize("NFKC", t).lower().replace("’", "'")
    return re.sub(r"[^a-z0-9'äöüß%-]+", "", t).strip("-'")


def candidates(en):
    """Mögliche gesprochene Formen einer Vokabel, z. B. 'to found, to establish'."""
    base = re.sub(r"\(.*?\)", " ", en or "")
    forms = [base] + re.split(r"[,/;]| – ", base)
    out = []
    for f in forms:
        toks = [norm_token(x) for x in f.split()]
        toks = [t for t in toks if t]
        while len(toks) > 1 and toks[0] in ("to", "the", "a", "an"):
            toks = toks[1:]
        if toks and toks not in out:
            out.append(toks)
    return out


def _best_window(cand, toks):
    """Beste Fundstelle einer Wortfolge: (i, j, score) mit Token-Indizes i..j."""
    target = " ".join(cand)
    n = len(cand)
    need = 0.92 if len(target) <= 4 else 0.8
    best = None
    for size in ({n, n + 1} if n > 1 else {1}):
        for i in range(0, max(0, len(toks) - size + 1)):
            win = [t for t in toks[i:i + size] if t]
            if not win:
                continue
            score = SequenceMatcher(None, target, " ".join(win)).ratio()
            score += 0.02 * min(n, 3) - 0.03 * (size - n)
            if score >= need and (best is None or score > best[2] + 1e-9):
                best = (i, i + size - 1, score)
    return best


def clip_bounds(transcript, i, j):
    """Großzügiger Puffer um die Wörter i..j, ohne weit ins Nachbarwort zu ragen."""
    s, e = transcript[i]["s"], transcript[j]["e"]
    prev_e = transcript[i - 1]["e"] if i > 0 else 0.0
    next_s = transcript[j + 1]["s"] if j + 1 < len(transcript) else e + 2.0
    start = max(0.0, max(s - 0.3, min(s - 0.1, prev_e)))
    stop = min(e + 0.45, max(e + 0.2, next_s + 0.05))
    return round(start, 2), round(stop, 2)


def match_words(vocab, transcript):
    """vocab: [{id, en}], transcript: [{w, s, e, p}] -> {word_id: (start, end, score)}"""
    toks = [norm_token(t["w"]) for t in transcript]
    result = {}
    for v in vocab:
        cands = candidates(v["en"])
        full = _best_window(cands[0], toks) if cands else None
        alts = [b for b in (_best_window(c, toks) for c in cands[1:]) if b] if len(cands) > 2 else []
        pick = full
        if len(alts) >= 2:
            # mehrere Bedeutungen ("labour, work"): direkt hintereinander gesprochen -> alle in einen Clip
            alts.sort(key=lambda b: b[0])
            groups, cur = [], [alts[0]]
            for b in alts[1:]:
                if transcript[b[0]]["s"] - transcript[cur[-1][1]]["e"] <= 2.5:
                    cur.append(b)
                else:
                    groups.append(cur)
                    cur = [b]
            groups.append(cur)
            g = max(groups, key=lambda g: (len(g), sum(b[2] for b in g)))
            if len(g) >= 2 and (pick is None or g[-1][1] - g[0][0] + 1 >= pick[1] - pick[0] + 1):
                pick = (g[0][0], g[-1][1], sum(b[2] for b in g) / len(g))
        if pick is None and alts:
            pick = max(alts, key=lambda b: b[2])
        if pick:
            st, en = clip_bounds(transcript, pick[0], pick[1])
            result[v["id"]] = (st, en, pick[2])
    return result


# ---------------------------------------------------------------- Modelle
_whisper = None
_voices = {}
_lock = threading.Lock()


def whisper_model():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        log.info("Lade Whisper-Modell '%s' (beim ersten Mal wird es heruntergeladen) …", WHISPER_MODEL)
        _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8",
                                download_root=os.path.join(MODELS, "whisper"), cpu_threads=WHISPER_THREADS)
    return _whisper


def piper_voice(name):
    if name not in _voices:
        from piper import PiperVoice
        d = os.path.join(MODELS, "piper")
        os.makedirs(d, exist_ok=True)
        onnx = os.path.join(d, name + ".onnx")
        if not os.path.exists(onnx):
            lang, speaker, quality = name.split("-", 2)
            base = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang.split('_')[0]}/{lang}/{speaker}/{quality}/{name}"
            log.info("Lade Piper-Stimme %s …", name)
            for ext in (".onnx.json", ".onnx"):
                tmp = onnx.replace(".onnx", ext) + ".part"
                urllib.request.urlretrieve(base + ext, tmp)
                os.replace(tmp, onnx.replace(".onnx", ext))
        _voices[name] = PiperVoice.load(onnx)
    return _voices[name]


def synth_mp3(text, voice_name, out_mp3):
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "a.wav")
        if FAKE:
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=0.6", wav], check=True)
        else:
            v = piper_voice(voice_name)
            with wave.open(wav, "wb") as wf:
                try:  # piper-tts >= 1.3
                    from piper import SynthesisConfig
                    v.synthesize_wav(text, wf, syn_config=SynthesisConfig(length_scale=PIPER_SPEED))
                except ImportError:  # ältere piper-tts
                    v.synthesize(text, wf, length_scale=PIPER_SPEED)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-af",
                        "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse,adelay=60",
                        "-ac", "1", "-b:a", "64k", out_mp3], check=True)


def transcribe(path, prompt):
    if FAKE:
        fake = os.environ.get("FAKE_TRANSCRIPT")
        with open(fake) as f:
            return json.load(f), 60.0
    import numpy as np
    m = whisper_model()
    # WAV selbst einlesen (16 kHz mono) – umgeht die PyAV-Inkompatibilität von faster-whisper
    with wave.open(path, "rb") as wf:
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segs, info = m.transcribe(audio, word_timestamps=True, language=WHISPER_LANG, initial_prompt=prompt,
                              vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
                              condition_on_previous_text=False, beam_size=5)
    words = []
    for seg in segs:
        for w in seg.words or []:
            t = w.word.strip()
            if t:
                words.append({"w": t, "s": round(w.start, 2), "e": round(w.end, 2), "p": round(w.probability, 2)})
    return words, float(info.duration)


# ---------------------------------------------------------------- Lebenszeichen
TICKS = {}
BUSY = {}


def tick(name):
    TICKS[name] = time.time()


def watchdog():
    """Beendet den Prozess, wenn eine Schleife hängt – Docker startet ihn dann neu."""
    last_beat = 0
    while True:
        time.sleep(30)
        now = time.time()
        for name, t in list(TICKS.items()):
            if not BUSY.get(name) and now - t > 600:
                log.error("Schleife '%s' hängt seit %d s – Worker startet neu", name, now - t)
                os._exit(1)
        if now - last_beat > 1800:
            last_beat = now
            log.info("Lebenszeichen: Worker läuft (%s)", ", ".join(f"{k} vor {int(now - v)} s" for k, v in TICKS.items()))


# ---------------------------------------------------------------- Aufgaben
def settings(pb):
    items = pb.full_list("meta", "key='settings'")
    return (items[0].get("data") or {}) if items else {}


def tts_loop():
    pb = PB()
    samples_at = 0
    while True:
        tick("tts")
        if time.time() - samples_at > 3600:
            samples_at = time.time()
            try:
                ensure_samples(pb)
            except Exception as e:
                log.warning("Hörproben konnten nicht geladen werden: %s", e)
        try:
            BUSY["tts"] = True
            made = tts_pass(pb)
            BUSY["tts"] = False
            time.sleep(2 if made else 20)
        except Exception as e:
            BUSY["tts"] = False
            log.exception("TTS-Fehler: %s", e)
            time.sleep(30)


def ensure_samples(pb):
    """Hörproben der wählbaren Stimmen einmal vom Piper-Projekt holen und lokal in PocketBase ablegen."""
    have = {r["text"] for r in pb.full_list("tts", pb_filter_eq("voice", "sample"))}
    for name in VOICE_CHOICES:
        if name in have:
            continue
        with tempfile.TemporaryDirectory() as td:
            mp3 = os.path.join(td, "sample.mp3")
            if FAKE:
                synth_mp3("Hello", name, mp3)
            else:
                lang, speaker, quality = name.split("-", 2)
                url = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang.split('_')[0]}/{lang}/{speaker}/{quality}/samples/speaker_0.mp3"
                urllib.request.urlretrieve(url, mp3)
            with open(mp3, "rb") as f:
                pb.req("POST", "/api/collections/tts/records", data={"key": "sample-" + name, "text": name, "voice": "sample"},
                       files={"file": ("sample.mp3", f, "audio/mpeg")})
        log.info("Hörprobe für Stimme %s gespeichert", name)


def tts_pass(pb, limit=40):
    voice, model = voice_model(settings(pb))
    lessons = sorted(pb.full_list("lessons"), key=lambda l: (l.get("date") or "", l.get("order") or 0), reverse=True)
    texts = []
    for l in lessons:
        for w in l.get("words") or []:
            if w.get("kind") == "note":
                continue
            t = tts_text(w.get("en"))
            if t and t not in texts:
                texts.append(t)
    have = {r["key"]: r for r in pb.full_list("tts", pb_filter_eq("voice", voice))}
    wanted = {hashlib.sha1(f"{voice}|{model}|{t}".encode()).hexdigest()[:32]: t for t in texts}
    # veraltete Einträge (Wort geändert/gelöscht oder andere Stimme gewählt) aufräumen
    for k, r in have.items():
        if k not in wanted:
            pb.req("DELETE", f"/api/collections/tts/records/{r['id']}")
    made = 0
    for k, t in wanted.items():
        if k in have:
            continue
        with tempfile.TemporaryDirectory() as td:
            mp3 = os.path.join(td, "tts.mp3")
            with _lock:
                synth_mp3(t, model, mp3)
            with open(mp3, "rb") as f:
                pb.req("POST", "/api/collections/tts/records",
                       data={"key": k, "text": t, "voice": voice}, files={"file": ("tts.mp3", f, "audio/mpeg")})
        made += 1
        if made == 1 or made % 25 == 0:
            log.info("KI-Stimme (%s): %d neu erzeugt …", voice, made)
        if made >= limit:
            break
    return made


def pb_filter_eq(field, value):
    return f"{field}='{value}'"


def rec_loop():
    pb = PB()
    # nach einem Absturz liegengebliebene Aufträge neu starten
    for r in pb.full_list("recordings", "status='processing'"):
        pb.req("PATCH", f"/api/collections/recordings/records/{r['id']}", json={"status": "pending"})
    last_rematch = 0
    while True:
        tick("aufnahmen")
        try:
            if time.time() - last_rematch > 30:
                last_rematch = time.time()
                rematch(pb)
            pending = pb.full_list("recordings", "status='pending'")
            for r in pending:
                BUSY["aufnahmen"] = True
                try:
                    process_recording(pb, r)
                finally:
                    BUSY["aufnahmen"] = False
            time.sleep(5)
        except Exception as e:
            log.exception("Aufnahme-Schleife: %s", e)
            time.sleep(15)


def process_recording(pb, rec):
    rid = rec["id"]
    log.info("Verarbeite Aufnahme %s (%s) …", rid, rec.get("orig_name"))
    pb.req("PATCH", f"/api/collections/recordings/records/{rid}", json={"status": "processing", "error": ""})
    try:
        lesson = find_lesson(pb, rec["lesson_key"])
        vocab = [w for w in (lesson.get("words") or []) if w.get("en") and w.get("kind") != "note"] if lesson else []
        prompt = "Vocabulary: " + ", ".join(tts_text(w["en"]) for w in vocab)
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "in")
            pb.download("recordings", rec, "file", src)
            wav = os.path.join(td, "a.wav")
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-ac", "1", "-ar", "16000", wav], check=True)
            t0 = time.time()
            with _lock:
                words, duration = transcribe(wav, prompt[:800])
            log.info("Whisper fertig in %.0f s: %d Wörter erkannt", time.time() - t0, len(words))
        hits = match_words(vocab, words)
        matched = 0
        lesson = find_lesson(pb, rec["lesson_key"])  # frisch laden, falls inzwischen bearbeitet
        if lesson:
            changed = False
            for w in lesson.get("words") or []:
                h = hits.get(w.get("id"))
                if not h or w.get("noClip") or (w.get("clip") or {}).get("manual"):
                    continue
                s, e, score = h
                w["clip"] = {"rec": rid, "s": s, "e": e, "score": round(score, 2)}
                matched += 1
                changed = True
            if changed:
                pb.req("PATCH", f"/api/collections/lessons/records/{lesson['id']}", json={"words": lesson["words"]})
        pb.req("PATCH", f"/api/collections/recordings/records/{rid}",
               json={"status": "done", "transcript": words, "duration": duration, "matched": matched})
        log.info("Aufnahme %s: %d von %d Vokabeln zugeordnet", rid, matched, len(vocab))
    except Exception as e:
        log.exception("Aufnahme %s fehlgeschlagen", rid)
        pb.req("PATCH", f"/api/collections/recordings/records/{rid}", json={"status": "error", "error": str(e)[:1900]})


def attempt_loop():
    """Aussprache-Training: kurze Aufnahmen schnell transkribieren (ohne Hilfe-Prompt, damit es ehrlich bleibt)."""
    pb = PB()
    last_purge = 0
    if not FAKE:
        try:  # Modell vorladen, damit der erste Sprechversuch schnell geht
            BUSY["aussprache"] = True
            whisper_model()
        except Exception as e:
            log.warning("Whisper-Modell konnte nicht vorgeladen werden: %s", e)
        finally:
            BUSY["aussprache"] = False
    while True:
        tick("aussprache")
        try:
            for a in pb.full_list("attempts", "status='pending'"):
                BUSY["aussprache"] = True
                try:
                    heard = transcribe_attempt(pb, a)
                    pb.req("PATCH", f"/api/collections/attempts/records/{a['id']}", json={"status": "done", "heard": heard})
                except Exception as e:
                    log.exception("Aussprache-Versuch %s fehlgeschlagen", a["id"])
                    pb.req("PATCH", f"/api/collections/attempts/records/{a['id']}", json={"status": "error", "error": str(e)[:900]})
                finally:
                    BUSY["aussprache"] = False
            if time.time() - last_purge > 600:  # alte Versuche löschen (Speicher sparen)
                last_purge = time.time()
                cutoff = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - 3600))
                for a in pb.full_list("attempts", f"created < '{cutoff}'"):
                    pb.req("DELETE", f"/api/collections/attempts/records/{a['id']}")
            time.sleep(1)
        except Exception as e:
            log.exception("Aussprache-Schleife: %s", e)
            time.sleep(10)


def transcribe_attempt(pb, a):
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "in")
        pb.download("attempts", a, "file", src)
        wav = os.path.join(td, "a.wav")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-ac", "1", "-ar", "16000", wav], check=True)
        if FAKE:
            return os.environ.get("FAKE_HEARD", a.get("expected") or "")
        import numpy as np
        with wave.open(wav, "rb") as wf:
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        t0 = time.time()
        with _lock:
            segs, _ = whisper_model().transcribe(audio, language="en", beam_size=5, vad_filter=False,
                                                 condition_on_previous_text=False, without_timestamps=True)
            text = " ".join(s.text.strip() for s in segs).strip()
        log.info("Aussprache: erwartet '%s', gehört '%s' (%.1f s)", a.get("expected"), text, time.time() - t0)
        return text


def rematch(pb):
    """Wörter, die nach dem Hochladen der MP3 dazugekommen sind, im vorhandenen Transkript suchen (ohne Whisper)."""
    recs = [r for r in pb.full_list("recordings", "status='done'") if r.get("transcript")]
    by_lesson = {}
    for r in recs:
        by_lesson.setdefault(r["lesson_key"], []).append(r)
    if not by_lesson:
        return
    for lesson in pb.full_list("lessons"):
        rs = by_lesson.get(lesson.get("key"))
        if not rs:
            continue
        rec_ids = {r["id"] for r in rs}
        open_words = [w for w in (lesson.get("words") or [])
                      if w.get("en") and w.get("kind") != "note" and not w.get("noClip")
                      and not ((w.get("clip") or {}).get("rec") in rec_ids)]
        if not open_words:
            continue
        changed = 0
        for r in sorted(rs, key=lambda r: r.get("created") or "", reverse=True):
            hits = match_words([w for w in open_words if not w.get("clip") or w["clip"].get("rec") not in rec_ids], r["transcript"])
            for w in open_words:
                h = hits.get(w.get("id"))
                if h and not (w.get("clip") or {}).get("rec") in rec_ids:
                    w["clip"] = {"rec": r["id"], "s": h[0], "e": h[1], "score": round(h[2], 2)}
                    changed += 1
        if changed:
            fresh = find_lesson(pb, lesson["key"])  # frisch laden, nur Clips ergänzen
            if not fresh:
                continue
            new = {w["id"]: w["clip"] for w in open_words if (w.get("clip") or {}).get("rec") in rec_ids}
            n = 0
            for w in fresh.get("words") or []:
                if w.get("id") in new and not w.get("clip") and not w.get("noClip"):
                    w["clip"] = new[w["id"]]
                    n += 1
            if n:
                pb.req("PATCH", f"/api/collections/lessons/records/{fresh['id']}", json={"words": fresh["words"]})
                log.info("Stunde %s: %d neue Wörter in vorhandener Aufnahme gefunden", fresh.get("name"), n)


# ---------------------------------------------------------------- Tagesübersicht & Erinnerungen
APP_TZ = os.environ.get("APP_TZ", "Europe/Berlin")
DAY_MS = 86400000
INTERVALS = [0, 1, 3, 7, 14, 30, 60, 120]


def norm_en(s):
    s = str(s or "").lower().replace("’", "'").replace("‘", "'").replace("`", "'")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r'[.,!?;:"…]', " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"^(to|the|a|an) ", "", s)


def _tz(name):
    from zoneinfo import ZoneInfo
    try:
        return ZoneInfo(name or APP_TZ)
    except Exception:
        return ZoneInfo("Europe/Berlin")


def compute_summary(lessons, progress, meta, tz_name=None, now=None, prev_wod=None):
    """Spiegelt die Startseite der App: fällig, neu (Tageslimit), Serie, sicher, Wort des Tages."""
    from datetime import datetime, timedelta
    tz = _tz(tz_name)
    now = now or datetime.now(tz)
    now_ms = int(now.timestamp() * 1000)
    day0 = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    today = now.strftime("%Y-%m-%d")
    settings_ = meta.get("settings") or {}
    try:
        per_day = int(settings_.get("newPerDay", 10))
    except (TypeError, ValueError):
        per_day = 10
    # neueste Stunden zuerst (wie in der App)
    lessons = sorted(lessons, key=lambda l: (l.get("date") or "", l.get("order") or 0), reverse=True)
    # neue Wörter der beiden neuesten Stunden kommen immer dran (ohne Tageslimit)
    recent = {norm_en(w.get("en")) for l in lessons[:2] for w in (l.get("words") or []) if w.get("kind") != "note"}
    due = sure = total = 0
    new_keys, today_keys, pool = [], set(), []
    seen_new = set()
    for l in lessons:
        pw = (progress.get(l.get("key")) or {})
        for w in l.get("words") or []:
            if w.get("kind") == "note":
                continue
            total += 1
            p = pw.get(w.get("id")) or {}
            n = p.get("n") or 0
            k = norm_en(w.get("en"))
            if n and (p.get("d") or 0) <= now_ms:
                due += 1
            if n and (p.get("b") or 0) >= 4:
                sure += 1
            if not n and k not in seen_new:
                seen_new.add(k)
                new_keys.append(k)
            if p.get("f") and p["f"] >= day0 and k not in recent:
                today_keys.add(k)
            if len(tts_text(w.get("en")).split()) <= 4 and (p.get("b") or 0) < 4 and w.get("en") and w.get("de"):
                pool.append((l, w))
    recent_new = [k for k in new_keys if k in recent]
    older_new = [k for k in new_keys if k not in recent]
    quota = max(0, per_day - len(today_keys)) if per_day > 0 else len(older_new)
    new_today = len(recent_new) + min(len(older_new), quota)
    days = set((meta.get("stats") or {}).get("days") or [])
    practiced = today in days
    streak, d = 0, now.date()
    if not practiced:
        d -= timedelta(days=1)
    while d.strftime("%Y-%m-%d") in days:
        streak += 1
        d -= timedelta(days=1)
    wod = prev_wod if prev_wod and prev_wod.get("date") == today else None
    if not wod and pool:
        l, w = pool[int(hashlib.sha1(today.encode()).hexdigest(), 16) % len(pool)]
        wod = {"date": today, "en": w.get("en"), "de": w.get("de"), "ex": (w.get("ex") or "").replace("[", "").replace("]", ""),
               "lesson": l.get("name")}
    return {"date": today, "due": due, "new": new_today, "today": due + new_today, "streak": streak,
            "practicedToday": practiced, "sure": sure, "total": total, "wod": wod}


def load_state(pb):
    lessons = pb.full_list("lessons")
    progress = {r["key"]: (r.get("w") or {}) for r in pb.full_list("progress")}
    meta = {r["key"]: (r.get("data") or {}) for r in pb.full_list("meta")}
    ids = {r["key"]: r["id"] for r in pb.full_list("meta")}
    return lessons, progress, meta, ids


def save_meta(pb, ids, key, data):
    if key in ids:
        pb.req("PATCH", f"/api/collections/meta/records/{ids[key]}", json={"data": data})
    else:
        r = pb.req("POST", "/api/collections/meta/records", json={"key": key, "data": data})
        ids[key] = r["id"]


VAPID_FILE = os.path.join(MODELS, "vapid_private.pem")


def vapid_public():
    """VAPID-Schlüsselpaar für Web-Push: einmal erzeugen, im Modelle-Ordner aufheben."""
    from py_vapid import Vapid, b64urlencode
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    if os.path.exists(VAPID_FILE):
        v = Vapid.from_file(VAPID_FILE)
    else:
        os.makedirs(os.path.dirname(VAPID_FILE), exist_ok=True)
        v = Vapid()
        v.generate_keys()
        v.save_key(VAPID_FILE)
        log.info("Neue Schlüssel für Push-Mitteilungen erzeugt")
    return b64urlencode(v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))


def push_contact():
    c = os.environ.get("PUSH_CONTACT") or os.environ.get("APP_OPERATOR_CONTACT") or PB_EMAIL
    return c if c.startswith(("mailto:", "https://")) else "mailto:" + c


def send_push(sub, payload):
    """True = zugestellt, False = Abo ungültig (löschen), Exception = sonstiger Fehler."""
    from pywebpush import webpush, WebPushException
    try:
        webpush(subscription_info=sub, data=json.dumps(payload, ensure_ascii=False), vapid_private_key=VAPID_FILE,
                vapid_claims={"sub": push_contact()}, ttl=4 * 3600, timeout=20)
        return True
    except WebPushException as e:
        code = getattr(e.response, "status_code", None)
        if code in (404, 410):
            return False
        raise


def reminder_text(s, test=False):
    n = s["today"]
    if test:
        title = "Test: so sieht deine Erinnerung aus"
    elif s["streak"]:
        title = f"🔥 {s['streak']} {'Tag' if s['streak'] == 1 else 'Tage'} in Folge – mach weiter!"
    else:
        title = "Zeit für Englisch 📚"
    body = f"{n} {'Wort wartet' if n == 1 else 'Wörter warten'} auf dich." if n else "Heute ist nichts fällig – Zeit für ein paar neue Wörter?"
    if s.get("wod"):
        body += f"\nWort des Tages: {s['wod']['en']} = {s['wod']['de']}"
    return {"title": title, "body": body, "url": "/"}


def due_slots(times, last, now):
    """Erinnerungszeiten, die heute dran sind (bis 60 Min. nach der Uhrzeit, nur einmal pro Tag)."""
    out = []
    today = now.strftime("%Y-%m-%d")
    mins = now.hour * 60 + now.minute
    for t in times or []:
        try:
            h, m = (int(x) for x in str(t).split(":"))
        except ValueError:
            continue
        if 0 <= mins - (h * 60 + m) <= 60 and (last or {}).get(t) != today:
            out.append(t)
    return out


def push_pass(pb):
    from datetime import datetime
    lessons, progress, meta, ids = load_state(pb)
    pub = vapid_public()
    if (meta.get("push") or {}).get("publicKey") != pub:
        save_meta(pb, ids, "push", {"publicKey": pub})
    s = compute_summary(lessons, progress, meta, prev_wod=(meta.get("summary") or {}).get("wod"))
    old = dict(meta.get("summary") or {})
    old.pop("updated", None)
    if old != s:  # nur bei Änderung schreiben (jede Änderung erreicht die App live)
        save_meta(pb, ids, "summary", dict(s, updated=int(time.time() * 1000)))
    for sub in pb.full_list("push"):
        now = datetime.now(_tz(sub.get("tz")))
        st = compute_summary(lessons, progress, meta, sub.get("tz"), now, s.get("wod"))
        last = dict(sub.get("last") or {})
        msgs = []
        if sub.get("test"):
            msgs.append(reminder_text(st, test=True))
        for t in due_slots(sub.get("times"), last, now):
            last[t] = now.strftime("%Y-%m-%d")
            if not st["practicedToday"]:
                msgs.append(reminder_text(st))
        if not msgs and last == (sub.get("last") or {}):
            continue
        ok = True
        for m in msgs:
            ok = send_push(sub.get("sub"), m)
            log.info("Erinnerung %s: %s", "verschickt" if ok else "nicht zustellbar – Abo gelöscht", m["title"])
            if not ok:
                break
        if ok:
            pb.req("PATCH", f"/api/collections/push/records/{sub['id']}", json={"last": last, "test": False})
        else:
            pb.req("DELETE", f"/api/collections/push/records/{sub['id']}")


def push_loop():
    pb = PB()
    while True:
        tick("erinnerung")
        try:
            push_pass(pb)
        except Exception as e:
            log.exception("Fehler bei Tagesübersicht/Erinnerung: %s", e)
        time.sleep(int(os.environ.get("PUSH_INTERVAL", "30")))


def find_lesson(pb, key):
    items = pb.full_list("lessons", pb_filter_eq("key", key.replace("'", "")))
    return items[0] if items else None


if __name__ == "__main__":
    log.info("Worker startet (Whisper: %s, Stimmen: %s)%s", WHISPER_MODEL, VOICES, " [FAKE]" if FAKE else "")
    for name in ("tts", "aufnahmen", "aussprache", "erinnerung"):
        tick(name)
    threading.Thread(target=push_loop, daemon=True).start()
    threading.Thread(target=tts_loop, daemon=True).start()
    threading.Thread(target=attempt_loop, daemon=True).start()
    threading.Thread(target=watchdog, daemon=True).start()
    rec_loop()
