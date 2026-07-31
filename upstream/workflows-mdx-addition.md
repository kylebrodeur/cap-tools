<!--
Draft only — NOT posted, NOT yet a PR. Per the user: recreated after the
original local branch (agents-workflows-auto-zoom-recording on the
kylebrodeur/Cap fork) was lost — never pushed to the fork's remote, and no
local worktree survived. Saved here so it can be tested locally against a
capt-driven recording before opening the actual PR.

Target file: apps/web/content/docs/agents/workflows.mdx (CapSoftware/Cap)
Placement: insert as a new "## " section, after "Record and share a bug
reproduction" and before "Upload an existing recording" — see
upstream/workflows-full-draft.mdx for the complete file with this section
already inserted at that position, ready to diff against the live file.

Style notes matched from the live file (fetched 2026-07-31):
- "**Ask your agent:**" blockquote with a realistic natural-language prompt
- "The agent should:" numbered list, ending on a confirmation/validation step
- a fenced ```sh code block with the actual CLI sequence
- a closing "**Success check:**" line
-->

## Record a walkthrough with automatic zoom

**Ask your agent:**

> Record a walkthrough of `<task or URL>` and give it Loom-style zoom-ins on the moments that mattered — no manual Studio timeline editing afterward.

The agent should:

1. Check readiness with `cap doctor --json` and confirm a screen or window target with `cap targets --json`.
2. Start a detached recording, then drive the walkthrough itself (its own browser automation, or by asking you to perform the steps live) — tracking the elapsed-time offset of every meaningful action (a click, a form submission, an explicit "mark this moment" cue) relative to when the recording actually started, not to whenever the agent happened to begin driving it.
3. Stop that exact session and require `recordingMetaExists: true`.
4. Turn each tracked offset into a short zoom segment (a few seconds before through a couple seconds after) and merge those segments into the project's existing `timeline.zoomSegments` — read-merge-write, never overwriting segments the project already had.
5. Validate the merged result with `cap project validate <path.cap> --json` before exporting.

```sh
cap record start --screen <screen-id> --detach --json
# ... agent drives the walkthrough, tracking elapsed_s at each meaningful action ...
cap record stop --id <recording-id> --json
cap project validate <path.cap> --json
# merge computed zoomSegments into project-config.json's timeline.zoomSegments here
cap export <path.cap> --output walkthrough.mp4 --json
```

**Success check:** Every zoom segment's start/end falls within the recording's duration, any zoom or mask segments the project already had are still present after the merge, and the exported video visibly zooms in at each tracked moment instead of staying static throughout.
