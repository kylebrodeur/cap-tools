# Cap Recording Processing Log

Generated: 2026-06-14

## Recordings processed

| Recording | Status | Steps | Output location |
|-----------|--------|-------|-----------------|
| `0ceb703ee260.cap` | ✅ Processed | 8 | `spike/spike-output/cap/0ceb703ee260/guide.html` |
| `4dd6c24287ff.cap` | ✅ Processed | 13 | `spike/spike-output/cap/4dd6c24287ff/guide.html` |
| `1fd8ca9a8df3.cap` | 🗑 Removed | 0 | N/A — empty cursor.json (no clicks/moves) |
| `9339207681a0.cap` | ⏸ Left as-is | — | In-progress Cap recording; video still fragmented into `.m4s` segments |

## Tool used

```bash
uv run --no-project python spike/cap_ingest.py <path-to-recording.cap> --out spike/spike-output/cap
```

Both successful recordings produced:

- `guide.html` — illustrated step guide with click-marker overlays
- `steps.json` — structured step data
- `frames/step_NN_s<timestamp>.jpg` — extracted screenshots

## Notes

- No transcripts were generated. Transcripts / voice-over will be added later when narration is recorded.
- Output artifacts are gitignored (`spike/spike-output/`) because they contain screen recordings and client screen content.
