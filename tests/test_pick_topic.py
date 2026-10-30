"""Tests for the topic picker.

Run: python -m pytest tests/ -q      (or: python tests/test_pick_topic.py)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pick_topic  # noqa: E402

CURRICULUM = {
    "domains": [
        {"domain": "A", "persona": "You are A.", "topics": ["a1", "a2"]},
        {"domain": "B", "persona": "You are B.", "topics": ["b1", "b2"]},
        {"domain": "C", "persona": "You are C.", "topics": ["c1", "c2"]},
    ]
}


def walk(n: int) -> list[dict]:
    state: dict = {"used": []}
    seq = []
    for _ in range(n):
        c = pick_topic.pick(CURRICULUM, state)
        seq.append(c)
        state["used"].append(
            {"topic": c["topic"], "domain": c["domain"], "at": "2026-01-01T00:00:00Z"}
        )
    return seq


def test_rotates_domains_not_topics():
    seq = walk(3)
    assert [c["domain"] for c in seq] == ["A", "B", "C"], "should rotate A,B,C once each"


def test_no_repeat_before_curriculum_exhausted():
    seq = walk(6)
    topics = [c["topic"] for c in seq]
    assert len(set(topics)) == 6, f"repeated too early: {topics}"


def test_angle_added_only_on_reuse():
    seq = walk(7)
    assert seq[0]["angle"] == "", "first pass should have no angle"
    assert seq[6]["angle"] != "", "7th video must reuse a topic and get an angle"
    assert seq[6]["subject"].endswith(seq[6]["angle"])


def test_angle_keeps_subject_distinct():
    seq = walk(12)
    subjects = [c["subject"] for c in seq]
    assert len(set(subjects)) == len(subjects), f"duplicate video subject: {subjects}"


def test_balanced_across_domains():
    seq = walk(30)
    counts: dict[str, int] = {}
    for c in seq:
        counts[c["domain"]] = counts.get(c["domain"], 0) + 1
    assert max(counts.values()) - min(counts.values()) <= 1, counts


def test_cli_dry_run_does_not_touch_state(tmp_path):
    cur = tmp_path / "c.json"
    cur.write_text(json.dumps(CURRICULUM))
    state = tmp_path / "used.json"
    out = tmp_path / "topic.json"

    rc = pick_topic.main(
        ["--curriculum", str(cur), "--state", str(state), "--out", str(out), "--dry-run"]
    )
    assert rc == 0
    assert out.exists(), "topic.json should still be written in dry-run"
    assert not state.exists(), "dry-run must not create state"

    payload = json.loads(out.read_text())
    assert payload["dry_run"] is True
    assert payload["domain"] == "A"
    assert payload["system_prompt"].startswith("You are A.")
    assert "\n" not in json.dumps(payload) or True  # single-line file check below
    assert out.read_text().count("\n") == 0, "must be one line for shell safety"


def test_cli_writes_state_when_not_dry(tmp_path):
    cur = tmp_path / "c.json"
    cur.write_text(json.dumps(CURRICULUM))
    state = tmp_path / "used.json"
    out = tmp_path / "topic.json"

    pick_topic.main(["--curriculum", str(cur), "--state", str(state), "--out", str(out)])
    data = json.loads(state.read_text())
    assert len(data["used"]) == 1
    assert data["used"][0]["domain"] == "A"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            if t.__code__.co_argcount:  # needs tmp_path -> skip in bare runner
                print(f"SKIP {t.__name__} (needs pytest)")
                continue
            t()
            print(f"ok   {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    sys.exit(1 if failed else 0)
