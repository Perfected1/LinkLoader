# LinkLoad

Paste a video link, preview it, pick a quality and download it. React + Bootstrap
frontend, Python/Flask backend, yt-dlp for metadata and downloads — shipped as a
web app and as an Android app (Capacitor).

## Features

- Link validation for YouTube, Facebook, X (Twitter), Instagram, TikTok, Twitch,
  Reddit, Vimeo and Dailymotion (watch, shorts, reel, status, share and
  short-link forms)
- Video preview card: title, channel, duration, thumbnail, platform
- Quality picker with one option per available resolution plus "Best available"
- Optional clipping: enter a start and end time to save just that section as its
  own MP4 (times accepted as seconds or `mm:ss`)
- AI clips: Gemini reads the video's subtitles and either suggests highlights or
  finds the moment you describe in plain English; one click fills the clip range
- Streamed downloads with a clean filename and automatic temp-file cleanup
- Clear, specific errors for private, age-restricted, removed or unsupported videos
- Android app: same UI in a native shell, with a server address field and files
  handed to the Android share sheet so they can be saved anywhere on the device

## Project layout

```
LinkLoad/
├── src/                    # React app
│   ├── App.jsx             # page shell, link form, flow state
│   ├── api.js              # API client + error normalisation
│   ├── config.js           # backend address (build-time default + per device)
│   ├── saveFile.js         # browser download / Android share-sheet save
│   └── components/
│       ├── VideoInfoCard.jsx
│       ├── QualitySelector.jsx
│       └── ServerSettings.jsx
├── capacitor.config.json   # Android shell config (appId, webDir)
├── vercel.json             # static deploy of dist/ on Vercel
├── android/                # generated native Android project
├── index.html
├── vite.config.js          # dev proxy: /api -> http://127.0.0.1:5000
└── backend/
    ├── app/
    │   ├── __init__.py     # app factory (serves dist/ when built)
    │   ├── main.py         # /api routes
    │   ├── validation.py   # URL validation
    │   ├── extractor.py    # yt-dlp metadata + download/clip helpers
    │   └── ai_clips.py     # subtitles -> transcript -> Gemini clip picks
    ├── tests/test_api.py
    ├── run.py              # dev server
    ├── wsgi.py             # production entrypoint
    └── requirements.txt
```

## Deploy the web app (Vercel)

The frontend is a plain static Vite build, so Vercel serves it as-is. `vercel.json`
already pins the framework, build command and output directory.

1. Push the repo to GitHub and import it at <https://vercel.com/new> — Vercel
   detects Vite and uses those settings.
2. Tell the app where its backend lives, whichever way suits you:
   - **Build-time (recommended):** set `VITE_API_BASE=https://your-backend.example.com`
     in *Settings → Environment Variables* for Production and Preview, then redeploy.
   - **At runtime:** leave it unset. A static host has no `/api` of its own, so the
     page probes that path on load, and when nothing answers it shows the server card
     instead of the link form. The address is saved in the browser, per visitor.
3. Local dry run: `npm run build && npx vite preview`.

### The Python backend cannot run on Vercel

Only the static UI goes there. `/api/download` streams MP4 files and a single request
stays open for minutes while yt-dlp and ffmpeg work, which serverless functions on
Vercel cannot do:

- function responses are capped at ~4.5 MB, so a normal video download fails,
- functions time out long before a download finishes,
- the runtime has no ffmpeg binary and the filesystem is ephemeral.

Keep the Flask app on something that holds a process open with a writable disk — a
container/VM host, a home server, or your own machine — and hand the frontend its
origin through `VITE_API_BASE`. Because the Vercel page is HTTPS, that origin must be
HTTPS too; browsers block an `http://` backend as mixed content. CORS is already
open for `/api/*` in `backend/app/__init__.py`, so no proxy is needed.

## Android app

The same React UI also runs as an Android app wrapped with [Capacitor](https://capacitorjs.com).
The device does the phone-side work and talks to a LinkLoad backend over HTTP, so
the Python side (yt-dlp, ffmpeg, Gemini) keeps running on a server, laptop or
NAS — no Python on the phone.

### Build it

You need [Android Studio](https://developer.android.com/studio) (which bundles a
JDK) and Android SDK Platform 36. Then:

```bash
npm install
npm run android:sync        # builds dist/ and copies it into android/
npm run android:open        # opens the project in Android Studio
```

In Android Studio press **Run** for a connected device or emulator, or
**Build > Build Bundle(s)/APK(s) > Build APK(s)**. The APK lands in
`android/app/build/outputs/apk/debug/app-debug.apk`.

Command line instead of Android Studio (needs `JAVA_HOME` and `ANDROID_HOME`):

```bash
npm run android:sync
cd android && ./gradlew assembleDebug
```

Run `npm run android:sync` after every frontend change; Capacitor copies `dist/`
into the app, so the APK does not read the web files from your dev server.

### Pointing the app at a server

On first launch the app asks for a **server address** (also reachable later via
the link at the top of the screen). Enter the origin of your backend, e.g.
`https://linkload.example.com` or, on the same Wi-Fi, `http://192.168.1.20:5000`.

- The backend must be reachable from the phone: start it on `0.0.0.0`
  (`gunicorn wsgi:app --bind 0.0.0.0:8000`) rather than `127.0.0.1`, and use the
  machine's LAN address.
- Addresses are saved in the WebView, so each device keeps its own.
- Plain `http://` is allowed on purpose (`network_security_config.xml`) so a
  local dev server works; prefer `https://` for anything public.
- Without an address the app shows the setup card instead of the link form.

### Downloads on Android

A browser-style download link does not work inside the WebView, so the app saves
the finished MP4 into its cache and opens the Android share sheet — pick **Files**,
**Downloads**, Drive, or send it straight on. The download itself is buffered in
memory before it is written, so very large videos are better handled by the web
build on a machine with more RAM.

## Setup

Requires Python 3.10+ and Node 18+. `ffmpeg` is optional: the backend falls back
to the static binary shipped with `imageio-ffmpeg`.

AI clips are optional too. Without a key the rest of the app works and the AI
panel reports that it is not configured. To enable it, create a Gemini API key
at <https://aistudio.google.com/apikey> and export it before starting the backend:

```bash
export GEMINI_API_KEY="your-key"
# optional, defaults to gemini-3.8-flash
export GEMINI_MODEL="gemini-3.8-flash"
```

AI clips need a video with subtitles; videos without captions get a clear
message instead of suggestions.

```bash
# backend
cd LinkLoad
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt

# frontend
npm install
```

## Development

Two terminals:

```bash
# terminal 1 — API on :5000
cd LinkLoad/backend
source ../venv/bin/activate
python run.py

# terminal 2 — UI on :5173 (proxies /api to :5000)
cd LinkLoad
npm run dev
```

Open http://localhost:5173.

## Production

```bash
npm run build                     # writes dist/
cd backend
source ../venv/bin/activate
gunicorn wsgi:app --bind 0.0.0.0:8000 --workers 2 --timeout 600
```

When `dist/` exists the Flask app serves the built UI at `/` alongside the API,
so a single process (and a single origin) is enough. The 600s timeout matters
because a download request stays open until yt-dlp finishes.

## API

All responses are JSON with `ok: true, data` or `ok: false, error {code, message}`.

| Method | Path           | Body                  | Result                                  |
| ------ | -------------- | --------------------- | --------------------------------------- |
| GET    | `/api/health`  | –                     | `{"status": "ok"}`                      |
| POST   | `/api/validate`| `{"url": "..."}`      | platform + normalised URL               |
| POST   | `/api/info`    | `{"url": "..."}`      | title, uploader, duration, thumbnail    |
| POST   | `/api/formats` | `{"url": "..."}`      | selectable qualities (one per height)   |
| POST   | `/api/ai/clips`| `{"url", "prompt"?, "duration"?}` | AI clip ranges (`start`, `end`, `title`, `reason`) |
| POST   | `/api/download`| `{"url", "height", "start", "end"}` | MP4 file stream (`height: "best"` ok; `start`/`end` in seconds, both omitted for the full video) |

## Tests

```bash
source venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
python -m pytest -q
```

Tests cover URL validation across platforms, quality de-duplication, response
shapes, invalid-quality and invalid-clip rejection, clip boundary parsing, a real
ffmpeg trim, subtitle (WebVTT) parsing, AI clip validation and the download
streaming/cleanup path. The network, yt-dlp and Gemini are stubbed, so they run
offline.

## Responsible use

LinkLoad downloads only content you own or have permission to save. It does not
bypass DRM, paywalls or access controls, and it cannot download private,
age-restricted or removed videos. Respect each platform's terms and applicable
copyright law.
