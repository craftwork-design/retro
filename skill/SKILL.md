---
name: retro
description: >
  Weekly retro for your coding agent. Scans local Claude Code transcripts for
  recurring friction (corrections, agent admissions like "you're right",
  instructions repeated across sessions, dictated rules, interrupts, nudges,
  retry loops, denials, abandoned sessions), clusters the patterns, and
  proposes evidence-backed improvements to CLAUDE.md, skills, hooks, and
  permissions. Use when the user runs /retro or asks why the agent keeps
  making the same mistakes, what keeps going wrong, or how to improve their
  agent setup.
argument-hint: "[7d|30d|90d|all]"
---

# retro — turn your agent's failures into harness improvements

You are running a retrospective on how the agent (you) has been performing
for this user, based on their real session transcripts. The goal is not a
report for the sake of a report. The goal is a small number of concrete,
minimal changes to the harness (CLAUDE.md, skills, hooks, permissions,
memory) that would have prevented the friction you find. Evidence first,
changes second.

## Arguments

`$ARGUMENTS` maps to scanner flags:

- `Nd` (e.g. `7d`, `90d`) → `--days N` (strip the `d`)
- `all` → `--all` (omit `--project`)
- they combine: `/retro all 90d` → `--all --days 90`
- no arguments → current project, `--days 30`

## Step 1 — collect signals

Locate the scanner, in order: `~/.claude/skills/retro/scripts/scan.py`; if
`$CLAUDE_CONFIG_DIR` is set, `$CLAUDE_CONFIG_DIR/skills/retro/scripts/scan.py`;
then `.claude/skills/retro/scripts/scan.py` in the project. Then run it with
an explicit absolute project path (do not rely on the shell's cwd):

```bash
python3 ~/.claude/skills/retro/scripts/scan.py \
  --project "<absolute path to the project>" --days 30 --format json
```

Sanity-check the output before proceeding:

- `project` and `sessions_scanned` look right for this project.
- If the scanner exits with "no transcripts", say so and stop; offer
  `/retro all`.
- If `truncated` is true, the window was capped by `--limit` (default 200
  sessions): rerun with `--limit 1000`, or state the real coverage in the
  report header instead of "last N days".
- Sessions are selected by file modification time; individual quotes carry
  their own `ts` and may predate the window. Check the `ts` of every quote
  you cite; present older evidence as such, never as recent.

## Step 2 — read the current harness

Read the project's `CLAUDE.md` (also check `claude.md` / `Claude.md` and
`~/.claude/CLAUDE.md`). You need it to tell which failures happened BECAUSE
a rule is missing, unclear, or being ignored, versus failures no rule could
have prevented.

If no project CLAUDE.md exists, the Step 4 diff becomes a proposed new file:
say "create `<project>/CLAUDE.md`" and show its full contents. Rules that
describe the user rather than one project (reply language, tone, commit
habits) belong in `~/.claude/CLAUDE.md` — mark those as user-level.

## Step 3 — cluster into patterns

Identify at most 5 recurring patterns. A pattern needs at least 2
independent occurrences (exception below). For each candidate, check the
excerpts yourself: a "correction" flagged by the scanner may be a normal
instruction — drop those.

Start with the highest-yield fields:

- `rule_requests` — the user dictated a rule out loud ("запомни, отныне
  всегда..."). **Exception to the 2-occurrence rule: one rule_request is
  enough** — the user explicitly asked. But read the surrounding transcript
  before converting: reconcile with existing CLAUDE.md content (the literal
  words may contradict a documented legitimate case), and drop entries too
  vague to reconstruct.
- `repeated_instructions` — the same ask across 2+ sessions, with session
  ids and timestamps per example. Each cluster is a *candidate* rule, not a
  rule by definition: reject clusters that are per-task go-ahead commands
  the user must issue deliberately (deploy, "commit this now"), and clusters
  already covered by CLAUDE.md — those become "rule exists but isn't
  followed", which is a different fix (sharpen the rule's wording or move it
  higher in the file).
- `admissions` — the agent conceded a mistake; `user_text` holds what the
  user complained about, `admission` often names the root cause.
- `error_loops` — the same tool+target failing 2+ times: the source for
  "wrong default in the harness" patterns (wrong test runner, missing env).
  `retry_loops` is the ≥3-failure subset.
- `nudges` — only per-session counts: filter `sessions[]` for `nudges >= 2`
  (= the agent stalls mid-task). For quotes, grep those transcripts;
  otherwise cite session titles and dates from `sessions[]`.

To form candidates from the flat `corrections` list: group by recurring
nouns/verbs in `text` and by session overlap with other signals; a candidate
is any theme with 2+ entries. Weigh `reasons` tags in this order (strongest
first):

1. `after_success_claim` — agent said "done/fixed", user came back with a
   failure. Near-certain, and the most expensive kind.
2. `frustration` — the user is visibly angry.
3. `post_interrupt` — Esc + redirect. ~70% are real.
4. `failure_report` — something built or claimed broke.
5. `correction` / `redo` / `repeat_paste` — real but noisier; verify quotes.

Multi-reason entries outrank single-reason ones. Note: the excerpt arrays
are capped (`corrections` 80, `admissions` 40, `sessions` 100 + all
abandoned) — use `totals` for counts, arrays for quotes. Ignore
`top_correction_terms` unless it shows an obvious theme.

If you need more context on a session, its transcript is at
`~/.claude/projects/<munged-project-path>/<session-id>.jsonl` — grep around
the relevant timestamps; transcripts are large.

## Step 3.5 — fan out to subagents when the report is large

If `totals.corrections + totals.admissions > 40`, or you have 5+ candidate
patterns, do not judge everything in this context — you will skim and miss.
Spawn one verification subagent per candidate pattern (Agent/Task tool, in
parallel). Give each: the pattern name, its excerpts with session ids and
timestamps, the transcript directory path, and this instruction:

> Verify this candidate pattern against the raw transcripts. Return:
> CONFIRMED or REJECTED, the 2 best verbatim quotes with dates, a one-line
> root cause, and a proposed minimal rule. Reject if the quotes read as
> normal instructions rather than friction.

Then judge the returned evidence yourself and keep at most 5 confirmed
patterns. Subagents read transcripts locally; nothing leaves the machine.

## Step 4 — write the retro

Present in chat, in the user's language, in this shape:

```
# Retro: <project> — <real coverage: "last N days" or "N most recent sessions">

<one-paragraph summary: sessions scanned, the single biggest issue>

## Pattern 1: <plain-language name> (<N> occurrences, <M> sessions)
Evidence: 1-3 real quotes, each dated (or "N sessions, undated" — never invent dates)
Root cause: one sentence
Fix: the exact change, quoted

... up to 5 patterns, ranked by cost to the user ...

## Proposed changes
<one fenced block PER TARGET FILE: project CLAUDE.md, ~/.claude/CLAUDE.md,
.claude/settings.json, memory files. Unified diff for existing files, full
contents for new ones.>

## What went well
<1-2 lines, only if genuinely notable — do not pad>
```

## Step 5 — apply on confirmation

Number every proposed fix and let the user pick (all / numbers / none).
Apply only what they picked. Rules must be short, imperative, and specific
("Run tests with `pnpm vitest run`, never `npm test`"), never vague ("be
more careful with tests").

- Hooks/permissions: do not write settings.json schemas from memory — they
  change between versions. Consult the harness settings docs or the
  update-config skill if available. Prefer project `.claude/settings.json`
  unless the rule is user-wide.
- If the user dictated "remember this" rules, auto-memory files
  (`~/.claude/projects/<munged>/memory/`) are a valid target alongside
  CLAUDE.md.

## Hard rules

- Never invent evidence. Every quote must come from the scanner output or a
  transcript you actually read; every date from a real `ts`.
- Fewer, sharper findings beat a long list. Zero real patterns is a valid
  outcome — say so.
- Never modify CLAUDE.md, settings, skills, or memory without explicit
  confirmation in this conversation.
- Everything stays local. Never send transcript content to any external
  service.
- Do not treat scanner counts as truth; they are candidates. You are the
  judge.
