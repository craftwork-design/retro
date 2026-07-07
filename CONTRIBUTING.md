# Contributing to retro

The most valuable contribution right now is a **language pack**: retro ships
with English and Russian detectors, and every new language makes the tool
useful to a whole new group of people.

## Adding a language pack

1. Copy [skill/patterns/example-es.json](skill/patterns/example-es.json) to
   `skill/patterns/<lang>.json`.
2. Fill in regexes for your language. The classes that matter most, in order:
   `correction`, `failure_report`, `admission`, `rule_request`, `redo`,
   `nudge`, `continuation`, `frustration`.
3. Test against your own transcripts:
   `python3 skill/scripts/scan.py --patterns skill/patterns/<lang>.json`
4. Open a PR with 2-3 anonymized examples of what the pack catches.

Tips: keep patterns case-insensitive-friendly (the scanner compiles with
`re.I | re.U`), use `(?<!\w)...(?!\w)` instead of `\b` for non-Latin scripts,
and prefer word stems over exact forms for inflected languages.

## Code changes

- Stdlib only. No dependencies, ever — it's the core promise of the tool.
- No network calls of any kind.
- Run `python3 tests/smoke.py` before pushing; CI runs it on 3.8 and 3.12.
- If you add a detector class, add a line to the fixture
  (`tests/fixtures/session.jsonl`) and an assertion to `tests/smoke.py`.

## Reporting detection misses

The best bug report is: the (anonymized) user message that should have been
caught, the signal class you expected, and your language. Open an issue with
the `detection-miss` label.
