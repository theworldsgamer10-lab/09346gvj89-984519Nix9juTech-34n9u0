#!/usr/bin/env python3
"""Generate YouTube metadata (title, description, tags) for a topic.

Runs a second, small LLM call - separate from the one that writes the video
script - because search metadata and spoken narration are different jobs with
different constraints (keyword density vs. natural speech).

Falls back to a deterministic template when the API is unavailable, so a
metadata outage never blocks a publish.

Output: out/metadata.json  {title, description, tags, tags_csv, made_for_kids}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DISCLOSURE = (
    "Narration and visuals in this video were produced with AI assistance "
    "and reviewed before publishing."
)

TITLE_RULES = (
    "Write a YouTube title. Rules: max 70 characters, front-load the search "
    "phrase, no clickbait, no ALL CAPS, no emojis, no quotation marks, no "
    "trailing period. It must read as a real question or a real claim."
)

DESC_RULES = (
    "Write a YouTube description of 90-140 words. First sentence must restate "
    "the video's answer in plain language (this is the part that shows in "
    "search). Then 3-5 short lines of what the viewer learns. Then one line "
    "inviting a subscribe. No hashtags, no links, no emojis, no markdown. "
    "End with a single line of 8 comma-separated topic keywords."
)


def call_llm(prompt: str, provider: str, key: str, model: str, timeout: int = 30) -> str:
    """Minimal OpenAI-compatible chat call. Returns '' on any failure."""
    endpoints = {
        "groq": "https://api.groq.com/openai/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        "deepseek": "https://api.deepseek.com/chat/completions",
    }
    url = endpoints.get(provider)
    if not url:
        return ""  # gemini/pollinations use different shapes; template covers it

    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You write YouTube metadata. Reply with the "
                                          "requested text only, no preamble, no labels."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 500,
    }).encode()

    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError,
            TimeoutError) as exc:
        print(f"::warning::metadata llm unavailable ({type(exc).__name__}); using template")
        return ""


def clean_title(raw: str, topic: str) -> str:
    t = raw.strip().splitlines()[0] if raw.strip() else ""
    t = re.sub(r'["\u201c\u201d*#]', "", t).strip().rstrip(".")
    if not (15 <= len(t) <= 100):
        t = topic[:95]
    return t[:100]


def template_title(topic: str) -> str:
    t = topic.strip()
    return t if len(t) <= 95 else t[:92].rstrip() + "..."


def build_description(topic: str, domain: str, body: str) -> str:
    if body:
        desc = re.sub(r"\n{3,}", "\n\n", body.strip())
    else:
        desc = (
            f"{topic} - explained clearly, in under a minute.\n\n"
            f"What this video covers:\n"
            f"- the mechanism behind it, in plain language\n"
            f"- one everyday analogy to hold onto\n"
            f"- one detail most explanations leave out\n\n"
            f"Part of a series covering {domain.lower()} and the rest of the "
            f"school curriculum you actually remember.\n\n"
            f"Subscribe for one clear explanation at a time."
        )
    return f"{desc}\n\n{DISCLOSURE}"


def build_tags(meta: dict, topic: str, domain: str) -> list[str]:
    raw = meta.get("keywords", "") or ""
    tags = [re.sub(r"[^\w\s-]", "", t).strip().lower()
            for t in re.split(r"[,\n]", raw) if t.strip()]
    base = [topic.lower(), domain.lower(), "explained", "education",
            "how it works", "science explained", "learn something"]
    out: list[str] = []
    for t in tags + base:
        if t and t not in out and len(t) <= 60:
            out.append(t)
    return out[:25]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True)
    ap.add_argument("--domain", default="Education")
    ap.add_argument("--out", default="out/metadata.json")
    args = ap.parse_args(argv)

    provider = os.environ.get("LLM_PROVIDER", "groq").lower()
    key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")

    meta: dict = {}
    if key:
        prompt = (
            f"Video topic: {args.topic}\nSubject: {args.domain}\n\n"
            f"TASK 1\n{TITLE_RULES}\n\nTASK 2\n{DESC_RULES}\n\n"
            "Reply in exactly this format:\nTITLE: <title>\nDESCRIPTION: <description>\n"
            "KEYWORDS: <8 comma separated keywords>"
        )
        raw = call_llm(prompt, provider, key, model)
        if raw:
            tm = re.search(r"TITLE:\s*(.+)", raw)
            dm = re.search(r"DESCRIPTION:\s*(.+?)(?:\nKEYWORDS:|$)", raw, re.S)
            km = re.search(r"KEYWORDS:\s*(.+)", raw)
            meta = {
                "title_raw": tm.group(1) if tm else "",
                "description_raw": dm.group(1) if dm else "",
                "keywords": km.group(1) if km else "",
            }

    title = clean_title(meta.get("title_raw", ""), args.topic) or template_title(args.topic)
    description = build_description(args.topic, args.domain, meta.get("description_raw", ""))
    tags = build_tags(meta, args.topic, args.domain)

    payload = {
        "title": title,
        "description": description,
        "tags": tags,
        "tags_csv": ",".join(tags),
        "made_for_kids": False,
        "topic": args.topic,
        "domain": args.domain,
        "ai_generated_metadata": bool(meta),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"title ({len(title)} chars): {title}")
    print(f"description: {len(description)} chars, {len(description.splitlines())} lines")
    print(f"tags ({len(tags)}): {payload['tags_csv'][:160]}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
