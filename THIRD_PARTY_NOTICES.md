# Drittanbieter-Software und Lizenzen

Der Code des Vokabeltrainers selbst steht unter der MIT-Lizenz (siehe `LICENSE`). Fremde Bestandteile behalten ihre eigenen Lizenzen:

## An den Browser ausgeliefert (`pocketbase/pb_public`)

| Bestandteil | Version | Lizenz | Lizenztext |
|---|---|---|---|
| PocketBase JS SDK – © 2022 – present, Gani Georgiev | 0.28.1 | MIT | `pb_public/legal/LICENSE-pocketbase-js-sdk.txt` |
| SheetJS Community Edition (`@e965/xlsx`) – © 2013 – present, SheetJS LLC | 0.20.3 | Apache-2.0 | `pb_public/legal/LICENSE-sheetjs-apache-2.0.txt` |
| Atkinson Hyperlegible (Fontsource, Subset latin) – © 2020 Braille Institute of America | 5.3.0 | SIL OFL 1.1 | `pb_public/legal/OFL-AtkinsonHyperlegible.txt` |
| Fraunces Variable (Fontsource, Subset latin) – © 2020 The Fraunces Project Authors | 5.3.0 | SIL OFL 1.1 | `pb_public/legal/OFL-Fraunces.txt` |

Beide Dateien sind unverändert. Das SDK hat nur einen Lizenz-Kopfkommentar erhalten.

## Nur auf dem Server (wird nicht weitergegeben)

| Bestandteil | Lizenz |
|---|---|
| PocketBase 0.40.6 | MIT |
| faster-whisper, CTranslate2 | MIT |
| Whisper-Modelle (OpenAI, CTranslate2-Konvertierung von SYSTRAN) | MIT |
| piper-tts 1.8.0 (OHF-Voice/piper1-gpl) inkl. eSpeak NG | GPL-3.0-or-later |
| onnxruntime | MIT |
| requests | Apache-2.0 |
| NumPy | BSD-3-Clause |
| pywebpush 2.0.3, py-vapid (Push-Erinnerungen) | MPL-2.0 |
| http-ece | MIT |
| cryptography | Apache-2.0 oder BSD-3-Clause |
| aiohttp | Apache-2.0 |
| tzdata | Apache-2.0 |
| FFmpeg (Debian-Paket) | LGPL-2.1+/GPL-2+ |

Piper ist GPL-lizenziert. Es läuft unverändert im Worker-Container, und die App liefert nur die erzeugten MP3-Dateien aus, also keine Weitergabe der Software. Wer das **Docker-Image selbst weitergibt**, muss die GPL-Pflichten erfüllen: Quellcode-Hinweis <https://github.com/OHF-Voice/piper1-gpl>.

## Stimmen (Piper)

| Stimme | Datensatz | Lizenz |
|---|---|---|
| en_GB-cori-high | LibriVox | gemeinfrei |
| en_US-ljspeech-high | LJ Speech Dataset | gemeinfrei |

Stimmen auf Basis des Blizzard-2013-Lessac-Datensatzes (`en_US-lessac-*`) sind nur für Forschung bzw. nicht-kommerziell lizenziert. Der Worker ersetzt sie deshalb automatisch, außer `PIPER_ALLOW_RESTRICTED=1` ist gesetzt.
