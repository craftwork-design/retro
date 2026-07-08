#!/usr/bin/env python3
"""retro scan: extract friction signals from local Claude Code transcripts.

Reads ~/.claude/projects/<project>/*.jsonl and surfaces the moments where the
agent caused friction: user corrections and failure reports, assistant
self-admissions ("you're right"), post-interrupt redirections, nudges
("continue"), rule requests ("remember, from now on..."), instructions the
user repeats across sessions, permission denials, tool errors, retry loops,
and sessions abandoned right after a failure.

Output is JSON (consumed by the retro skill) or a pretty terminal summary.
Stdlib only. Nothing ever leaves your machine.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

VERSION = "0.3.0"
SCHEMA_VERSION = 3
MAX_LINE_CHARS = 50_000_000


def rx(*patterns):
    return [re.compile(p, re.I | re.U) for p in patterns]


# --- user-message signal patterns -------------------------------------------
# The scanner aims for recall; the skill (the model) judges precision.
# Every hit is a CANDIDATE with a reason tag, not a verdict.

# explicit corrections: "that's wrong", "я же сказал", "откати"
CORRECTION_RE = rx(
    r"that'?s (just )?wrong", r"that is wrong", r"not what i (asked|wanted|meant)",
    r"you ignored", r"(?<![a-z])i already (told|said|asked)\b",
    r"(?<![a-z])i (told|said|asked) you\b",
    r"\bundo (this|that|it)\b", r"\brevert (this|that|it)\b", r"stop doing",
    r"don'?t do (that|this)", r"still (wrong|broken)\b",
    r"still not (working|right|fixed)\b",
    r"you keep (doing|making|adding|ignoring|changing|breaking)",
    r"you'?re not listening", r"start over", r"\bas i said\b",
    r"^no[,.!]? (that|this|it|don'?t|do not|stop|wait|wrong|not)\b", r"^no[.!]?$",
    r"^stop[.!]?$", r"^stop (it|that)\b",
    r"это не то\b", r"не то,? что я просил", r"я же (сказал|просил|говорил)",
    r"я (тебя )?просил", r"откат(и|ите)(?!\w)", r"верн(и|ите)(?!\w)",
    r"почему ты", r"ты (опять|снова)", r"(опять|снова) не (так|то)\b",
    r"не слушаешь", r"начни заново", r"^нет\b", r"^стоп(?!\w)", r"^стой(?!\w)",
    r"^не (делай|пиши|надо|нужно)", r"хватит\b", r"^так стоп\b",
)

# the user reports something you built/claimed done is broken
FAILURE_RE = rx(
    r"не (работает|сработал\w*|запускается|запустил\w*|открывается|включается|"
    r"вызывается|копир\w+|грузится|загружа\w+|сохраня\w+|отобража\w+|показыва\w+|"
    r"подключа\w+|видно|вижу|появля\w+|обновля\w+)",
    r"(ошибк|краш|сломал|глюч|глюк|завис|вылет|отвал)\w*",
    r"\bупал[ао]?\b", r"закрыл(ся|ась|ось)",
    r"doesn'?t work", r"not working", r"is broken", r"\bcrash\w*", r"still fails?\b",
    r"error again\b", r"same (error|issue|problem)( again| still)?\b",
    r"still (get|getting|see|seeing|throws?) ",
)

# redo requests phrased as bare imperatives / comparatives: "компактнее",
# "поправь хедер", "давай покороче"
REDO_RE = rx(
    r"(?<!\w)(передела\w+|передизайн\w+|перепиш\w+|переработ\w+|поправ\w+|"
    r"исправ\w+|убер(и|ите)(?!\w)|убира(й|йте)(?!\w)|redo\b|rewrite\b|"
    r"перегенер\w+)",
    r"(?<!\w)(покороче|попроще|компактнее|поменьше|побольше|поинтереснее|"
    r"покачественнее|поаккуратнее|подлиннее|поразвернутее|развернутее|"
    r"проще|короче|компактней)(?!\w)",
    r"(давай|сделай) (чуть|немного|по)?\s?(короче|проще|меньше|больше|компактнее|развернуте)",
    r"(make it|a bit) (shorter|simpler|smaller|cleaner|longer)",
)

# weak markers: only count toward score, never fire alone
WEAK_RE = rx(
    r"(?<!\w)(nope|wrong|instead|actually|rather|incorrect)(?!\w)",
    r"try again\b", r"why (did|would) you", r"still not\b", r"you keep\b",
    r"(?<![a-z])i (told|said|asked)\b",
    r"(?<!\w)(неправильно|неверно|вместо|заново|не надо|не нужно|не так)(?!\w)",
)

# frustration: boosts severity of whatever else fired
FRUSTRATION_RE = rx(
    r"умоляю", r"сколько (можно|раз)", r"how many times", r"!{3,}",
    r"(?<!\w)хрень(?!\w)", r"(бля|нахуй|пиздец|ебан|заеб|охуе|fuck|wtf)\w*",
)

# the user dictates a standing rule out loud: ready-made CLAUDE.md material
RULE_REQUEST_RE = rx(
    r"запомни(?!\w)", r"отныне", r"с этого момента", r"запиши (себе|это)",
    r"(?<!\w)всегда (делай|пиши|используй|ставь|добавляй|проверяй|отвечай|запускай)",
    r"больше (так )?(никогда )?не делай", r"никогда (больше )?не (делай|пиши|используй|ставь)",
    r"from now on", r"^remember (to|that|this)\b", r"remember this:",
    r"always (do|use|write|run|reply|answer|start|put)\b",
    r"never (do|use|write|run|touch|commit)\b",
)

# bare "continue" messages: the agent stalled and had to be prodded
NUDGE_RE = rx(
    r"^(продолжай|продолжи|продолжаем|дальше|давай дальше|continue|go on|"
    r"proceed|keep going)[.!…\s]*$",
    r"^(закончил|закончила|готово|ну что|done|finished|ready)\??[.!\s]*$",
)

# benign post-interrupt messages: not redirections
CONTINUATION_RE = rx(
    r"^(продолжай|продолжи|давай|дальше|continue|go on|да|ага|запускай|ок|okay|ok|yes)[.!)\s…]*$",
)

# the assistant claiming success; a failure report right after one is the
# strongest friction signal there is
SUCCESS_CLAIM_RE = rx(
    r"(?<!\w)(готово|сделано|исправил|исправлено|починил|запущено|заработало|"
    r"все работает|всё работает|done|fixed|deployed|completed|working now|"
    r"should work now|works now|ready)(?!\w)",
)

# assistant self-admissions: the agent conceding it was wrong
ADMISSION_RE = rx(
    r"you'?re (absolutely |completely |totally )?right\b", r"\bmy (mistake|bad|error)\b",
    r"\bi apologi[sz]e\b", r"\bgood catch\b",
    r"(?<!\w)(ты|вы) (абсолютно |совершенно |полностью )?прав\w*",
    r"извиняюсь", r"прошу прощен", r"(?<!\w)виноват(?!\w)",
)
ADMISSION_ANCHORED_RE = rx(r"^(справедлив\w*|согласен)[,.!: ]")

# extendable via --patterns lang-pack JSON: {"correction": ["regex", ...], ...}
PATTERN_CLASSES = {
    "correction": CORRECTION_RE,
    "failure_report": FAILURE_RE,
    "redo": REDO_RE,
    "weak": WEAK_RE,
    "frustration": FRUSTRATION_RE,
    "rule_request": RULE_REQUEST_RE,
    "nudge": NUDGE_RE,
    "continuation": CONTINUATION_RE,
    "admission": ADMISSION_RE,
}


def load_patterns(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("patterns file must be a JSON object of {class: [regex, ...]}")
    for cls, pats in data.items():
        if cls.startswith("_"):
            continue
        if cls not in PATTERN_CLASSES:
            known = ", ".join(sorted(PATTERN_CLASSES))
            raise ValueError(f"unknown pattern class {cls!r}; expected one of: {known}")
        if not isinstance(pats, list):
            raise ValueError(f"pattern class {cls!r} must be a list of regex strings")
        compiled = []
        for i, pat in enumerate(pats):
            if not isinstance(pat, str):
                raise ValueError(f"pattern {cls}[{i}] must be a string")
            compiled.append(re.compile(pat, re.I | re.U))
        PATTERN_CLASSES[cls].extend(compiled)


DENIAL_MARKERS = [
    "user doesn't want to proceed", "user doesn't want to take this action",
    "user rejected", "user declined", "user chose not to", "don't ask again",
    "the user denied", "permission to use", "requested permissions",
    "tool permission request failed",
]
CANCEL_MARKERS = [
    "cancelled: parallel tool call", "request was aborted",
    "tool use was interrupted",
]

# harness-injected tag blocks stripped from user text (the remainder is real)
TAG_STRIP_RE = re.compile(
    r"<(ide_opened_file|ide_selection|ide_diagnostics|system-reminder|"
    r"task-notification|teammate-message|local-command-stdout|"
    r"local-command-stderr|ide_diff)\b[^>]*>.*?</\1>",
    re.S | re.I,
)
SKIP_IF_LEFT = ("<command-name>", "<local-command", "<command-message>")

STOPWORDS = set(
    """the a an and or but is are was were be been to of in on for with this
    that it its as at by from not you your i we he she they them then than so
    just can could should would will do does did done have has had what which
    when where how all any some more most other into out up down over under
    let lets please make made need want try use used using file files code
    это что как для был была было быть его ее их мы вы они оно там тут если
    чтобы когда где только еще уже вот так там мне тебе нам вам меня тебя
    надо нужно можно давай сделай сделать есть нет да по на в с у к от до за
    же бы ли или но а и о об при про из под над без все всё сам сама сами
    вроде очень чуть теперь давай делай сделай сделать пусть просто тоже
    everything anything nothing okay yes also very really now then here
    там тут так как""".split()
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


def clean_user_text(raw):
    """Strip harness-injected tags; return the genuine user text (or "")."""
    if any(m in raw for m in SKIP_IF_LEFT):
        return ""
    text = TAG_STRIP_RE.sub(" ", raw).strip()
    if not text:
        return ""
    if text.startswith("Caveat:") or text.startswith("This session is being continued"):
        return ""
    return text


def hits(regexes, text):
    return sum(1 for r in regexes if r.search(text))


def classify_user_msg(text):
    """Return (score, reasons) for one genuine user message."""
    tl = re.sub(r"\s+", " ", text.lower()).strip()
    score, reasons = 0, []
    n = hits(CORRECTION_RE, tl)
    if n:
        score += 2 * min(n, 2)
        reasons.append("correction")
    if hits(FAILURE_RE, tl):
        score += 2
        reasons.append("failure_report")
    if hits(REDO_RE, tl):
        score += 2
        reasons.append("redo")
    w = hits(WEAK_RE, tl)
    if w:
        score += min(w, 2)
    if hits(FRUSTRATION_RE, tl):
        score += 3
        reasons.append("frustration")
    # one-word comparative like "компактнее" / "короче"
    if len(tl) <= 30 and re.fullmatch(r"(по)?[а-яё]+(ее|ей|че)[.!…]*", tl):
        score += 2
        if "redo" not in reasons:
            reasons.append("redo")
    return score, reasons


def is_denial(text):
    tl = text.lower()
    return any(m in tl for m in DENIAL_MARKERS)


def is_cancel(text):
    tl = text.lower()
    return any(m in tl for m in CANCEL_MARKERS)


def tool_key(name, inp):
    if not isinstance(inp, dict):
        return ""
    if name == "Bash":
        cmd = (inp.get("command") or "").strip().split("\n")[0]
        return excerpt(cmd, 80)
    for field in ("file_path", "path", "pattern", "url", "query", "skill"):
        if inp.get(field):
            return excerpt(str(inp[field]), 80)
    return ""


# light suffix-stripping stemmer: folds "запусти/запустил/запускай" and
# "commit/commits/committed" into one token for clustering. O(1) per word.
_RU_SUFFIXES = sorted(
    ("иями ями ами иях ях ах ией ого его ому ему ыми ими ете ите йте ешь ишь "
     "ает яет ует ают яют уют ать ять еть ить уть ай яй ой ый ий ая яя ое ее "
     "ие ые ов ев ом ем ам ям ей ью ья ье ал ял ел ил ла ло ли ся сь ем им "
     "ит ат ят ут ют у ю а я о е ы и ь").split(),
    key=len, reverse=True,
)
_EN_SUFFIXES = ("ing", "ed", "es", "ly", "s")


def stem(w):
    if w[0].isascii():
        for suf in _EN_SUFFIXES:
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                return w[: -len(suf)]
        return w
    for suf in _RU_SUFFIXES:
        # short suffixes fold aggressively (нашел→наш): demand longer stems
        keep = 4 if len(suf) <= 2 else 3
        if w.endswith(suf) and len(w) - len(suf) >= keep:
            return w[: -len(suf)]
    return w


def tokens_of(text):
    out = set()
    for w in re.findall(r"[a-zа-яё0-9']+", text.lower()):
        if len(w) < 3 or w in STOPWORDS:
            continue
        s = stem(w)
        if s not in STOPWORDS:  # stems can collapse into stopwords (такой→так)
            out.add(s)
    return out


def parse_session(path, max_excerpt):
    s = {
        "id": path.stem,
        "title": None,
        "user_msgs": 0,
        "tool_calls": 0,
        "errors": 0,
        "interrupts": 0,
        "nudges": 0,
        "corrections": [],
        "admissions": [],
        "rule_requests": [],
        "denials": [],
        "start": None,
        "end": None,
        "first_prompt": None,
        "cwd": None,
        "_msgs": [],  # genuine user msgs kept for cross-session clustering
    }
    tool_uses = {}
    error_groups = {}
    last_event = None
    prev_was_interrupt = False
    prev_user_text = None
    prev_user_norm = None
    admission_since_user = False
    last_assistant_claim = False

    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return None

    with fh:
        for line in fh:
            if len(line) > MAX_LINE_CHARS:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(obj, dict) or obj.get("isSidechain"):
                continue

            otype = obj.get("type")

            if otype in ("custom-title", "ai-title"):
                title = obj.get("customTitle") or obj.get("aiTitle") or obj.get("title")
                if title and (otype == "custom-title" or not s["title"]):
                    s["title"] = excerpt(str(title), 120)
                continue

            ts = parse_ts(obj.get("timestamp"))
            if ts:
                s["start"] = s["start"] or ts
                s["end"] = ts
            if not s["cwd"] and obj.get("cwd"):
                s["cwd"] = obj["cwd"]

            msg = obj.get("message") or {}

            if otype == "assistant":
                if obj.get("isApiErrorMessage"):
                    continue
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                event_claim = None  # tri-state: None = no text blocks in event
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_use":
                        name = b.get("name") or "?"
                        key = tool_key(name, b.get("input"))
                        tool_uses[b.get("id")] = (name, key)
                        s["tool_calls"] += 1
                        last_event = "tool_use"
                    elif b.get("type") == "text":
                        text = (b.get("text") or "").strip()
                        if not text:
                            continue
                        last_event = "assistant_text"
                        event_claim = bool(event_claim) or bool(
                            hits(SUCCESS_CLAIM_RE, text.lower())
                        )
                        if not admission_since_user and prev_user_text:
                            tl = text.lower().lstrip()
                            if hits(ADMISSION_RE, tl) or hits(ADMISSION_ANCHORED_RE, tl):
                                s["admissions"].append({
                                    "ts": ts.isoformat() if ts else None,
                                    "user_text": excerpt(prev_user_text, max_excerpt),
                                    "admission": excerpt(text, 160),
                                })
                                admission_since_user = True
                if event_claim is not None:
                    last_assistant_claim = event_claim

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
                            elif is_cancel(err):
                                last_event = "interrupt"
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
                    # fall through: the same event may carry genuine user text
                    # alongside tool_results (block_text ignores results)

                if obj.get("isMeta"):
                    continue
                raw = block_text(content)
                if not raw.strip():
                    continue
                if raw.lstrip().startswith("[Request interrupted"):
                    s["interrupts"] += 1
                    prev_was_interrupt = True
                    last_event = "interrupt"
                    continue
                text = clean_user_text(raw)
                if not text:
                    continue

                is_first = s["first_prompt"] is None
                if is_first:
                    s["first_prompt"] = excerpt(text, 160)
                s["user_msgs"] += 1
                tl = re.sub(r"\s+", " ", text.lower()).strip()

                if len(text) <= 600 and hits(RULE_REQUEST_RE, tl):
                    s["rule_requests"].append({
                        "ts": ts.isoformat() if ts else None,
                        "text": excerpt(text, max_excerpt),
                    })

                nudge = bool(hits(NUDGE_RE, tl))
                if nudge and not prev_was_interrupt and not is_first:
                    s["nudges"] += 1
                    last_event = "user_msg"
                    prev_user_text = text
                    # prev_user_norm intentionally NOT updated: a nudge between
                    # two identical pastes must not break repeat detection
                    admission_since_user = False
                    last_assistant_claim = False
                    continue

                if not is_first:
                    score, reasons = classify_user_msg(text)
                    if last_assistant_claim and (
                        "failure_report" in reasons or "correction" in reasons
                    ):
                        reasons.append("after_success_claim")
                        score += 2
                    if prev_was_interrupt and not hits(CONTINUATION_RE, tl):
                        reasons.append("post_interrupt")
                        score = max(score, 2)
                    if prev_user_norm and tl[:200] == prev_user_norm and len(tl) > 20:
                        reasons.append("repeat_paste")
                        score = max(score, 2)
                    # long pasted texts trip markers by accident; demand more
                    threshold = 2 if len(text) <= 400 else (4 if len(text) <= 1500 else 6)
                    if reasons and (
                        score >= threshold
                        or "post_interrupt" in reasons
                        or "repeat_paste" in reasons
                    ):
                        s["corrections"].append({
                            "ts": ts.isoformat() if ts else None,
                            "score": score,
                            "reasons": reasons,
                            "after_interrupt": prev_was_interrupt,
                            "text": excerpt(text, max_excerpt),
                        })
                        last_event = "correction"
                    else:
                        last_event = "user_msg"

                # first prompts included: session-opener repeats are exactly
                # the recurring-task pattern we hunt for
                toks = tokens_of(text)
                if 3 <= len(toks) <= 60 and len(text) <= 1200 \
                        and not text.startswith(("[", "/")):
                    s["_msgs"].append({
                        "tokens": toks,
                        "text": excerpt(text, 120),
                        "session": s["id"],
                        "ts": ts.isoformat() if ts else None,
                    })

                prev_was_interrupt = False
                prev_user_text = text
                prev_user_norm = tl[:200]
                admission_since_user = False
                last_assistant_claim = False

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
        + 2 * len(s["admissions"])
        + 2 * len(s["denials"])
        + s["errors"]
        + 2 * len(s["retry_loops"])
        + 2 * max(0, s["nudges"] - 1)
        + (4 if s["abandoned"] else 0)
    )
    return s


def cluster_repeats(msgs):
    """Cross-session near-duplicate user instructions (token-set Jaccard)."""
    n = len(msgs)
    if n < 2:
        return []
    df = Counter(t for m in msgs for t in m["tokens"])
    maxdf = max(4, n // 8)
    index = defaultdict(list)
    for i, m in enumerate(msgs):
        for t in m["tokens"]:
            if df[t] <= maxdf:
                index[t].append(i)

    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    seen_pairs = set()
    for ids in index.values():
        if len(ids) > 60:
            continue
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                pair = (ids[a], ids[b])
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                ta, tb = msgs[pair[0]]["tokens"], msgs[pair[1]]["tokens"]
                inter = len(ta & tb)
                # binary Jaccard on stemmed tokens; do NOT down-weight
                # frequent tokens here — repeated instructions are frequent
                # by definition, that's the whole point. Tiny token sets
                # need more shared tokens or transitive union-find chains
                # unrelated messages together.
                need = 3 if min(len(ta), len(tb)) <= 4 else 2
                if inter >= need and inter / len(ta | tb) >= 0.5:
                    parent[find(pair[0])] = find(pair[1])

    clusters = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(i)

    out = []
    for ids in clusters.values():
        if len(ids) < 2:
            continue
        sessions = {msgs[i]["session"] for i in ids}
        if len(sessions) < 2:
            continue
        out.append({
            "count": len(ids),
            "sessions": len(sessions),
            "examples": [
                {"text": msgs[i]["text"], "session": msgs[i]["session"],
                 "ts": msgs[i]["ts"]}
                for i in ids[:4]
            ],
        })
    out.sort(key=lambda c: (c["sessions"], c["count"]), reverse=True)
    return out[:15]


def session_files(project_dirs, days, limit):
    cutoff = datetime.now(timezone.utc) - timedelta(days=min(days, 36500))
    per_dir = []
    for d in project_dirs:
        files = []
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
        if files:
            per_dir.append(files)
    # round-robin newest-first across dirs, so one busy project can't
    # starve the others out of the --limit budget
    out, rank = [], 0
    while len(out) < limit and any(rank < len(fs) for fs in per_dir):
        for fs in per_dir:
            if rank < len(fs) and len(out) < limit:
                out.append(fs[rank][1])
        rank += 1
    return out


def is_synthetic_dir(d):
    """Headless/SDK agent scratch dirs that would pollute --all stats."""
    return (
        d.name == "-"
        or d.name.startswith("-private-var-folders")
        or d.name.startswith("-private-tmp-")
        or d.name.startswith("-tmp-")
        or d.name.startswith("-var-folders")
    )


def aggregate(sessions, days, project_label):
    corrections, admissions, rule_requests = [], [], []
    denial_counter = Counter()
    error_counter = {}
    retry_loops = []
    term_counter = Counter()
    all_msgs = []

    # detector marker words would just echo back as "top terms"
    marker_terms = set(
        """работает сработало ошибка ошибку вижу видно почему поправь исправь
        перепиши переделай передела стоп стой верни хватит заново вместо
        неправильно неверно опять снова крашнулось сломалось сломал упал
        wrong broken error crash instead actually stop undo revert again
        сделал запускается запустилось открывается""".split()
    )
    for s in sessions:
        for c in s["corrections"]:
            corrections.append({**c, "session": s["id"]})
            for w in re.findall(r"[\w']+", c["text"].lower(), re.UNICODE):
                if (len(w) >= 3 and w not in STOPWORDS
                        and w not in marker_terms and not w.isdigit()):
                    term_counter[w] += 1
        for a in s["admissions"]:
            admissions.append({**a, "session": s["id"]})
        for r in s["rule_requests"]:
            rule_requests.append({**r, "session": s["id"]})
        for d in s["denials"]:
            denial_counter[(d["tool"], d["key"])] += 1
        for g in s["error_groups"]:
            key = (g["tool"], g["key"])
            e = error_counter.setdefault(key, {"count": 0, "example": g["example"]})
            e["count"] += g["count"]
        for r in s["retry_loops"]:
            retry_loops.append({**r, "session": s["id"]})
        all_msgs.extend(s.pop("_msgs"))

    corrections.sort(key=lambda c: c.get("ts") or "", reverse=True)
    admissions.sort(key=lambda a: a.get("ts") or "", reverse=True)
    rule_requests.sort(key=lambda r: r.get("ts") or "", reverse=True)
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
    repeated = cluster_repeats(all_msgs)
    session_rows = sorted(sessions, key=lambda s: s["friction"], reverse=True)
    # abandoned sessions are the most expensive signal: never let the
    # top-100 cap hide them from the report
    listed = session_rows[:100]
    listed_ids = {s["id"] for s in listed}
    listed += [s for s in session_rows[100:] if s["abandoned"]
               and s["id"] not in listed_ids][:20]

    return {
        "schema_version": SCHEMA_VERSION,
        "project": project_label,
        "window_days": days,
        "sessions_scanned": len(sessions),
        "totals": {
            "user_msgs": sum(s["user_msgs"] for s in sessions),
            "tool_calls": sum(s["tool_calls"] for s in sessions),
            "corrections": sum(len(s["corrections"]) for s in sessions),
            "admissions": sum(len(s["admissions"]) for s in sessions),
            "rule_requests": sum(len(s["rule_requests"]) for s in sessions),
            "interrupts": sum(s["interrupts"] for s in sessions),
            "nudges": sum(s["nudges"] for s in sessions),
            "denials": sum(len(s["denials"]) for s in sessions),
            "errors": sum(s["errors"] for s in sessions),
            "retry_loops": len(retry_loops),
            "repeated_instruction_clusters": len(repeated),
            "abandoned_after_failure": sum(1 for s in sessions if s["abandoned"]),
        },
        "top_correction_terms": [
            {"term": w, "count": c} for w, c in term_counter.most_common(12)
        ],
        "corrections": corrections[:80],
        "admissions": admissions[:40],
        "rule_requests": rule_requests[:20],
        "repeated_instructions": repeated,
        "denials_top": denials_top[:25],
        "error_loops": [e for e in error_loops if e["count"] >= 2][:25],
        "retry_loops": retry_loops[:25],
        "sessions": [
            {
                "id": s["id"],
                "title": s["title"],
                "start": s["start"].isoformat() if s["start"] else None,
                "cwd": s["cwd"],
                "first_prompt": s["first_prompt"],
                "user_msgs": s["user_msgs"],
                "tool_calls": s["tool_calls"],
                "corrections": len(s["corrections"]),
                "admissions": len(s["admissions"]),
                "nudges": s["nudges"],
                "denials": len(s["denials"]),
                "errors": s["errors"],
                "interrupts": s["interrupts"],
                "abandoned": s["abandoned"],
                "friction": s["friction"],
            }
            for s in listed
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
    print(dim("  " + "─" * 58))
    rows = [
        ("corrections", t["corrections"], "you told the agent it was wrong", red),
        ("admissions", t["admissions"], "the agent said \"you're right\"", red),
        ("interrupts", t["interrupts"], "you hit Esc mid-action", red),
        ("nudges", t["nudges"], "you typed \"continue\" to unstick it", yellow),
        ("rule requests", t["rule_requests"], "rules you dictated out loud", cyan),
        ("repeated asks", t["repeated_instruction_clusters"],
         "same instruction across sessions", cyan),
        ("denials", t["denials"], "permission prompts you rejected", yellow),
        ("errors", t["errors"], "failed tool calls", yellow),
        ("retry loops", t["retry_loops"], "same call failed 3+ times", yellow),
        ("abandoned", t["abandoned_after_failure"], "sessions that ended on a failure", red),
    ]
    for label, value, note, tint in rows:
        v = tint(f"{value:>5}") if value else dim(f"{value:>5}")
        print(f"  {label:<14}{v}   {dim(note)}")
    print(dim("  " + "─" * 58))

    if report["repeated_instructions"]:
        print(bold("  instructions you keep repeating (ready-made CLAUDE.md rules)"))
        for r in report["repeated_instructions"][:5]:
            print(f"  {cyan(str(r['sessions']) + ' sessions')}  "
                  f"{excerpt(r['examples'][0]['text'], 80)}")
        print()

    if report["rule_requests"]:
        print(bold("  rules you dictated out loud"))
        for r in report["rule_requests"][:4]:
            print(f"  {dim('•')} {excerpt(r['text'], 88)}")
        print()

    if report["admissions"]:
        print(bold("  the agent admitted it was wrong"))
        for a in report["admissions"][:4]:
            print(f"  {red('✗')} {excerpt(a['user_text'], 70)}")
            print(f"    {dim('→ ' + excerpt(a['admission'], 70))}")
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
                label = s["title"] or s["first_prompt"] or ""
                print(f"  {dim(s['id'][:8])}  friction {s['friction']:>3}  "
                      f"{excerpt(label, 58)}{flag}")
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
    ap.add_argument("--patterns", metavar="FILE",
                    help="JSON lang pack merged into built-in detectors")
    ap.add_argument("--version", action="version", version=f"retro {VERSION}")
    args = ap.parse_args()

    if args.patterns:
        try:
            load_patterns(args.patterns)
        except (OSError, ValueError, re.error) as e:
            sys.exit(f"retro: bad --patterns file: {e}")

    claude_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    projects_root = claude_dir / "projects"
    if not projects_root.is_dir():
        sys.exit(f"retro: no transcripts found at {projects_root}")

    if args.all:
        dirs = [
            d for d in projects_root.iterdir()
            if d.is_dir() and not is_synthetic_dir(d)
        ]
        label = "all projects"
    else:
        # walk up from the given path: the user may be in a subdirectory of
        # the project Claude Code was launched from. Try both the path as
        # given and fully resolved (symlinks: /tmp vs /private/tmp), and
        # never match the root "-" project.
        given = Path(args.project).absolute()
        candidates = [given, *given.parents]
        resolved = given.resolve()
        if resolved != given:
            candidates += [resolved, *resolved.parents]
        d = next(
            (projects_root / munge_path(p) for p in candidates
             if munge_path(p) != "-" and (projects_root / munge_path(p)).is_dir()),
            None,
        )
        if d is None:
            sys.exit(
                f"retro: no transcripts for {args.project} or any parent directory\n"
                f"       (looked in {projects_root})\n"
                f"       try --all to scan every project"
            )
        # sibling dirs of the same repo: worktrees and subdirectory launches
        # (e.g. <proj>--claude-worktrees-x, <proj>-packages-y)
        dirs = [d] + [
            x for x in projects_root.iterdir()
            if x.is_dir() and x.name != d.name and x.name.startswith(d.name + "-")
        ]
        label = Path(args.project).name  # placeholder; refined from cwd below

    files = session_files(dirs, args.days, args.limit)
    sessions = [s for f in files if (s := parse_session(f, args.max_excerpt))]
    sessions = [s for s in sessions if s["user_msgs"] > 0 or s["tool_calls"] > 0]

    if not args.all:
        # the munged dir name can't be reliably un-munged (hyphens are
        # ambiguous), so take the real basename from a session's recorded cwd
        cwd = next((s["cwd"] for s in sessions if s.get("cwd")), None)
        if cwd:
            label = Path(cwd).name or label

    report = aggregate(sessions, args.days, label)
    report["truncated"] = len(files) >= args.limit

    if args.format == "json":
        json.dump(report, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        print_pretty(report, color=sys.stdout.isatty() and not args.no_color)


if __name__ == "__main__":
    main()
