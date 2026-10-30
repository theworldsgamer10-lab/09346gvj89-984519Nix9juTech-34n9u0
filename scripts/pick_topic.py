#!/usr/bin/env python3
"""Pick the next topic for the channel.

Strategy
--------
1. Round-robin across domains: always pick the domain with the fewest
   videos already made, tie-broken by curriculum order. This means the
   channel alternates Physics -> Chemistry -> Biology ... instead of
   publishing eight physics videos in a row.
2. Inside that domain, pick the topic used least often (curriculum order
   breaks ties), so each subject marches beginner -> advanced.
3. If a topic comes around again, attach a fresh angle so the video is
   not a duplicate upload.

Output
------
Writes a single-line-JSON file (default: out/topic.json) consumed by the
workflow, and appends the choice to the state file. JSON is written as one
line on purpose: the workflow reads fields back with python -c and passes
them as quoted shell args, so multi-line values would break it.

Usage
-----
    python scripts/pick_topic.py --dry-run     # preview, change nothing
    python scripts/pick_topic.py               # commit the pick to state
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Appended to a topic when it has already been used once or more.
ANGLES = [
    "explained in 60 seconds",
    "with one everyday analogy",
    "the version school never taught you",
    "and the common myth about it",
    "told as a single cause and effect",
]

BASE_PROMPT = (
    "Write narration for a 45-60 second educational short. Open with a concrete hook, "
    "explain the mechanism in plain language, give exactly one analogy, add one "
    "surprising concrete detail, and close with one sentence that leaves the viewer "
    "genuinely smarter. No hype words, no emojis, no markdown. Second person, present "
    "tense, 110-130 words. Never state something you are not confident is true; if a "
    "number is uncertain, leave it out. "
)


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON: {exc}") from exc


def pick(curriculum: dict, state: dict) -> dict:
    """Return {'domain', 'topic', 'persona', 'angle', 'subject'}."""
    domains = curriculum["domains"]
    used = state.get("used", [])

    domain_count: dict[str, int] = {}
    topic_count: dict[str, int] = {}
    for entry in used:
        d = entry.get("domain", "")
        t = entry.get("topic", "")
        domain_count[d] = domain_count.get(d, 0) + 1
        topic_count[t] = topic_count.get(t, 0) + 1

    # 1. least-used domain, ties broken by curriculum order (min() is stable)
    dom = min(domains, key=lambda x: domain_count.get(x["domain"], 0))
    name = dom["domain"]

    # 2. least-used topic inside that domain
    topic = min(dom["topics"], key=lambda t: topic_count.get(t, 0))
    reuse = topic_count.get(topic, 0)

    # 3. fresh angle on reuse
    angle = ANGLES[(reuse - 1) % len(ANGLES)] if reuse > 0 else ""

    return {
        "domain": name,
        "topic": topic,
        "persona": dom["persona"],
        "angle": angle,
        "subject": f"{topic} - {angle}" if angle else topic,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--curriculum", default=str(ROOT / "topics" / "curriculum.json"))
    ap.add_argument("--state", default=str(ROOT / "state" / "used.json"))
    ap.add_argument("--out", default=str(ROOT / "out" / "topic.json"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", action="store_true", help="print the chosen topic")
    args = ap.parse_args(argv)

    curriculum = load_json(Path(args.curriculum), {})
    if not curriculum.get("domains"):
        raise SystemExit(f"no domains found in {args.curriculum}")

    state = load_json(Path(args.state), {"used": []})
    choice = pick(curriculum, state)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "domain": choice["domain"],
        "topic": choice["topic"],
        "subject": choice["subject"],
        "system_prompt": (choice["persona"] + " " + BASE_PROMPT).replace("\n", " ").strip(),
        "picked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": bool(args.dry_run),
    }
    # one line, UTF-8, no trailing newline surprises
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    if args.dry_run:
        print(f"[dry-run] {payload['domain']}: {payload['subject']}")
        print(f"[dry-run] would write {out}; state untouched")
        return 0

    state.setdefault("used", []).append(
        {
            "topic": choice["topic"],
            "domain": choice["domain"],
            "at": payload["picked_at"],
        }
    )
    state["used"] = state["used"][-3000:]
    sp = Path(args.state)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")

    if args.show:
        print(f"[{payload['domain']}] {payload['subject']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
