#!/usr/bin/env python3
"""Guard the landing-page hero art: extract each ARTS[].h template, strip the
<span> tags, and assert no broken chars, no absurdly wide lines, and — for
bordered (NFO-style) arts — every line the same width. Run: python3 tests/art_check.py

This exists because hand-counting box widths shipped a broken FRICTION MONITOR
once. Never again."""

import re
import sys
from pathlib import Path

HTML = Path(__file__).resolve().parent.parent / "docs" / "index.html"
MAX_WIDTH = 42  # hero pre scrolls, but anything wider is a mistake

TAG = re.compile(r"<[^>]+>")


def extract_arts(js):
    """Pull each art's `h:` concatenated string literal out of the ARTS array."""
    arts = []
    # each art block starts at "h:" and the string is a run of '...' + '...'
    for m in re.finditer(r"\bh:\s*((?:'(?:[^'\\]|\\.)*'\s*\+\s*)*'(?:[^'\\]|\\.)*')", js):
        parts = re.findall(r"'((?:[^'\\]|\\.)*)'", m.group(1))
        s = "".join(parts)
        s = s.replace("\\n", "\n").replace("\\'", "'").replace("\\\\", "\\")
        arts.append(s)
    return arts


def main():
    html = HTML.read_text(encoding="utf-8")
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    arts = extract_arts(js)
    if len(arts) < 5:
        sys.exit(f"art_check: only found {len(arts)} arts, expected >=5 — parser drift?")

    fails = []
    for idx, art in enumerate(arts):
        lines = [TAG.sub("", ln) for ln in art.split("\n")]
        if "�" in art:
            fails.append(f"art {idx}: contains a replacement char (broken glyph)")
        widths = [len(ln) for ln in lines]
        for i, w in enumerate(widths):
            if w > MAX_WIDTH:
                fails.append(f"art {idx} line {i}: width {w} > {MAX_WIDTH}: {lines[i]!r}")
        # bordered art: first line is all box/dash border chars -> all lines equal
        first = lines[0].strip()
        if first and all(ch in "-─═╔╗╚╝," for ch in first) and len(first) > 8:
            content = [w for w in widths[:-1] if w > 0]  # last line often a caption
            if len(set(content)) > 1:
                fails.append(
                    f"art {idx}: bordered but line widths differ: {sorted(set(content))}")

    print(f"checked {len(arts)} hero arts")
    if fails:
        print("\n".join("FAIL  " + f for f in fails))
        sys.exit(1)
    print("PASS  no broken glyphs, no over-wide lines, borders aligned")


if __name__ == "__main__":
    main()
