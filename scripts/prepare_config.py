#!/usr/bin/env python3
"""Build a working config.toml for MoneyPrinterTurbo from environment variables.

Why a script instead of a hand-written TOML
-------------------------------------------
Upstream's config has ~845 lines and changes between releases. Hand-writing a
minimal one means the day upstream adds a required key, the render breaks with
an unhelpful error. So we vendor the official template and patch only the keys
we care about. Unknown keys are preserved untouched.

Environment
-----------
Required:
  LLM_PROVIDER    groq | gemini | openrouter | deepseek | moonshot | pollinations
  LLM_API_KEY     key for that provider

Optional:
  VIDEO_SOURCE        pexels | pixabay | coverr          (default: pexels)
  PEXELS_API_KEY, PIXABAY_API_KEY, COVERR_API_KEY
  MPT_HOME            where config.toml is written       (default: ~/.mpt)
  SUBTITLE_PROVIDER   edge | whisper                     (default: edge)

Exit codes: 0 ok, 2 missing/invalid input.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import tomlkit
except ImportError:  # pragma: no cover
    raise SystemExit("missing dependency: pip install tomlkit")

# provider -> (config.toml key for the api key, default model name)
PROVIDERS = {
    "groq": ("groq_api_key", "llama-3.3-70b-versatile"),
    "gemini": ("gemini_api_key", "gemini-2.0-flash"),
    "openrouter": ("openrouter_api_key", "meta-llama/llama-3.3-70b-instruct"),
    "deepseek": ("deepseek_api_key", "deepseek-chat"),
    "moonshot": ("moonshot_api_key", "moonshot-v1-8k"),
    "pollinations": ("pollinations_api_key", "openai"),
}

SOURCE_KEYS = {
    "pexels": "pexels_api_keys",
    "pixabay": "pixabay_api_keys",
    "coverr": "coverr_api_keys",
}

ROOT = Path(__file__).resolve().parent.parent


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def fail(msg: str) -> None:
    print(f"::error::{msg}", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    template = Path(env("TEMPLATE", str(ROOT / "config" / "mpt-config.template.toml")))
    if not template.exists():
        fail(f"template not found: {template}")

    provider = env("LLM_PROVIDER", "groq").lower()
    if provider not in PROVIDERS:
        fail(f"unknown LLM_PROVIDER '{provider}'. Choose from: {', '.join(PROVIDERS)}")

    key_env, model = PROVIDERS[provider]
    api_key = env("LLM_API_KEY")
    if not api_key:
        fail("LLM_API_KEY is empty - add it in repo Settings -> Secrets -> Actions")

    source = env("VIDEO_SOURCE", "pexels").lower()
    if source not in SOURCE_KEYS:
        fail(f"unknown VIDEO_SOURCE '{source}'. Choose from: {', '.join(SOURCE_KEYS)}")

    source_key = SOURCE_KEYS[source]
    stock_key = env(f"{source.upper()}_API_KEY")
    if not stock_key:
        fail(f"{source.upper()}_API_KEY is empty - the render needs stock footage keys")

    doc = tomlkit.parse(template.read_text(encoding="utf-8"))
    app = doc["app"]

    # --- language model -----------------------------------------------------
    app["llm_provider"] = provider
    app[key_env] = api_key
    if not str(app.get(f"{provider}_model_name", "") or "").strip():
        app[f"{provider}_model_name"] = model

    # --- footage ------------------------------------------------------------
    app["video_source"] = source
    app[source_key] = [stock_key]

    # --- subtitles ----------------------------------------------------------
    subtitle_provider = env("SUBTITLE_PROVIDER", "edge").lower()
    if subtitle_provider not in {"edge", "whisper"}:
        fail("SUBTITLE_PROVIDER must be 'edge' or 'whisper'")
    app["subtitle_provider"] = subtitle_provider

    # --- housekeeping -------------------------------------------------------
    app["hide_config"] = True
    app["material_concurrency"] = int(env("MATERIAL_CONCURRENCY", "2") or 2)

    # Publishing is deliberately NOT configured here. The CLI has no publish
    # code path (verified against cli.py); uploading is done by
    # scripts/youtube_upload.py so the two concerns stay separate.

    home = Path(env("MPT_HOME", str(Path.home() / ".mpt"))).expanduser()
    home.mkdir(parents=True, exist_ok=True)
    out = home / "config.toml"
    out.write_text(tomlkit.dumps(doc), encoding="utf-8")

    # Never echo the key itself.
    print(f"wrote {out}")
    print(f"  llm_provider  = {provider} ({model})")
    print(f"  video_source  = {source}")
    print(f"  subtitle      = {subtitle_provider}")
    print(f"  llm key       = set ({len(api_key)} chars)")
    print(f"  stock key     = set ({len(stock_key)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
