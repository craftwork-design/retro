---
name: retro
description: >
  Weekly retro for your coding agent. Scans local Claude Code transcripts for
  recurring friction (user corrections, interruptions, retry loops, permission
  denials, abandoned sessions), clusters the patterns, and proposes
  evidence-backed improvements to CLAUDE.md, skills, hooks, and permissions.
  Use when the user runs /retro or asks why the agent keeps making the same
  mistakes, what keeps going wrong, or how to improve their agent setup.
---

# retro — turn your agent's failures into harness improvements

You are running a retrospective on how the agent (you) has been performing for
this user, based on their real session transcripts. The goal is not a report
for the sake of a report. The goal is a small number of concrete, minimal
changes to the harness (CLAUDE.md, skills, hooks, permission settings) that
would have prevented the friction you find. Evidence first, changes second.

## Arguments

- `/retro` — current project, last 30 days
- `/retro 7d` / `/retro 90d` — custom window
- `/retro all` — every project on this machine

## Step 1 — collect signals

Run the bundled scanner. It lives in `scripts/scan.py` next to this SKILL.md
file (default install: `~/.claude/skills/retro/scripts/scan.py`).

```bash
python3 ~/.claude/skills/retro/scripts/scan.py --project "$PWD" --days 30 --format json
```

Use `--all` instead of `--project` when the user asked for all projects.
The scanner is deterministic and local-only; it surfaces candidates with high
recall. Your job is precision: judge which candidates are real friction.

## Step 2 — read the current harness

Read the project's `CLAUDE.md` (and `~/.claude/CLAUDE.md` if present). You
need it to tell which failures happened BECAUSE a rule is missing, unclear,
or being ignored, versus failures no rule could have prevented.

## Step 3 — cluster into patterns

From the JSON, identify at most 5 recurring patterns. A pattern needs at
least 2 independent occurrences; ignore one-offs. For each candidate, check
the excerpts yourself: a "correction" flagged by the scanner may be a normal
instruction — drop those. Typical real patterns:

- The user repeats the same stylistic correction across sessions (missing CLAUDE.md rule)
- A CLAUDE.md rule exists but is violated anyway (rule is buried, vague, or contradicted)
- The same command fails repeatedly (wrong default in the harness: wrong test runner, missing env, wrong package manager)
- Permission denials on the same tool/path (over-broad or missing permission config, or the agent attempts things the user never wants)
- Sessions abandoned right after a failure (the most expensive signal: the user gave up)

If you need more context on a specific session, its transcript is at
`~/.claude/projects/<munged-project-path>/<session-id>.jsonl` — read
selectively (grep around the relevant timestamps), transcripts are large.

## Step 4 — write the retro

Present in chat, in the user's language, in this shape:

```
# Retro: <project> — last <N> days

<one-paragraph summary: sessions scanned, the single biggest issue>

## Pattern 1: <plain-language name> (<N> occurrences, <M> sessions)
Evidence: 1-3 real quotes/failures, dated
Root cause: one sentence
Fix: the exact change, quoted (CLAUDE.md rule / hook / permission / skill)

... up to 5 patterns, ranked by cost to the user ...

## Proposed CLAUDE.md diff
<one unified diff block with ALL proposed rule changes together>

## What went well
<1-2 lines, only if genuinely notable — do not pad>
```

## Step 5 — apply on confirmation

Ask which fixes to apply. Apply only the confirmed ones. Rules you add must
be short, imperative, and specific ("Run tests with `pnpm vitest run`, never
`npm test`"), never vague ("be more careful with tests"). If a fix is a hook
or permission change, show the exact `settings.json` snippet before touching
anything.

## Hard rules

- Never invent evidence. Every quote must come from the scanner output or a transcript you actually read.
- Fewer, sharper findings beat a long list. Zero real patterns is a valid outcome — say so.
- Never modify CLAUDE.md, settings, or skills without explicit confirmation in this conversation.
- Everything stays local. Never send transcript content to any external service.
- Do not treat scanner counts as truth; they are candidates. You are the judge.
