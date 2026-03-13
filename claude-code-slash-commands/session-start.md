Start a new working session for a goal. Sets up the session directory and loads context from the previous session so you can pick up exactly where you left off.

## Steps

### 1. Detect goals

Scan for a `.goals/` directory in the current working directory.

**Case A — No `.goals/` directory exists:**
Use `AskUserQuestion` to collect:
- Goal slug (short kebab-case name, e.g. `auth-refactor`)
- Goal description (one paragraph: what we're ultimately building or achieving)

Then create the following structure:
```
.goals/{slug}/GOAL.md
.goals/{slug}/sessions/
.goals/{slug}/workspace/
```

Write `GOAL.md` using this template:
```markdown
# Goal: {slug}

## Description
{description}

## Current Status
Not started.

## Active Focus
Begin initial exploration and planning.

## Session History
| # | Date | Focus | Key Outcome |
|---|------|-------|-------------|

## Known Issues & Blockers
_(none yet)_
```

This is Session 1. Skip to Step 5.

**Case B — Exactly one goal directory exists:**
Use it automatically. Read its `GOAL.md`.

**Case C — Multiple goal directories exist:**
Use `AskUserQuestion` to present a numbered list of goal names and ask which to work on (include an option to create a new goal). If creating new, follow Case A logic then continue.

---

### 2. Load goal context

Read the selected goal's `GOAL.md` in full.

---

### 3. Find the prior session

List all subdirectories of `.goals/{goal}/sessions/`. Find the one with the highest session number (directories are named `{NNN}-{YYYY-MM-DD}-{slug}`).

If one exists, read its `HANDOFF.md`. If `HANDOFF.md` is missing, note this but continue — context will come from `GOAL.md` alone.

---

### 4. Survey the workspace

List all files in `.goals/{goal}/workspace/`. For each file, read it if it's reasonably short (scripts, notes, analysis). These are persistent tools available this session — announce them so you know to use them rather than recreating them.

---

### 5. Get this session's focus

Use `AskUserQuestion` to ask: "What's the focus or goal for this session?" (This becomes the slug in the session directory name.)

---

### 6. Create the session directory

Determine the next session number by counting existing session directories (pad to 3 digits: `001`, `002`, etc.). Create:
```
.goals/{goal}/sessions/{NNN}-{YYYY-MM-DD}-{focus-slug}/
.goals/{goal}/sessions/{NNN}-{YYYY-MM-DD}-{focus-slug}/notes/
```

Use today's date in `YYYY-MM-DD` format. Convert the focus to a kebab-case slug (lowercase, hyphens, no special chars, max ~30 chars).

---

### 7. Present the context brief

Output a structured summary:

```
## Session {N} — {goal-name}
**Date:** {today}
**Session directory:** .goals/{goal}/sessions/{dirname}/

### Goal
{description from GOAL.md}

### Current Status
{current status from GOAL.md}

### Active Focus (from last session)
{active focus from GOAL.md}

### Handoff from Previous Session
{full contents of HANDOFF.md, or "No prior handoff — this is session 1."}

### Workspace
{list of files in workspace/ with one-line descriptions, or "Empty — no persistent scripts yet."}
```

---

### 8. Announce and orient

Tell the user:
- Session is open and ready
- Session scratch notes go in `.goals/{goal}/sessions/{dirname}/notes/`
- Persistent scripts/notes go in `.goals/{goal}/workspace/`
- Run `/session-end` when done to write the summary and handoff for next time
