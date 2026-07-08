# retro

**Never type the same correction twice.**

Your coding agent keeps making the same mistakes. You keep typing the same corrections. Every one of them is already written down, in transcripts nobody reads.

Every Claude Code session you ever ran is sitting in `~/.claude/projects/` as a full transcript. Inside those files is a precise record of every time the agent got it wrong: every "no, not like that", every Esc you hit mid-action, every command it retried five times, every session you rage-quit after a failure.

`retro` reads those transcripts and closes the loop:

```
your failures → clusters → evidence → a concrete CLAUDE.md diff
```

This is the Replit-style self-improvement loop (production failures → clusters → evidence → patches), applied to the harness you already own. No fine-tuning, no API keys, no telemetry. Continual learning at the layer you can actually change.

## Isn't this just /insights?

Claude Code's built-in `/insights` gives you a great 30-day usage report with suggestions. retro is a different tool for a different job:

- **Evidence, not summaries.** Every proposed rule comes with verbatim quotes from your transcripts, dated. You see exactly which failures a rule would have prevented, and can veto it.
- **Signals /insights doesn't mine.** The agent admitting "you're right" (69 times in my last 45 days), rules you dictated out loud ("запомни, отныне..."), Esc-interrupts and what you said right after.
- **Closes the loop.** retro doesn't stop at suggestions: it drafts the CLAUDE.md diff, you confirm, it applies.
- **Inspectable and hackable.** One stdlib Python file, deterministic, bilingual (EN/RU) with pluggable language packs, custom windows (`7d`/`90d`/`all`), JSON output you can pipe anywhere.

Use both: `/insights` for the big picture, `/retro` for turning failures into rules.

## Install

```bash
git clone https://github.com/craftwork-design/retro.git && cd retro && ./install.sh
```

Manual install (also works for updating):

```bash
TMP=$(mktemp -d) && git clone https://github.com/craftwork-design/retro.git "$TMP" \
  && rm -rf ~/.claude/skills/retro && mkdir -p ~/.claude/skills \
  && cp -r "$TMP/skill" ~/.claude/skills/retro
```

Requires Python 3.8+ (stdlib only, no dependencies). On Windows, use Git Bash for the commands above and `python` instead of `python3`. If you use a custom `CLAUDE_CONFIG_DIR`, both the installer and the scanner respect it.

**Claude Code only.** retro reads `~/.claude/projects/` transcripts. Cursor, Codex, and Zed are on the roadmap, not supported today. New to retro or a fresh machine? Start with `/retro all` — a brand-new project has almost no history, so the single-project view will look empty until you've used it a while.

## Use

Inside Claude Code, in any project:

```
/retro          # current project, last 30 days
/retro 7d       # last week
/retro all      # every project on this machine
```

The agent scans your transcripts, clusters recurring friction, and shows you a retro with evidence and a proposed CLAUDE.md diff. Nothing is applied without your confirmation.

Want just the numbers, without the agent? Run the scanner directly:

```bash
python3 ~/.claude/skills/retro/scripts/scan.py            # pretty terminal report
python3 ~/.claude/skills/retro/scripts/scan.py --all      # all projects
python3 ~/.claude/skills/retro/scripts/scan.py --format json
```

## What it detects

| Signal | What it means |
|---|---|
| Corrections | You told the agent it was wrong: explicit ("not like that"), bug reports ("it crashed again"), redo requests ("shorter", "поправь хедер") |
| Admissions | The agent itself said "you're right" or "my mistake". Catches corrections no keyword list ever would |
| Repeated asks | The same instruction given across 2+ different sessions. Each cluster is a ready-made CLAUDE.md rule |
| Rule requests | You dictated a rule out loud: "remember, from now on always..." |
| Interrupts | You hit Esc while it was doing something, plus whatever you said right after |
| Nudges | You typed a bare "continue" because the agent stalled mid-task |
| Denials | Permission prompts you rejected |
| Retry loops | The same call failed 3+ times in a session |
| Abandoned sessions | The session ended right after a failure. The most expensive signal there is |

### Languages

Roughly half of the signals are language-agnostic by construction: interrupts, nudge-free repeated instructions (token clustering), repeated pastes, denials, errors, retry loops, abandoned sessions. The lexical detectors (corrections, admissions, rule requests, nudges) ship with English and Russian patterns, morphology-aware.

Other languages plug in as a JSON pattern pack, no code changes:

```bash
python3 skill/scripts/scan.py --patterns skill/patterns/example-es.json
```

See [skill/patterns/example-es.json](skill/patterns/example-es.json) for the format. Language pack PRs are very welcome.

The scanner is deterministic and high-recall; the skill (the model) does the judgment: which candidates are real patterns, what the root cause is, and what minimal rule, hook, or permission change would have prevented them.

## Example

```
# Retro: my-app — last 30 days

Scanned 42 sessions. The biggest issue: test runner confusion.

## Pattern 1: wrong test command (9 failures, 6 sessions)
Evidence: `npm test` failed with "missing script" on Jun 12, 14, 19...
Root cause: repo uses pnpm + vitest, CLAUDE.md never says so
Fix: add rule "Run tests with `pnpm vitest run`, never `npm test`"

## Proposed CLAUDE.md diff
+ ## Commands
+ - Run tests with `pnpm vitest run`, never `npm test`
+ - Dev server is already running on :3000, never start a second one
```

See [examples/report-example.md](examples/report-example.md) for a full report.

## Privacy

Everything runs on your machine. The scanner is a single stdlib Python file with no dependencies. No network calls, no telemetry, nothing leaves your laptop. Your transcripts are yours.

## Roadmap

- [ ] HTML report you can actually share (numbers only, no transcript content)
- [ ] Hook suggestions generated from denial patterns
- [ ] Report history: did last week's fixes reduce this week's corrections?
- [ ] **retro for teams**: one shared set of lessons across 20 engineers, synced rules registry, weekly PR into your repo with evidence. If that sounds like your team, open an issue on this repo.

## License

MIT

---

Independent open-source project. Not affiliated with, endorsed, or sponsored by Anthropic or id Software. Claude and Claude Code are trademarks of Anthropic; DOOM is a trademark of id Software LLC.
