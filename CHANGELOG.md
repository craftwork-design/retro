# Changelog

## 0.3.0 (unreleased)

- Light ru/en stemmer for cross-session clustering; real clusters grew
- `after_success_claim`: failure reports right after the agent claimed success
- SKILL.md: reason-tag weighting, subagent fan-out for large reports
- Clean-install installer (no stale files on upgrade), fixed README commands
- "vs /insights" positioning section
- CI smoke test (fixture transcript, macOS + Linux, Python 3.8/3.12)

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
