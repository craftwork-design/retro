# retro — plan

## One-liner

Your coding agent keeps making the same mistakes. retro reads your own Claude Code
session transcripts, finds the recurring failures, and turns them into concrete
CLAUDE.md / skill / hook improvements with evidence. Continual learning at the
harness level, no model weights required.

## Why now

- Replit showed the pattern: production failures → clusters → hypotheses → patches → evidence → ship.
- Every Claude Code user already has the raw material: full JSONL transcripts in `~/.claude/projects/`.
- Existing tools stop earlier: transcript viewers "view and measure"; built-in `/insights` summarizes usage and suggests rules but doesn't mine friction signals (admissions, cross-session repeats, post-Esc redirects), doesn't quote evidence, and doesn't apply the diff. Positioning: "use /insights for the big picture, /retro to turn failures into rules". Known name collisions: several small "retro/retrospective" skills exist on mcpmarket/GitHub — they reflect on the current session only; our differentiator is mining ALL transcripts with evidence.

## MVP (v0.1 — this repo)

A free, open-source Claude Code skill:

1. `scripts/scan.py` — stdlib-only Python. Parses local transcripts, extracts friction signals:
   - user corrections (you told the agent it was wrong)
   - interruptions (Esc mid-action)
   - permission denials
   - tool errors + retry loops (same command failing repeatedly)
   - sessions abandoned right after a failure
   Outputs compact JSON (for the skill) or a pretty terminal report (for humans and screenshots).
2. `SKILL.md` — the `/retro` command. Runs the scanner, reads the project's CLAUDE.md,
   clusters the signals into named patterns, and proposes a minimal evidence-backed diff.
   Never applies changes without confirmation.

Everything runs locally. No telemetry, no uploads.

## v0.2

- `--html` shareable report (anonymized numbers only)
- Plugin packaging (`.claude-plugin/plugin.json` + marketplace) for versioned install/update via `/plugin install`
- Hook suggestions (auto-generate settings.json hooks from denial patterns)
- Weekly cadence: `/loop`-friendly mode + saved report history to track whether fixes actually reduced friction

## v1 — retro for teams (paid)

- Aggregate clusters across a team: 20 engineers, one set of shared lessons
- Shared rules registry with "does this rule actually reduce corrections" analytics
- GitHub App: weekly PR into the repo updating CLAUDE.md/skills with evidence, Replit-loop style
- Privacy model: only learned rules and cluster stats sync, never raw transcripts
- Pricing target: $20–30/seat/month

## Distribution

- GitHub repo + one-line install
- Launch on X (founder account), HN Show HN, r/ClaudeAI
- The pretty terminal report is the marketing asset: every screenshot is an ad
