#!/usr/bin/env python3
"""Smoke test: run the scanner against a fixture transcript and assert that
every detector class fires. Run: python3 tests/smoke.py"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCANNER = ROOT / "skill" / "scripts" / "scan.py"
FIXTURE = ROOT / "tests" / "fixtures" / "session.jsonl"


def main():
    tmp = Path(tempfile.mkdtemp(prefix="retro-smoke-")).resolve()
    try:
        # a real project dir, so the scanner's path resolution matches
        project = tmp / "fixture-project"
        project.mkdir()
        munged = re.sub(r"[^A-Za-z0-9]", "-", str(project))
        proj_dir = tmp / "projects" / munged
        proj_dir.mkdir(parents=True)
        shutil.copy(FIXTURE, proj_dir / "fixture.jsonl")

        env = {**os.environ, "CLAUDE_CONFIG_DIR": str(tmp)}
        out = subprocess.run(
            [sys.executable, str(SCANNER), "--project", str(project),
             "--days", "36500", "--format", "json"],
            env=env, capture_output=True, text=True, timeout=60,
        )
        assert out.returncode == 0, f"scanner exited {out.returncode}: {out.stderr}"
        report = json.loads(out.stdout)
        t = report["totals"]

        checks = {
            "sessions_scanned": report["sessions_scanned"] == 1,
            "correction (failure report)": t["corrections"] >= 2,
            "admission": t["admissions"] >= 1,
            "after_success_claim tag": any(
                "after_success_claim" in c["reasons"] for c in report["corrections"]
            ),
            "post_interrupt capture": any(
                "post_interrupt" in c["reasons"] for c in report["corrections"]
            ),
            "interrupt": t["interrupts"] == 1,
            "rule_request": t["rule_requests"] >= 1,
            "nudge": t["nudges"] >= 1,
            "errors": t["errors"] == 3,
            "retry_loop": t["retry_loops"] == 1,
            "ide tag stripped, redo caught": any(
                "покороче" in c["text"] for c in report["corrections"]
            ),
        }
        failed = [name for name, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(("PASS  " if ok else "FAIL  ") + name)
        if failed:
            print(f"\n{len(failed)} check(s) failed")
            print(json.dumps(t, ensure_ascii=False, indent=1))
            sys.exit(1)

        # pretty mode must not crash either
        out2 = subprocess.run(
            [sys.executable, str(SCANNER), "--project", str(project),
             "--days", "36500", "--format", "pretty", "--no-color"],
            env=env, capture_output=True, text=True, timeout=60,
        )
        assert out2.returncode == 0, f"pretty mode exited {out2.returncode}"
        print("PASS  pretty mode")

        out3 = subprocess.run(
            [sys.executable, str(SCANNER), "--project", str(project),
             "--days", "36500", "--format", "json",
             "--patterns", str(ROOT / "skill" / "patterns" / "example-es.json")],
            env=env, capture_output=True, text=True, timeout=60,
        )
        assert out3.returncode == 0, f"example patterns exited {out3.returncode}: {out3.stderr}"
        json.loads(out3.stdout)
        print("PASS  example pattern pack")

        bad_patterns = tmp / "bad-patterns.json"
        bad_patterns.write_text(json.dumps({"typo": ["no funciona"]}), encoding="utf-8")
        out4 = subprocess.run(
            [sys.executable, str(SCANNER), "--project", str(project),
             "--days", "36500", "--format", "json", "--patterns", str(bad_patterns)],
            env=env, capture_output=True, text=True, timeout=60,
        )
        assert out4.returncode != 0 and "unknown pattern class" in out4.stderr, (
            "bad pattern pack was not rejected"
        )
        print("PASS  bad pattern pack rejected")

        print("\nAll smoke checks passed.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
