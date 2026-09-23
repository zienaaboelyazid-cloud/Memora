# MEMORA — Real Website Front-End for the Python Project

**Theme:** dark neon / cyberpunk (glass cards, neon pink/violet/cyan glow,
Syne + Space Grotesk fonts) with a full landing page. `bg.jpg` is now the
fixed glassy background behind every screen (change `--bg-opacity-landing` (first screen, 0.8) and `--bg-opacity` (every other screen, 0.3) at the top of `style.css` to make it more or less visible; `hero.jpg` is no longer used) before the Patient / Caregiver role picker.

3 files:
- `index.html` — markup
- `style.css` — all styling
- `script.js` — all app logic (talks to the real backend below)

This is now a **real front-end**, not a browser-only demo: it talks over
HTTP to `api_server.py` (a small Flask API you add to your Python
project), which uses your ACTUAL `database/`, `recognition/`, and
`ai/assistant.py` code — the same SQLite database, the same InsightFace
face recognition, the same local Ollama model as the terminal app.

## Setup (one time)

1. Copy `api_server.py` into your `code elzehimer` project folder (next
   to `main.py`) — it's included in the Python project zip you already
   have. It needs the same dependencies your terminal app already uses
   (`opencv-python`, `insightface`, `ollama`, plus `flask`).
2. In that project folder, install Flask if you don't have it:
   ```
   pip install flask
   ```

## Running it

1. **Start the backend** — in the `code elzehimer` folder:
   ```
   python api_server.py
   ```
   Leave this terminal window open. You should see:
   ```
   MEMORA API running on http://127.0.0.1:5000
   ```
2. **Start the website** — open this folder in VS Code, install the
   **Live Server** extension (by Ritwick Dey) if you don't have it, then
   right-click `index.html` → **Open with Live Server**.
   (Don't just double-click `index.html` — browsers block camera access
   on `file://` pages. Live Server serves it over `http://localhost`.)

If the two are running on different machines/ports, edit the line near
the top of `index.html`:
```html
<script>window.MEMORA_API_BASE = 'http://127.0.0.1:5000/api';</script>
```

## What's real now vs. still simplified

| Feature | Status |
|---|---|
| Accounts, family, schedule, safe zone | **Real** — saved in your actual `data/memora.db` SQLite file |
| Face registration & recognition | **Real** — runs your actual InsightFace pipeline on the server |
| AI Assistant chat | **Real** — calls your actual `Assistant` class → your local Ollama model |
| Text-to-speech / speech-to-text | **Real** — the browser's own Web Speech API |
| Map & Safe Zone | **Real map** (Leaflet + Esri dark tiles — free, no API key; CARTO's tiles now need one), real lat/lng, saved to the real database. The green "You" marker is a draggable stand-in for GPS (browsers can't fake your real location) — use "Move 'You' to my real GPS" to place it at your actual location, or "Check using server's own GPS" to use the server machine's real GPS (Windows + `winsdk`), exactly like the terminal app's live monitor |
| Caregiver / Admin login | Static account, checked by the server: `NanZy@memora.NZ` / `NanZy` |

## Notes

- The Flask server loads the face-recognition model once at startup —
  the first request or two may be slow while it "warms up".
- If the red banner at the top says it can't reach the server, make
  sure `api_server.py` is still running and that `MEMORA_API_BASE`
  matches its address.
- CORS is wide open (`Access-Control-Allow-Origin: *`) for local
  development convenience — tighten this before exposing the server
  beyond your own machine.

## Latest changes

- **Landing nav underline** - the underline under Home / Features / How It Works / Safety / Contact now follows
  the link you click and the section you scroll to (it used to stay stuck on "Home").
- **Patient photo** - asked right after sign-up, and at login for any account that has no photo yet. The face
  is checked with InsightFace, saved to `data/people/`, stored as the patient's photo, and registered as
  "Patient (self)" (same as the terminal app). The photo shows in the dashboard top bar.
- **AI Assistant knows the patient** - name, age, date of birth, national ID, every family member with their
  relationship ("Who is Sara?" -> "Sara is your sister"), the date/time, and today's schedule.
- **Schedule refreshes every 24 hours** - `SCHEDULE_REFRESH_HOURS` in `config.py`. Login only asks "what's your
  schedule today?" when it's missing or 24h old, the open dashboard asks again once it turns 24h old, and the
  assistant stops presenting an expired schedule as today's. "My data" has an "Update today's schedule" button.
- **Camera tab** - an unknown face now has an "Add them now" button that opens the name + relationship form.
