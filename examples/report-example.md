# Retro: acme-dashboard — last 30 days

Scanned 38 sessions. Overall friction is moderate, but one pattern alone cost
you an estimated 6 abandoned or derailed sessions: the agent keeps starting a
second dev server instead of using the one already running.

## Pattern 1: duplicate dev server (11 occurrences, 7 sessions)

Evidence:
- Jun 14: `npm run dev` → "Port 3000 is already in use", retried 4 times
- Jun 19: you interrupted with Esc and wrote "the server is ALREADY running, just open the page"
- Jun 27: session abandoned two minutes after the third `EADDRINUSE` error

Root cause: nothing in CLAUDE.md says a dev server is always running on :3000.
The agent assumes a cold environment every session.

Fix: one rule in CLAUDE.md (see diff below).

## Pattern 2: wrong test runner (6 failures, 4 sessions)

Evidence:
- `npm test` → "Missing script: test" on Jun 12, 16, 23
- Jun 23: you corrected: "we use pnpm vitest, how many times"

Root cause: repo migrated to pnpm workspaces in May; CLAUDE.md predates it.

Fix: one rule in CLAUDE.md (see diff below).

## Pattern 3: unwanted commits (3 denials, 3 sessions)

Evidence:
- You rejected `git commit` permission prompts on Jun 15, 21, 30 — every time
  after a task where you never asked for a commit.

Root cause: agent commits proactively after finishing tasks; you prefer to
review and commit yourself.

Fix: one rule in CLAUDE.md, plus optionally deny `git commit` in
`.claude/settings.json` permissions.

## Proposed CLAUDE.md diff

```diff
 # acme-dashboard

+## Environment
+- The dev server is always already running on :3000. Never start another one.
+
+## Commands
+- Run tests with `pnpm vitest run`. `npm test` does not exist in this repo.
+
+## Workflow
+- Never commit. Leave changes in the working tree; I review and commit myself.
```

## What went well

Zero corrections about code style in 38 sessions — the existing style rules
in CLAUDE.md are doing their job.

---

Apply all three rules? (1/2/3/all/none)
