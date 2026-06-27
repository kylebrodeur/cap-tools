# Reference Scripts

Scripts gathered from source projects. These are **reference implementations**
— not meant to run directly from this repo, but to inform the refactored
extension. Each has a source annotation at the top.

Project-specific details (URLs, beat names, file paths) are annotated with
`# PROJECT-SPECIFIC` comments throughout.

## Index

| Script | Source | What it does |
|---|---|---|
| [record-beat.sh](./record-beat.sh) | an internal reference project | Start Cap, drive one named beat via Playwright, stop Cap |
| [record-studio.cjs](./record-studio.cjs) | an internal reference project | Node.js CDP driver — full Playwright beat orchestration |
| [export-beat.sh](./export-beat.sh) | an internal reference project | Export a `.cap` project to MP4 |
| [record-preflight.py](./record-preflight.py) | an internal reference project | Preflight gate checks (Python) |
| [assemble-video.py](./assemble-video.py) | an internal reference project | ffmpeg assembly — beats + VO + captions → final MP4 |
| [verify-cdp.py](./verify-cdp.py) | an internal reference project | Quick CDP connection verification screenshot |

## What's generic vs project-specific

### Generic (reusable as-is):
- Cap CLI detach spawn pattern (`capStartDetached`, temp file + sleep + parse)
- CDP connection with retry (HTTP fetch + hostname rewrite + `connectOverCDP`)
- `Browser.setWindowBounds` maximise via CDP session
- HF banner / overlay dismissal via JS injection
- `isRecording()` / `capJson()` JSON parsing with depth-tracking fallback
- ffmpeg concat assembly pipeline (`assemble-video.py`)
- Preflight gate structure (`record-preflight.py`)

### Project-specific (needs generalisation):
- `SPACE_URL` / target URL
- Beat names and `BEATS` registry (`beatLoad`, `beatSlice`, etc.)
- Specific selectors (`#ce-benchy`, `.ce-pills label`, etc.)
- Warm-up / model-load waits
- Window size `1707x1067` (screen resolution)
- Cap CLI binary path (`/mnt/c/Users/<your-windows-username>/AppData/Local/Cap/cap-cli.exe`)
- Gateway IP `172.25.144.1` (WSL default; should be discovered dynamically)
