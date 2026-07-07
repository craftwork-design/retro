#!/usr/bin/env python3
"""retro scan: extract friction signals from local Claude Code transcripts.

Reads ~/.claude/projects/<project>/*.jsonl and surfaces the moments where the
agent caused friction: user corrections, interruptions, permission denials,
tool errors, retry loops, and sessions abandoned right after a failure.

Output is JSON (consumed by the retro skill) or a pretty terminal summary.
Stdlib only. Nothing ever leaves your machine.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA_VERSION = 1
MAX_LINE_BYTES = 3_000_000

# --- correction heuristics -------------------------------------------------
# The scanner aims for recall; the skill (the model) judges precision.

STRONG_PHRASES = [
    "that's wrong", "that is wrong", "not what i asked", "not what i wanted",
    "not what i meant", "you ignored", "i already told", "i said", "i asked you",
    "undo this", "undo that", "revert this", "revert that", "stop doing",
    "don't do that", "why did you", "why would you", "still wrong",
    "still broken", "still not", "you keep", "you're not listening",
    "start over", "do it again", "try again", "as i said",
    "это не то", "не то что я просил", "я же сказал", "я же просил",
    "я просил", "откати", "верни как было", "верни обратно", "почему ты",
    "ты опять", "ты снова", "снова не так", "опять не так", "не слушаешь",
    "заново", "переделай", "исправь обратно",
]

WEAK_PHRASES = [
    "not what", "don't", "do not", "should not", "shouldn't",
    "не надо", "не нужно", "не так", "без спроса",
]

WEAK_WORDS = [
    "no", "nope", "wrong", "instead", "actually", "stop", "redo", "undo",
    "revert", "rather", "incorrect", "broke", "broken",
    "нет", "неправильно", "вместо", "стой", "хватит", "убери", "опять",
    "снова", "сломал", "сломалось", "неверно",
]

WEAK_WORD_RE = [re.compile(r"(?<!\w)" + re.escape(w) + r"(?!\w)") for w in WEAK_WORDS]

DENIAL_MARKERS = [
    "user doesn't want to proceed", "user doesn't want to take this action",
    "user rejected", "user declined", "user chose not to", "don't ask again",
    "the user denied", "permission to use", "requested permissions",
]

SKIP_TEXT_MARKERS = (
    "<command-name>", "<local-command", "<system-reminder>",
    "<task-notification>", "<ide_opened_file>", "<ide_selection>",
    "<ide_diagnostics>", "<teammate-message",
)

STOPWORDS = set(
    """the a an and or but is are was were be been to of in on for with this
    that it its as at by from not you your i we he she they them then than so
    just can could should would will do does did done have has had what which
    when where how all any some more most other into out up down over under
    let lets please make made need want try use used using file files code
    это что как для был была было быть его ее их мы вы они оно там тут если
    чтобы когда где только еще уже вот так там мне тебе нам вам меня тебя
    надо нужно можно давай сделай сделать есть нет да по на в с у к от до за
    же бы ли или но а и о об при про из под над без""".split()
)


def munge_path(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def excerpt(text, limit):
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def block_text(content):
    """Text from a message content field (string or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text") or "")
        return "\n".join(parts)
    return ""


def result_text(block):
    c = block.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(
            b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def correction_score(text):
    tl = " " + re.sub(r"\s+", " ", text.lower()) + " "
    score = 0
    for p in STRONG_PHRASES:
        if p in tl:
            score += 2
    for p in WEAK_PHRASES:
        if p in tl:
            score += 1
    for rx in WEAK_WORD_RE:
        if rx.search(tl):
            score += 1
    return min(score, 8)


def is_denial(text):
    tl = text.lower()
    return any(m in tl for m in DENIAL_MARKERS)


def tool_key(name, inp):
    """A short identity key for a tool call, used to spot repeats."""
    if not isinstance(inp, dict):
        return ""
    if name == "Bash":
        cmd = (inp.get("command") or "").strip().split("\n")[0]
        return excerpt(cmd, 80)
    for field in ("file_path", "path", "pattern", "url", "query", "skill"):
        if inp.get(field):
            return excerpt(str(inp[field]), 80)
    return ""


def parse_session(path, max_excerpt):
    s = {
        "id": path.stem,
        "user_msgs": 0,
        "tool_calls": 0,
        "errors": 0,
        "interrupts": 0,
        "corrections": [],
        "denials": [],
        "start": None,
        "end": None,
        "first_prompt": None,
        "cwd": None,
    }
    tool_uses = {}
    error_groups = {}  # (tool, key) -> {count, example}
    last_event = None
    prev_was_interrupt = False

    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return None

    with fh:
        for line in fh:
            if len(line) > MAX_LINE_BYTES:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(obj, dict) or obj.get("isSidechain"):
                continue

            ts = parse_ts(obj.get("timestamp"))
            if ts:
                s["start"] = s["start"] or ts
                s["end"] = ts
            if not s["cwd"] and obj.get("cwd"):
                s["cwd"] = obj["cwd"]

            otype = obj.get("type")
            msg = obj.get("message") or {}

            if otype == "assistant":
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_use":
                        name = b.get("name") or "?"
                        key = tool_key(name, b.get("input"))
                        tool_uses[b.get("id")] = (name, key)
                        s["tool_calls"] += 1
                        last_event = "tool_use"
                    elif b.get("type") == "text" and (b.get("text") or "").strip():
                        last_event = "assistant_text"

            elif otype == "user":
                content = msg.get("content")
                results = [
                    b for b in content
                    if isinstance(b, dict) and b.get("type") == "tool_result"
                ] if isinstance(content, list) else []

                if results:
                    for b in results:
                        name, key = tool_uses.get(b.get("tool_use_id"), ("?", ""))
                        if b.get("is_error"):
                            err = result_text(b)
                            if is_denial(err):
                                s["denials"].append({"tool": name, "key": key})
                                last_event = "denial"
                            else:
                                s["errors"] += 1
                                g = error_groups.setdefault(
                                    (name, key), {"count": 0, "example": ""}
                                )
                                g["count"] += 1
                                if not g["example"]:
                                    g["example"] = excerpt(err, 160)
                                last_event = "error"
                        else:
                            last_event = "tool_ok"
                    continue

                if obj.get("isMeta"):
                    continue
                text = block_text(content)
                if not text.strip():
                    continue
                if any(m in text for m in SKIP_TEXT_MARKERS) or text.startswith("Caveat:"):
                    continue
                if text.startswith("This session is being continued"):
                    continue
                if text.startswith("[Request interrupted"):
                    s["interrupts"] += 1
                    prev_was_interrupt = True
                    last_event = "interrupt"
                    continue

                is_first = s["first_prompt"] is None
                if is_first:
                    s["first_prompt"] = excerpt(text, 160)
                s["user_msgs"] += 1

                if not is_first:
                    score = correction_score(text)
                    # long pasted texts trip weak markers by accident;
                    # demand stronger evidence the longer the message is
                    threshold = 2 if len(text) <= 400 else (4 if len(text) <= 1500 else 6)
                    if score >= threshold or (score >= 1 and prev_was_interrupt):
                        s["corrections"].append({
                            "ts": ts.isoformat() if ts else None,
                            "score": score,
                            "after_interrupt": prev_was_interrupt,
                            "text": excerpt(text, max_excerpt),
                        })
                        last_event = "correction"
                    else:
                        last_event = "user_msg"
                prev_was_interrupt = False

    # retry loops: the same call FAILING 3+ times in one session
    s["retry_loops"] = [
        {"tool": t, "key": k, "count": v["count"]}
        for (t, k), v in error_groups.items()
        if v["count"] >= 3 and t != "?"
    ]
    s["error_groups"] = [
        {"tool": t, "key": k, "count": v["count"], "example": v["example"]}
        for (t, k), v in error_groups.items()
        if t != "?"
    ]
    s["abandoned"] = (
        last_event in ("error", "correction", "interrupt", "denial")
        and (s["errors"] + len(s["corrections"])) > 0
    )
    s["friction"] = (
        3 * len(s["corrections"])
        + 2 * len(s["denials"])
        + s["errors"]
        + 2 * len(s["retry_loops"])
        + (4 if s["abandoned"] else 0)
    )
    return s


def session_files(project_dirs, days, limit):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    files = []
    for d in project_dirs:
        for f in d.glob("*.jsonl"):
            if f.name.startswith("agent-"):
                continue
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if mtime >= cutoff:
                files.append((mtime, f))
    files.sort(reverse=True)
    return [f for _, f in files[:limit]]


def aggregate(sessions, days, project_label):
    corrections = []
    denial_counter = Counter()
    error_counter = {}
    retry_loops = []
    term_counter = Counter()

    for s in sessions:
        for c in s["corrections"]:
            corrections.append({**c, "session": s["id"]})
            for w in re.findall(r"[\w']+", c["text"].lower(), re.UNICODE):
                if len(w) >= 3 and w not in STOPWORDS and not w.isdigit():
                    term_counter[w] += 1
        for d in s["denials"]:
            denial_counter[(d["tool"], d["key"])] += 1
        for g in s["error_groups"]:
            key = (g["tool"], g["key"])
            e = error_counter.setdefault(key, {"count": 0, "example": g["example"]})
            e["count"] += g["count"]
        for r in s["retry_loops"]:
            retry_loops.append({**r, "session": s["id"]})

    corrections.sort(key=lambda c: c.get("ts") or "", reverse=True)
    retry_loops.sort(key=lambda r: r["count"], reverse=True)
    error_loops = sorted(
        (
            {"tool": t, "key": k, "count": v["count"], "example": v["example"]}
            for (t, k), v in error_counter.items()
        ),
        key=lambda e: e["count"],
        reverse=True,
    )
    denials_top = sorted(
        ({"tool": t, "key": k, "count": c} for (t, k), c in denial_counter.items()),
        key=lambda d: d["count"],
        reverse=True,
    )

    session_rows = sorted(sessions, key=lambda s: s["friction"], reverse=True)

    return {
        "schema_version": SCHEMA_VERSION,
        "project": project_label,
        "window_days": days,
        "sessions_scanned": len(sessions),
        "totals": {
            "user_msgs": sum(s["user_msgs"] for s in sessions),
            "tool_calls": sum(s["tool_calls"] for s in sessions),
            "corrections": sum(len(s["corrections"]) for s in sessions),
            "interrupts": sum(s["interrupts"] for s in sessions),
            "denials": sum(len(s["denials"]) for s in sessions),
            "errors": sum(s["errors"] for s in sessions),
            "retry_loops": len(retry_loops),
            "abandoned_after_failure": sum(1 for s in sessions if s["abandoned"]),
        },
        "top_correction_terms": [
            {"term": w, "count": c} for w, c in term_counter.most_common(12)
        ],
        "corrections": corrections[:60],
        "denials_top": denials_top[:25],
        "error_loops": [e for e in error_loops if e["count"] >= 2][:25],
        "retry_loops": retry_loops[:25],
        "sessions": [
            {
                "id": s["id"],
                "start": s["start"].isoformat() if s["start"] else None,
                "cwd": s["cwd"],
                "first_prompt": s["first_prompt"],
                "user_msgs": s["user_msgs"],
                "tool_calls": s["tool_calls"],
                "corrections": len(s["corrections"]),
                "denials": len(s["denials"]),
                "errors": s["errors"],
                "interrupts": s["interrupts"],
                "abandoned": s["abandoned"],
                "friction": s["friction"],
            }
            for s in session_rows[:100]
        ],
    }


# --- pretty output -----------------------------------------------------------

def c(code, text, color):
    return f"\033[{code}m{text}\033[0m" if color else text


def print_pretty(report, color):
    t = report["totals"]
    dim = lambda x: c("2", x, color)
    bold = lambda x: c("1", x, color)
    red = lambda x: c("31", x, color)
    yellow = lambda x: c("33", x, color)
    cyan = lambda x: c("36", x, color)

    print()
    print(bold("  retro") + dim("  ·  what your agent got wrong lately"))
    print(dim(f"  project: {report['project']}   sessions: {report['sessions_scanned']}"
              f"   window: {report['window_days']}d"))
    print(dim("  " + "─" * 56))
    rows = [
        ("corrections", t["corrections"], "you told the agent it was wrong", red),
        ("interrupts", t["interrupts"], "you hit Esc mid-action", red),
        ("denials", t["denials"], "permission prompts you rejected", yellow),
        ("errors", t["errors"], "failed tool calls", yellow),
        ("retry loops", t["retry_loops"], "same call failed 3+ times", yellow),
        ("abandoned", t["abandoned_after_failure"], "sessions that ended on a failure", red),
    ]
    for label, value, note, tint in rows:
        v = tint(f"{value:>5}") if value else dim(f"{value:>5}")
        print(f"  {label:<13}{v}   {dim(note)}")
    print(dim("  " + "─" * 56))

    if report["top_correction_terms"]:
        terms = "  ".join(
            f"{w['term']}({w['count']})" for w in report["top_correction_terms"][:8]
        )
        print(f"  {bold('words you use when correcting the agent:')}")
        print(f"  {cyan(terms)}")
        print()

    if report["corrections"]:
        print(bold("  recent corrections"))
        for cor in report["corrections"][:8]:
            mark = red("↩ esc ") if cor["after_interrupt"] else dim("      ")
            print(f"  {mark}{excerpt(cor['text'], 92)}")
        print()

    if report["error_loops"]:
        print(bold("  repeat failures (same call, failed 2+ times)"))
        for e in report["error_loops"][:6]:
            times = yellow(str(e["count"]) + "×")
            print(f"  {times} {e['tool']}: {dim(excerpt(e['key'], 70))}")
        print()

    if report["sessions"]:
        top = [s for s in report["sessions"] if s["friction"] > 0][:5]
        if top:
            print(bold("  highest-friction sessions"))
            for s in top:
                flag = red(" ✗ abandoned") if s["abandoned"] else ""
                print(f"  {dim(s['id'][:8])}  friction {s['friction']:>3}  "
                      f"{excerpt(s['first_prompt'] or '', 60)}{flag}")
            print()

    print(dim("  run /retro in Claude Code to turn this into CLAUDE.md fixes"))
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default=os.getcwd(),
                    help="project path to analyze (default: cwd)")
    ap.add_argument("--all", action="store_true", help="scan all projects")
    ap.add_argument("--days", type=int, default=30, help="lookback window (default 30)")
    ap.add_argument("--limit", type=int, default=200, help="max sessions to scan")
    ap.add_argument("--max-excerpt", type=int, default=220)
    ap.add_argument("--format", choices=["json", "pretty"], default="pretty")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    claude_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    projects_root = claude_dir / "projects"
    if not projects_root.is_dir():
        sys.exit(f"retro: no transcripts found at {projects_root}")

    if args.all:
        dirs = [d for d in projects_root.iterdir() if d.is_dir()]
        label = "all projects"
    else:
        # walk up from the given path: the user may be in a subdirectory
        # of the project Claude Code was launched from
        candidates = [Path(args.project).resolve()]
        candidates += list(candidates[0].parents)
        d = next(
            (projects_root / munge_path(p) for p in candidates
             if (projects_root / munge_path(p)).is_dir()),
            None,
        )
        if d is None:
            sys.exit(
                f"retro: no transcripts for {args.project} or any parent directory\n"
                f"       (looked in {projects_root})\n"
                f"       try --all to scan every project"
            )
        dirs = [d]
        label = d.name.rsplit("-", 1)[-1] or d.name

    files = session_files(dirs, args.days, args.limit)
    sessions = [s for f in files if (s := parse_session(f, args.max_excerpt))]
    sessions = [s for s in sessions if s["user_msgs"] > 0 or s["tool_calls"] > 0]

    report = aggregate(sessions, args.days, label)

    if args.format == "json":
        json.dump(report, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        print_pretty(report, color=sys.stdout.isatty() and not args.no_color)


if __name__ == "__main__":
    main()
