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
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCANNER = ROOT / "skill" / "scripts" / "scan.py"
FIXTURE = ROOT / "tests" / "fixtures" / "session.jsonl"


def write_session(dest, cwd=None, age_days=0):
    """Copy the fixture, optionally recording a cwd and shifting every
    timestamp so the session ends `age_days` ago."""
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    end = datetime.now(timezone.utc) - timedelta(days=age_days)
    out = []
    for i, line in enumerate(lines):
        obj = json.loads(line)
        obj["timestamp"] = (end - timedelta(minutes=len(lines) - i)).isoformat()
        if cwd:
            obj["cwd"] = str(cwd)
        out.append(json.dumps(obj, ensure_ascii=False))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")


def scan_json(project, env, *extra):
    out = subprocess.run(
        [sys.executable, str(SCANNER), "--project", str(project),
         "--format", "json", *extra],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, f"scanner exited {out.returncode}: {out.stderr}"
    return json.loads(out.stdout)


def check_project_scope_and_window(tmp):
    """Siblings with a shared munged prefix: keep worktrees, drop other
    projects. Old history in a freshly touched file must not count."""
    base = tmp / "scope"
    project = base / "app"
    other = base / "app-v2"
    worktree = project / ".claude" / "worktrees" / "x"
    for d in (project, other, worktree):
        d.mkdir(parents=True)
    root = base / "cfg" / "projects"
    munge = lambda p: re.sub(r"[^A-Za-z0-9]", "-", str(p))
    write_session(root / munge(project) / "main.jsonl", cwd=project)
    write_session(root / munge(other) / "other.jsonl", cwd=other)
    write_session(root / munge(worktree) / "wt.jsonl", cwd=worktree)
    write_session(root / munge(project) / "old.jsonl", cwd=project, age_days=400)
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(base / "cfg")}

    report = scan_json(project, env, "--days", "30")
    ids = {s["id"] for s in report["sessions"]}
    checks = {
        "worktree sibling included": "wt" in ids,
        "prefix-sharing project excluded": "other" not in ids,
        "old history outside window dropped": "old" not in ids,
        "window counts only in-window events": report["totals"]["errors"] == 6,
    }
    report = scan_json(project, env, "--days", "30", "--limit", "1")
    checks["truncated when limit cuts files"] = report["truncated"] is True
    # three files touched recently: main, wt, and old (fresh mtime, old events)
    report = scan_json(project, env, "--days", "30", "--limit", "3")
    checks["not truncated at exact fit"] = report["truncated"] is False
    return checks


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
        checks.update(check_project_scope_and_window(tmp))
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
