# Productization Plans (Draft)

> Draft strategy for turning the guide-tool spike into a product. Pairs with
> [ROADMAP.md](ROADMAP.md) (engineering backlog) and [DECISIONS.md](DECISIONS.md).
> Status: exploratory — for discussion, not committed.
>
> **Tightened recommendation:** build the deterministic guide generator as
> **`cap guide`** and **contribute it upstream to Cap**; keep our deep "review
> analysis" as a companion on top. Full design in
> [CAP-UPSTREAM-PROPOSAL.md](CAP-UPSTREAM-PROPOSAL.md).

## Thesis

We are **not** building "another Scribe." We turn a **narrated screen recording
of any desktop app** into a **structured, analyzed, illustrated SOP / feedback
doc** — **locally and privately** — by riding on **Cap's** best-in-class
open-source capture. The wedge no incumbent combines:

1. **Desktop-grade capture** (any app, high quality) — not browser-only screenshots.
2. **Deep AI analysis** — narration → an *analyzed* breakdown (titles, decisions,
   contradictions resolved, open questions, tab-aware grouping), not just "Click X."
3. **Privacy / local-first** — transcription + vision run on your hardware.
4. **Agent-native / dev-friendly** — CLI + MCP; the `.cap` dir + `items.json` are a contract.

## Landscape (researched June 2026)

| Tool | Category | Capture | Output | AI depth | Platform | Price | Gap vs us |
|---|---|---|---|---|---|---|---|
| **Scribe** | Click→step guide | Browser ext + desktop (Pro) | Screenshots + text steps | Shallow ("click X") | Cloud | Free / ~$23/u/mo | Browser-centric, raw screenshots, no spoken-walkthrough analysis |
| **Tango** | Click→step guide + in-app guidance | Browser/desktop | Step guides, reminders | Shallow | Cloud | ~$22/u/mo | Adoption-focused; same capture limits |
| **Guidde** | AI video docs | Browser ext | AI-voiceover video + guide + PDF | Medium (auto steps + voiceover) | Cloud | Free / $23–50/creator | Browser-centric, cloud, step text is descriptive not analytical |
| **Supademo / Arcade** | Interactive demos | Browser ext | Clickable HTML demos | Medium (auto annotations) | Cloud | ~$38/mo (AI) | Sales/marketing demos, not SOPs; browser |
| **iorad** | Interactive tutorials | Browser | Tutorials + **SCORM/LMS** | Low | Cloud | — | Deep LMS export, dated UX, browser |
| **Whatfix / Whale / Waybook / Trainual** | Process/knowledge **systems** | Mixed | Managed SOP libraries | Medium | Cloud | Enterprise | Heavy systems; weak on capture quality/depth |
| **Screen Studio / Rekort** | Polished recording + **auto-zoom-on-click** | Desktop (Mac) | Beautiful videos | None (no doc gen) | Desktop | $29/mo or $229 once | Recordings only; no structured doc / analysis |
| **Cap** (we build on it) | OSS Loom alt | **Any desktop app, high-q Studio** + cursor/zoom | Video + transcript/chapters; self-host/own-data | Young | Cross-platform, OSS | Free + paid | Stated: *not* a doc/SOP generator; young AI |

**Trends:** (1) teams migrate from one-off **capture** tools to **process systems**;
(2) AI voiceover + auto-steps are now table stakes; (3) **auto-zoom-on-click** is the
polish bar (Screen Studio set it); (4) **every incumbent is cloud SaaS and
browser-first.** Notably, Guidde already publishes a *"Scribe vs Cap"* comparison —
Cap is already treated as a competitor in this category.

## Our differentiation (the moat)
- **Any desktop app, high image quality** (Cap Studio) vs browser screenshots.
- **Analytical output** — we documented a *spoken UX review* into decisions /
  contradictions / open questions (the Microfactory run). No incumbent does
  "narrated walkthrough → structured analysis."
- **Local / private** — nothing leaves the machine (WSL transcription + Ollama
  vision). Decisive for regulated/internal SOPs that can't go to cloud SaaS.
- **Agent-native** — CLI + MCP; an agent can ingest, edit `items.json`, re-render.
- **Cursor-region overlays + Cap auto-zoom focus** — show exactly what's described.
- **Open + self-hostable** foundation; you own the data.

## Leveraging Cap's auto-zoom for SOPs
Confirmed in the `.cap` `project-config.json`: `timeline.zoomSegments` (44 in the
sample), each `{start, end, amount, mode:"auto", …}` — Cap has **already segmented
the recording into the moments it judged important**, with a zoom amount
(≈ importance). Also available: `annotations`, `maskSegments` (redaction!),
`textSegments`, `captionSegments`, `keyboardSegments`.

**Leverage:**
- Use `zoomSegments` (mode `auto`) as **candidate SOP step boundaries / "important
  moments"** — a strong signal complementing clicks and cursor dwell.
- The cursor position during each zoom segment gives the **focal region** → render
  **auto-framed/zoomed SOP screenshots** (the Screen Studio polish bar, applied to
  SOP docs) and corroborate our cursor-dwell rectangle.
- Respect `maskSegments` as redaction zones; reuse `annotations`/`textSegments`.
- Net: "Cap decides what to zoom on; we turn those focus moments into clean,
  framed, annotated SOP steps." This is the concrete payoff of building on Cap.

**Cap ships a CLI + agent skill — the clean integration surface (verified).** The
desktop app bundles a `cap` CLI (`~/.cap/bin`, shared binary):
`cap record`, `cap export <.cap> -o out.mp4` (renders **with auto-zoom applied,
headless** — NDJSON progress + `Completed` event; proven on a real recording),
`cap project validate`, `cap screenshot`, `cap targets`, and `cap guide --json`
(machine-readable capability manifest). There's even a ready-made
`skill/cap/SKILL.md` for Claude/Agent SDK. **Implications:** (1) the manual
"Studio → enable zoom → export" step is replaced by one command; (2) our companion
can drive Cap end-to-end programmatically (`record → [our pipeline] → export`); (3)
Cap explicitly supports headless/agent use — which de-risks **option B** (work
*with* Cap) and reinforces the agent-native positioning. Two ways to get
auto-zoomed visuals: **(a)** read `zoomSegments` + cursor and crop our own frames
(fast, no full render, we keep coordinates), or **(b)** `cap export` the polished
zoomed video and pull frames from it (most faithful to Cap's look; full render).

## Leveraging Cap (open source) — strategy
**License reality:** Cap core is **AGPLv3** (only `cap-camera*` / `scap-*` crates are
MIT). Implications:
- A **closed-source commercial fork** is not viable (AGPL copyleft, incl. network use).
- **Our companion tool reads `.cap` *output files*** — it does not link or distribute
  Cap's code, so it's an independent work we can license freely. ✅
- **Upstream contributions** to Cap would be AGPL (fine, and the goodwill play).

**Options (increasing integration):**
- **A. Companion / add-on (now):** separate CLI+MCP tool that consumes `.cap`
  recordings. "Works with Cap," full attribution. Fast, clean, license-safe. ← current
- **B. Contribute upstream:** open an RFC/issue with CapSoftware proposing a
  "Guide/SOP export" or a post-recording hook/plugin API; offer a PR. Credit them; if
  accepted, our capability ships *inside* Cap → instant distribution to Cap's users.
  (Your instinct: "give credit, maybe they'll integrate it.")
- **C. Fork (fallback):** maintain an AGPL fork with the pipeline embedded — only if
  upstream declines and deep integration is required; must stay AGPL/open.
- **D. Partnership/sponsorship:** Cap is a funded OSS startup; SOP/enterprise-doc is
  adjacent to their roadmap — propose collaboration.

**Recommended:** **A now**, open a **B** conversation in parallel (RFC + offer to
contribute), keep **C** as fallback. Respects OSS norms and could win distribution.

## Productization options (business shapes)
1. **OSS tool, local-first** — release the pipeline open-source (credits Cap), free,
   private; grow community; monetize later via hosted/team features. Matches Cap's ethos.
2. **"Works-with-Cap" companion app** (Tauri) — packaged add-on that watches Cap
   recordings → guides; freemium (local free; cloud sync / team / export paid).
3. **Internal tool + services edge** — use it for UofD ops/SOPs now, and as a
   differentiator in client SOP/doc work. Immediate ROI, no GTM needed.
4. **Upstream feature in Cap** — not a standalone business, but distribution + goodwill.
5. **Privacy-first SaaS (later)** — hosted for teams who won't run local; competes with
   Scribe/Guidde but leads with desktop + depth + privacy.

## Positioning (draft)
> "Turn a narrated screen recording into a structured, illustrated SOP —
> privately, on your own machine, for any desktop app. Built on Cap."

## Target wedge
- **Internal ops/SOP teams** documenting desktop LMS/admin workflows (our own use case).
- **Product/eng teams** capturing spoken UX reviews → structured feedback (Microfactory).
- **Regulated/enterprise** teams that can't send recordings to cloud SaaS.
- **AI/agent builders** wanting a programmatic guide generator.

## Pricing thoughts (if productized)
- Local/OSS core: **free**.
- Team/hosted: market band is **~$20–50/user/mo** (Scribe/Tango/Guidde) — lead with
  privacy + desktop + analytical depth, not price.
- Or **one-time desktop license** for the companion (Screen Studio model, ~$129–229).

## Risks / open questions
- **Cap's appetite** to integrate/partner (B/D) — unknown until we ask.
- **Local-first adoption friction** — non-technical users need a one-click installer
  with bundled sidecars (see DECISIONS D3: Ollama + CTranslate2, not a frozen monolith).
- **Incumbents are fast/cheap for simple browser flows** — don't fight there; win on
  desktop + depth + privacy.
- **"Capture → process system" pull** — do we stop at doc generation or grow into a
  knowledge system? (scope decision)
- **AGPL boundaries** — keep the companion a clean consumer of `.cap` files.

## Recommended path (phased)
- **Phase 1 (now):** ship the companion **CLI + MCP add-on**, "Works with Cap,"
  local-first; dogfood on UofD SOPs.
- **Phase 2:** packaged desktop companion (Tauri) + **Cap auto-zoom (`zoomSegments`)
  integration** for auto-framed SOP screenshots; open the **upstream RFC/issue** with
  CapSoftware (credit + offer to contribute).
- **Phase 3:** optional **privacy-first hosted/team** tier and/or upstream feature;
  evaluate process-system features (assign/track/maintain SOPs).

---

### Sources
- [Scribe — pricing/features (GetApp)](https://www.getapp.com/operations-management-software/a/scribe/) · [Scribe alternatives (scribe.com)](https://scribe.com/library/scribe-alternatives-competitors)
- [Guidde — review/pricing (Research.com)](https://research.com/software/reviews/guidde-review) · [Guidde "Scribe vs Cap" comparison](https://www.guidde.com/tool-comparison/scribe-vs-cap-pricing-comparison-2026)
- [Tango — Scribe alternatives](https://www.tango.ai/blog/scribe-alternatives) · [Scribe alternatives for SOPs (Waybook)](https://www.waybook.com/blog/scribe-alternatives-the-best-tools-for-process-documentation)
- [Interactive demo tools — Supademo vs Arcade](https://supademo.com/compare/arcade-alternative) · [Best interactive demo software (Arcade)](https://www.arcade.software/post/best-interactive-demo-software-2026)
- [Cap features](https://cap.so/features) · [Cap Studio Mode](https://cap.so/features/studio-mode) · [Auto-zoom on click (Rekort)](https://rekort.app/blog/screen-recording-with-zoom-effect) · [Screen Studio](https://screen.studio/)
- Cap license: AGPLv3 core (MIT for `cap-camera*`/`scap-*`) — from the Cap repo `LICENSE`.
