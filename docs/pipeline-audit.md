# Pipeline Audit & Current State — 2026-06-14

A retrospective on the first full end-to-end run (an 18-minute narrated Cap
Studio recording → reviewed HTML/Markdown item breakdown), walking **backwards**
from the review to the capture, auditing what worked and what to improve. Ends
with an honest read of where we are and prioritized next steps.

> Source run: `Microfactory Node 3D Printer — 2026-06-14 02.50 AM` (18:22, 83
> clicks, 2,385-word narration). Deliverable:
> `spike/spike-output/an internal project-0250/walkthrough/{index.html,index.md,images/}`.

---

## The pipeline, end to end

```
Cap Studio .cap
  → transcribe_local.py   (faster-whisper small.en, CPU int8 — STAND-IN for WSL tool)
  → cap_ingest.py         (clicks → frames + steps.json; debounce; multi-seg timeline)
  → items.json            (analysis: 83 clicks + 228 segments → 54 items, hand-authored)
  → build_walkthrough_doc.py  (items.json + display.mp4 → index.html + index.md + images/)
  → two-agent review      (text accuracy ‖ screenshot/tab match) → fixes applied
```

---

## Backwards audit (review → capture)

### 6. Review stage — *highest leverage, worked well*
- **Worked:** Two agents in parallel (text-accuracy vs transcript; screenshot-vs-claim) caught two real defects I'd have shipped: an **undiscovered 4th "Print" tab** (the app is Studio/Build/Print/Review) and **4 wrong-tab frames**. The visual agent reading all 54 frames was the single highest-value check.
- **Weak:** Triggered manually and ad hoc; the text agent's timestamp findings overlapped the visual agent's; nothing *automatically* checks "is this frame on the tab the item claims?"
- **Improve:** (a) Add a cheap **tab detector** — crop the tab-bar strip of each frame, detect which tab is highlighted (the orange active state is trivially detectable), and flag mismatches *before* any agent runs. (b) Make review a first-class pipeline stage emitting structured findings, and **auto-apply low-risk fixes** (timestamp nudges). (c) Let the verifier propose corrected timestamps directly.

### 5. Document build (`build_walkthrough_doc.py`) — *solid, a few gaps*
- **Worked:** File-based named images (killed the 37 MB base64 problem → 42 KB HTML), CSS click-marker overlay from normalized cursor x/y, clean structured HTML, now Markdown too.
- **Weak:** Each frame is grabbed at a **single timestamp (t+0.3s)** — brittle near tab switches (the root cause of the 4 wrong-tab frames). Only a point marker, no **region** overlay. No table-of-contents / jump nav. No "decided vs open" status chips.
- **Improve:** (a) **Robust frame selection** — sample a few frames around `t` and pick the one whose tab matches the expected tab (and is sharpest/settled). (b) **Cursor-region rectangle overlay** (see Recommendation). (c) TOC + per-tab counts + anchor links. (d) status chips (Decision / Open / Resolved-contradiction).

### 4. Analysis (`items.json`) — *the core value, but hand-made*
- **Worked:** Collapsed 83 clicks + 228 transcript segments into **54 coherent, deduplicated items** grouped by tab, each with an actionable *Decision*, plus resolved *Contradictions* and surfaced *Open Questions* — exactly the requested breakdown.
- **Weak:** **Hand-authored by the model in-context** — not reproducible or automatable, and effort-bound. Timestamps were eyeballed (review caught `review-02` etc.). Tab assignment was inferred from narration cues, which **missed the Print tab**. Item boundaries are judgment calls.
- **Improve:** (a) Drive this with the **automated "format pass"** (the OpenAI-compatible structuring step already in the architecture) over transcript+steps, producing `items.json` programmatically → then agent review. Reproducible. (b) Derive each item's timestamp from the **transcript segment that states it**, not eyeballing. (c) Assign tabs from **frame detection**, not narration. (d) Cross-link each item to its transcript segment id(s) for traceability.

### 3. Ingest (`cap_ingest.py`) — *good mechanics, click-centric*
- **Worked:** Clicks→frames, debounce (83→74), global multi-segment timeline via per-segment `ffprobe`, normalized-xy marker, `steps.json`, end-of-segment seek clamp.
- **Weak:** **Click-only frames miss narration-only feedback** — and most items here were narrated *without* a click. Debounce is a simple time+distance heuristic. Cursor **moves**, cursor **shape**, and **keyboard** streams are unused. Fixed +0.5s offset. No tab awareness.
- **Improve:** (a) Use **cursor dwell/region** for narration items (rectangle overlay). (b) Use **cursor-shape changes** (pointer/hand/ibeam) to classify hovering vs editing. (c) Adaptive offset. (d) Emit a tab label per step (frame detection).

### 2. Transcription (`transcribe_local.py`) — *unblocked us, but a stand-in*
- **Worked:** Local faster-whisper `small.en` int8 + VAD produced 228 word-level segments with good accuracy on technical content (even got "LoRA", "QAT"); unblocked the whole run **without** the WSL endpoint.
- **Weak:** CPU stand-in (slow-ish), small model, **no domain vocabulary**, and **not the user's WSL tool** (the intended backend). Cap's own GPU Parakeet engine errored / is manual.
- **Improve:** (a) **Wire the WSL transcription endpoint** — the one remaining concrete integration gap. (b) Pass a domain `initial_prompt`/vocabulary (Studio/Build/Print/Review, Benchy, LoRA, QAT, "La Forge", Inspector grade) to cut errors. (c) Larger model on the RTX 5080 if quality demands. (d) Use Cap `captions.json` when it's produced.

### 1. Capture (Cap) — *the format is right; discipline is the lever*
- **Worked:** Studio mode delivered exactly what we need — high-q `display.mp4`, a **clean isolated mic track** (Opus 48 k), cursor clicks+moves, keyboard, all as documented JSON.
- **Weak:** Cap's local transcription **errored** (Parakeet/whisper-rs, manual trigger, transcribes from the audio stream so it fails on no-audio recordings); tab switches **aren't narrated**, so tab structure must be inferred; recording quality of *guidance* (how the user narrates/points) is the real lever on output quality.
- **Improve:** (a) Light **capture guidance**: say the tab name on switch; pause and **point at the region** being discussed (this makes the rectangle overlay reliable). (b) Prefer recordings **with mic**. (c) Just always use our transcription rather than fighting Cap's. (d) Treat cursor-as-pointer as a designed capture-time signal.

### Cross-cutting themes
1. **Frame-derived awareness (tab + pointed region) is the biggest untapped lever** — it would have auto-prevented *both* review findings.
2. **The analysis should be the automated format pass**, not hand-authoring — for reproducibility.
3. **One concrete integration gap remains: the WSL transcription endpoint.**

---

## Recommendation: cursor-region rectangle overlay (answering the open question)

**Yes — worth building, with confidence-gating.** It directly fixes the audit's
biggest functional gap: narration-only items (most of them) have no meaningful
click marker, but the user *gestures with the cursor* while saying "this section
here / this whole block." Cursor dwell during the narration window is the
strongest "what am I pointing at" signal we have.

**Approach:**
1. For each item, gather cursor `moves` within the item's narration window (the
   transcript segment span, or `[t-3s, t+2s]`).
2. **Weight by dwell** — slow/stationary samples are deliberate pointing; fast
   transit isn't. Cluster the dwell-weighted points.
3. Bounding box of the **dominant dwell cluster**, padded → draw a rectangle
   overlay (same CSS-percentage technique as the dot, since x/y are normalized).
4. **Confidence-gate:** only draw the rectangle if the cluster is tight enough
   (e.g. < ~45% of the screen) and has enough dwell; otherwise fall back to the
   point marker, or nothing.

**Tradeoffs / why gate it:** the cursor isn't always a deliberate pointer
(sometimes parked); naive bounding boxes can swallow the whole screen. So ship
it **opt-in/experimental with a dot fallback**, and visually evaluate on this
recording before trusting it. **Bonus signal:** Cap records cursor *shape*
(hand/ibeam/pointer) — a "hand" cursor means hovering a clickable element, a
strong element-level cue we can layer in later.

---

## Where we are (opinion)

**The spike's core question is answered — yes.** Consuming a Cap Studio
recording and turning it into a transcript + clicks + frames → an analyzed,
illustrated, reviewed document **works on real, messy, 18-minute data.** The
architecture is coherent and now validated: consume Cap (don't rebuild the
recorder), CLI/MCP add-on, HTML+Markdown output, a single format-pass (not
chat), local/WSL inference behind one OpenAI-compatible URL.

What remains is **integration and quality polish, not feasibility:**
- the analysis is still hand-authored (should be the automated format pass),
- transcription is a local stand-in (should be the WSL tool),
- frames lack tab/region awareness (rectangle overlay + tab detection),
- it isn't yet packaged as a CLI/MCP tool.

We are, realistically, at **"validated prototype"** — the hard unknowns are
resolved; the path to a usable tool is now mostly engineering.

## Next steps (prioritized)

1. **Decide the 3 open questions** (single-print vs iterations; second-opinion button vs tab; outcome/logging clarity) — finishes the Microfactory doc as a real spec.
2. **Build the cursor-region rectangle overlay** (above) — biggest single output-quality win; validate visually on this recording.
3. **Automate the analysis as the format pass** — transcript+steps → `items.json` via the OpenAI-compatible endpoint; keep the two-agent review. Makes it reproducible.
4. **Wire the WSL transcription endpoint** + domain vocabulary; retire the faster-whisper stand-in.
5. **Frame-based tab detection** — auto-assign tabs and flag wrong-tab frames (kills two whole classes of the bugs we hit).
6. **Productize:** `cap-guide` CLI + MCP tools (`list_recordings`, `ingest`, `get_steps`, `render_guide`) on `mcp_server.py`; optional recordings-folder watcher.
