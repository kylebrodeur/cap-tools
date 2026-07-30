<!--
Draft only — NOT posted. Per docs/upstream-agent-brief.md: a human submits this.

Submission mechanics (verified 2026-07-30 against github.com/CapSoftware/Cap):
- GitHub Discussions are DISABLED on this repo (`has_discussions: false` via `gh api
  repos/CapSoftware/Cap`) — there is no Discussions tab to post an RFC to. The original
  plan (issue + separate Discussion) doesn't have a landing spot for the Discussion half.
- CONTRIBUTING.md's own text says: "Suggest a feature (via Discord)" — Cap's stated
  process routes feature discussion to Discord, not GitHub.
- In practice, feature requests DO also get filed as GitHub issues (e.g. #144,
  "[feature request] export as gif", closed) using a `[feature request] ...` title
  convention and the `enhancement` label — there's no dedicated issue template for
  this (only `bug_report.md` exists under .github/ISSUE_TEMPLATE/), so it's freeform.
- Recommended real submission path: post this ISSUE.md as a GitHub issue titled with
  the `[feature request]` convention, and separately share DISCUSSION.md's fuller
  detail in Cap's Discord (server invite in CONTRIBUTING.md) — link the Discord thread
  back into the issue once posted. Do not create a GitHub Discussion; the feature isn't
  enabled.
-->

**[feature request] `cap doc` — generate an illustrated step / SOP doc from a recording**

### Problem
Cap produces beautiful recordings and transcripts, but stops there. The
"turn a recording into a step-by-step guide / SOP document" layer is currently
owned by tools like Scribe, Tango, and Guidde — all cloud-hosted, browser-first,
and with lower-fidelity screenshots than Cap already captures. Cap users who want
a doc (onboarding, SOPs, support articles) export the video and rebuild steps by
hand elsewhere.

### Proposal
Add a `cap doc <project.cap>` subcommand that renders a self-contained,
illustrated step/SOP document (`index.html` + `index.md` + `images/`) from data
Cap already has — cursor clicks/moves, `timeline.zoomSegments`, and captions.

```
cap doc <project.cap> [--out <dir>] [--format html|md|both] [--ai <openai-url>] [--json]
```

- **Deterministic by default, fully local** — steps come from `zoomSegments`
  (the moments Cap already judged important) + click events; each step's
  screenshot is auto-framed on the cursor focus (the polish Cap's zoom already
  computes); captions come from the recording's transcript.
- **AI optional** — `--ai <openai-compatible-url>` runs a single "format pass"
  to clean caption text into step instructions. Off by default; works with local
  models. No change to Cap's privacy posture.
- Sits beside `cap export` (export → video; doc → SOP). Respects
  `maskSegments` (redaction). Same `--json`/NDJSON contract as `export`.

### Why now
Cap's CLI has grown substantially this year — `caps`, `organizations`, `library`,
`jobs`, `mcp serve`, and (2026-07-18) a full agent/MCP install flow
(`cap agents install --target codex|claude|cursor`, see `cap.so/docs/agents`).
`cap doc` would slot naturally into that same agent-facing surface — another
capability the bundled skill/MCP server can expose. Despite all that growth,
nothing in the current CLI (checked `apps/cli/src/*.rs`, 29 command modules as of
this writing) does recording → doc/SOP generation. The gap this issue describes
is still open.

### Note on naming
We originally drafted this as `cap guide`, then found `cap guide --json` already
exists as your agent capability-manifest command (`apps/cli/src/guide.rs`, added
2026-06-04). Renamed to `cap doc` to avoid the collision — happy to use whatever
name you'd prefer.

### Status
We have a working prototype (reads real `.cap` recordings end-to-end, a Python
reference implementation faithful to the proposed Rust design) and a port map to
a `crates/doc` crate + `apps/cli` subcommand (mirrors `crates/export` /
`apps/cli/src/export.rs`). **Happy to contribute a PR (AGPLv3) if this is welcome
upstream.** Demo doc attached: [link].

Would the maintainers be open to this? Any preferences on naming, crate boundary,
or the AI-provider abstraction before we open a PR?
