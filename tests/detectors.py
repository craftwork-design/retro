#!/usr/bin/env python3
"""Table test for the lexical detectors: phrases that must fire and phrases
that must stay quiet. Add a row for every detection miss or false positive
you fix. Run: python3 tests/detectors.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skill" / "scripts"))
import scan  # noqa: E402

# (message, reason expected in classify_user_msg, or None = must not fire)
CLASSIFY = [
    ("не работает, в консоли ошибка", "failure_report"),
    ("приложение зависает на старте", "failure_report"),
    ("опять вылетает при сохранении", "failure_report"),
    ("всё поломалось после твоего коммита", "failure_report"),
    ("it crashed again", "failure_report"),
    ("я же просил не трогать конфиг", "correction"),
    ("that's not what i asked", "correction"),
    ("переделай хедер", "redo"),
    ("компактнее", "redo"),
    ("покороче", "redo"),
    ("обнови зависимости в package.json", None),
    ("это зависит от версии ноды", None),
    ("раньше это зависело от env", None),
    ("добавь вылетающее меню слева", None),
    ("далее", None),
    ("более", None),
    ("добавь обработку ошибок", None),
]

NUDGE = [
    ("продолжай", True),
    ("continue", True),
    ("готово?", True),
    ("done?", True),
    ("ну что", True),
    ("готово", False),  # the user finished a manual step
    ("done", False),
    ("ready", False),
]

# (text, tokens that must be present)
TOKENS = [
    ("запусти тесты через pnpm", {"запуст", "тест", "pnpm"}),
    ("la función está rota otra vez", {"función", "está", "rota"}),
    ("don't commit the lockfile", {"don't", "commit", "lockfile"}),
    ("修复登录页面的错误", {"修复", "登录", "错误"}),
]


def main():
    fails = []
    for text, want in CLASSIFY:
        score, reasons = scan.classify_user_msg(text)
        if want is None:
            if score >= 2:
                fails.append(f"false positive {text!r}: score {score} {reasons}")
        elif want not in reasons or score < 2:
            fails.append(f"missed {text!r}: want {want}, got {score} {reasons}")
    for text, want in NUDGE:
        got = bool(scan.hits(scan.NUDGE_RE, text.lower()))
        if got != want:
            fails.append(f"nudge {text!r}: want {want}, got {got}")
    for text, want in TOKENS:
        got = scan.tokens_of(text)
        if not want <= got:
            fails.append(f"tokens {text!r}: missing {sorted(want - got)} in {sorted(got)}")

    total = len(CLASSIFY) + len(NUDGE) + len(TOKENS)
    print(f"checked {total} detector cases")
    if fails:
        print("\n".join("FAIL  " + f for f in fails))
        sys.exit(1)
    print("PASS  all detector cases")


if __name__ == "__main__":
    main()
