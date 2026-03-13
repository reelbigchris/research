Wrap up the current working session. Writes a session summary, creates a handoff for next time, updates the goal's status, and prompts to save any reusable work to the persistent workspace.

## Steps

### 1. Identify the active goal

List subdirectories in `.goals/`.

- If one exists, use it.
- If multiple exist, use `AskUserQuestion` to ask which goal this session was for.

---

### 2. Find the current session directory

List all subdirectories of `.goals/{goal}/sessions/`. The current session is the one with the highest number. Note its full path.

---

### 3. Write SUMMARY.md

Create `.goals/{goal}/sessions/{current}/SUMMARY.md` with a thorough record of this session:

```markdown
# Session Summary — {date}

## What Was Accomplished
{bullet list of meaningful work completed: features built, bugs fixed, problems solved, code written, decisions finalized}

## What Was Investigated / Discovered
{things explored even if not directly shipped: root causes found, architecture understood, failed approaches tried}

## Files Changed
{list of key files created or modified, with a one-line note on what changed}

## Decisions Made
{significant choices made during this session and the reasoning behind them}
```

Be specific and honest. Future sessions will read this to understand what ground has been covered.

---

### 4. Write HANDOFF.md

Create `.goals/{goal}/sessions/{current}/HANDOFF.md` — the most important artifact. It will be read at the start of the next session to restore context immediately.

```markdown
# Handoff — {date}

## In Progress
{what was actively being worked on when this session ended — specific enough that work can resume without re-exploring}

## Key Decisions
{decisions made this session and why — especially ones that constrain future work}

## Next Steps
{specific, ordered list of what to do next session — not vague "continue the work" but concrete actions}

## Watch Out For
{gotchas, surprises, non-obvious constraints, things that cost time this session}

## Key Files
{paths most relevant to ongoing work, with one-line descriptions of their role}

## Open Questions
{unresolved questions that need investigation or decisions — don't let these get lost}
```

Write this as if briefing someone who is smart but has no memory of this session. Concrete > vague.

---

### 5. Update GOAL.md

Read the current `GOAL.md`, then update it:

1. **Session History table**: Append a new row:
   `| {N} | {YYYY-MM-DD} | {session focus slug} | {one-line outcome} |`

2. **Current Status**: Replace with an honest assessment of where the goal stands right now — what's working, what's not, what's left.

3. **Active Focus**: Replace with what the next session should prioritize, based on the Next Steps in HANDOFF.md.

Write the updated file back.

---

### 6. Workspace promotion

Use `AskUserQuestion` to ask:

> "Are there any scripts, analysis files, or notes from this session's `notes/` folder (or elsewhere) that should be saved to `workspace/` for use in future sessions?"

If yes: move or copy the specified files to `.goals/{goal}/workspace/`. If the user describes something to write rather than move, write it as a new file in `workspace/`.

Good candidates for workspace:
- Helper scripts that will run again (DB resets, data migrations, test flows)
- Analysis files that took significant effort to produce
- Architecture diagrams or notes that aren't appropriate for CLAUDE.md
- Reference docs specific to this goal

---

### 7. Confirm and close

Print a brief confirmation:
```
Session {N} closed.

Written:
  ✓ .goals/{goal}/sessions/{dirname}/SUMMARY.md
  ✓ .goals/{goal}/sessions/{dirname}/HANDOFF.md
  ✓ .goals/{goal}/GOAL.md (updated)
  {✓ any workspace files saved}

Next session: run /session-start to load this handoff and continue.
Tip: run /clear now to reset the context window.
```
