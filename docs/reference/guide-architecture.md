# Guide Tool — Architecture

> **Note (June 2026):** This document predates the decision to build on Cap (see
> [DECISIONS.md](DECISIONS.md) D6). It assumes ffmpeg frame extraction as the
> primary path, a screenpipe-style native capture layer, a Tauri GUI, and UACS.
> Those remain useful context, but where they conflict with the current
> direction, [README.md](README.md) and [DECISIONS.md](DECISIONS.md) are
> authoritative.

## The Layered Build-Out

The goal is a tool where the AI is invisible — you interact with a clean project interface and
guides come out the other side. But you get there in layers, each one working before building the next.

```
Layer 3 (future):  ┌─────────────────────────────────────┐
                   │           GUI / Desktop App          │
                   │  (Electron/Tauri shell around Layer 2)│
                   └──────────────┬──────────────────────┘
                                  │ calls
Layer 2 (near):    ┌──────────────▼──────────────────────┐
                   │         guide.py CLI                 │
                   │  project mgmt · asset tracking ·     │
                   │  context loading · build orchestration│
                   └──────────────┬──────────────────────┘
                                  │ loads context into
Layer 1 (now):     ┌──────────────▼──────────────────────┐
                   │     Claude Cowork / Code             │
                   │  AI brain: analysis · frame select · │
                   │  text generation · review loop       │
                   └─────────────────────────────────────┘
```

**The key principle**: the AI layer (Layer 1) never changes. What changes across layers is
how much scaffolding, context, and interface exists around it. The GUI in Layer 3 is just
a shell — it calls the same CLI commands as you run today, just without a terminal visible.

---

## What Exists Now (Layer 1 → 2)

```
guide-tool/
├── guide.py              ← CLI entry point
├── config.json           ← Global preferences (author, branding, AI settings, style prefs)
├── projects/
│   └── <project-name>/
│       ├── context.json        ← Project-level context (platform, audience, terminology, corrections)
│       ├── build.py            ← HTML build script (customized per project)
│       ├── recordings/         ← Source .mp4 files
│       ├── transcripts/        ← Whisper JSON files (same base name as recording)
│       ├── frames/
│       │   ├── main/           ← Frames extracted from main recordings
│       │   └── coverage/       ← Frames from supplemental/coverage clips
│       ├── output/             ← Generated HTML guides
│       └── sessions/
│           ├── YYYY-MM-DD.json ← Session log (focus, completed, pending, re-shoots, notes)
│           └── primer-YYYY-MM-DD.txt ← Generated Cowork session primer
└── .example/             ← Example project showing all file formats
```

## The Context Hierarchy in Practice

The `guide.py session <project>` command assembles the full context from all four levels
and prints a primer you paste into Cowork. This replaces the current "re-explain everything
each session" problem. Claude reads it, loads the project state, and is immediately ready
to work without you re-orienting it.

```
┌─────────────────────────────────────────────────────────┐
│  CONTEXT SCOPE       │  SOURCE FILE         │  CHANGES  │
├─────────────────────────────────────────────────────────┤
│  Global              │  config.json         │  Rarely   │
│  Project             │  project/context.json│  Per guide │
│  Session             │  sessions/today.json │  Per day  │
│  Task (in-flight)    │  In-conversation     │  Real-time│
└─────────────────────────────────────────────────────────┘
```

**Global context** shapes every guide: branding, style preferences, how to format step text,
what callout types to use. Set it once and forget it.

**Project context** shapes this guide: what platform is being documented, who the audience is,
known terminology (so Claude never calls the activity by the wrong name), and the corrections
history (so Claude never makes the same mistake twice across sessions).

**Session context** is the working memory for today: what we're focused on, what's done,
what's pending, any re-shoot requests. It gets updated automatically by guide.py commands and
manually by `guide.py note <project> "text"`.

**Task context** is the real-time steering — the conversation. "That screenshot is wrong",
"Make this step shorter", "Add a warning callout here." These corrections can optionally be
promoted to project context (as a correction in `corrections_history`) so they persist.

---

## The Conversation Layer — How It Works

The text/voice input at different scopes works like this:

```
User types or says:                    Routes to:
──────────────────                     ──────────
"always keep guides under 8 steps"  → config.json (global)
"this guide is for LMS admins"      → context.json (project)
"today I want to fix the Properties → sessions/today.json (session)
  tab screenshots"
"that frame shows the wrong tab"    → in-conversation, optionally
                                       promoted to corrections_history
```

The routing is currently manual (you update the right file). In the GUI, it becomes
a small prompt: "Remember this for: [Just this task] [This project] [All guides]."

---

## Path to Layer 3 (GUI)

The GUI doesn't replace guide.py — it wraps it. Each button in the UI calls a guide.py command.
The conversation panel is a Claude API call with the session primer pre-loaded.

**Minimal GUI scope (Electron/Tauri):**
- Left sidebar: project list (`guide.py list`)
- Main panel: project status view (`guide.py status`)
- Record button: launches screen capture + starts Whisper
- Storyboard view: card per step, frame picker, approve/flag
- Chat panel: persistent conversation, scoped to current project
- Export button: `guide.py build`

**What the GUI adds that the CLI can't:**
- Storyboard card view (visual, not terminal output)
- Frame picker filmstrip (click a frame = use it)
- In-line step text editing on the card
- Voice input for the conversation layer
- Real-time guide preview as you approve cards
- "Re-shoot this step" button with guided HUD during re-recording

**What the GUI deliberately omits:**
- Video timeline editing
- Audio editing
- Cloud sync
- Multi-user collaboration (Phase 3+)

---

## Immediate Next Steps

1. **Wire up the existing Widget Mastery project** into guide.py
   ```bash
   python3 guide.py new sample-lms-guide
   # copy existing recordings, transcripts, build.py into the project folder
   # fill in context.json with platform/audience/terminology from this session
   ```

2. **Use `guide.py session` at the start of every Cowork session** instead of re-explaining
   context. Paste the primer into chat. Claude is immediately oriented.

3. **Use `guide.py note` during sessions** to capture corrections and pending items.
   After a session, promote important corrections to `context.json → corrections_history`.

4. **Build a simple storyboard view** — even a static HTML page that reads the frames
   directory and displays cards — before committing to a full GUI framework.
   This validates the UX pattern cheaply.

---

## Voice / Text Input — Design Note

The conversation layer operates at all four context scopes simultaneously. The UX question
is how to make scope selection feel natural rather than like a settings panel.

The filmmaking analogy suggests an answer: on a film set, the director says "let's do another
take on that close-up" (task scope) vs. "for this whole project, we're going for a cold,
desaturated look" (project scope) vs. "my general rule is always shoot coverage" (global scope).
The difference is obvious from context — not from a dropdown.

For the guide tool: Claude should infer scope from the language used:
- "for this step" / "right here" / "this one" → task scope
- "for this guide" / "in this project" → project scope
- "always" / "in all my guides" / "by default" → global scope
- Unqualified corrections → task scope by default, with an option to promote

This inference can be built into the Cowork session prompt and later into a dedicated
system prompt for the chat panel in the GUI.

---

## Technical Reference: Screenpipe Analysis

Reviewed March 2026. Screenpipe (github.com/mediar-ai/screenpipe) is an open-source
always-on screen memory tool built with Tauri + Rust + TypeScript + SQLite. Its use case
(passive recall) diverges from ours (intentional documentation), but several of its solved
technical problems map directly to this tool.

### What to adapt from screenpipe

**Event-driven frame capture + accessibility tree pairing**
This is the core insight. Rather than recording a video and extracting frames with ffmpeg,
screenpipe listens for OS events (click, focus change, app switch, typing pause) and on
each event captures: (a) a JPEG screenshot and (b) the OS accessibility tree at that
moment — button names, field labels, text values, window titles, focused element. No OCR,
no timestamp guessing, no "was the cursor in a hover state?" problem. The frame arrives
already labeled with what was on screen and what was interacted with.

This is the sidecar data concept already in this architecture, but it's a solved
implementation problem in screenpipe's Rust codebase. The Windows and Mac accessibility
APIs (UI Automation / AXUIElement) are already wrapped. Study their capture approach as a
reference; write it cleanly for this purpose rather than integrating directly.

**Implication for the guide tool's recording mode:**
The deliverable is always **both** a video and a guide — video is a primary output, not a
byproduct. What the screenpipe approach adds is a parallel capture track: event-driven
frames + accessibility data recorded alongside the video. The video remains authoritative
for playback and review; the event log is authoritative for "what element was clicked and
what was it called." Guide assembly uses the event log for precise frame selection and
step text; the video ships alongside the guide as a companion asset. The two tracks are
complementary, not competing — ffmpeg extraction becomes a fallback for videos recorded
without the native capture mode, not the primary method.

**Tauri + Rust core + SQLite**
Confirmed right choices. Screenpipe ships this stack at production scale. SQLite holds
frames + events + transcript segments in one queryable store — exactly what a guide
project session database needs.

**Frame deduplication**
Screenpipe skips identical frames (pixel-level hash comparison). Adopt this: if the user
pauses on a screen without interacting, don't store 30 copies of the same frame.

### What NOT to adapt from screenpipe

| Screenpipe feature | Why not |
|---|---|
| Always-on passive recording | Guide tool needs intentional, session-scoped capture only |
| Memory/recall UX | Wrong mental model — production, not recall |
| Pipes plugin system | Generalist agent system; overkill for this use case |
| Semantic search over history | Not needed; project-scoped SQLite queries are sufficient |
| Full background service | Guide sessions are discrete; no daemon needed |

### MCP server — near-term bridge

Screenpipe exposes an MCP server so Claude can query screen history. The guide tool
should do the same, but scoped to projects: an MCP server that exposes current project
state, session context, and frame metadata. This replaces the `guide.py session` primer
copy-paste with a direct query Claude can make at the start of any session. That's the
cleanest bridge between the CLI-now and GUI-later phases.

### Screenpipe's capture pipeline (simplified, for reference)

```
OS event fires (click / focus / app switch)
    │
    ├─► Screenshot (JPEG, event-driven — not time-based)
    │
    ├─► Accessibility tree query (element names, roles, values)
    │       └─► Falls back to OCR if accessibility unavailable
    │
    ├─► Audio chunk (continuous, separate thread)
    │       └─► Whisper transcription (local or cloud)
    │
    └─► SQLite insert: frame + accessibility_text + transcript_segment + timestamp
```

For the guide tool, this pipeline runs only during an active recording session,
not continuously. The session database is project-scoped, not a global history.

---

## UACS Integration (Universal Agent Context System)

UACS (github.com/kylebrodeur/universal-agent-context) replaces the manual session primer
copy-paste pattern. Rather than running `guide.py session` and pasting a block of text
into Cowork, UACS auto-injects the right project context into every Claude session via its
MCP server and Claude Code hooks.

### Why UACS fits here

The guide tool's context hierarchy (global → project → session → task) maps directly onto
UACS's two memory scopes:

| Guide tool scope | UACS scope         | What lives there                                    |
|------------------|--------------------|-----------------------------------------------------|
| Global           | Global memory      | Style preferences, branding, default output formats |
| Project          | Project memory     | Platform, audience, terminology, corrections history|
| Session          | Project memory     | Today's focus, pending items, re-shoot requests     |
| Task (real-time) | In-conversation    | Specific corrections, frame swaps                   |

UACS handles deduplication automatically — corrections that repeat across sessions don't
pile up as duplicate memories.

### How it works in practice

```
guide.py sync <project>
    └─► uacs memory add "Platform: Acme Learning Platform" --scope project:my-guide
    └─► uacs memory add "Terminology — 'badge delivery activity': ..." --scope project:my-guide
    └─► uacs memory add "Correction [2026-03-11]: Advanced tab fires On Enrollment..." --scope project:my-guide
    └─► uacs memory add "Style: use bold for UI element names..." --scope global
    ...

Claude opens Cowork
    └─► UACS UserPromptSubmit hook fires
    └─► Relevant memories injected into context automatically
    └─► Claude knows the project, terminology, corrections — no paste needed
```

`guide.py note <project> "text"` writes to the local session JSON **and** calls
`uacs memory add` with project scope. Corrections are immediately searchable and
auto-loaded in the next session.

### Running UACS alongside guide.py

```bash
# Start UACS MCP server (keep running in background)
uacs serve

# First time setup for a project — pushes everything to UACS memory
uv run guide.py sync <project-name>

# After that — notes auto-sync on write
uv run guide.py note <project-name> "Advanced tab fires On Enrollment not On Completion"

# UACS loads context automatically when Cowork opens
# guide.py session is still available as a fallback when UACS isn't running
```

### Degraded mode (UACS not running)

`guide.py` detects UACS availability via subprocess call. If `uacs` is not found or times
out, all sync calls fail silently and the tool continues working with local JSON files only.
`guide.py session` remains fully functional as a manual fallback — paste the primer into
Cowork to get the same context. The two approaches are complementary, not exclusive.

### guide-tool MCP server (implemented — `mcp_server.py`)

Runs alongside the UACS MCP server. Covers the file system and build layer that UACS
has no concept of. The two servers are complementary with zero overlap:

| Layer        | Server       | Tools                                                     |
|---|---|---|
| Memory       | UACS         | `memory.add`, `memory.search`, `add_decision`, `search`   |
| Project ops  | guide-tool   | `guide_list_projects`, `guide_project_status`, etc.        |

**Tools exposed by mcp_server.py:**

| Tool | What it does |
|---|---|
| `guide_list_projects` | All projects with status, last session, asset counts |
| `guide_project_status` | Full project state: context, assets, session, corrections |
| `guide_add_note` | Add a note → saves to session JSON + syncs to UACS memory |
| `guide_list_frames` | List extracted frames by subdir (main / coverage) |
| `guide_get_transcript` | Read transcript content with timestamps |
| `guide_run_build` | Trigger build.py, return stdout |
| `guide_run_analyze` | Trigger frame extraction on all recordings |
| `guide_session_primer` | Return the full session primer text |

**What `guide_add_note` does NOT duplicate:** It writes the note to the session JSON file
(local structured state) AND calls `uacs memory add` (persistent cross-session memory).
Two different layers, one operation. The UACS `memory.add` tool alone wouldn't update the
local session JSON; this tool does both in one call.

**Claude Desktop config** (`~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "guide-tool": {
      "command": "uv",
      "args": ["run", "/absolute/path/to/guide-tool/mcp_server.py"]
    },
    "uacs": {
      "command": "uacs",
      "args": ["serve"]
    }
  }
}
```

With both servers running, Claude in Cowork has:
- UACS → auto-injected project memories at session start (UserPromptSubmit hook)
- guide-tool → live file system queries, frame lists, transcripts, build triggers on demand

**Running the server standalone** (for testing):

```bash
cd guide-tool
uv run mcp_server.py
```
