# Changelog

## 0.3.0 (unreleased)

- Light ru/en stemmer for cross-session clustering; real clusters grew
- `after_success_claim`: failure reports right after the agent claimed success
- SKILL.md: reason-tag weighting, subagent fan-out for large reports,
  rule-age check (predates vs postdates failures) before claiming a rule
  was ignored — found via a live end-to-end run on a real project
- Clean-install installer (no stale files on upgrade), fixed README commands
- "vs /insights" positioning section
- CI smoke test (fixture transcript, macOS + Linux, Python 3.8/3.12)
- `--days` filters events by their own timestamp, not just file mtime:
  a resumed old session no longer drags months of history into the window
- Project scope: sibling transcript dirs are kept only if their sessions ran
  inside the project (worktrees yes, `app-v2` next to `app` no)
- `corrections` cap keeps the 80 strongest entries, not the 80 newest
- Fewer false positives: "зависимости", "зависит", "независимо",
  "вылетающее меню", "далее", and a bare "готово"/"done" (now a nudge only
  with "?"); "поломалось" now caught
- Tokenizer handles any script (accented Latin, CJK via bigrams), so
  repeated-instruction clustering works with non-en/ru language packs
- `truncated` is true only when `--limit` actually cut files off
- `tests/detectors.py`: table test of must-fire / must-stay-quiet phrases

## 0.2.0 — 2026-07-07

Scanner v2, built from a 3-agent audit of 1.3 GB of real transcripts
(hand-audit recall of v1 was 4%):

- New signals: assistant admissions ("you're right"), unconditional
  post-interrupt capture, failure reports, bare-imperative redos, dictated
  rules ("запомни, отныне..."), cross-session repeated instructions,
  nudges ("продолжай"), frustration boost, repeat pastes
- Parser: harness tags stripped instead of dropping messages, session titles,
  big lines parsed, denial/cancel markers extended, synthetic dirs excluded,
  api-error lines no longer mask abandonment
- `--patterns` JSON language packs (example-es included)

## 0.1.0 — 2026-07-07

Initial release: /retro skill + stdlib scanner (corrections, interrupts,
denials, errors, retry loops, abandoned sessions), installer, MIT.
