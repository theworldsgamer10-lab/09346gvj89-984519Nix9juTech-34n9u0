#!/usr/bin/env python3
"""Small CI glue for the workflow. Keeps YAML free of inline Python.

Subcommands
-----------
  override-topic TEXT   replace the picked topic with a manual one
  emit-topic            write topic fields to $GITHUB_OUTPUT (safe, quoted)
  meta FIELD            print one field from out/metadata.json
  desc-file PATH        write the description to a file (avoids process
                        substitution, which `sh` does not support)
  plan                  print a dry-run summary of what would happen
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TOPIC = Path("out/topic.json")
META = Path("out/metadata.json")


def load(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"::error::{path} missing - did an earlier step fail?")
    return json.loads(path.read_text(encoding="utf-8"))


def gh_output(pairs: dict[str, str]) -> None:
    """Write key=value to $GITHUB_OUTPUT using the documented delimiter form."""
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        # Local run: just print.
        for k, v in pairs.items():
            print(f"{k}={v}")
        return
    with open(target, "a", encoding="utf-8") as fh:
        for key, value in pairs.items():
            if "\n" in value:
                import uuid

                marker = f"EOF_{uuid.uuid4().hex}"
                fh.write(f"{key}<<{marker}\n{value}\n{marker}\n")
            else:
                fh.write(f"{key}={value}\n")


def cmd_override_topic(text: str) -> int:
    data = load(TOPIC)
    data["subject"] = text
    data["topic"] = text
    data["overridden"] = True
    TOPIC.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"::notice::topic overridden -> {text}")
    return 0


def cmd_emit_topic() -> int:
    data = load(TOPIC)
    gh_output({
        "subject": data["subject"],
        "domain": data.get("domain", "Education"),
        "topic": data.get("topic", data["subject"]),
    })
    print(f"::notice::[{data.get('domain')}] {data['subject']}")
    return 0


def cmd_meta(field: str) -> int:
    data = load(META)
    if field not in data:
        raise SystemExit(f"::error::no '{field}' in {META}")
    value = data[field]
    sys.stdout.write(value if isinstance(value, str) else json.dumps(value))
    return 0


def cmd_desc_file(path: str) -> int:
    data = load(META)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(data["description"], encoding="utf-8")
    print(f"wrote {out} ({len(data['description'])} chars)")
    return 0


def cmd_plan() -> int:
    topic = load(TOPIC)
    print("=" * 60)
    print("DRY RUN - nothing will be rendered or uploaded")
    print("=" * 60)
    print(f"domain       : {topic.get('domain')}")
    print(f"subject      : {topic.get('subject')}")
    print(f"aspect       : 9:16  (Shorts)")
    print(f"llm provider : {os.environ.get('LLM_PROVIDER', 'groq')}")
    print(f"video source : {os.environ.get('VIDEO_SOURCE', 'pexels')}")
    print(f"voice        : {os.environ.get('VOICE_NAME', 'en-US-AndrewNeural')}")
    print(f"config       : {os.environ.get('MPT_HOME', '~/.mpt')}/config.toml")
    print(f"autopublish  : {os.environ.get('AUTOPUBLISH', 'false')}")
    print(f"system prompt: {topic.get('system_prompt', '')[:160]}...")
    print("=" * 60)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        print(__doc__)
        return 1
    cmd, rest = args[0], args[1:]
    handlers = {
        "override-topic": (cmd_override_topic, 1),
        "emit-topic": (cmd_emit_topic, 0),
        "meta": (cmd_meta, 1),
        "desc-file": (cmd_desc_file, 1),
        "plan": (cmd_plan, 0),
    }
    if cmd not in handlers:
        print(f"unknown subcommand: {cmd}", file=sys.stderr)
        return 1
    fn, need = handlers[cmd]
    if need and len(rest) < need:
        print(f"{cmd} needs {need} argument(s)", file=sys.stderr)
        return 1
    return fn(*rest[:need]) if need else fn()


if __name__ == "__main__":
    sys.exit(main())
